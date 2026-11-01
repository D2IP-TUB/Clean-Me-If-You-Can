#!/usr/bin/env python3
"""Count distinct clean records in each runtime subset.

Identifier columns (``id``, ``_id``, ``graph_iri``, ``provenance_graph_iri``)
and the helper ``postcode_fix`` are dropped before the distinct count.
Every other column is part of the record.

Usage:
    python count_distinct_subset_records.py
    python count_distinct_subset_records.py runtime
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


def subset_sort_key(name: str) -> tuple:
    if name.endswith("_full") or name == "full_full":
        return (10**18, name)
    digits = "".join(ch for ch in name if ch.isdigit())
    return (int(digits) if digits else 10**17, name)


def count_distinct(path: Path) -> tuple[int, int, list[str]]:
    csv.field_size_limit(sys.maxsize)
    seen: set[tuple[str, ...]] = set()
    n_rows = 0
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError(f"No header in {path}")
        keep = [col for col in reader.fieldnames if col not in DROP_COLS]
        if not keep:
            raise ValueError(f"No data columns left in {path}")
        for row in reader:
            n_rows += 1
            seen.add(tuple(row[col] if row[col] is not None else "" for col in keep))
    return n_rows, len(seen), keep


def main() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "runtime_dir",
        nargs="?",
        type=Path,
        default=repo_root / "runtime",
        help="Directory of subset folders, each with a clean.csv",
    )
    args = parser.parse_args()
    root = args.runtime_dir
    if not root.is_dir():
        sys.exit(f"Not a directory: {root}")

    cleans = sorted(root.glob("*/clean.csv"), key=lambda path: subset_sort_key(path.parent.name))
    if not cleans:
        sys.exit(f"No */clean.csv under {root}")

    print(f"{'subset':<16} {'rows':>12} {'distinct':>12}")
    for path in cleans:
        n_rows, n_distinct, _keep = count_distinct(path)
        print(f"{path.parent.name:<16} {n_rows:>12,} {n_distinct:>12,}")


if __name__ == "__main__":
    main()
