"""
run_holoclean.py — run HoloClean detection + correction experiments.

HoloClean pipeline per dataset:
  1. Create a fresh HoloClean session
  2. Load dirty data
  3. Load denial constraints (FDs_address.txt)
  4. Detect errors
  5. Repair
  6. Export repaired CSV
  7. Diff dirty vs repaired → evaluate()

Requires PostgreSQL running with holocleanuser / holocleandb configured.
All DB parameters are read from config.json.
"""

import argparse
import copy
import os
import sys
import tempfile

import pandas as pd

EXPERIMENTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, EXPERIMENTS_DIR)

HOLOCLEAN_DIR = os.path.normpath(os.path.join(EXPERIMENTS_DIR, "../baselines/holoclean/holoclean"))
sys.path.insert(0, HOLOCLEAN_DIR)

from runner_utils import (
    load_config, list_effectiveness_datasets, list_runtime_datasets,
    setup_run_dir, PeakMemoryTracker, purge_holoclean_db, log, log_error,
    get_memory_limit_mb, init_log_file,
)
from evaluate import evaluate, record_runtime, diff_repaired

_HOLOCLEAN_FDS_FALLBACK = os.path.normpath(
    os.path.join(EXPERIMENTS_DIR, "../rules/fds/fds_full_full_holoclean.txt")
)


def _holoclean_fds_path(dataset_name: str, fds_dir: str) -> str:
    """Return FD file for dataset, mapping any subset to its canonical full-dataset FDs."""
    if dataset_name.startswith("de_"):
        canonical = "de_full"
    elif dataset_name.startswith("full_"):
        canonical = "full_full"
    elif dataset_name.startswith("russia_"):
        canonical = "russia_full"
    else:
        canonical = dataset_name  # poi_Library, poi_ShoppingCenter, etc.
    per_dataset = os.path.join(fds_dir, f"fds_{canonical}_holoclean.txt")
    if os.path.exists(per_dataset):
        return per_dataset
    return _HOLOCLEAN_FDS_FALLBACK


def _run_holoclean_session(dirty_path: str, dataset_name: str, fds_path: str, sys_cfg: dict):
    """
    Runs a full HoloClean pipeline on dirty_path.
    Returns repaired DataFrame or None on failure.
    """
    import holoclean
    from holoclean.detect import NullDetector, ViolationDetector
    from holoclean.repair.featurize import OccurAttrFeaturizer, FreqFeaturizer, ConstraintFeaturizer

    db_cfg = sys_cfg["db"]
    hc = holoclean.HoloClean(
        db_name=db_cfg["db_name"],
        db_user=db_cfg["db_user"],
        db_pwd=os.environ.get(db_cfg["db_pwd_env"], ""),
        db_host=db_cfg.get("db_host", "localhost"),
        db_port=db_cfg.get("db_port", 5432),
        threads=sys_cfg.get("threads", 4),
        timeout=sys_cfg.get("timeout", 3 * 60),
        verbose=False,
    ).session

    hc.load_data(dataset_name, dirty_path)
    hc.load_dcs(fds_path)
    hc.ds.set_constraints(hc.get_dcs())

    detectors = [NullDetector(), ViolationDetector()]
    hc.detect_errors(detectors)

    hc.setup_domain()
    featurizers = [
        OccurAttrFeaturizer(),
        FreqFeaturizer(),
        ConstraintFeaturizer(),
    ]
    hc.repair_errors(featurizers)

    repaired_df = hc.ds.repaired_data
    return repaired_df


def run_holoclean_effectiveness(dataset: dict, cfg: dict, results_base: str, fds_dir: str, rep: int = 1):
    sys_cfg = cfg["systems"]["holoclean"]
    time_limit = cfg["experiment"]["time_limit_seconds"]

    run_dir = setup_run_dir(results_base, "holoclean", dataset["name"])
    log(f"HoloClean | {dataset['name']}")

    dirty_df = pd.read_csv(dataset["dirty"], dtype=str, keep_default_na=False)
    clean_df = pd.read_csv(dataset["clean"], dtype=str, keep_default_na=False)

    purge_holoclean_db(sys_cfg["db"]["db_name"])

    import signal
    timed_out = False
    repaired_df = None
    tracker = PeakMemoryTracker(limit_mb=get_memory_limit_mb(cfg))
    try:
        with tracker:
            def _timeout(signum, frame):
                raise TimeoutError()
            signal.signal(signal.SIGALRM, _timeout)
            signal.alarm(time_limit)
            try:
                repaired_df = _run_holoclean_session(dataset["dirty"], dataset["name"], _holoclean_fds_path(dataset["name"], fds_dir), sys_cfg)
            finally:
                signal.alarm(0)
    except TimeoutError:
        timed_out = True
        log_error(f"  HoloClean timed out on {dataset['name']}")
    except Exception as e:
        log_error(f"  HoloClean failed on {dataset['name']}: {e}")

    run_config = {
        "system": "holoclean",
        "dataset": dataset["name"],
        "error_rate": dataset["error_rate"],
        "slice": dataset["slice"],
        "mode": "effectiveness",
        "timed_out": timed_out,
        "repetition": rep,
    }

    if repaired_df is None or timed_out:
        record_runtime(run_dir, run_config, tracker.elapsed, tracker.peak_mb)
        return

    # Align columns
    if "_tid_" in repaired_df.columns:
        repaired_df = repaired_df.drop(columns=["_tid_"])
    for col in dirty_df.columns:
        if col not in repaired_df.columns:
            repaired_df[col] = dirty_df[col]
    repaired_df = repaired_df[dirty_df.columns]

    changed_cells = diff_repaired(dirty_df, repaired_df)

    evaluate(
        dirty_df=dirty_df,
        clean_df=clean_df,
        detected_cells=changed_cells,
        corrected_cells=changed_cells,
        labeled_rows=set(),
        out_dir=run_dir,
        run_config=run_config,
        runtime_seconds=tracker.elapsed,
        peak_memory_mb=tracker.peak_mb,
    )
    log(f"  -> {run_dir}")


def run_holoclean_runtime(dataset: dict, cfg: dict, results_base: str, fds_dir: str):
    sys_cfg = cfg["systems"]["holoclean"]
    time_limit = cfg["experiment"]["time_limit_seconds"]
    fds_path = _holoclean_fds_path(dataset["name"], fds_dir)

    import signal
    for variant, input_path in [("dirty", dataset["dirty"]), ("clean", dataset["clean"])]:
        run_dir = setup_run_dir(results_base, "holoclean_runtime", f"{dataset['name']}_{variant}")
        log(f"HoloClean runtime | {dataset['name']} ({variant}) | n={dataset['n_records']}")

        purge_holoclean_db(sys_cfg["db"]["db_name"])

        timed_out = False
        oom = False
        tracker = PeakMemoryTracker(limit_mb=get_memory_limit_mb(cfg))
        try:
            with tracker:
                def _timeout(signum, frame):
                    raise TimeoutError()
                signal.signal(signal.SIGALRM, _timeout)
                signal.alarm(time_limit)
                try:
                    _run_holoclean_session(input_path, dataset["name"], fds_path, sys_cfg)
                finally:
                    signal.alarm(0)
        except TimeoutError:
            timed_out = True
        except MemoryError as e:
            oom = True
            log_error(f"  HoloClean OOM on {dataset['name']} ({variant}): {e}")
        except Exception as e:
            log_error(f"  HoloClean failed ({variant}): {e}")

        run_config = {
            "system": "holoclean",
            "dataset": dataset["name"],
            "variant": variant,
            "n_records": dataset["n_records"],
            "mode": "runtime",
            "timed_out": timed_out,
            "oom": oom,
        }
        record_runtime(run_dir, run_config, tracker.elapsed, tracker.peak_mb)
        log(f"  -> {tracker.elapsed:.1f}s  {tracker.peak_mb:.0f}MB  timed_out={timed_out}  oom={oom}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["effectiveness", "runtime"], required=True)
    parser.add_argument("--config", default=os.path.join(EXPERIMENTS_DIR, "config.json"))
    parser.add_argument("--datasets-dir", default=os.path.join(EXPERIMENTS_DIR, "experiment_datasets"))
    parser.add_argument("--results-dir", default=os.path.join(EXPERIMENTS_DIR, "results"))
    args = parser.parse_args()

    cfg = load_config(args.config)
    os.makedirs(args.results_dir, exist_ok=True)
    init_log_file(os.path.join(args.results_dir, f"holoclean_{args.mode}.log"))
    if not cfg["systems"]["holoclean"]["enabled"]:
        log("HoloClean disabled in config")
        return

    fds_dir = os.path.join(args.datasets_dir, "fds")

    if args.mode == "effectiveness":
        n_reps = cfg.get("experiment", {}).get("n_effectiveness_runs", 3)
        datasets = list_effectiveness_datasets(cfg, args.datasets_dir)
        log(f"Found {len(datasets)} effectiveness datasets, {n_reps} repetitions")
        for rep in range(1, n_reps + 1):
            log(f"=== Effectiveness repetition {rep}/{n_reps} ===")
            for ds in datasets:
                run_holoclean_effectiveness(ds, cfg, args.results_dir, fds_dir, rep=rep)
    else:
        for ds in list_runtime_datasets(cfg, args.datasets_dir):
            run_holoclean_runtime(ds, cfg, args.results_dir, fds_dir)


if __name__ == "__main__":
    main()
