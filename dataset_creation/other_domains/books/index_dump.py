"""Build a SQLite index from an Open Library dump.

Usage:
  python -m books.index_dump
  python -m books.index_dump --dump data/openlibrary/ol_dump_2026-08-31.txt.gz
"""

from __future__ import annotations

import argparse
import gzip
import json
from collections.abc import Iterator
from pathlib import Path

from loguru import logger
from tqdm import tqdm

from books.openlibrary import _flatten_edition, normalize_isbn
from shared.io import project_root
from shared.sqlite_index import connect_sqlite

TYPE_AUTHOR = "/type/author"
TYPE_EDITION = "/type/edition"
BATCH_SIZE = 20_000


def iter_dump_records(
    path: Path, *, type_iri: str | None = None
) -> Iterator[tuple[str, str, dict]]:
    prefix = f"{type_iri}\t" if type_iri else None
    with gzip.open(path, "rt", encoding="utf-8", errors="replace") as f:
        for line in f:
            if prefix and not line.startswith(prefix):
                continue
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 5:
                continue
            try:
                rec = json.loads(parts[4])
            except json.JSONDecodeError:
                continue
            if isinstance(rec, dict):
                yield parts[0], parts[1], rec


def _edition_isbns(edition: dict) -> list[str]:
    raw: list[str] = []
    for key in ("isbn_13", "isbn_10", "isbn"):
        val = edition.get(key)
        if isinstance(val, list):
            raw.extend(str(x) for x in val if x)
        elif val:
            raw.append(str(val))
    out: list[str] = []
    seen: set[str] = set()
    for item in raw:
        norm = normalize_isbn(item)
        if norm and norm not in seen:
            seen.add(norm)
            out.append(norm)
    return out


def _resolve_authors(edition: dict, names: dict[str, str]) -> dict:
    authors = []
    for a in edition.get("authors") or []:
        if not isinstance(a, dict):
            continue
        if a.get("name"):
            authors.append({"name": a["name"]})
            continue
        key = a.get("key")
        if key and key in names:
            authors.append({"name": names[key]})
        elif key:
            authors.append({"key": key})
    edition = dict(edition)
    edition["authors"] = authors
    return edition


def _work_key(edition: dict) -> str | None:
    works = edition.get("works") or []
    if works and isinstance(works[0], dict):
        key = works[0].get("key")
        return str(key) if key else None
    return None


def _publishers(edition: dict) -> list[str] | None:
    publishers = edition.get("publishers") or []
    if isinstance(publishers, str):
        publishers = [publishers]
    names = [str(p) for p in publishers if p]
    return names or None


def _pages(edition: dict) -> int | None:
    val = edition.get("number_of_pages")
    if isinstance(val, int):
        return val
    if isinstance(val, str) and val.isdigit():
        return int(val)
    return None


def _dumps_list(values: list | None) -> str | None:
    if not values:
        return None
    return json.dumps(values, ensure_ascii=False)


def build_index(dump_path: Path, sqlite_path: Path) -> None:
    con = connect_sqlite(sqlite_path, replace=True)
    con.execute("CREATE TABLE authors (key TEXT PRIMARY KEY, name TEXT NOT NULL)")
    con.execute(
        "CREATE TABLE editions ("
        "key TEXT PRIMARY KEY, work_key TEXT, title TEXT NOT NULL, "
        "authors TEXT, publish_date TEXT, publishers TEXT, "
        "number_of_pages INTEGER, languages TEXT)"
    )
    con.execute("CREATE TABLE isbn (isbn TEXT PRIMARY KEY, edition_key TEXT NOT NULL)")

    logger.info("Pass 1/2: authors from {}", dump_path)
    names: dict[str, str] = {}
    batch: list[tuple[str, str]] = []
    for type_iri, key, rec in tqdm(
        iter_dump_records(dump_path, type_iri=TYPE_AUTHOR), desc="authors", unit="rec"
    ):
        name = rec.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        name = name.strip()
        names[key] = name
        batch.append((key, name))
        if len(batch) >= BATCH_SIZE:
            con.executemany("INSERT OR IGNORE INTO authors VALUES (?, ?)", batch)
            batch.clear()
    if batch:
        con.executemany("INSERT OR IGNORE INTO authors VALUES (?, ?)", batch)
        batch.clear()
    n_authors = con.execute("SELECT COUNT(*) FROM authors").fetchone()[0]
    logger.info("Indexed {:,} authors", n_authors)

    logger.info("Pass 2/2: editions + ISBNs")
    edition_batch: list[tuple] = []
    isbn_batch: list[tuple[str, str]] = []
    skipped = 0
    for type_iri, key, rec in tqdm(
        iter_dump_records(dump_path, type_iri=TYPE_EDITION), desc="editions", unit="rec"
    ):
        if not rec.get("title"):
            skipped += 1
            continue
        resolved = _resolve_authors(rec, names)
        flat = _flatten_edition(resolved, match="isbn")
        authors = list(flat.get("authors") or [])
        title = flat["title"]
        edition_batch.append(
            (
                key,
                _work_key(resolved),
                title,
                _dumps_list(authors or None),
                flat.get("publish_date"),
                _dumps_list(_publishers(resolved)),
                _pages(resolved),
                json.dumps(flat.get("languages"), ensure_ascii=False)
                if flat.get("languages") is not None
                else None,
            )
        )
        for isbn in _edition_isbns(resolved):
            isbn_batch.append((isbn, key))
        if len(edition_batch) >= BATCH_SIZE:
            con.executemany(
                "INSERT OR IGNORE INTO editions VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                edition_batch,
            )
            edition_batch.clear()
        if len(isbn_batch) >= BATCH_SIZE:
            con.executemany("INSERT OR IGNORE INTO isbn VALUES (?, ?)", isbn_batch)
            isbn_batch.clear()
    if edition_batch:
        con.executemany(
            "INSERT OR IGNORE INTO editions VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            edition_batch,
        )
    if isbn_batch:
        con.executemany("INSERT OR IGNORE INTO isbn VALUES (?, ?)", isbn_batch)

    n_editions = con.execute("SELECT COUNT(*) FROM editions").fetchone()[0]
    n_isbn = con.execute("SELECT COUNT(*) FROM isbn").fetchone()[0]
    logger.info(
        "Indexed {:,} editions, {:,} ISBNs ({} editions skipped)",
        n_editions,
        n_isbn,
        skipped,
    )
    con.execute("CREATE INDEX isbn_edition_key ON isbn(edition_key)")
    con.commit()
    con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    con.close()
    logger.info("Wrote {}", sqlite_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Index an Open Library dump into SQLite.")
    parser.add_argument("--dump", type=Path, default=None, help="Combined ol_dump_*.txt.gz")
    parser.add_argument("--sqlite", type=Path, default=None)
    parser.add_argument("--dump-date", default="2026-08-31")
    args = parser.parse_args()
    root = project_root() / "data" / "openlibrary"
    dump = args.dump or (root / f"ol_dump_{args.dump_date}.txt.gz")
    sqlite_path = args.sqlite or (root / "openlibrary.sqlite")
    if not dump.exists():
        raise SystemExit(f"Missing dump {dump}. Run `python -m books.download_dump` first.")
    build_index(dump, sqlite_path)


if __name__ == "__main__":
    main()
