#!/usr/bin/env python3
"""Count distinct ground-truth records after dropping identifier columns.

At the record level, ``_id`` / ``id`` and ``graph_iri`` / ``provenance_graph_iri``
are identifiers, not address content. This script drops them (and the
non-schema ``postcode_fix`` helper) and counts distinct remaining tuples
in a ground-truth CSV.

Usage:
    python count_distinct_gt_records.py
    python count_distinct_gt_records.py clean_record_fixed/full_clean_fixed.csv
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

DROP_COLS = {
    "id",
    "_id",
    "graph_iri",
    "provenance_graph_iri",
    "postcode_fix",
}

# Address without the entity name, for the co-location summary.
ADDRESS_COLS = [
    "house_number",
    "road",
    "postcode",
    "locality",
    "region",
    "country",
    "country_code",
]


def count_distinct_rows(path: Path) -> dict:
    csv.field_size_limit(sys.maxsize)
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError(f"No header in {path}")
        keep = [col for col in reader.fieldnames if col not in DROP_COLS]
        missing_addr = [col for col in ADDRESS_COLS if col not in keep]
        if missing_addr:
            raise ValueError(f"Missing address columns {missing_addr} in {path}")
        if "name" not in keep:
            raise ValueError(f"Missing name column in {path}")

        records: set[tuple[str, ...]] = set()
        names_at_address: dict[tuple[str, ...], set[str]] = {}
        name_idx = keep.index("name")
        addr_idx = [keep.index(col) for col in ADDRESS_COLS]
        n_rows = 0
        for row in reader:
            n_rows += 1
            record = tuple(row[col] if row[col] is not None else "" for col in keep)
            if record in records:
                continue
            records.add(record)
            address = tuple(record[i] for i in addr_idx)
            names_at_address.setdefault(address, set()).add(record[name_idx])

    n_addresses = len(names_at_address)
    sizes = [len(names) for names in names_at_address.values()]
    return {
        "path": str(path),
        "n_rows": n_rows,
        "columns": keep,
        "n_distinct_records": len(records),
        "n_distinct_addresses": n_addresses,
        "mean_entities_per_address": (sum(sizes) / n_addresses) if n_addresses else 0.0,
        "max_entities_per_address": max(sizes) if sizes else 0,
    }


def main() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    default_clean = repo_root / "clean_record_fixed" / "full_clean_fixed.csv"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "clean_csv",
        nargs="?",
        type=Path,
        default=default_clean,
        help="Ground-truth CSV (default: clean_record_fixed/full_clean_fixed.csv)",
    )
    args = parser.parse_args()
    path = args.clean_csv
    if not path.is_file():
        sys.exit(f"Ground-truth file not found: {path}")

    stats = count_distinct_rows(path)
    print(f"file: {stats['path']}")
    print(f"rows: {stats['n_rows']:,}")
    print(f"columns kept: {', '.join(stats['columns'])}")
    print(f"distinct records: {stats['n_distinct_records']:,}")
    print(f"distinct addresses (without name): {stats['n_distinct_addresses']:,}")
    print(f"mean entities per address: {stats['mean_entities_per_address']:.2f}")
    print(f"max entities per address: {stats['max_entities_per_address']:,}")


if __name__ == "__main__":
    main()
