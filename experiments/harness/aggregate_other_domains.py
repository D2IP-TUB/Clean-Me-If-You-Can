#!/usr/bin/env python3
"""
aggregate_other_domains.py — effectiveness CSVs (avg over runs).

For each system under results_other_domains/, load healthy summary.csv runs,
keep up to --max-runs (default 3) most recent per (system, dataset), average
metrics, and write one CSV per (system, slice):

  {out_dir}/{system}_{slice}.csv   e.g. raha_books.csv, glocks_movies.csv

Schema:
  system,dataset,slice,error_rate,n_iterations,det_precision,det_recall,det_f1,
  corr_precision,corr_recall,corr_f1,runtime_seconds,peak_memory_mb

Usage:
  python aggregate_other_domains.py \\
      --results-dir ./results_other_domains \\
      --out-dir ../manuscript_results_other_domains/effectiveness
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import pandas as pd

EXPERIMENTS_DIR = Path(__file__).resolve().parent

METRIC_COLS = [
    "det_precision",
    "det_recall",
    "det_f1",
    "cor_precision",
    "cor_recall",
    "cor_f1",
    "runtime_seconds",
    "peak_memory_mb",
]

OUT_COLS = [
    "system",
    "dataset",
    "slice",
    "error_rate",
    "n_iterations",
    "det_precision",
    "det_recall",
    "det_f1",
    "corr_precision",
    "corr_recall",
    "corr_f1",
    "runtime_seconds",
    "peak_memory_mb",
]

SYSTEM_ORDER = [
    "raha",
    "baran",
    "datawig",
    "holoclean",
    "horizon",
    "uniclean",
    "glocks",
    "zerodccorrection",
]

# Skip non-system dirs / runtime suffixes
SKIP_DIR_PREFIXES = ("_",)
SKIP_DIR_SUFFIXES = ("_runtime",)


def _dataset_stem(run_dir_name: str) -> str:
    return re.sub(r"_\d{8}_\d{6}$", "", run_dir_name)


def _infer_slice(dataset: str) -> str:
    if dataset.startswith("books_"):
        return "books"
    if dataset.startswith("movies_"):
        return "movies"
    if dataset.startswith("de_"):
        return "de"
    if dataset.startswith("russia_"):
        return "russia"
    if dataset.startswith("full_"):
        return "full"
    if dataset.startswith("poi_"):
        # poi_Library_sample_... → poi_Library
        parts = dataset.split("_")
        if len(parts) >= 2:
            return f"{parts[0]}_{parts[1]}"
        return dataset
    return ""


def _run_ok(run_dir: Path, summary_row: dict) -> bool:
    """Exclude timed-out / failed / empty (no-op) runs."""
    cfg_path = run_dir / "run_config.json"
    if cfg_path.exists():
        try:
            cfg = json.loads(cfg_path.read_text())
            if cfg.get("timed_out") is True or cfg.get("failed") is True:
                return False
        except Exception:
            pass
    # API-key / crash stubs often write summary with zero detections & corrections
    try:
        n_det = float(summary_row.get("n_detected") or 0)
        n_cor = float(summary_row.get("n_corrected") or 0)
    except (TypeError, ValueError):
        n_det, n_cor = 0.0, 0.0
    if n_det == 0.0 and n_cor == 0.0:
        return False
    return True


def _load_system_runs(system_dir: Path, system: str) -> pd.DataFrame:
    rows = []
    for run_dir in sorted(system_dir.iterdir()):
        if not run_dir.is_dir():
            continue
        summary = run_dir / "summary.csv"
        if not summary.exists():
            continue
        try:
            df = pd.read_csv(summary)
        except Exception as exc:
            print(f"  skip {summary}: {exc}", file=sys.stderr)
            continue
        if df.empty:
            continue
        row = df.iloc[0].to_dict()
        if not _run_ok(run_dir, row):
            continue
        dataset = str(row.get("dataset") or _dataset_stem(run_dir.name))
        row["system"] = system
        row["dataset"] = dataset
        row["slice"] = _infer_slice(dataset)
        row["_run_dir"] = str(run_dir)
        row["_mtime"] = run_dir.stat().st_mtime
        rows.append(row)
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows)


def aggregate_runs(df: pd.DataFrame, max_runs: int) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=OUT_COLS)

    for col in METRIC_COLS + ["error_rate"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    if "timestamp" in df.columns:
        df["_ts"] = pd.to_datetime(df["timestamp"], errors="coerce")
    else:
        df["_ts"] = pd.NaT
    df = df.sort_values(
        ["system", "dataset", "_ts", "_mtime"],
        ascending=[True, True, False, False],
    )

    out_rows = []
    for (system, dataset), g in df.groupby(["system", "dataset"], sort=True):
        g = g.head(max_runs)
        n = len(g)
        slice_name = g["slice"].iloc[0]
        err = g["error_rate"].dropna()
        error_rate = float(err.iloc[0]) if len(err) else None
        means = {c: float(g[c].mean()) if c in g.columns else None for c in METRIC_COLS}
        out_rows.append(
            {
                "system": system,
                "dataset": dataset,
                "slice": slice_name,
                "error_rate": error_rate,
                "n_iterations": n,
                "det_precision": means["det_precision"],
                "det_recall": means["det_recall"],
                "det_f1": means["det_f1"],
                "corr_precision": means["cor_precision"],
                "corr_recall": means["cor_recall"],
                "corr_f1": means["cor_f1"],
                "runtime_seconds": means["runtime_seconds"],
                "peak_memory_mb": means["peak_memory_mb"],
            }
        )
    out = pd.DataFrame(out_rows, columns=OUT_COLS)
    sys_rank = {s: i for i, s in enumerate(SYSTEM_ORDER)}
    out["_sys_rank"] = out["system"].map(lambda s: sys_rank.get(s, 999))
    out = out.sort_values(
        ["_sys_rank", "system", "error_rate", "dataset"]
    ).drop(columns=["_sys_rank"]).reset_index(drop=True)
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--results-dir",
        default=str(EXPERIMENTS_DIR / "results_other_domains"),
    )
    parser.add_argument(
        "--out-dir",
        default=str(
            EXPERIMENTS_DIR.parent / "manuscript_results_other_domains" / "effectiveness"
        ),
    )
    parser.add_argument(
        "--max-runs",
        type=int,
        default=3,
        help="Max most-recent healthy runs to average per dataset (default 3)",
    )
    parser.add_argument(
        "--systems",
        nargs="+",
        default=None,
        help="Only these systems (default: all with summaries)",
    )
    args = parser.parse_args()

    results_dir = Path(args.results_dir)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if not results_dir.is_dir():
        print(f"Results dir not found: {results_dir}", file=sys.stderr)
        sys.exit(1)

    systems = sorted(
        p.name
        for p in results_dir.iterdir()
        if p.is_dir()
        and not p.name.startswith(SKIP_DIR_PREFIXES)
        and not p.name.endswith(SKIP_DIR_SUFFIXES)
    )
    if args.systems:
        wanted = set(args.systems)
        systems = [s for s in systems if s in wanted]

    frames = []
    for system in systems:
        runs = _load_system_runs(results_dir / system, system)
        if runs.empty:
            print(f"{system}: no healthy summaries — skipped")
            continue
        frames.append(runs)
        print(f"{system}: {len(runs)} healthy run summaries")

    if not frames:
        print("No data to aggregate", file=sys.stderr)
        sys.exit(1)

    all_runs = pd.concat(frames, ignore_index=True)
    agg = aggregate_runs(all_runs, max_runs=args.max_runs)

    # Clean previous layouts
    for old in out_dir.glob("*.csv"):
        old.unlink()
    for sub in ("by_slice", "by_system"):
        d = out_dir / sub
        if d.is_dir():
            for old in d.glob("*.csv"):
                old.unlink()

    written = []
    for (system, slice_name), g in agg.groupby(["system", "slice"], sort=False):
        out_path = out_dir / f"{system}_{slice_name}.csv"
        g.to_csv(out_path, index=False, float_format="%.6f")
        print(f"{system}_{slice_name}: {len(g)} rows -> {out_path}")
        written.append(out_path)

    print(f"Done: {len(written)} CSV(s) in {out_dir}")


if __name__ == "__main__":
    main()
