#!/usr/bin/env python3
import os
import sys
from typing import List

import pandas as pd

DEFAULT_PATH = "../datasets/values.csv"
OUTPUT_CSV = "analysis_summary.csv"
TOP_N = 20  # value-counts per column (for printing and CSV)


def analyze_dataset(
        path: str = DEFAULT_PATH,
        output_csv: str = OUTPUT_CSV,
        top_n: int = TOP_N
) -> pd.DataFrame:
    """
    Loads a CSV, computes null stats, duplicate rows count, and simple value counts.
    Returns a long-form DataFrame and writes it to `output_csv`.
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"Input file not found: {path}")

    print(f"Loading CSV: {path}")
    df = pd.read_csv(path, low_memory=True)  # low_memory to keep memory footprint smaller
    print("Head Values")
    print(df.head())
    n_rows, n_cols = df.shape
    print(f"Loaded dataframe with {n_rows:,} rows × {n_cols:,} columns\n")

    rows: List[dict] = []

    # ---- Nulls per column ----
    print("=== NULLS PER COLUMN ===")
    null_counts = df.isna().sum()
    null_pct = (null_counts / len(df)) * 100.0
    nulls_table = pd.DataFrame({
        "column": df.columns,
        "null_count": null_counts.values,
        "null_pct": null_pct.values
    }).sort_values(by="null_count", ascending=False)

    rows_with_nulls = df[df.isnull().any(axis=1)]

    print("Rows with null values:")
    print(rows_with_nulls)

    # Add to combined rows
    for _, r in nulls_table.iterrows():
        rows.append({
            "metric": "nulls",
            "column": r["column"],
            "key": "null_count",
            "value": int(r["null_count"])
        })
        rows.append({
            "metric": "nulls",
            "column": r["column"],
            "key": "null_pct",
            "value": float(r["null_pct"])
        })

    # Print a compact head
    print(nulls_table.head(20).to_string(index=False, formatters={
        "null_pct": lambda v: f"{v:.2f}%"
    }))
    print()

    # ---- Duplicate rows (entire-row duplicates) ----
    print("=== DUPLICATE ROWS (ENTIRE ROW) ===")
    dup_count = int(df.duplicated(keep="first").sum())
    print(f"Duplicate rows: {dup_count:,}\n")

    rows.append({
        "metric": "duplicates",
        "column": "__all_columns__",
        "key": "duplicate_rows_count",
        "value": dup_count
    })

    # ---- Value Counts ----
    print("=== VALUE COUNTS (TOP {top_n}) ===".format(top_n=top_n))
    from pandas.api.types import is_object_dtype, is_categorical_dtype, is_numeric_dtype

    for col in df.columns:
        s = df[col]
        # Decide if we’ll compute value_counts
        compute_counts = False

        if is_object_dtype(s) or is_categorical_dtype(s):
            compute_counts = True
        elif is_numeric_dtype(s):
            nunq = s.nunique(dropna=True)
            if nunq <= 50:
                compute_counts = True
            else:
                # record a skip for high-cardinality numeric
                rows.append({
                    "metric": "value_counts",
                    "column": col,
                    "key": "skipped_high_cardinality_nunique",
                    "value": int(nunq)
                })

        if compute_counts:
            vc = s.value_counts(dropna=False)
            # Write top-N to console
            print(f"\n-- {col} --")
            print(vc.head(top_n).to_string())

            # Save top-N (long form) to combined CSV rows
            for key_val, cnt in vc.head(top_n).items():
                key_str = "<NA>" if (pd.isna(key_val)) else str(key_val)
                rows.append({
                    "metric": "value_counts",
                    "column": col,
                    "key": key_str,
                    "value": int(cnt)
                })

    # ---- Combine and write CSV ----
    summary_df = pd.DataFrame(rows, columns=["metric", "column", "key", "value"])
    summary_df.to_csv(output_csv, index=False)
    print(f"\nWrote combined summary to: {os.path.abspath(output_csv)}")

    # Short run summary
    print("\n=== RUN SUMMARY ===")
    print(f"Rows: {n_rows:,}, Cols: {n_cols:,}")
    print(f"Nulls summarized for {n_cols} columns.")
    print(f"Duplicate rows: {dup_count:,}")
    print(f"Value counts saved (top {top_n}); high-cardinality numeric columns noted as skipped.")
    return summary_df


def main():
    # Simple CLI: optional path override
    path = DEFAULT_PATH
    if len(sys.argv) > 1:
        path = sys.argv[1]

    analyze_dataset(path=path, output_csv=OUTPUT_CSV, top_n=TOP_N)


if __name__ == "__main__":
    main()
