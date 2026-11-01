"""
run_nominatim.py — Nominatim/OSM detection + correction baseline.

For each dirty row, structured-search Nominatim (same query fields as dataset
creation), map the hit with pack extraction rules, then:

  detection  : Nominatim value present and != dirty  → error
  correction : Nominatim value present               → proposed repair
  abstain    : no hit / missing field                → not predicted (FN if oracle error)

Usage:
  # One dirty/clean pair
  python run_nominatim.py --dirty DIRTY.csv --clean CLEAN.csv --out-dir OUT

  # Harness sweep
  python run_nominatim.py --mode effectiveness --config config.json \\
      --datasets-dir ./experiment_datasets --results-dir ./results
"""

import argparse
import json
import os
import sys

import pandas as pd

EXPERIMENTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, EXPERIMENTS_DIR)

from evaluate import evaluate, record_runtime
from nominatim_baseline import detect_and_correct, query_rows
from runner_utils import (
    PeakMemoryTracker,
    get_memory_limit_mb,
    init_log_file,
    list_effectiveness_datasets,
    list_runtime_datasets,
    load_config,
    log,
    log_error,
    setup_run_dir,
)


def _rows_from_df(df: pd.DataFrame) -> list:
    return df.to_dict(orient="records")


def _load_or_query_features(dirty_rows, cache_path, nominatim_url, max_workers, timeout):
    cached = None
    if cache_path and os.path.exists(cache_path):
        with open(cache_path, encoding="utf-8") as f:
            loaded = json.load(f)
        if isinstance(loaded, list) and len(loaded) == len(dirty_rows):
            cached = loaded
            n_hit = sum(1 for f in cached if f is not None)
            log(f"  Loaded cache {n_hit}/{len(cached)} hits from {cache_path}")
        else:
            log(f"  Cache size mismatch ({len(loaded) if isinstance(loaded, list) else '?'} vs {len(dirty_rows)}); re-querying")

    features = query_rows(
        dirty_rows,
        nominatim_url=nominatim_url,
        max_workers=max_workers,
        timeout=timeout,
        log=log,
        existing=cached,
    )
    if cache_path:
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(features, f, ensure_ascii=False)
        log(f"  Wrote Nominatim cache: {cache_path}")
    return features


def run_one(
    dirty_path: str,
    clean_path: str,
    out_dir: str,
    cfg: dict,
    dataset_name: str = "",
    error_rate="",
    slice_name: str = "",
    mode: str = "effectiveness",
    n_records=None,
):
    sys_cfg = cfg.get("systems", {}).get("nominatim", {})
    nominatim_url = sys_cfg.get("nominatim_url", "http://127.0.0.1:9020")
    max_workers = int(sys_cfg.get("max_concurrent", 64))
    timeout = float(sys_cfg.get("timeout_seconds", 60.0))
    data_cols = cfg.get("dataset", {}).get("data_columns") or None

    os.makedirs(out_dir, exist_ok=True)
    dirty_df = pd.read_csv(dirty_path, dtype=str, keep_default_na=False)
    clean_df = pd.read_csv(clean_path, dtype=str, keep_default_na=False)
    col_names = [c for c in (data_cols or list(dirty_df.columns)) if c in dirty_df.columns]
    dirty_rows = _rows_from_df(dirty_df)

    cache_path = os.path.join(out_dir, "nominatim_features.json")
    tracker = PeakMemoryTracker(limit_mb=get_memory_limit_mb(cfg) if cfg.get("experiment") else None)
    n_hit = 0
    detected, corrected = {}, {}
    try:
        with tracker:
            features = _load_or_query_features(
                dirty_rows, cache_path, nominatim_url, max_workers, timeout
            )
            n_hit = sum(1 for f in features if f is not None)
            detected, corrected = detect_and_correct(dirty_rows, features, col_names)
    except Exception as e:
        log_error(f"Nominatim baseline failed on {dataset_name or dirty_path}: {e}")
        raise

    run_config = {
        "system": "nominatim",
        "dataset": dataset_name,
        "error_rate": error_rate,
        "slice": slice_name,
        "mode": mode,
        "nominatim_url": nominatim_url,
        "max_concurrent": max_workers,
        "n_rows": len(dirty_df),
        "n_nominatim_hits": n_hit,
        "n_nominatim_misses": len(dirty_df) - n_hit,
        "n_records": n_records if n_records is not None else len(dirty_df),
    }
    log(
        f"  hits={n_hit}/{len(dirty_df)}  detected={len(detected)}  "
        f"corrected={len(corrected)}  {tracker.elapsed:.1f}s"
    )

    if mode == "runtime":
        record_runtime(out_dir, run_config, tracker.elapsed, tracker.peak_mb)
    else:
        evaluate(
            dirty_df=dirty_df,
            clean_df=clean_df,
            detected_cells=detected,
            corrected_cells=corrected,
            labeled_rows=set(),
            out_dir=out_dir,
            run_config=run_config,
            runtime_seconds=tracker.elapsed,
            peak_memory_mb=tracker.peak_mb,
        )
    log(f"  -> {out_dir}")
    return out_dir


def run_nominatim_effectiveness(dataset: dict, cfg: dict, results_base: str, rep: int = 1):
    run_dir = setup_run_dir(results_base, "nominatim", dataset["name"])
    log(f"Nominatim | {dataset['name']} | rep={rep}")
    run_one(
        dirty_path=dataset["dirty"],
        clean_path=dataset["clean"],
        out_dir=run_dir,
        cfg=cfg,
        dataset_name=dataset["name"],
        error_rate=dataset.get("error_rate", ""),
        slice_name=dataset.get("slice", ""),
        mode="effectiveness",
    )


def run_nominatim_runtime(dataset: dict, cfg: dict, results_base: str):
    run_dir = setup_run_dir(results_base, "nominatim_runtime", dataset["name"])
    log(f"Nominatim runtime | {dataset['name']} | n={dataset.get('n_records')}")
    run_one(
        dirty_path=dataset["dirty"],
        clean_path=dataset["clean"],
        out_dir=run_dir,
        cfg=cfg,
        dataset_name=dataset["name"],
        mode="runtime",
        n_records=dataset.get("n_records"),
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["effectiveness", "runtime"])
    parser.add_argument("--config", default=os.path.join(EXPERIMENTS_DIR, "config.json"))
    parser.add_argument("--datasets-dir", default=os.path.join(EXPERIMENTS_DIR, "experiment_datasets"))
    parser.add_argument("--results-dir", default=os.path.join(EXPERIMENTS_DIR, "results"))
    parser.add_argument("--dirty", default=None, help="One-shot dirty CSV")
    parser.add_argument("--clean", default=None, help="One-shot clean CSV")
    parser.add_argument("--out-dir", default=None, help="One-shot output directory")
    parser.add_argument("--reps", type=int, default=None)
    parser.add_argument("--first-rep", type=int, default=1)
    parser.add_argument("--filter-datasets", default=None)
    args = parser.parse_args()

    cfg = load_config(args.config)
    os.makedirs(args.results_dir, exist_ok=True)

    if args.dirty:
        if not args.clean:
            parser.error("--dirty requires --clean")
        out_dir = args.out_dir or setup_run_dir(args.results_dir, "nominatim", "oneshot")
        init_log_file(os.path.join(out_dir, "nominatim.log"))
        run_one(
            dirty_path=args.dirty,
            clean_path=args.clean,
            out_dir=out_dir,
            cfg=cfg,
            dataset_name=os.path.basename(os.path.dirname(args.dirty)),
            mode="effectiveness",
        )
        return

    if not args.mode:
        parser.error("--mode is required unless --dirty/--clean is set")

    init_log_file(os.path.join(args.results_dir, f"nominatim_{args.mode}.log"))
    if not cfg.get("systems", {}).get("nominatim", {}).get("enabled", True):
        log("Nominatim disabled in config")
        return

    if args.mode == "effectiveness":
        n_reps = args.reps if args.reps is not None else cfg.get("experiment", {}).get("n_effectiveness_runs", 1)
        datasets = list_effectiveness_datasets(cfg, args.datasets_dir)
        if args.filter_datasets:
            filters = [f.strip() for f in args.filter_datasets.split(",") if f.strip()]
            datasets = [ds for ds in datasets if any(f in ds["name"] for f in filters)]
        last_rep = args.first_rep + n_reps - 1
        log(f"Found {len(datasets)} effectiveness datasets, repetitions {args.first_rep}-{last_rep}")
        for rep in range(args.first_rep, last_rep + 1):
            log(f"=== Effectiveness repetition {rep}/{last_rep} ===")
            for ds in datasets:
                run_nominatim_effectiveness(ds, cfg, args.results_dir, rep=rep)
    else:
        datasets = list_runtime_datasets(cfg, args.datasets_dir)
        if args.filter_datasets:
            filters = [f.strip() for f in args.filter_datasets.split(",") if f.strip()]
            datasets = [ds for ds in datasets if any(f in ds["name"] for f in filters)]
        for ds in datasets:
            run_nominatim_runtime(ds, cfg, args.results_dir)


if __name__ == "__main__":
    main()
