import gzip
import json
from pathlib import Path

from books.index_dump import build_index
from books.openlibrary import OpenLibraryDumpValidator


def _write_dump(path: Path, rows: list[tuple[str, str, dict]]) -> None:
    with gzip.open(path, "wt", encoding="utf-8") as f:
        for type_iri, key, rec in rows:
            f.write(f"{type_iri}\t{key}\t1\t2026-01-01T00:00:00\t{json.dumps(rec)}\n")


def _fixture_dump(path: Path) -> None:
    _write_dump(
        path,
        [
            (
                "/type/author",
                "/authors/OL1A",
                {"key": "/authors/OL1A", "name": "J. R. R. Tolkien"},
            ),
            (
                "/type/work",
                "/works/OL1W",
                {"key": "/works/OL1W", "title": "The Hobbit"},
            ),
            (
                "/type/edition",
                "/books/OL1M",
                {
                    "key": "/books/OL1M",
                    "title": "The Hobbit",
                    "isbn_13": ["978-0-261-10221-7"],
                    "authors": [{"key": "/authors/OL1A"}],
                    "works": [{"key": "/works/OL1W"}],
                    "publishers": ["Allen & Unwin"],
                },
            ),
            (
                "/type/edition",
                "/books/OL2M",
                {
                    "key": "/books/OL2M",
                    "title": "Farmer Giles of Ham",
                    "authors": [{"key": "/authors/OL1A"}],
                    "works": [{"key": "/works/OL2W"}],
                },
            ),
        ],
    )


def test_dump_isbn_index_resolves_author(tmp_path: Path):
    dump = tmp_path / "ol_dump.txt.gz"
    sqlite_path = tmp_path / "ol.sqlite"
    _fixture_dump(dump)
    build_index(dump, sqlite_path)

    v = OpenLibraryDumpValidator(sqlite_path)
    out = v.record_query_validator(
        {"data": {"name": "Hobbit", "isbn": "9780261102217"}},
        isbn_only=True,
    )
    assert out is not None
    assert out["kb"]["title"] == "The Hobbit"
    assert out["kb"]["authors"] == ["J. R. R. Tolkien"]
    assert out["kb"]["match"] == "isbn"
    assert v.record_query_validator({"data": {"isbn": "0000000000"}}, isbn_only=True) is None


def test_isbn_hit_kept_when_title_disagrees(tmp_path: Path):
    dump = tmp_path / "ol_dump.txt.gz"
    sqlite_path = tmp_path / "ol.sqlite"
    _fixture_dump(dump)
    build_index(dump, sqlite_path)

    v = OpenLibraryDumpValidator(sqlite_path)
    mismatched = v.record_query_validator(
        {"data": {"name": "Some Other Novel", "isbn": "9780261102217"}}
    )
    assert mismatched is not None
    assert mismatched["kb"]["match"] == "isbn"
    ok = v.record_query_validator({"data": {"name": "Hobbit", "isbn": "9780261102217", "author": "Tolkien"}})
    assert ok is not None
    assert ok["kb"]["match"] == "isbn"


def test_record_without_isbn_is_dropped(tmp_path: Path):
    dump = tmp_path / "ol_dump.txt.gz"
    sqlite_path = tmp_path / "ol.sqlite"
    _fixture_dump(dump)
    build_index(dump, sqlite_path)

    v = OpenLibraryDumpValidator(sqlite_path)
    assert v.record_query_validator({"data": {"name": "Farmer Giles of Ham", "author": "Tolkien"}}) is None
    assert v.record_query_validator({"data": {"name": "Hobbit"}}) is None
