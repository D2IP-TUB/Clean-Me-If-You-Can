#!/usr/bin/env python3
"""
Evaluate ZeroDCcorrection results broken down by error type.

For each (table, human_repair_N) result folder:
  - Compare corrections.csv vs dirty.csv to find corrected cells.
  - A corrected cell is TP if corrections[cell] == clean[cell] AND dirty[cell] != clean[cell].
  - Look up error type via error_map_all_tables.csv + merged_cell_source_map.csv
    (or per-table error_map.csv when the consolidated file is absent).
  - Aggregate tp, fp, fn per error type across the lake.

Outputs:
  - zerodccorrection_per_type_per_table.csv  : one row per (dataset, human_repair_num, error_type)
  - zerodccorrection_per_type_summary.csv    : aggregated across all tables per (human_repair_num, error_type)
"""

from pathlib import Path
import html
import os
import re

import numpy as np
import pandas as pd


_REPO = Path(__file__).resolve().parents[3]
TABLES_PATH = str(_REPO / 'datasets' / 'real_lakes' / 'open_data_uk_merged_set_union')
RESULTS_PATH = str(_REPO / 'results' / 'zerodccorrection' / 'open_data_uk_pm_labeling_budget_10')
# Consolidated error annotations (UK source table_id, row, column_name -> error_type)
ERROR_MAP_ALL_PATH = os.path.join(TABLES_PATH, "error_map_all_tables.csv")
DIRTY_FILE = "dirty.csv"
CLEAN_FILE = "clean.csv"


def value_normalizer(value):
    if isinstance(value, str):
        value = html.unescape(value)
        value = re.sub(r"[\t\n ]+", " ", value)
        value = value.strip("\t\n ")
    return value


def load_consolidated_error_map(all_tables_path):
    """
    Single read of error_map_all_tables.csv.
    Returns (global_map, totals) where global_map maps
    (source_table_id, row_idx, column_name) -> error_type, or (None, {}) on failure.
    """
    if not os.path.exists(all_tables_path):
        return None, {}
    df = pd.read_csv(all_tables_path, keep_default_na=False, dtype=str, encoding="latin1")
    need = {"table_id", "row_number", "column_name", "error_type"}
    if df.empty or not need.issubset(df.columns):
        return None, {}
    et = df["error_type"].astype(str).str.strip()
    totals = et[et != ""].value_counts().to_dict()
    rn = pd.to_numeric(df["row_number"], errors="coerce")
    tid = df["table_id"].astype(str).str.strip()
    cname = df["column_name"].astype(str).str.strip()
    valid = et.ne("") & tid.ne("") & cname.ne("") & rn.notna()
    if not valid.any():
        return None, totals
    rn_i = rn[valid].astype(np.int64)
    out = {
        (t, int(r), c): e
        for t, r, c, e in zip(tid[valid], rn_i, cname[valid], et[valid])
    }
    return out, totals


def load_merged_source_lookup(table_path):
    """
    Map merged (row_number, column_id) -> (source_table_id, source_row, source_column_name).
    """
    path = os.path.join(table_path, "merged_cell_source_map.csv")
    if not os.path.exists(path):
        return None
    df = pd.read_csv(path, keep_default_na=False, dtype=str, encoding="latin1")
    need = {"row_number", "column_id", "source_table", "source_row", "source_column"}
    if df.empty or not need.issubset(df.columns):
        return None
    mr = pd.to_numeric(df["row_number"], errors="coerce")
    mc = pd.to_numeric(df["column_id"], errors="coerce")
    sr = pd.to_numeric(df["source_row"], errors="coerce")
    st = df["source_table"].astype(str).str.strip()
    scol = df["source_column"].astype(str).str.strip()
    valid = st.ne("") & scol.ne("") & mr.notna() & mc.notna() & sr.notna()
    if not valid.any():
        return None
    lookup = {
        (int(r), int(c)): (s, int(sr_i), col)
        for r, c, sr_i, s, col in zip(
            mr[valid], mc[valid], sr[valid], st[valid], scol[valid]
        )
    }
    return lookup


def load_error_map(table_path):
    """
    Returns dict {(row_idx, col_idx): error_type} where row_idx is 0-based
    (matching the DataFrame row index after header).
    Returns None if error_map.csv is missing or malformed.
    """
    emap_path = os.path.join(table_path, "error_map.csv")
    if not os.path.exists(emap_path):
        return None
    df = pd.read_csv(emap_path, keep_default_na=False, dtype=str, encoding="latin1")
    if df.empty or not {"row_number", "column_name", "error_type"}.issubset(df.columns):
        return None

    dirty_path = os.path.join(table_path, DIRTY_FILE)
    if not os.path.exists(dirty_path):
        return None
    dirty_cols = list(pd.read_csv(dirty_path, nrows=0, encoding="latin1").columns)
    col_to_idx = {name: idx for idx, name in enumerate(dirty_cols)}

    error_map = {}
    for _, row in df.iterrows():
        try:
            r = int(row["row_number"])
        except (ValueError, TypeError):
            continue
        col_name = str(row["column_name"]).strip()
        c = col_to_idx.get(col_name)
        if c is None:
            continue
        et = str(row.get("error_type", "")).strip()
        if et:
            error_map[(r, c)] = et
    return error_map


def evaluate_table_result(table_path, corrections_path, global_error_map=None):
    """
    Compare corrections vs dirty/clean for one (table, human_repair_N) pair.

    Returns a dict:
      per_type: {error_type: {"tp": int, "fp": int}}
      total_corrected: int   (cells where corrections != dirty)
      total_tp: int
    Or None if data is unavailable.
    """
    dirty_path = os.path.join(table_path, DIRTY_FILE)
    clean_path = os.path.join(table_path, CLEAN_FILE)
    corr_path = os.path.join(corrections_path, "corrections.csv")

    if not all(os.path.exists(p) for p in [dirty_path, clean_path, corr_path]):
        return None

    read_kw = dict(keep_default_na=False, dtype=str, encoding="latin1")
    dirty = pd.read_csv(dirty_path, **read_kw).map(value_normalizer)
    clean = pd.read_csv(clean_path, **read_kw).map(value_normalizer)
    corr = pd.read_csv(corr_path, **read_kw).map(value_normalizer)

    # Align column names (corrections may use dirty headers)
    corr.columns = dirty.columns
    if dirty.shape != clean.shape or dirty.shape != corr.shape:
        print(f"  Shape mismatch: dirty={dirty.shape} clean={clean.shape} corr={corr.shape}")
        return None

    # Vectorised: boolean masks over the entire DataFrame
    was_corrected = corr != dirty          # ZeroDCcorrection changed this cell
    was_error = dirty != clean             # cell was actually erroneous
    is_tp_mask = was_corrected & was_error & (corr == clean)
    is_fp_mask = was_corrected & ~is_tp_mask

    total_corrected = int(was_corrected.values.sum())
    total_tp = int(is_tp_mask.values.sum())

    merged_lookup = None
    if global_error_map is not None:
        merged_lookup = load_merged_source_lookup(table_path)
    legacy_error_map = None
    if global_error_map is None or merged_lookup is None:
        legacy_error_map = load_error_map(table_path)

    # Build a DataFrame of corrected cells with their (row, col) indices
    corrected_rows, corrected_cols = np.where(was_corrected.values)
    if len(corrected_rows) == 0:
        return {
            "per_type": {},
            "total_corrected": total_corrected,
            "total_tp": total_tp,
        }

    if global_error_map is not None and merged_lookup is not None:
        tp_flat = is_tp_mask.values[corrected_rows, corrected_cols]
        per_type: dict = {}
        for r, c, tp in zip(corrected_rows.tolist(), corrected_cols.tolist(), tp_flat.tolist()):
            src = merged_lookup.get((int(r), int(c)))
            if src is None:
                et = "NOT_IN_MAP"
            else:
                et = global_error_map.get((src[0], src[1], src[2]), "NOT_IN_MAP")
            stats = per_type.setdefault(et, {"tp": 0, "fp": 0})
            if tp:
                stats["tp"] += 1
            else:
                stats["fp"] += 1
        return {
            "per_type": per_type,
            "total_corrected": total_corrected,
            "total_tp": total_tp,
        }

    if legacy_error_map is None:
        return {
            "per_type": {},
            "total_corrected": total_corrected,
            "total_tp": total_tp,
        }

    tp_flat = is_tp_mask.values[corrected_rows, corrected_cols]

    per_type = {}
    for r, c, tp in zip(corrected_rows.tolist(), corrected_cols.tolist(), tp_flat.tolist()):
        et = legacy_error_map.get((r, c), "NOT_IN_MAP")
        stats = per_type.setdefault(et, {"tp": 0, "fp": 0})
        if tp:
            stats["tp"] += 1
        else:
            stats["fp"] += 1

    return {
        "per_type": per_type,
        "total_corrected": total_corrected,
        "total_tp": total_tp,
    }


def get_error_type_totals(tables_base_path):
    """
    Count total erroneous cells per error type across the lake (from error_map.csv).
    Returns {error_type: count}.
    """
    totals = {}
    for table in os.listdir(tables_base_path):
        if table.startswith("union_summary") or table.endswith(".json"):
            continue
        emap_path = os.path.join(tables_base_path, table, "error_map.csv")
        if not os.path.exists(emap_path):
            continue
        df = pd.read_csv(emap_path, keep_default_na=False, dtype=str, encoding="latin1")
        if df.empty or "error_type" not in df.columns:
            continue
        for et in df["error_type"].dropna():
            et = str(et).strip()
            if et:
                totals[et] = totals.get(et, 0) + 1
    return totals


def main():
    print(f"Tables path : {TABLES_PATH}")
    print(f"Results path: {RESULTS_PATH}")

    global_error_map = None
    if os.path.isfile(ERROR_MAP_ALL_PATH):
        global_error_map, error_type_totals = load_consolidated_error_map(ERROR_MAP_ALL_PATH)
        if global_error_map:
            print(
                f"Using consolidated error map: {ERROR_MAP_ALL_PATH} "
                f"({len(global_error_map)} keyed cells)"
            )
        else:
            print(
                f"WARNING: could not build map from {ERROR_MAP_ALL_PATH}; "
                "falling back to per-table error_map.csv"
            )
            error_type_totals = get_error_type_totals(TABLES_PATH)
    else:
        print(f"No {ERROR_MAP_ALL_PATH}; using per-table error_map.csv if present")
        error_type_totals = get_error_type_totals(TABLES_PATH)
    print(f"\nTotal errors per type across the lake:")
    for et, cnt in sorted(error_type_totals.items()):
        print(f"  {et}: {cnt}")

    per_table_rows = []

    for dataset in sorted(os.listdir(RESULTS_PATH)):
        dataset_results_dir = os.path.join(RESULTS_PATH, dataset)
        if not os.path.isdir(dataset_results_dir):
            continue
        # Skip summary CSVs at the top level
        if dataset.endswith(".csv"):
            continue

        table_path = os.path.join(TABLES_PATH, dataset)
        if not os.path.isdir(table_path):
            print(f"  WARNING: table path not found for {dataset}, skipping")
            continue

        for run_dir in sorted(os.listdir(dataset_results_dir)):
            if not run_dir.startswith("human_repair_"):
                continue
            run_path = os.path.join(dataset_results_dir, run_dir)
            if not os.path.isdir(run_path):
                continue

            try:
                human_repair_num = int(run_dir.replace("human_repair_", ""))
            except ValueError:
                continue

            result = evaluate_table_result(table_path, run_path, global_error_map=global_error_map)
            if result is None:
                print(f"  SKIP: {dataset}/{run_dir}")
                continue

            for et, stats in result["per_type"].items():
                per_table_rows.append(
                    {
                        "dataset": dataset,
                        "human_repair_num": human_repair_num,
                        "error_type": et,
                        "tp": stats["tp"],
                        "fp": stats["fp"],
                        "total_corrected_of_type": stats["tp"] + stats["fp"],
                        "total_errors_of_type": error_type_totals.get(et, 0),
                    }
                )

            print(
                f"  {dataset} / human_repair={human_repair_num:2d} : "
                f"corrected={result['total_corrected']}  tp={result['total_tp']}"
            )

    if not per_table_rows:
        print("\nNo results found.")
        return

    per_table_df = pd.DataFrame(per_table_rows)

    # Save per-table breakdown
    per_table_out = os.path.join(RESULTS_PATH, "zerodccorrection_per_type_per_table.csv")
    per_table_df.to_csv(per_table_out, index=False)
    print(f"\nPer-table results saved to: {per_table_out}")

    # Aggregate across all tables per (human_repair_num, error_type)
    summary_rows = []
    for (hrn, et), grp in per_table_df.groupby(["human_repair_num", "error_type"]):
        tp_total = grp["tp"].sum()
        fp_total = grp["fp"].sum()
        corrected_total = grp["total_corrected_of_type"].sum()
        fn_total = error_type_totals.get(et, 0) - tp_total

        precision = tp_total / corrected_total if corrected_total > 0 else 0.0
        recall = tp_total / error_type_totals.get(et, 1) if error_type_totals.get(et, 0) > 0 else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

        summary_rows.append(
            {
                "human_repair_num": hrn,
                "error_type": et,
                "tp": int(tp_total),
                "fp": int(fp_total),
                "fn": int(fn_total),
                "total_corrected": int(corrected_total),
                "total_errors_in_lake": error_type_totals.get(et, 0),
                "precision": round(precision, 4),
                "recall": round(recall, 4),
                "f1": round(f1, 4),
            }
        )

    summary_df = pd.DataFrame(summary_rows).sort_values(["human_repair_num", "error_type"])

    summary_out = os.path.join(RESULTS_PATH, "zerodccorrection_per_type_summary.csv")
    summary_df.to_csv(summary_out, index=False)
    print(f"Per-type summary saved to: {summary_out}")

    print("\n" + "=" * 70)
    print("PER-ERROR-TYPE METRICS (aggregated across all tables)")
    print("=" * 70)
    print(summary_df.to_string(index=False))


if __name__ == "__main__":
    main()
