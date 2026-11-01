"""Build a SQLite index from IMDb TSV dumps.

Usage:
  python -m movies.index_imdb
"""

from __future__ import annotations

import argparse
import csv
import gzip
from collections.abc import Iterator
from pathlib import Path

from shared.io import project_root
from shared.sqlite_index import connect_sqlite

REQUIRED_FILES = ("title.basics", "title.crew", "title.principals", "name.basics")
BATCH_SIZE = 50_000
NULL = r"\N"


def _cell(cols: list[str], idx: dict[str, int], name: str) -> str | None:
    i = idx[name]
    if i >= len(cols):
        return None
    v = cols[i]
    if not v or v == NULL:
        return None
    return v


def iter_tsv(path: Path) -> Iterator[tuple[dict[str, int], list[str]]]:
    with gzip.open(path, "rt", encoding="utf-8", newline="") as f:
        reader = csv.reader(f, delimiter="\t", quoting=csv.QUOTE_NONE)
        header = next(reader)
        idx = {name: i for i, name in enumerate(header)}
        for cols in reader:
            yield idx, cols


def _flush(con, sql: str, batch: list) -> None:
    if batch:
        con.executemany(sql, batch)
        batch.clear()


def _count(con, table: str) -> int:
    return con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def build_titles(con, path: Path) -> int:
    con.execute(
        "CREATE TABLE titles ("
        "tconst TEXT PRIMARY KEY, title_type TEXT, primary_title TEXT, "
        "original_title TEXT, start_year TEXT, end_year TEXT, "
        "runtime_minutes TEXT, genres TEXT)"
    )
    batch: list[tuple] = []
    sql = "INSERT OR IGNORE INTO titles VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
    for idx, cols in iter_tsv(path):
        tconst = _cell(cols, idx, "tconst")
        if not tconst:
            continue
        batch.append(
            (
                tconst,
                _cell(cols, idx, "titleType"),
                _cell(cols, idx, "primaryTitle"),
                _cell(cols, idx, "originalTitle"),
                _cell(cols, idx, "startYear"),
                _cell(cols, idx, "endYear"),
                _cell(cols, idx, "runtimeMinutes"),
                _cell(cols, idx, "genres"),
            )
        )
        if len(batch) >= BATCH_SIZE:
            _flush(con, sql, batch)
    _flush(con, sql, batch)
    return _count(con, "titles")


def build_crew(con, path: Path) -> int:
    con.execute("CREATE TABLE crew (tconst TEXT PRIMARY KEY, directors TEXT, writers TEXT)")
    batch: list[tuple] = []
    sql = "INSERT OR IGNORE INTO crew VALUES (?, ?, ?)"
    for idx, cols in iter_tsv(path):
        tconst = _cell(cols, idx, "tconst")
        if not tconst:
            continue
        batch.append((tconst, _cell(cols, idx, "directors"), _cell(cols, idx, "writers")))
        if len(batch) >= BATCH_SIZE:
            _flush(con, sql, batch)
    _flush(con, sql, batch)
    return _count(con, "crew")


def build_principals(con, path: Path) -> int:
    con.execute(
        "CREATE TABLE principals (tconst TEXT, ordering INTEGER, nconst TEXT, "
        "category TEXT, job TEXT, characters TEXT)"
    )
    batch: list[tuple] = []
    sql = "INSERT INTO principals VALUES (?, ?, ?, ?, ?, ?)"
    for idx, cols in iter_tsv(path):
        tconst = _cell(cols, idx, "tconst")
        raw_ord = _cell(cols, idx, "ordering")
        try:
            ordering = int(raw_ord) if raw_ord is not None else None
        except ValueError:
            ordering = None
        batch.append(
            (
                tconst,
                ordering,
                _cell(cols, idx, "nconst"),
                _cell(cols, idx, "category"),
                _cell(cols, idx, "job"),
                _cell(cols, idx, "characters"),
            )
        )
        if len(batch) >= BATCH_SIZE:
            _flush(con, sql, batch)
    _flush(con, sql, batch)
    con.execute("CREATE INDEX idx_principals_tconst ON principals(tconst, ordering)")
    return _count(con, "principals")


def build_names(con, path: Path) -> int:
    con.execute("CREATE TABLE names (nconst TEXT PRIMARY KEY, primary_name TEXT)")
    batch: list[tuple] = []
    sql = "INSERT OR IGNORE INTO names VALUES (?, ?)"
    for idx, cols in iter_tsv(path):
        nconst = _cell(cols, idx, "nconst")
        if not nconst:
            continue
        batch.append((nconst, _cell(cols, idx, "primaryName")))
        if len(batch) >= BATCH_SIZE:
            _flush(con, sql, batch)
    _flush(con, sql, batch)
    return _count(con, "names")


def build_index(imdb_dir: Path, sqlite_path: Path) -> None:
    con = connect_sqlite(sqlite_path, replace=True)
    counts = {
        "titles": build_titles(con, imdb_dir / "title.basics.tsv.gz"),
        "crew": build_crew(con, imdb_dir / "title.crew.tsv.gz"),
        "principals": build_principals(con, imdb_dir / "title.principals.tsv.gz"),
        "names": build_names(con, imdb_dir / "name.basics.tsv.gz"),
    }
    con.commit()
    con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    con.close()
    print(f"Indexed {counts} -> {sqlite_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a local SQLite index from IMDb TSV dumps.")
    parser.add_argument("--imdb-dir", type=Path, default=None)
    parser.add_argument("--sqlite", type=Path, default=None)
    args = parser.parse_args()
    root = project_root() / "data" / "imdb"
    imdb_dir = (args.imdb_dir or root).resolve()
    sqlite_path = (args.sqlite or (root / "imdb_index.sqlite")).resolve()

    missing = [name for name in REQUIRED_FILES if not (imdb_dir / f"{name}.tsv.gz").exists()]
    if missing:
        raise SystemExit(
            f"Missing {missing} under {imdb_dir}. Run `python -m movies.download_imdb` first."
        )
    build_index(imdb_dir, sqlite_path)


if __name__ == "__main__":
    main()
