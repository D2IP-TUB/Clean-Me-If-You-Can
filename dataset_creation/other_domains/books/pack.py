"""Pack validated Book records into dirty/clean CSVs."""

from __future__ import annotations

import argparse
from pathlib import Path

from loguru import logger

from books.openlibrary import ensure_string
from shared.io import project_root, read_from_jsongz
from shared.pack_common import assign_ids, unique_rows, write_flat_dataset

EXPERIMENT_COLUMNS = [
    "title",
    "author",
    "isbn",
    "date_published",
    "publisher",
    "number_of_pages",
]
PROVENANCE_COLUMNS = [
    "entity_type",
    "crawl_url",
    "provenance_graph_iri",
    "provenance_wdc_release",
    "provenance_subset",
    "provenance_source_file",
    "openlibrary_key",
    "work_key",
    "match",
]


def _join(value) -> str | None:
    return ensure_string(value)


def row_from_record(record: dict) -> dict:
    crawl = record.get("crawl") or {}
    data = crawl.get("data") or {}
    query = record.get("entity_query") or {}
    kb = record.get("kb") or {}
    meta = crawl.get("crawl_metadata") or {}
    prov = meta.get("provenance") or {}
    return {
        "title": _join(query.get("title") or data.get("name")),
        "author": _join(data.get("author")),
        "isbn": _join(query.get("isbn") or data.get("isbn") or data.get("gtin13")),
        "date_published": _join(data.get("datePublished") or data.get("copyrightYear")),
        "publisher": _join(data.get("publisher")),
        "number_of_pages": _join(data.get("numberOfPages")),
        "target_title": _join(kb.get("title")),
        "target_author": _join(kb.get("authors")),
        "target_isbn": _join(kb.get("isbn")),
        "target_date_published": _join(kb.get("publish_date")),
        "target_publisher": _join(kb.get("publishers")),
        "target_number_of_pages": _join(kb.get("number_of_pages")),
        "entity_type": data.get("@type") or "Book",
        "crawl_url": meta.get("url"),
        "provenance_graph_iri": prov.get("graph_iri"),
        "provenance_wdc_release": prov.get("wdc_release"),
        "provenance_subset": prov.get("subset"),
        "provenance_source_file": prov.get("source_file"),
        "openlibrary_key": kb.get("openlibrary_key"),
        "work_key": kb.get("work_key"),
        "match": kb.get("match"),
    }


def write_split(dataset_dir: Path, rows: list[dict]) -> None:
    write_flat_dataset(
        dataset_dir,
        rows,
        EXPERIMENT_COLUMNS,
        PROVENANCE_COLUMNS,
        extra_id_columns=("openlibrary_key", "work_key", "match"),
    )


def load_validated_rows(validated_root: Path) -> list[dict]:
    rows: list[dict] = []
    for path in sorted(validated_root.glob("**/*.json.gz")):
        if path.name.endswith("_sample.json.gz"):
            continue
        records = read_from_jsongz(path)
        if not isinstance(records, list):
            continue
        for rec in records:
            if rec.get("kb") is None:
                continue
            rows.append(row_from_record(rec))
    return unique_rows(rows)


def pack_books(validated_root: Path, output_dir: Path) -> None:
    rows = assign_ids(load_validated_rows(validated_root))
    write_split(output_dir, rows)
    logger.info(f"Packed {len(rows)} unique validated rows -> {output_dir}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Pack validated books into dirty/clean CSVs.")
    parser.add_argument("--validated-root", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=None)
    args = parser.parse_args()
    validated_root = (args.validated_root or (project_root() / "data" / "validated" / "Book")).resolve()
    output_dir = (args.output_dir or (project_root() / "data" / "pack" / "Book")).resolve()
    pack_books(validated_root, output_dir)


if __name__ == "__main__":
    main()
