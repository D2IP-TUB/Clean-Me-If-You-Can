"""
collect_results.py — aggregate per-run summary.csv files into manuscript-format CSVs.

Reads all results/{system}/{dataset}_{ts}/summary.csv files and writes:
  {manuscript_results_dir}/effectiveness/{full,de,russia,poi_Library,poi_ShoppingCenter}/{system}.csv
  {manuscript_results_dir}/runtime/error_detection/{system}.csv
  {manuscript_results_dir}/runtime/error_correction/{system}.csv

Column schemas match what the LaTeX TikZ plots expect (derived from existing
manuscript CSVs).

Usage:
    python collect_results.py [--config config.json] [--results-dir ./results]
"""

import argparse
import json
import os
import sys

import pandas as pd

EXPERIMENTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, EXPERIMENTS_DIR)

from runner_utils import load_config, log, log_error

# Canonical slice ordering (also used as subdir names under effectiveness/)
SLICE_ORDER = ["full", "de", "russia", "poi_Library", "poi_ShoppingCenter"]

# Systems that have a detection phase and a separate correction phase
DETECTION_SYSTEMS = {"raha", "zerodc_detection"}
CORRECTION_SYSTEMS = {"baran"}
BOTH_SYSTEMS = {
    "datawig", "holoclean", "horizon", "uniclean", "glocks",
    "zerodccorrection", "zerodccorrection_zerodcprompts", "katara",
}

# Runtime-mode system names (the runners append _runtime suffix)
RUNTIME_SUFFIX = "_runtime"

# Manuscript effectiveness CSV columns
EFF_COLS_DET = [
    "error_rate", "dataset_name",
    "det_precision", "det_recall", "det_f1",
    "n_actual_errors", "n_detected", "n_labeled_rows",
    "runtime_seconds", "peak_memory_mb",
]
EFF_COLS_COR = [
    "error_rate", "dataset_name",
    "cor_precision", "cor_recall", "cor_f1",
    "det_f1",
    "n_actual_errors", "n_corrected", "n_labeled_rows",
    "runtime_seconds", "peak_memory_mb",
]

# Manuscript runtime CSV columns
RT_COLS = ["n_records", "runtime_seconds", "peak_memory_mb", "timed_out"]


def load_all_summaries(results_dir: str) -> pd.DataFrame:
    """Walk results_dir, load every summary.csv, return concatenated DataFrame."""
    rows = []
    if not os.path.isdir(results_dir):
        log_error(f"Results dir not found: {results_dir}")
        return pd.DataFrame()

    for system_dir in os.listdir(results_dir):
        system_path = os.path.join(results_dir, system_dir)
        if not os.path.isdir(system_path):
            continue
        for run_dir in os.listdir(system_path):
            run_path = os.path.join(system_path, run_dir)
            summary_csv = os.path.join(run_path, "summary.csv")
            if not os.path.exists(summary_csv):
                continue
            try:
                df = pd.read_csv(summary_csv, dtype=str)
                df["_run_dir"] = run_path
                df["_system_dir"] = system_dir
                rows.append(df)
            except Exception as e:
                log_error(f"Could not read {summary_csv}: {e}")

    if not rows:
        return pd.DataFrame()
    combined = pd.concat(rows, ignore_index=True)
    return combined


def _to_float(val, default=None):
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _slice_for_dataset(dataset_name: str) -> str:
    """Infer slice name from dataset name."""
    if dataset_name.startswith("poi_"):
        return dataset_name
    if dataset_name.startswith("de_"):
        return "de"
    if dataset_name.startswith("russia_"):
        return "russia"
    if dataset_name.startswith("full_"):
        return "full"
    return "full"


def write_csv(path: str, df: pd.DataFrame):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    df.to_csv(path, index=False)
    log(f"  Written: {path}  ({len(df)} rows)")


def collect_effectiveness(df: pd.DataFrame, manuscript_dir: str, cfg: dict):
    eff_df = df[df.get("mode", df["_system_dir"].str.replace(RUNTIME_SUFFIX, "")) != "runtime"].copy()
    # Filter to effectiveness runs only
    if "mode" in eff_df.columns:
        eff_df = eff_df[eff_df["mode"] == "effectiveness"]
    else:
        eff_df = eff_df[~eff_df["_system_dir"].str.endswith(RUNTIME_SUFFIX)]

    # Collect by slice and system
    for slice_name in SLICE_ORDER:
        slice_df = eff_df[eff_df["dataset"].apply(_slice_for_dataset) == slice_name]
        if slice_df.empty:
            continue
        for system in slice_df["system"].unique():
            if "_smoke" in str(system):  # smoke-test runs are never part of the results
                continue
            sys_df = slice_df[slice_df["system"] == system].copy()

            rows = []
            for _, row in sys_df.iterrows():
                r = {
                    "error_rate": _to_float(row.get("error_rate"), 0),
                    "dataset_name": row.get("dataset", ""),
                    "det_precision": _to_float(row.get("det_precision")),
                    "det_recall": _to_float(row.get("det_recall")),
                    "det_f1": _to_float(row.get("det_f1")),
                    "cor_precision": _to_float(row.get("cor_precision")),
                    "cor_recall": _to_float(row.get("cor_recall")),
                    "cor_f1": _to_float(row.get("cor_f1")),
                    "n_actual_errors": _to_float(row.get("n_actual_errors"), 0),
                    "n_detected": _to_float(row.get("n_detected"), 0),
                    "n_corrected": _to_float(row.get("n_corrected"), 0),
                    "n_labeled_rows": _to_float(row.get("n_labeled_rows"), 0),
                    "runtime_seconds": _to_float(row.get("runtime_seconds")),
                    "peak_memory_mb": _to_float(row.get("peak_memory_mb")),
                }
                rows.append(r)

            out_df = pd.DataFrame(rows)
            # Average across multiple runs for the same (error_rate, dataset_name)
            numeric_cols = [
                "det_precision", "det_recall", "det_f1",
                "cor_precision", "cor_recall", "cor_f1",
                "n_actual_errors", "n_detected", "n_corrected", "n_labeled_rows",
                "runtime_seconds", "peak_memory_mb",
            ]
            present = [c for c in numeric_cols if c in out_df.columns]
            out_df = (
                out_df.groupby(["error_rate", "dataset_name"], as_index=False)[present]
                .mean()
                .sort_values(["error_rate", "dataset_name"])
            )
            out_path = os.path.join(manuscript_dir, "effectiveness", slice_name, f"{system}.csv")
            write_csv(out_path, out_df)


def collect_runtime(df: pd.DataFrame, manuscript_dir: str, cfg: dict):
    rt_df = df.copy()
    if "mode" in rt_df.columns:
        rt_df = rt_df[rt_df["mode"] == "runtime"]
    else:
        rt_df = rt_df[rt_df["_system_dir"].str.endswith(RUNTIME_SUFFIX)]

    # Canonical system name: strip _runtime suffix
    rt_df["system_clean"] = rt_df["system"].str.replace(r"_runtime$", "", regex=True)

    # Derive n_records from dataset name (e.g. "full_10000")
    def _n_records(row):
        try:
            return int(str(row.get("dataset", "")).rsplit("_", 1)[-1])
        except ValueError:
            return -1

    rt_df["n_records_num"] = rt_df.apply(_n_records, axis=1)

    for system in rt_df["system_clean"].unique():
        sys_df = rt_df[rt_df["system_clean"] == system].copy()
        rows = []
        for _, row in sys_df.iterrows():
            # n_records: prefer explicit field written by record_runtime, fall back to parsed name
            n_rec = (
                _to_float(row.get("n_records")) or
                _to_float(row.get("n_rows")) or
                _to_float(row.get("n_records_num")) or -1
            )
            rows.append({
                "n_records": int(n_rec),
                "runtime_seconds": _to_float(row.get("runtime_seconds")),
                "peak_memory_mb": _to_float(row.get("peak_memory_mb")),
                "timed_out": row.get("timed_out", "False"),
            })
        out_df = pd.DataFrame(rows)
        # Average across multiple runs for the same dataset size
        out_df = (
            out_df.groupby("n_records", as_index=False)
            .agg({"runtime_seconds": "mean", "peak_memory_mb": "mean", "timed_out": "first"})
            .sort_values("n_records")
        )

        # Detection systems (raha + both)
        if system in DETECTION_SYSTEMS | BOTH_SYSTEMS:
            path = os.path.join(manuscript_dir, "runtime", "error_detection", f"{system}.csv")
            write_csv(path, out_df[RT_COLS])

        # Correction systems (baran + both)
        if system in CORRECTION_SYSTEMS | BOTH_SYSTEMS:
            path = os.path.join(manuscript_dir, "runtime", "error_correction", f"{system}.csv")
            write_csv(path, out_df[RT_COLS])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=os.path.join(EXPERIMENTS_DIR, "config.json"))
    parser.add_argument("--results-dir", default=os.path.join(EXPERIMENTS_DIR, "results"))
    args = parser.parse_args()

    cfg = load_config(args.config)
    manuscript_dir = os.path.normpath(
        os.path.join(EXPERIMENTS_DIR, cfg["paths"]["manuscript_results_dir"])
    )

    results_dir = args.results_dir
    log(f"Loading summaries from: {results_dir}")
    df = load_all_summaries(results_dir)

    if df.empty:
        log("No summary files found. Nothing to collect.")
        return

    log(f"Loaded {len(df)} run summaries")
    collect_effectiveness(df, manuscript_dir, cfg)
    collect_runtime(df, manuscript_dir, cfg)
    log("Done.")


if __name__ == "__main__":
    main()
