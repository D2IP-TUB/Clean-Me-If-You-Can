import json
from pathlib import Path

from books.pack import EXPERIMENT_COLUMNS, pack_books, unique_rows
from shared.pack_common import deduplicate_by_dirty, keep_complete_gt


def _rec(title, target, match="search", isbn=None):
    return {
        "kb": {
            "title": target,
            "authors": ["A"],
            "isbn": isbn or "9780000000000",
            "publish_date": "1937",
            "publishers": ["Allen & Unwin"],
            "number_of_pages": "310",
            "openlibrary_key": "/works/OL1W",
            "work_key": "/works/OL1W",
            "match": match,
        },
        "crawl": {
            "data": {"@type": "Book", "name": title, "isbn": isbn, "inLanguage": "en"},
            "crawl_metadata": {
                "url": "https://example.org/p",
                "provenance": {"graph_iri": "https://example.org/p", "subset": "Book"},
            },
        },
        "entity_query": {"title": title, "isbn": isbn, "author": None},
    }


def test_unique_rows_keeps_same_experiment_different_provenance():
    from books.pack import row_from_record

    a = row_from_record(_rec("The Hobbit", "The Hobbit"))
    b = row_from_record(_rec("The Hobbit", "The Hobbit"))
    b["provenance_graph_iri"] = "https://example.org/other"
    assert len(unique_rows([a, b])) == 2


def test_unique_rows_drops_exact_duplicates():
    from books.pack import row_from_record

    a = row_from_record(_rec("The Hobbit", "The Hobbit"))
    b = row_from_record(_rec("The Hobbit", "The Hobbit"))
    assert len(unique_rows([a, b])) == 1


def test_unique_rows_drops_case_only_duplicates():
    from books.pack import row_from_record

    a = row_from_record(_rec("The Hobbit", "The Hobbit"))
    b = row_from_record(_rec("the hobbit", "The Hobbit"))
    assert len(unique_rows([a, b])) == 1


def test_unique_rows_keeps_eszett_distinct_from_ss():
    from books.pack import row_from_record

    a = row_from_record(_rec("Straße", "Straße"))
    b = row_from_record(_rec("Strasse", "Strasse"))
    assert len(unique_rows([a, b])) == 2


def test_deduplicate_by_dirty_ignores_capitalization():
    dirty = [
        {"id": "1", "title": "The Hobbit", "author": "A", "isbn": "1",
         "date_published": "", "publisher": "", "number_of_pages": ""},
        {"id": "2", "title": "the hobbit", "author": "A", "isbn": "1",
         "date_published": "", "publisher": "", "number_of_pages": ""},
    ]
    clean = [{"id": "1", "title": "X"}, {"id": "2", "title": "Y"}]
    prov = [{"id": "1"}, {"id": "2"}]
    d, c, _p, removed = deduplicate_by_dirty(dirty, clean, prov, EXPERIMENT_COLUMNS)
    assert [r["id"] for r in d] == ["1"]
    assert removed == ["2"]


def test_pack_and_merge_roundtrip(tmp_path: Path):
    import gzip

    from books.merge import merge_books

    validated = tmp_path / "validated" / "Book"
    validated.mkdir(parents=True)
    records = [
        _rec("The Hobbit", "The Hobbit"),
        _rec("The Hobbit", "The Hobbit"),
        _rec("Other Book", "Completely Different"),
    ]
    with gzip.open(validated / "sample.json.gz", "wt", encoding="utf-8") as f:
        json.dump(records, f)
    pack_dir = tmp_path / "pack" / "Book"
    pack_books(validated, pack_dir)
    packed = (pack_dir / "values_experiment.csv").read_text()
    assert "The Hobbit" in packed
    assert "Other Book" in packed
    header = packed.splitlines()[0]
    assert "language" not in header
    assert "provenance_graph_iri" in header
    assert not (pack_dir / "excluded_low_sim").exists()

    pack_root = tmp_path / "pack"
    merge_books(pack_root, tmp_path / "merged")
    merged = (tmp_path / "merged" / "merged_values_experiment.csv").read_text()
    assert merged.count("The Hobbit") == 1
    assert "source_subset" not in merged.splitlines()[0]
    assert "provenance_graph_iri" not in merged.splitlines()[0]


def test_pack_writes_flat_layout_without_named_unnamed_split(tmp_path: Path):
    import gzip

    validated = tmp_path / "validated" / "Book"
    validated.mkdir(parents=True)
    with gzip.open(validated / "part_0.json.gz", "wt", encoding="utf-8") as f:
        json.dump([_rec("The Hobbit", "The Hobbit")], f)
    pack_dir = tmp_path / "pack" / "Book"
    pack_books(validated, pack_dir)
    assert (pack_dir / "values_experiment.csv").exists()
    assert not (pack_dir / "named").exists()
    assert not (pack_dir / "unnamed").exists()


def test_keep_complete_gt_drops_empty_clean_cell():
    rows = [
        {
            "title": "A",
            "target_title": "A",
            "target_author": "X",
            "target_isbn": "1",
            "target_date_published": "1937",
            "target_publisher": "P",
            "target_number_of_pages": "10",
        },
        {
            "title": "B",
            "target_title": "B",
            "target_author": "X",
            "target_isbn": "2",
            "target_date_published": "",
            "target_publisher": "P",
            "target_number_of_pages": "10",
        },
    ]
    kept = keep_complete_gt(rows, EXPERIMENT_COLUMNS)
    assert [r["title"] for r in kept] == ["A"]


def test_deduplicate_by_dirty_drops_aligned_clean():
    dirty = [
        {"id": "1", "title": "A", "author": "", "isbn": "", "date_published": "",
         "publisher": "", "number_of_pages": ""},
        {"id": "2", "title": "A", "author": "", "isbn": "", "date_published": "",
         "publisher": "", "number_of_pages": ""},
    ]
    clean = [{"id": "1", "title": "X"}, {"id": "2", "title": "Y"}]
    prov = [{"id": "1"}, {"id": "2"}]
    d, c, _p, removed = deduplicate_by_dirty(dirty, clean, prov, EXPERIMENT_COLUMNS)
    assert [r["id"] for r in d] == ["1"]
    assert [r["id"] for r in c] == ["1"]
    assert removed == ["2"]
