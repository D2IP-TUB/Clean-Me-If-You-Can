#!/usr/bin/env python3
"""Evaluate error repair system performance broken down by error type.

Usage
-----
  python eval_by_error_type.py \\
      --cells_csv          experiments_data_results/results/horizon/de_sample_de_0.05_.../cells.csv \\
      --cell_error_types_csv  <analysis_outdir>/cell_error_types.csv \\
      [--output_csv        error_type_metrics.csv]

cell_error_types.csv is produced by analyze_error_types_v3.py and contains
one row per cell: row_index, feature, dirty_value, clean_value, error_type.

Output
------
A CSV (and console table) with per-error-type:
  error_type  |  n_cells
  det_tp  det_fp  det_fn  det_precision  det_recall  det_f1
  cor_tp  cor_fp  cor_fn  cor_precision  cor_recall  cor_f1
"""

import argparse
import csv
import os
import sys
from collections import defaultdict

import pandas as pd


# ---------------------------------------------------------------------------
# Load cell_error_types.csv produced by analyze_error_types_v3.py
# ---------------------------------------------------------------------------

def load_cell_error_types(path: str) -> dict:
    """Return {(row_index, feature): error_type} from cell_error_types.csv."""
    result = {}
    with open(path, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            result[(int(row["row_index"]), row["feature"])] = row["error_type"]
    return result


# ---------------------------------------------------------------------------
# Compute F1 from TP / FP / FN
# ---------------------------------------------------------------------------

def prf(tp: int, fp: int, fn: int):
    p = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    r = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f = 2 * p * r / (p + r) if (p + r) > 0 else 0.0
    return p, r, f


# ---------------------------------------------------------------------------
# Main evaluation
# ---------------------------------------------------------------------------

def evaluate(cells_csv: str, cell_dict: dict) -> pd.DataFrame:
    """Return a DataFrame with per-error-type aggregated metrics."""

    stats: dict = defaultdict(lambda: {
        "n": 0,
        "det_tp": 0, "det_fp": 0, "det_fn": 0,
        "cor_tp": 0, "cor_fp": 0, "cor_fn": 0,
    })

    with open(cells_csv, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            if int(row["is_actual_error"]) == 0:
                et = "Clean"
            else:
                et = cell_dict.get((int(row["row_id"]), row["col_name"]), "Unknown")
            s = stats[et]
            s["n"] += 1
            s["det_tp"] += int(row["det_tp"])
            s["det_fp"] += int(row["det_fp"])
            s["det_fn"] += int(row["det_fn"])
            s["cor_tp"] += int(row["cor_tp"])
            s["cor_fp"] += int(row["cor_fp"])
            s["cor_fn"] += int(row["cor_fn"])

    rows = []
    for et, s in sorted(stats.items()):
        dp, dr, df1 = prf(s["det_tp"], s["det_fp"], s["det_fn"])
        cp, cr, cf1 = prf(s["cor_tp"], s["cor_fp"], s["cor_fn"])
        rows.append({
            "error_type": et,
            "n_cells": s["n"],
            "det_tp": s["det_tp"], "det_fp": s["det_fp"], "det_fn": s["det_fn"],
            "det_precision": round(dp, 4),
            "det_recall": round(dr, 4),
            "det_f1": round(df1, 4),
            "cor_tp": s["cor_tp"], "cor_fp": s["cor_fp"], "cor_fn": s["cor_fn"],
            "cor_precision": round(cp, 4),
            "cor_recall": round(cr, 4),
            "cor_f1": round(cf1, 4),
        })

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Evaluate error repair performance per error type.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--cells_csv", required=True,
        help="Path to cells.csv from an experiment result directory.",
    )
    parser.add_argument(
        "--cell_error_types_csv", required=True,
        help="Path to cell_error_types.csv produced by analyze_error_types_v3.py.",
    )
    parser.add_argument(
        "--output_csv", default=None,
        help="Where to write the metrics CSV (default: <result_dir>/error_type_metrics.csv).",
    )
    parser.add_argument(
        "--show_dict", action="store_true",
        help="Print the first 20 entries of the (row_id, col_name)->error_type dict.",
    )
    args = parser.parse_args()

    print(f"Loading cell_error_types.csv …", file=sys.stderr)
    cell_dict = load_cell_error_types(args.cell_error_types_csv)
    print(f"  → {len(cell_dict):,} entries loaded.", file=sys.stderr)

    print("Evaluating cells …", file=sys.stderr)
    df = evaluate(args.cells_csv, cell_dict)

    out_csv = args.output_csv or os.path.join(
        os.path.dirname(os.path.abspath(args.cells_csv)),
        "error_type_metrics.csv",
    )
    df.to_csv(out_csv, index=False)
    print(f"Metrics written to: {out_csv}", file=sys.stderr)

    display_cols = [
        "error_type", "n_cells",
        "det_precision", "det_recall", "det_f1",
        "cor_precision", "cor_recall", "cor_f1",
    ]
    print("\n" + df[display_cols].to_string(index=False))

    if args.show_dict:
        print("\nSample cell -> error_type (first 20):")
        for k, v in list(cell_dict.items())[:20]:
            print(f"  {k} -> {v}")


if __name__ == "__main__":
    main()
