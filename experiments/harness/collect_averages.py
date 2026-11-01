"""
Average scored effectiveness runs into the paper table schema:

  dataset,slice,error_rate,n_iterations,det_precision,det_recall,det_f1,
  corr_precision,corr_recall,corr_f1,runtime_seconds,peak_memory_mb

Skips smoke dirs, failed/timeout runs with no F1, and runtime-mode summaries.
"""

import argparse
import csv
import json
import os
import re
from collections import defaultdict

EXPERIMENTS_DIR = os.path.dirname(os.path.abspath(__file__))

OUT_COLS = [
    "dataset", "slice", "error_rate", "n_iterations",
    "det_precision", "det_recall", "det_f1",
    "corr_precision", "corr_recall", "corr_f1",
    "runtime_seconds", "peak_memory_mb",
]

SKIP_DIR = {"_failed_attempts", "_stopped_cased_input", "_stopped_old_rules", "_averages"}


def _to_float(val):
    if val is None or val == "":
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _short_dataset(name: str, slice_name: str, error_rate) -> str:
    if name.startswith("full_sample_full_"):
        return f"full_{name.rsplit('_', 1)[-1]}"
    if name.startswith("russia_sample_"):
        return f"russia_{name.rsplit('_', 1)[-1]}"
    if name.startswith("de_"):
        return name
    m = re.search(r"(\d+\.\d+)$", name or "")
    if m and slice_name:
        return f"{slice_name}_{m.group(1)}"
    return name or ""


def _slice_of(name: str, cfg_slice: str) -> str:
    if cfg_slice:
        return cfg_slice
    if name.startswith("russia_"):
        return "russia"
    if name.startswith("de_"):
        return "de"
    if name.startswith("poi_Library"):
        return "poi_Library"
    if name.startswith("poi_ShoppingCenter"):
        return "poi_ShoppingCenter"
    return "full"


def load_scored_runs(results_dir: str):
    rows = []
    for system_dir in sorted(os.listdir(results_dir)):
        if system_dir in SKIP_DIR or "smoke" in system_dir:
            continue
        system_path = os.path.join(results_dir, system_dir)
        if not os.path.isdir(system_path):
            continue
        for run_name in sorted(os.listdir(system_path)):
            run_path = os.path.join(system_path, run_name)
            summary_csv = os.path.join(run_path, "summary.csv")
            if not os.path.isfile(summary_csv):
                continue
            cfg = {}
            rc = os.path.join(run_path, "run_config.json")
            if os.path.isfile(rc):
                with open(rc, encoding="utf-8") as f:
                    cfg = json.load(f)
            if cfg.get("mode") == "runtime":
                continue
            with open(summary_csv, encoding="utf-8") as f:
                recs = list(csv.DictReader(f))
            if not recs:
                continue
            rec = recs[-1]
            det_f1 = _to_float(rec.get("det_f1"))
            if det_f1 is None:
                continue
            if cfg.get("timed_out") or cfg.get("failed"):
                continue
            dataset = rec.get("dataset") or cfg.get("dataset") or ""
            slice_name = _slice_of(dataset, str(cfg.get("slice") or rec.get("slice") or ""))
            error_rate = _to_float(rec.get("error_rate") if rec.get("error_rate") not in ("", None) else cfg.get("error_rate"))
            rows.append({
                "system": rec.get("system") or cfg.get("system") or system_dir,
                "system_dir": system_dir,
                "dataset_raw": dataset,
                "dataset": _short_dataset(dataset, slice_name, error_rate),
                "slice": slice_name,
                "error_rate": error_rate,
                "det_precision": _to_float(rec.get("det_precision")),
                "det_recall": _to_float(rec.get("det_recall")),
                "det_f1": det_f1,
                "corr_precision": _to_float(rec.get("cor_precision")),
                "corr_recall": _to_float(rec.get("cor_recall")),
                "corr_f1": _to_float(rec.get("cor_f1")),
                "runtime_seconds": _to_float(rec.get("runtime_seconds")),
                "peak_memory_mb": _to_float(rec.get("peak_memory_mb")),
            })
    return rows


def average_groups(rows):
    groups = defaultdict(list)
    for r in rows:
        key = (r["system"], r["dataset"], r["slice"], r["error_rate"])
        groups[key].append(r)
    out = []
    metric_keys = [
        "det_precision", "det_recall", "det_f1",
        "corr_precision", "corr_recall", "corr_f1",
        "runtime_seconds", "peak_memory_mb",
    ]
    for (system, dataset, slice_name, error_rate), recs in groups.items():
        avg = {
            "system": system,
            "dataset": dataset,
            "slice": slice_name,
            "error_rate": error_rate,
            "n_iterations": len(recs),
        }
        for k in metric_keys:
            vals = [r[k] for r in recs if r[k] is not None]
            avg[k] = (sum(vals) / len(vals)) if vals else None
        out.append(avg)
    out.sort(key=lambda r: (r["system"], r["slice"], r["error_rate"] if r["error_rate"] is not None else 99, r["dataset"]))
    return out


def _fmt(val, ints=False):
    if val is None:
        return ""
    if ints:
        return str(int(val))
    return repr(val) if isinstance(val, float) else str(val)


def write_csv(path, rows, include_system=False):
    cols = (["system"] + OUT_COLS) if include_system else OUT_COLS
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            rec = dict(r)
            rec["n_iterations"] = rec["n_iterations"]
            w.writerow({c: "" if rec.get(c) is None else rec.get(c) for c in cols})


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--results-dir", default=os.path.join(EXPERIMENTS_DIR, "results"))
    p.add_argument("--out-dir", default=os.path.join(EXPERIMENTS_DIR, "results", "_averages"))
    args = p.parse_args()

    rows = load_scored_runs(args.results_dir)
    avgs = average_groups(rows)
    write_csv(os.path.join(args.out_dir, "all_systems.csv"), avgs, include_system=True)
    by_sys = defaultdict(list)
    for r in avgs:
        by_sys[r["system"]].append(r)
    for system, recs in by_sys.items():
        write_csv(os.path.join(args.out_dir, f"{system}.csv"), recs)
    print(f"Wrote {len(avgs)} averaged rows for {len(by_sys)} systems -> {args.out_dir}")
    for system, recs in sorted(by_sys.items()):
        ns = sorted({r["n_iterations"] for r in recs})
        print(f"  {system:24} datasets={len(recs)} n_iterations={ns}")


if __name__ == "__main__":
    main()
