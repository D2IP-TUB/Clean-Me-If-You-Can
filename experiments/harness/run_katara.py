"""
run_katara.py — KATARA detection + correction baseline.

Uses the domain-specific KB at `baselines/katara/dominSpecific`. The algorithm is the
non-interactive SimplifiedPatternDiscovery path: type coverage > 0.2,
pair coverage >= 0.15, pair repairs from subject→object lookups.

Usage:
  # One dirty/clean pair
  python run_katara.py --dirty DIRTY.csv --clean CLEAN.csv --out-dir OUT

  # Harness sweep
  python run_katara.py --mode effectiveness --config config.json \\
      --datasets-dir ./experiment_datasets --results-dir ./results
"""

import argparse
import json
import os
import sys

import pandas as pd

HARNESS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HARNESS_DIR)

KATARA_DIR = os.path.normpath(
    os.path.join(HARNESS_DIR, "../baselines/katara")
)
sys.path.insert(0, KATARA_DIR)

from evaluate import evaluate, record_runtime  # noqa: E402
from katara_baseline import detect_and_correct, load_domain_specific_kb, remap_cells  # noqa: E402
from runner_utils import (  # noqa: E402
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

SYSTEM_NAME = "katara"
DEFAULT_KB = os.path.join(KATARA_DIR, "dominSpecific")


def _sys_cfg(cfg: dict) -> dict:
    return cfg.get("systems", {}).get("katara", {})


def _kb_dir(cfg: dict, override: str = None) -> str:
    if override:
        return os.path.abspath(override)
    rel = _sys_cfg(cfg).get("kb_dir", DEFAULT_KB)
    if os.path.isabs(rel):
        return rel
    return os.path.normpath(os.path.join(HARNESS_DIR, rel))


def _write_cells(out_dir: str, detected: dict, corrected: dict) -> None:
    payload = {
        "detected": {f"{i},{j}": v for (i, j), v in sorted(detected.items())},
        "corrected": {f"{i},{j}": v for (i, j), v in sorted(corrected.items())},
    }
    with open(os.path.join(out_dir, "katara_cells.json"), "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)


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
    kb_dir: str = None,
    repetition: int = 1,
):
    sys_cfg = _sys_cfg(cfg)
    type_coverage = float(sys_cfg.get("type_coverage", 0.2))
    pair_coverage = float(sys_cfg.get("pair_coverage", 0.15))
    ignore_case = bool(sys_cfg.get("ignore_case", True))
    data_cols = cfg.get("dataset", {}).get("data_columns") or None
    kb_path = _kb_dir(cfg, kb_dir)

    os.makedirs(out_dir, exist_ok=True)
    dirty_df = pd.read_csv(dirty_path, dtype=str, keep_default_na=False)
    clean_df = pd.read_csv(clean_path, dtype=str, keep_default_na=False)
    all_cols = list(dirty_df.columns)
    use_cols = [c for c in (data_cols or all_cols) if c in dirty_df.columns]
    if not use_cols:
        use_cols = all_cols
    col_index = [all_cols.index(c) for c in use_cols]
    rows = dirty_df[use_cols].astype(str).values.tolist()

    tracker = PeakMemoryTracker(limit_mb=get_memory_limit_mb(cfg) if cfg.get("experiment") else None)
    detected, corrected = {}, {}
    n_types = n_rels = 0
    try:
        with tracker:
            types, rels = load_domain_specific_kb(kb_path)
            n_types, n_rels = len(types), len(rels)
            local_det, local_cor = detect_and_correct(
                rows,
                types,
                rels,
                type_coverage=type_coverage,
                pair_coverage=pair_coverage,
                ignore_case=ignore_case,
            )
            detected = remap_cells(local_det, col_index)
            corrected = remap_cells(local_cor, col_index)
    except Exception as e:
        log_error(f"KATARA baseline failed on {dataset_name or dirty_path}: {e}")
        raise

    _write_cells(out_dir, detected, corrected)
    run_config = {
        "system": SYSTEM_NAME,
        "dataset": dataset_name,
        "error_rate": error_rate,
        "slice": slice_name,
        "mode": mode,
        "kb_dir": kb_path,
        "type_coverage": type_coverage,
        "pair_coverage": pair_coverage,
        "ignore_case": ignore_case,
        "n_rows": len(dirty_df),
        "n_types": n_types,
        "n_relations": n_rels,
        "n_detected": len(detected),
        "n_corrected": len(corrected),
        "n_records": n_records if n_records is not None else len(dirty_df),
        "repetition": repetition,
        "columns": use_cols,
    }
    log(
        f"  types={n_types} rels={n_rels}  detected={len(detected)}  "
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


def run_katara_effectiveness(dataset: dict, cfg: dict, results_base: str, rep: int = 1):
    run_dir = setup_run_dir(results_base, SYSTEM_NAME, dataset["name"])
    log(f"KATARA | {dataset['name']} | rep={rep}")
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


def run_katara_runtime(dataset: dict, cfg: dict, results_base: str, rep: int = 1):
    run_dir = setup_run_dir(results_base, f"{SYSTEM_NAME}_runtime", dataset["name"])
    log(f"KATARA runtime | {dataset['name']} | n={dataset.get('n_records')} | rep={rep}")
    run_one(
        dirty_path=dataset["dirty"],
        clean_path=dataset["clean"],
        out_dir=run_dir,
        cfg=cfg,
        dataset_name=dataset["name"],
        mode="runtime",
        n_records=dataset.get("n_records"),
        repetition=rep,
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["effectiveness", "runtime"])
    parser.add_argument("--config", default=os.path.join(HARNESS_DIR, "config.json"))
    parser.add_argument("--datasets-dir", default=os.path.join(HARNESS_DIR, "experiment_datasets"))
    parser.add_argument("--results-dir", default=os.path.join(HARNESS_DIR, "results"))
    parser.add_argument("--dirty", default=None, help="One-shot dirty CSV")
    parser.add_argument("--clean", default=None, help="One-shot clean CSV")
    parser.add_argument("--out-dir", default=None, help="One-shot output directory")
    parser.add_argument("--kb-dir", default=None, help="Override domain-specific KB directory")
    parser.add_argument("--reps", type=int, default=None)
    parser.add_argument("--first-rep", type=int, default=1)
    parser.add_argument("--filter-datasets", default=None)
    args = parser.parse_args()

    cfg = load_config(args.config)
    os.makedirs(args.results_dir, exist_ok=True)

    if args.dirty:
        if not args.clean:
            parser.error("--dirty requires --clean")
        out_dir = args.out_dir or setup_run_dir(args.results_dir, SYSTEM_NAME, "oneshot")
        init_log_file(os.path.join(out_dir, "katara.log"))
        run_one(
            dirty_path=args.dirty,
            clean_path=args.clean,
            out_dir=out_dir,
            cfg=cfg,
            dataset_name=os.path.basename(os.path.dirname(args.dirty)),
            mode="effectiveness",
            kb_dir=args.kb_dir,
        )
        return

    if not args.mode:
        parser.error("--mode is required unless --dirty/--clean is set")

    init_log_file(os.path.join(args.results_dir, f"katara_{args.mode}.log"))
    if not _sys_cfg(cfg).get("enabled", True):
        log("KATARA disabled in config")
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
                run_katara_effectiveness(ds, cfg, args.results_dir, rep=rep)
    else:
        datasets = list_runtime_datasets(cfg, args.datasets_dir)
        if args.filter_datasets:
            filters = [f.strip() for f in args.filter_datasets.split(",") if f.strip()]
            datasets = [ds for ds in datasets if any(f in ds["name"] for f in filters)]
        n_reps = args.reps if args.reps is not None else cfg.get("experiment", {}).get("n_runtime_runs", 1)
        last_rep = args.first_rep + n_reps - 1
        log(f"Found {len(datasets)} runtime datasets, repetitions {args.first_rep}-{last_rep}")
        for rep in range(args.first_rep, last_rep + 1):
            log(f"=== Runtime repetition {rep}/{last_rep} ===")
            for ds in datasets:
                run_katara_runtime(ds, cfg, args.results_dir, rep=rep)


if __name__ == "__main__":
    main()
