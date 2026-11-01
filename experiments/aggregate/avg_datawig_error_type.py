"""
For each poi_ dataset, runs eval_by_error_type across the 3 datawig run
directories and writes an averaged error-type metrics CSV to:
  experiments_data_results/results/datawig/<dataset>_avg_error_type_metrics.csv
"""

import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from paths import AGGREGATE_DIR, cell_labels_csv, system_results_dir  # noqa: E402

RESULTS_DIR = system_results_dir("datawig")

CELL_ERROR_TYPES = {
    "poi_Library": cell_labels_csv("poi_Library"),
    "poi_ShoppingCenter": cell_labels_csv("poi_ShoppingCenter"),
}

sys.path.insert(0, AGGREGATE_DIR)
from eval_by_error_type import load_cell_error_types, evaluate  # noqa: E402

# Numeric columns to average
SCORE_COLS = [
    "n_cells",
    "det_tp", "det_fp", "det_fn",
    "det_precision", "det_recall", "det_f1",
    "cor_tp", "cor_fp", "cor_fn",
    "cor_precision", "cor_recall", "cor_f1",
]


def find_run_dirs(dataset_prefix: str) -> list[str]:
    """Return sorted list of result directories whose name starts with dataset_prefix."""
    dirs = sorted(
        os.path.join(RESULTS_DIR, e)
        for e in os.listdir(RESULTS_DIR)
        if e.startswith(dataset_prefix + "_") and os.path.isdir(os.path.join(RESULTS_DIR, e))
    )
    return dirs


def main():
    for dataset, cell_types_csv in CELL_ERROR_TYPES.items():
        print(f"\n=== {dataset} ===")

        if not os.path.isfile(cell_types_csv):
            print(f"  ERROR: cell_error_types.csv not found: {cell_types_csv}")
            continue

        cell_dict = load_cell_error_types(cell_types_csv)
        print(f"  Loaded {len(cell_dict):,} cell error-type entries.")

        run_dirs = find_run_dirs(dataset)
        if not run_dirs:
            print(f"  ERROR: no run directories found for {dataset}")
            continue

        # Keep only the 3 most recent if more exist
        if len(run_dirs) > 3:
            run_dirs = run_dirs[-3:]

        print(f"  Using {len(run_dirs)} run(s):")
        dfs = []
        for rdir in run_dirs:
            cells_csv = os.path.join(rdir, "cells.csv")
            if not os.path.isfile(cells_csv):
                print(f"    SKIP (no cells.csv): {rdir}")
                continue
            print(f"    {os.path.basename(rdir)}")
            df = evaluate(cells_csv, cell_dict)
            dfs.append(df)

        if not dfs:
            print("  ERROR: no valid runs evaluated.")
            continue

        # Average numeric columns across runs, keyed on error_type
        combined = pd.concat(dfs, ignore_index=True)
        avg_df = (
            combined.groupby("error_type", sort=True)[SCORE_COLS]
            .mean()
            .round(4)
            .reset_index()
        )
        # n_cells and TP/FP/FN counts are summed, not averaged, so show them as sums
        sum_cols = ["n_cells", "det_tp", "det_fp", "det_fn", "cor_tp", "cor_fp", "cor_fn"]
        avg_numeric = combined.groupby("error_type")[
            [c for c in SCORE_COLS if c not in sum_cols]
        ].mean().round(4)
        sum_numeric = combined.groupby("error_type")[sum_cols].sum()
        result_df = pd.concat([sum_numeric, avg_numeric], axis=1).reset_index()
        result_df = result_df[["error_type"] + SCORE_COLS]

        out_path = os.path.join(RESULTS_DIR, f"{dataset}_avg_error_type_metrics.csv")
        result_df.to_csv(out_path, index=False)
        print(f"  Written: {out_path}")

        display_cols = [
            "error_type", "n_cells",
            "det_precision", "det_recall", "det_f1",
            "cor_precision", "cor_recall", "cor_f1",
        ]
        print("\n" + result_df[display_cols].to_string(index=False))


if __name__ == "__main__":
    main()
