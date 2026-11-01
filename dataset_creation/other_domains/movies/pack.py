"""Pack validated movie records into dirty/clean CSVs."""

from __future__ import annotations

import argparse
from pathlib import Path

from loguru import logger

from shared.io import project_root, read_from_jsongz
from shared.pack_common import assign_ids, unique_rows, write_flat_dataset
from shared.text import ensure_string

EXPERIMENT_COLUMNS = [
    "title",
    "director",
    "actor",
    "date_published",
    "duration",
    "genre",
]
PROVENANCE_COLUMNS = [
    "entity_type",
    "crawl_url",
    "provenance_graph_iri",
    "provenance_wdc_release",
    "provenance_subset",
    "provenance_source_file",
    "imdb_id",
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
        "director": _join(data.get("director")),
        "actor": _join(data.get("actor")),
        "date_published": _join(data.get("datePublished") or data.get("dateCreated")),
        "duration": _join(data.get("duration")),
        "genre": _join(data.get("genre")),
        "target_title": _join(kb.get("title")),
        "target_director": _join(kb.get("director")),
        "target_actor": _join(kb.get("actor")),
        "target_date_published": _join(kb.get("release_date")),
        "target_duration": _join(kb.get("runtime")),
        "target_genre": _join(kb.get("genre")),
        "entity_type": data.get("@type") or "Movie",
        "crawl_url": meta.get("url"),
        "provenance_graph_iri": prov.get("graph_iri"),
        "provenance_wdc_release": prov.get("wdc_release"),
        "provenance_subset": prov.get("subset"),
        "provenance_source_file": prov.get("source_file"),
        "imdb_id": kb.get("imdb_id"),
        "match": kb.get("match"),
    }


def write_dataset(dataset_dir: Path, rows: list[dict]) -> None:
    write_flat_dataset(
        dataset_dir,
        rows,
        EXPERIMENT_COLUMNS,
        PROVENANCE_COLUMNS,
        extra_id_columns=("imdb_id", "match"),
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


def pack_movies(validated_root: Path, output_dir: Path) -> None:
    rows = assign_ids(load_validated_rows(validated_root))
    write_dataset(output_dir, rows)
    logger.info(f"Packed {len(rows)} unique validated rows -> {output_dir}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Pack validated movies into dirty/clean CSVs.")
    parser.add_argument("--validated-root", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=None)
    args = parser.parse_args()
    validated_root = (
        args.validated_root or (project_root() / "data" / "validated" / "Movie")
    ).resolve()
    output_dir = (args.output_dir or (project_root() / "data" / "pack" / "Movie")).resolve()
    pack_movies(validated_root, output_dir)


if __name__ == "__main__":
    main()
