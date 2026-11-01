#!/usr/bin/env python3
"""Distinct-clean runtime subsets at the full runtime error rate.

Reads runtime/full_full, keeps the first dirty/clean pair for each distinct
clean record, and draws a 100k sample with a 10k sample nested inside it.
Erroneous dirty cells are then replaced with the clean value until each
sample matches the cell error rate of runtime/full_full. Repairs never
introduce new errors.

Usage:
    python prepare_runtime_distinct.py
    python prepare_runtime_distinct.py --seed 0
"""

from __future__ import annotations

import argparse
import csv
import random
import sys
from pathlib import Path

EXPERIMENTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(EXPERIMENTS_DIR))
from evaluate import normalize

REPO_ROOT = EXPERIMENTS_DIR.parents[1]
DEFAULT_SOURCE = REPO_ROOT / "runtime" / "full_full"
DEFAULT_OUT = REPO_ROOT / "runtime"
SIZES = (100_000, 10_000)


def read_distinct_pairs(source: Path) -> tuple[list[str], list[tuple[str, ...]], list[tuple[str, ...]], int, int]:
    """Return columns, kept dirty rows, kept clean rows, source rows, source errors."""
    csv.field_size_limit(sys.maxsize)
    dirty_path = source / "dirty.csv"
    clean_path = source / "clean.csv"
    seen: set[tuple[str, ...]] = set()
    dirty_kept: list[tuple[str, ...]] = []
    clean_kept: list[tuple[str, ...]] = []
    n_rows = 0
    n_errors = 0
    with dirty_path.open(newline="", encoding="utf-8") as dirty_f, clean_path.open(
        newline="", encoding="utf-8"
    ) as clean_f:
        dirty_reader = csv.reader(dirty_f)
        clean_reader = csv.reader(clean_f)
        columns = next(dirty_reader)
        clean_header = next(clean_reader)
        if columns != clean_header:
            raise ValueError(f"Header mismatch: {columns} vs {clean_header}")
        for dirty_row, clean_row in zip(dirty_reader, clean_reader):
            if len(dirty_row) != len(columns) or len(clean_row) != len(columns):
                raise ValueError(f"Short row at source index {n_rows}")
            n_rows += 1
            for left, right in zip(dirty_row, clean_row):
                if normalize(left) != normalize(right):
                    n_errors += 1
            key = tuple(clean_row)
            if key in seen:
                continue
            seen.add(key)
            dirty_kept.append(tuple(dirty_row))
            clean_kept.append(key)
    return columns, dirty_kept, clean_kept, n_rows, n_errors


def error_positions(dirty_rows: list[tuple[str, ...]], clean_rows: list[tuple[str, ...]]) -> list[tuple[int, int]]:
    bad: list[tuple[int, int]] = []
    for i, (dirty_row, clean_row) in enumerate(zip(dirty_rows, clean_rows)):
        for j, (left, right) in enumerate(zip(dirty_row, clean_row)):
            if normalize(left) != normalize(right):
                bad.append((i, j))
    return bad


def match_error_rate(
    dirty_rows: list[tuple[str, ...]],
    clean_rows: list[tuple[str, ...]],
    target_rate: float,
    rng: random.Random,
) -> tuple[list[tuple[str, ...]], int]:
    """Replace random erroneous cells with the clean value down to target_rate."""
    n_cells = len(dirty_rows) * (len(dirty_rows[0]) if dirty_rows else 0)
    n_target = int(target_rate * n_cells)
    bad = error_positions(dirty_rows, clean_rows)
    n_fix = len(bad) - n_target
    if n_fix <= 0:
        return dirty_rows, len(bad)
    rng.shuffle(bad)
    mutable = [list(row) for row in dirty_rows]
    for i, j in bad[:n_fix]:
        mutable[i][j] = clean_rows[i][j]
    return [tuple(row) for row in mutable], n_target


def write_pair(columns: list[str], dirty_rows: list[tuple[str, ...]], clean_rows: list[tuple[str, ...]], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, rows in (("dirty.csv", dirty_rows), ("clean.csv", clean_rows)):
        with (out_dir / name).open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(columns)
            writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--sizes", type=int, nargs="+", default=list(SIZES))
    args = parser.parse_args()

    sizes = sorted(args.sizes, reverse=True)
    if any(size <= 0 for size in sizes):
        sys.exit("Sample sizes must be positive")

    columns, dirty_kept, clean_kept, n_rows, n_errors = read_distinct_pairs(args.source)
    n_cells = n_rows * len(columns)
    target_rate = n_errors / n_cells if n_cells else 0.0
    pool_errors = len(error_positions(dirty_kept, clean_kept))
    pool_cells = len(clean_kept) * len(columns)
    print(f"source rows: {n_rows:,}")
    print(f"distinct clean records: {len(clean_kept):,}")
    print(f"full runtime error rate: {target_rate:.6f}")
    print(f"distinct-pool error rate before repair: {pool_errors / pool_cells:.6f}")

    if sizes[0] > len(clean_kept):
        sys.exit(f"Largest sample {sizes[0]:,} exceeds {len(clean_kept):,} distinct records")

    rng = random.Random(args.seed)
    order = list(range(len(clean_kept)))
    rng.shuffle(order)
    # Nested: every smaller sample is a prefix of the largest shuffled draw.
    chosen = order[: sizes[0]]

    for size in sizes:
        idx = chosen[:size]
        dirty_sample = [dirty_kept[i] for i in idx]
        clean_sample = [clean_kept[i] for i in idx]
        before = len(error_positions(dirty_sample, clean_sample))
        before_cells = size * len(columns)
        dirty_out, n_kept_errors = match_error_rate(dirty_sample, clean_sample, target_rate, rng)
        if len(set(clean_sample)) != size:
            sys.exit(f"Sample of {size} is not distinct on clean records")
        out_dir = args.out / f"full_{size}_distinct"
        write_pair(columns, dirty_out, clean_sample, out_dir)
        achieved = n_kept_errors / before_cells
        print(
            f"{out_dir.name}: rows={size:,}  "
            f"rate {before / before_cells:.6f} -> {achieved:.6f}  "
            f"errors={n_kept_errors:,}"
        )


if __name__ == "__main__":
    main()
