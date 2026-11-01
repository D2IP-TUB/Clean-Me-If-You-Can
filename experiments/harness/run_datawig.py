"""
run_datawig.py — run DataWig (detection + correction) experiments.

Detection: predict each column from all others; cells where prediction != dirty
           and confidence >= threshold are flagged as detected errors.
Correction: predicted value for flagged cells.

20 clean training samples used (consistent with Raha/Baran's 20 labeled tuples),
confidence threshold = 0.5.
"""

import argparse
import os
import sys
import shutil

import numpy as np
import pandas as pd

EXPERIMENTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, EXPERIMENTS_DIR)

DATAWIG_DIR = os.path.normpath(os.path.join(EXPERIMENTS_DIR, "../baselines/datawig"))
sys.path.insert(0, DATAWIG_DIR)

from runner_utils import (
    load_config, list_effectiveness_datasets, list_runtime_datasets,
    setup_run_dir, PeakMemoryTracker, purge_datawig_cache, log, log_error,
    get_memory_limit_mb, init_log_file,
)
from evaluate import evaluate, record_runtime, get_actual_errors, normalize


def _train_and_predict(dirty_df, clean_df, train_rows, data_cols, confidence_threshold, models_dir):
    """
    For each column, train SimpleImputer on clean train_rows, predict on all (dirty) rows.
    Training on clean rows mirrors Raha/Baran which receive 20 ground-truth-labeled tuples.
    Returns detected_cells and corrected_cells dicts.
    """
    import datawig

    detected = {}
    corrected = {}
    col_names = list(dirty_df.columns)

    for target_col in data_cols:
        if target_col not in dirty_df.columns:
            continue
        input_cols = [c for c in data_cols if c in dirty_df.columns and c != target_col]
        if not input_cols:
            continue

        col_model_dir = os.path.join(models_dir, f"col_{target_col}")
        os.makedirs(col_model_dir, exist_ok=True)

        # Only use training rows where the target column is non-empty in clean data.
        # If all 20 sampled rows are empty for this column, DataWig builds an empty
        # vocabulary and fails — and there is genuinely no signal to learn from.
        valid_train_rows = [r for r in train_rows
                            if str(clean_df.iloc[r][target_col]).strip() != ""]
        if not valid_train_rows:
            continue

        train_df = clean_df.iloc[valid_train_rows][input_cols + [target_col]].copy().fillna("")

        try:
            imputer = datawig.SimpleImputer(
                input_columns=input_cols,
                output_column=target_col,
                output_path=col_model_dir,
            )
            imputer.fit(train_df=train_df, test_df=train_df, num_epochs=50)

            pred_df = imputer.predict(dirty_df[input_cols + [target_col]].fillna(""))
            pred_col = target_col + "_imputed"
            conf_col = target_col + "_imputed_proba"

            if pred_col not in pred_df.columns:
                continue

            j = dirty_df.columns.get_loc(target_col)
            for i in range(len(dirty_df)):
                conf = float(pred_df[conf_col].iloc[i]) if conf_col in pred_df.columns else 1.0
                if conf < confidence_threshold:
                    continue
                predicted_val = normalize(str(pred_df[pred_col].iloc[i]))
                dirty_val = normalize(str(dirty_df[target_col].iloc[i]))
                # Always store a correction (model prediction for every cell with
                # sufficient confidence), so actual errors that were not detected
                # still receive a correction attempt.
                corrected[(i, j)] = predicted_val
                if predicted_val != dirty_val:
                    detected[(i, j)] = predicted_val

        except Exception as e:
            log_error(f"  DataWig: col {target_col} failed: {e}")
            continue

    return detected, corrected


def run_datawig_effectiveness(dataset: dict, cfg: dict, results_base: str, rep: int = 1):
    sys_cfg = cfg["systems"]["datawig"]
    n_train = sys_cfg["num_training_samples"]
    threshold = sys_cfg["confidence_threshold"]
    data_cols = cfg["dataset"]["data_columns"]

    run_dir = setup_run_dir(results_base, "datawig", dataset["name"])
    models_dir = os.path.join(run_dir, "models")
    log(f"DataWig | {dataset['name']} | train={n_train} threshold={threshold}")

    dirty_df = pd.read_csv(dataset["dirty"], dtype=str, keep_default_na=False)
    clean_df = pd.read_csv(dataset["clean"], dtype=str, keep_default_na=False)

    import random
    rng = random.Random()  # system entropy — no fixed seed
    train_rows = sorted(rng.sample(range(len(dirty_df)), min(n_train, len(dirty_df))))

    tracker = PeakMemoryTracker(limit_mb=get_memory_limit_mb(cfg))
    detected, corrected = {}, {}
    try:
        with tracker:
            detected, corrected = _train_and_predict(
                dirty_df, clean_df, train_rows, data_cols, threshold, models_dir
            )
    except Exception as e:
        log_error(f"DataWig failed on {dataset['name']}: {e}")

    # Inject ground-truth labels for training rows — mirrors Raha/Baran behaviour where
    # labeled tuples are added directly from ground truth rather than from model predictions.
    for i in train_rows:
        for j in range(dirty_df.shape[1]):
            dirty_val = normalize(str(dirty_df.iloc[i, j]))
            clean_val = normalize(str(clean_df.iloc[i, j]))
            if dirty_val != clean_val:
                detected[(i, j)] = clean_val
                corrected[(i, j)] = clean_val

    run_config = {
        "system": "datawig",
        "dataset": dataset["name"],
        "error_rate": dataset["error_rate"],
        "slice": dataset["slice"],
        "num_training_samples": n_train,
        "confidence_threshold": threshold,
        "train_rows": train_rows,
        "mode": "effectiveness",
        "repetition": rep,
    }

    evaluate(
        dirty_df=dirty_df,
        clean_df=clean_df,
        detected_cells=detected,
        corrected_cells=corrected,
        labeled_rows=set(train_rows),
        out_dir=run_dir,
        run_config=run_config,
        runtime_seconds=tracker.elapsed,
        peak_memory_mb=tracker.peak_mb,
    )
    log(f"  -> {run_dir}")


def run_datawig_runtime(dataset: dict, cfg: dict, results_base: str, rep: int = 1):
    sys_cfg = cfg["systems"]["datawig"]
    n_train = sys_cfg["num_training_samples"]
    threshold = sys_cfg["confidence_threshold"]
    data_cols = cfg["dataset"]["data_columns"]
    time_limit = cfg["experiment"]["time_limit_seconds"]

    dataset_dir = os.path.dirname(dataset["dirty"])
    purge_datawig_cache(dataset_dir)

    run_dir = setup_run_dir(results_base, "datawig_runtime", dataset["name"])
    models_dir = os.path.join(run_dir, "models")
    log(f"DataWig runtime | {dataset['name']} | n={dataset['n_records']} | rep={rep}")

    dirty_df = pd.read_csv(dataset["dirty"], dtype=str, keep_default_na=False)
    clean_df = pd.read_csv(dataset["clean"], dtype=str, keep_default_na=False)

    import random, signal
    rng = random.Random()
    train_rows = sorted(rng.sample(range(len(dirty_df)), min(n_train, len(dirty_df))))

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
                _train_and_predict(dirty_df, clean_df, train_rows, data_cols, threshold, models_dir)
            finally:
                signal.alarm(0)
    except TimeoutError:
        timed_out = True
        log_error(f"  DataWig timed out on {dataset['name']}")
    except MemoryError as e:
        oom = True
        log_error(f"  DataWig OOM on {dataset['name']}: {e}")
    except Exception as e:
        log_error(f"  DataWig failed: {e}")

    run_config = {
        "system": "datawig",
        "dataset": dataset["name"],
        "n_records": dataset["n_records"],
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
    init_log_file(os.path.join(args.results_dir, f"datawig_{args.mode}.log"))
    if not cfg["systems"]["datawig"]["enabled"]:
        log("DataWig disabled in config")
        return

    if args.mode == "effectiveness":
        n_reps = args.reps if args.reps is not None else cfg.get("experiment", {}).get("n_effectiveness_runs", 3)
        datasets = list_effectiveness_datasets(cfg, args.datasets_dir)
        if args.filter_datasets:
            filters = [f.strip() for f in args.filter_datasets.split(",") if f.strip()]
            datasets = [ds for ds in datasets if any(f in ds["name"] for f in filters)]
        last_rep = args.first_rep + n_reps - 1
        log(f"Found {len(datasets)} effectiveness datasets, repetitions {args.first_rep}-{last_rep}")
        for rep in range(args.first_rep, last_rep + 1):
            log(f"=== Effectiveness repetition {rep}/{last_rep} ===")
            for ds in datasets:
                run_datawig_effectiveness(ds, cfg, args.results_dir, rep=rep)
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
                if run_datawig_runtime(ds, cfg, args.results_dir, rep=rep):
                    log("DataWig timeout/OOM — skipping remaining sizes and repetitions")
                    return


if __name__ == "__main__":
    main()
