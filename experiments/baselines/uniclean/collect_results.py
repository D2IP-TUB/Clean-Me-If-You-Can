#!/usr/bin/env python3
"""
collect_results.py  —  Aggregate UniClean run results into a single CSV.

For every completed run directory under results_experiments/uniclean/ it reads:
  - run_config.json        -> dataset, slice, error_rate, runtime_seconds, peak_memory_mb
  - *_total_evaluation.txt -> det/cor precision, recall, F1

Runs where timed_out=true or where the evaluation file is missing are excluded.
Multiple repetitions for the same dataset are averaged.

Output: results_summary.csv (or --output path)

Usage:
  python collect_results.py
  python collect_results.py --results-dir ./results_experiments/uniclean --output summary.csv
"""

import argparse
import csv
import json
import os
import re
import sys
from collections import defaultdict

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_RESULTS_DIR = os.path.join(THIS_DIR, "results_experiments", "uniclean")
DEFAULT_OUTPUT      = os.path.join(THIS_DIR, "results_summary.csv")

FIELDNAMES = [
    "dataset", "slice", "error_rate", "n_iterations",
    "det_precision", "det_recall", "det_f1",
    "corr_precision", "corr_recall", "corr_f1",
    "runtime_seconds", "peak_memory_mb",
]

# Patterns for evaluation file lines
_PATTERNS = {
    "corr_precision": re.compile(r"Correction Precision:\s*([\d.eE+\-]+)"),
    "corr_recall":    re.compile(r"Correction Recall:\s*([\d.eE+\-]+)"),
    "corr_f1":        re.compile(r"Correction F1:\s*([\d.eE+\-]+)"),
    "det_precision":  re.compile(r"Detection Precision:\s*([\d.eE+\-]+)"),
    "det_recall":     re.compile(r"Detection Recall:\s*([\d.eE+\-]+)"),
    "det_f1":         re.compile(r"Detection F1:\s*([\d.eE+\-]+)"),
}


def parse_eval_file(path: str) -> dict:
    metrics = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            for key, pat in _PATTERNS.items():
                m = pat.search(line)
                if m:
                    metrics[key] = float(m.group(1))
    return metrics


def parse_run_dir(run_dir: str) -> dict | None:
    config_path = os.path.join(run_dir, "run_config.json")
    if not os.path.exists(config_path):
        return None

    with open(config_path, encoding="utf-8") as f:
        cfg = json.load(f)

    if cfg.get("timed_out") or cfg.get("oom"):
        return None

    eval_files = [
        f for f in os.listdir(run_dir)
        if f.endswith("_total_evaluation.txt")
    ]
    if not eval_files:
        return None

    eval_path = os.path.join(run_dir, eval_files[0])
    metrics = parse_eval_file(eval_path)
    if len(metrics) < 6:
        return None  # incomplete evaluation

    return {
        "dataset":         cfg.get("dataset", ""),
        "slice":           cfg.get("slice",   ""),
        "error_rate":      cfg.get("error_rate", ""),
        "runtime_seconds": cfg.get("runtime_seconds", 0.0),
        "peak_memory_mb":  cfg.get("peak_memory_mb", 0.0),
        **metrics,
    }


def collect(results_dir: str) -> list[dict]:
    if not os.path.isdir(results_dir):
        print(f"Results directory not found: {results_dir}", file=sys.stderr)
        return []

    # Group rows by dataset key so we can average across repetitions
    groups: dict[str, list[dict]] = defaultdict(list)
    for name in sorted(os.listdir(results_dir)):
        run_dir = os.path.join(results_dir, name)
        if not os.path.isdir(run_dir):
            continue
        row = parse_run_dir(run_dir)
        if row is None:
            continue
        key = (row["dataset"], row["slice"], str(row["error_rate"]))
        groups[key].append(row)

    # Average numeric columns across repetitions
    numeric = [
        "det_precision", "det_recall", "det_f1",
        "corr_precision", "corr_recall", "corr_f1",
        "runtime_seconds", "peak_memory_mb",
    ]
    summary = []
    for (dataset, slice_, error_rate), rows in sorted(groups.items()):
        n = len(rows)
        avg = {col: sum(r[col] for r in rows) / n for col in numeric}
        summary.append({
            "dataset":         dataset,
            "slice":           slice_,
            "error_rate":      error_rate,
            "n_iterations":    n,
            **avg,
        })
    return summary


def main():
    parser = argparse.ArgumentParser(
        description="Aggregate UniClean run results into a single CSV.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--results-dir", default=DEFAULT_RESULTS_DIR,
                        help="Path to the uniclean results directory.")
    parser.add_argument("--output", default=DEFAULT_OUTPUT,
                        help="Output CSV path.")
    args = parser.parse_args()

    rows = collect(args.results_dir)
    if not rows:
        print("No completed runs found.", file=sys.stderr)
        sys.exit(1)

    with open(args.output, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {len(rows)} row(s) to {args.output}")
    # Also print to stdout for quick inspection
    with open(args.output, encoding="utf-8") as f:
        print(f.read())


if __name__ == "__main__":
    main()
