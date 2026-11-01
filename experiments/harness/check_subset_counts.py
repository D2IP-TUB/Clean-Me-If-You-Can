"""
check_subset_counts.py — report row counts for every dirty.csv in the subsets directory,
before and after the preprocessing steps used in prepare_datasets.py:
  1. Keep only the configured data columns (+ id), dropping extras like provenance_graph_iri.
  2. Deduplicate on data columns only (id is excluded from the duplicate check).
"""

import json
import os
import sys

import pandas as pd

EXPERIMENTS_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(EXPERIMENTS_DIR, "config.json")

SUBSETS_DIR = os.path.normpath(
    os.path.join(EXPERIMENTS_DIR, "../../data/subsets")
)


def load_config(path: str) -> dict:
    with open(path) as f:
        return json.load(f)


def find_dirty_files(root: str) -> list:
    paths = []
    for dirpath, _, filenames in os.walk(root):
        if "dirty.csv" in filenames:
            paths.append(os.path.join(dirpath, "dirty.csv"))
    return sorted(paths)


def main():
    cfg = load_config(CONFIG_PATH)
    data_cols = cfg["dataset"]["data_columns"]

    # Auto-detect id column: prefer config value, fall back to first column
    cfg_id_col = cfg["dataset"]["id_column"]

    dirty_files = find_dirty_files(SUBSETS_DIR)
    if not dirty_files:
        print(f"No dirty.csv files found under {SUBSETS_DIR}")
        sys.exit(1)

    header = f"{'Dataset':<55} {'raw':>8} {'col-select':>10} {'deduped':>8} {'removed':>8}"
    print(header)
    print("-" * len(header))

    for path in dirty_files:
        rel = os.path.relpath(path, SUBSETS_DIR)

        df = pd.read_csv(path, dtype=str, keep_default_na=False, low_memory=False)
        raw = len(df)

        # Determine id column for this file
        id_col = cfg_id_col if cfg_id_col in df.columns else df.columns[0]

        # Step 1: keep only id + data_columns
        keep = [id_col] + [c for c in data_cols if c in df.columns]
        df_sel = df[keep]
        after_select = len(df_sel)

        # Step 2: deduplicate on data columns only (ignore id)
        non_id = [c for c in df_sel.columns if c != id_col]
        df_dedup = df_sel[~df_sel.duplicated(subset=non_id, keep="first")]
        after_dedup = len(df_dedup)

        removed = after_select - after_dedup
        print(f"{rel:<55} {raw:>8} {after_select:>10} {after_dedup:>8} {removed:>8}")


if __name__ == "__main__":
    main()
