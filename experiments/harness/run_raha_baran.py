"""
run_raha_baran.py — run Raha (detection) and Baran (correction) experiments.

For effectiveness:  runs on all prepared effectiveness datasets, evaluates P/R/F1.
For runtime:        runs on runtime datasets, purges cache first, no evaluation.

Usage:
    python run_raha_baran.py --mode effectiveness [--config config.json] [--datasets-dir ...]
    python run_raha_baran.py --mode runtime       [--config config.json] [--datasets-dir ...]
    python run_raha_baran.py --mode effectiveness --system raha   # only raha
    python run_raha_baran.py --mode effectiveness --system baran  # only baran
"""

import argparse
import os
import sys
import time

import pandas as pd

EXPERIMENTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, EXPERIMENTS_DIR)

from runner_utils import (
    load_config, list_effectiveness_datasets, list_runtime_datasets,
    setup_run_dir, PeakMemoryTracker, purge_raha_cache, log, log_error,
    get_memory_limit_mb, init_log_file,
)
from evaluate import evaluate, record_runtime, get_actual_errors

# Raha/Baran lives one level up
RAHA_DIR = os.path.normpath(os.path.join(EXPERIMENTS_DIR, "../baselines/raha"))
sys.path.insert(0, RAHA_DIR)


def run_raha_effectiveness(dataset: dict, cfg: dict, results_base: str, rep: int = 1):
    import raha
    sys_cfg = cfg["systems"]["raha"]
    labeling_budget = sys_cfg["labeling_budget"]
    time_limit = cfg["experiment"]["time_limit_seconds"]

    run_dir = setup_run_dir(results_base, "raha", dataset["name"])
    log(f"Raha detection | {dataset['name']} | budget={labeling_budget}")

    dd = {
        "name": dataset["name"],
        "path": dataset["dirty"],
        "clean_path": dataset["clean"],
    }

    tracker = PeakMemoryTracker(limit_mb=get_memory_limit_mb(cfg))
    timed_out = False
    try:
        with tracker:
            import signal as _signal

            def _timeout_handler(signum, frame):
                raise TimeoutError("Raha exceeded time limit")

            _signal.signal(_signal.SIGALRM, _timeout_handler)
            _signal.alarm(time_limit)
            try:
                detector = raha.Detection()
                detector.LABELING_BUDGET = labeling_budget
                detector.VERBOSE = False
                detector.SAVE_RESULTS = True
                detection_dict = detector.run(dd)
            finally:
                _signal.alarm(0)

        labeled_rows = set(detector.d.labeled_tuples.keys()) if hasattr(detector, "d") else set()
    except TimeoutError:
        timed_out = True
        log_error(f"  Raha timed out on {dataset['name']}")
        run_config = {
            "system": "raha", "dataset": dataset["name"],
            "error_rate": dataset["error_rate"], "slice": dataset["slice"],
            "labeling_budget": labeling_budget, "mode": "effectiveness",
            "timed_out": True, "repetition": rep,
        }
        record_runtime(run_dir, run_config, tracker.elapsed, tracker.peak_mb)
        return
    except Exception as e:
        log_error(f"Raha failed on {dataset['name']}: {e}")
        return

    dirty_df = pd.read_csv(dataset["dirty"], dtype=str, keep_default_na=False)
    clean_df = pd.read_csv(dataset["clean"], dtype=str, keep_default_na=False)

    # Map Raha's {(row, col_idx): value} — value is dummy, set to "" for detection
    detected = {cell: "" for cell in detection_dict}

    run_config = {
        "system": "raha",
        "dataset": dataset["name"],
        "error_rate": dataset["error_rate"],
        "slice": dataset["slice"],
        "labeling_budget": labeling_budget,
        "mode": "effectiveness",
        "timed_out": False,
        "repetition": rep,
    }

    evaluate(
        dirty_df=dirty_df,
        clean_df=clean_df,
        detected_cells=detected,
        corrected_cells=None,
        labeled_rows=labeled_rows,
        out_dir=run_dir,
        run_config=run_config,
        runtime_seconds=tracker.elapsed,
        peak_memory_mb=tracker.peak_mb,
    )
    log(f"  -> saved to {run_dir}")


def run_baran_effectiveness(dataset: dict, cfg: dict, results_base: str, raha_results_dir: str = None, rep: int = 1):
    import raha
    sys_cfg = cfg["systems"]["baran"]
    labeling_budget = sys_cfg["labeling_budget"]

    run_dir = setup_run_dir(results_base, "baran", dataset["name"])
    log(f"Baran correction | {dataset['name']} | budget={labeling_budget}")

    dirty_df = pd.read_csv(dataset["dirty"], dtype=str, keep_default_na=False)
    clean_df = pd.read_csv(dataset["clean"], dtype=str, keep_default_na=False)

    # Oracle detection: provide all actual errors as detected cells
    actual_errors = get_actual_errors(dirty_df, clean_df)
    oracle_detected = {cell: "" for cell in actual_errors}

    dd = {
        "name": dataset["name"],
        "path": dataset["dirty"],
        "clean_path": dataset["clean"],
    }

    time_limit = cfg["experiment"]["time_limit_seconds"]
    tracker = PeakMemoryTracker(limit_mb=get_memory_limit_mb(cfg))
    timed_out = False
    try:
        with tracker:
            import signal as _signal

            def _timeout_handler(signum, frame):
                raise TimeoutError("Baran exceeded time limit")

            _signal.signal(_signal.SIGALRM, _timeout_handler)
            _signal.alarm(time_limit)
            try:
                import raha.dataset as _raha_dataset
                d_obj = _raha_dataset.Dataset(dd)
                d_obj.detected_cells = oracle_detected
                corrector = raha.Correction()
                corrector.LABELING_BUDGET = labeling_budget
                corrector.VERBOSE = False
                corrector.SAVE_RESULTS = True
                correction_dict = corrector.run(d_obj)
            finally:
                _signal.alarm(0)

        labeled_rows = set(corrector.d.labeled_tuples.keys()) if hasattr(corrector, "d") else set()
    except TimeoutError:
        timed_out = True
        log_error(f"  Baran timed out on {dataset['name']}")
        run_config = {
            "system": "baran", "dataset": dataset["name"],
            "error_rate": dataset["error_rate"], "slice": dataset["slice"],
            "labeling_budget": labeling_budget, "mode": "effectiveness",
            "oracle_detection": True, "timed_out": True, "repetition": rep,
        }
        record_runtime(run_dir, run_config, tracker.elapsed, tracker.peak_mb)
        return
    except Exception as e:
        log_error(f"Baran failed on {dataset['name']}: {e}")
        return

    run_config = {
        "system": "baran",
        "dataset": dataset["name"],
        "error_rate": dataset["error_rate"],
        "slice": dataset["slice"],
        "labeling_budget": labeling_budget,
        "mode": "effectiveness",
        "oracle_detection": True,
        "timed_out": False,
        "repetition": rep,
    }

    evaluate(
        dirty_df=dirty_df,
        clean_df=clean_df,
        detected_cells=oracle_detected,
        corrected_cells={cell: v for cell, v in correction_dict.items()},
        labeled_rows=labeled_rows,
        out_dir=run_dir,
        run_config=run_config,
        runtime_seconds=tracker.elapsed,
        peak_memory_mb=tracker.peak_mb,
    )
    log(f"  -> saved to {run_dir}")


def run_raha_runtime(dataset: dict, cfg: dict, results_base: str, rep: int = 1):
    import raha
    sys_cfg = cfg["systems"]["raha"]
    labeling_budget = sys_cfg["labeling_budget"]
    time_limit = cfg["experiment"]["time_limit_seconds"]

    dataset_dir = os.path.dirname(dataset["dirty"])
    purge_raha_cache(dataset_dir)

    run_dir = setup_run_dir(results_base, "raha_runtime", dataset["name"])
    log(f"Raha runtime | {dataset['name']} | n={dataset['n_records']} | rep={rep}")

    dd = {
        "name": dataset["name"],
        "path": dataset["dirty"],
        "clean_path": dataset["clean"],
    }

    tracker = PeakMemoryTracker(limit_mb=get_memory_limit_mb(cfg))
    timed_out = False
    oom = False
    try:
        with tracker:
            import signal as _signal

            def _timeout_handler(signum, frame):
                raise TimeoutError("Raha exceeded time limit")

            _signal.signal(_signal.SIGALRM, _timeout_handler)
            _signal.alarm(time_limit)
            try:
                detector = raha.Detection()
                detector.LABELING_BUDGET = labeling_budget
                detector.VERBOSE = False
                detector.SAVE_RESULTS = False
                detector.run(dd)
            finally:
                _signal.alarm(0)
    except TimeoutError:
        timed_out = True
        log_error(f"  Raha timed out on {dataset['name']}")
    except MemoryError as e:
        oom = True
        log_error(f"  Raha OOM on {dataset['name']}: {e}")
    except Exception as e:
        log_error(f"  Raha failed on {dataset['name']}: {e}")

    run_config = {
        "system": "raha",
        "dataset": dataset["name"],
        "n_records": dataset["n_records"],
        "labeling_budget": labeling_budget,
        "mode": "runtime",
        "repetition": rep,
        "timed_out": timed_out,
        "oom": oom,
    }
    record_runtime(run_dir, run_config, tracker.elapsed, tracker.peak_mb)
    log(f"  -> {tracker.elapsed:.1f}s  {tracker.peak_mb:.0f}MB  timed_out={timed_out}  oom={oom}")
    return timed_out or oom


def run_baran_runtime(dataset: dict, cfg: dict, results_base: str, rep: int = 1):
    import raha
    sys_cfg = cfg["systems"]["baran"]
    labeling_budget = sys_cfg["labeling_budget"]
    time_limit = cfg["experiment"]["time_limit_seconds"]

    dataset_dir = os.path.dirname(dataset["dirty"])
    purge_raha_cache(dataset_dir)

    run_dir = setup_run_dir(results_base, "baran_runtime", dataset["name"])
    log(f"Baran runtime | {dataset['name']} | n={dataset['n_records']} | rep={rep}")

    dd = {
        "name": dataset["name"],
        "path": dataset["dirty"],
        "clean_path": dataset["clean"],
    }

    tracker = PeakMemoryTracker(limit_mb=get_memory_limit_mb(cfg))
    timed_out = False
    oom = False
    try:
        with tracker:
            # Load data and build oracle inside the tracker so allocation is measured
            dirty_df = pd.read_csv(dataset["dirty"], dtype=str, keep_default_na=False)
            clean_df = pd.read_csv(dataset["clean"], dtype=str, keep_default_na=False)
            actual_errors = get_actual_errors(dirty_df, clean_df)
            oracle_detected = {cell: "" for cell in actual_errors}

            import signal as _signal

            def _timeout_handler(signum, frame):
                raise TimeoutError("Baran exceeded time limit")

            _signal.signal(_signal.SIGALRM, _timeout_handler)
            _signal.alarm(time_limit)
            try:
                import raha.dataset as _raha_dataset
                d_obj = _raha_dataset.Dataset(dd)
                d_obj.detected_cells = oracle_detected
                corrector = raha.Correction()
                corrector.LABELING_BUDGET = labeling_budget
                corrector.VERBOSE = False
                corrector.SAVE_RESULTS = False
                corrector.run(d_obj)
            finally:
                _signal.alarm(0)
    except TimeoutError:
        timed_out = True
        log_error(f"  Baran timed out on {dataset['name']}")
    except MemoryError as e:
        oom = True
        log_error(f"  Baran OOM on {dataset['name']}: {e}")
    except Exception as e:
        log_error(f"  Baran failed on {dataset['name']}: {e}")

    run_config = {
        "system": "baran",
        "dataset": dataset["name"],
        "n_records": dataset["n_records"],
        "labeling_budget": labeling_budget,
        "mode": "runtime",
        "repetition": rep,
        "timed_out": timed_out,
        "oom": oom,
    }
    record_runtime(run_dir, run_config, tracker.elapsed, tracker.peak_mb)
    log(f"  -> {tracker.elapsed:.1f}s  {tracker.peak_mb:.0f}MB  timed_out={timed_out}  oom={oom}")
    return timed_out or oom


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["effectiveness", "runtime"], required=True)
    parser.add_argument("--system", choices=["raha", "baran", "both"], default="both")
    parser.add_argument("--config", default=os.path.join(EXPERIMENTS_DIR, "config.json"))
    parser.add_argument("--datasets-dir", default=os.path.join(EXPERIMENTS_DIR, "experiment_datasets"))
    parser.add_argument("--results-dir", default=os.path.join(EXPERIMENTS_DIR, "results"))
    parser.add_argument("--reps", type=int, default=None,
                        help="How many repetitions to run (default: n_effectiveness_runs)")
    parser.add_argument("--first-rep", type=int, default=1,
                        help="Repetition number to start from")
    parser.add_argument("--filter-datasets", default=None,
                        help="Comma-separated substrings; only datasets whose name contains at least one are run")
    args = parser.parse_args()

    cfg = load_config(args.config)
    os.makedirs(args.results_dir, exist_ok=True)
    init_log_file(os.path.join(args.results_dir, f"raha_baran_{args.mode}.log"))
    run_raha = args.system in ("raha", "both") and cfg["systems"]["raha"]["enabled"]
    run_baran = args.system in ("baran", "both") and cfg["systems"]["baran"]["enabled"]

    if args.mode == "effectiveness":
        datasets = list_effectiveness_datasets(cfg, args.datasets_dir)
        if args.filter_datasets:
            filters = [f.strip() for f in args.filter_datasets.split(",") if f.strip()]
            datasets = [ds for ds in datasets if any(f in ds["name"] for f in filters)]
        n_reps = args.reps if args.reps is not None else cfg.get("experiment", {}).get("n_effectiveness_runs", 3)
        last_rep = args.first_rep + n_reps - 1
        log(f"Found {len(datasets)} effectiveness datasets, repetitions {args.first_rep}-{last_rep}")
        for rep in range(args.first_rep, last_rep + 1):
            log(f"=== Effectiveness repetition {rep}/{last_rep} ===")
            for ds in datasets:
                if run_raha:
                    run_raha_effectiveness(ds, cfg, args.results_dir, rep=rep)
                if run_baran:
                    run_baran_effectiveness(ds, cfg, args.results_dir, rep=rep)
    else:
        datasets = list_runtime_datasets(cfg, args.datasets_dir)
        if args.filter_datasets:
            filters = [f.strip() for f in args.filter_datasets.split(",") if f.strip()]
            datasets = [ds for ds in datasets if any(f in ds["name"] for f in filters)]
        n_reps = args.reps if args.reps is not None else cfg.get("experiment", {}).get("n_runtime_runs", 1)
        last_rep = args.first_rep + n_reps - 1
        log(f"Found {len(datasets)} runtime datasets, repetitions {args.first_rep}-{last_rep}")
        stop_raha = stop_baran = False
        for rep in range(args.first_rep, last_rep + 1):
            log(f"=== Runtime repetition {rep}/{last_rep} ===")
            for ds in datasets:
                if run_raha and not stop_raha:
                    if run_raha_runtime(ds, cfg, args.results_dir, rep=rep):
                        log("Raha timeout/OOM — skipping remaining sizes and repetitions")
                        stop_raha = True
                if run_baran and not stop_baran:
                    if run_baran_runtime(ds, cfg, args.results_dir, rep=rep):
                        log("Baran timeout/OOM — skipping remaining sizes and repetitions")
                        stop_baran = True
                if (not run_raha or stop_raha) and (not run_baran or stop_baran):
                    return


if __name__ == "__main__":
    main()
