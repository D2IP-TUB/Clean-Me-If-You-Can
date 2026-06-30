"""
run_uniclean.py — run UniClean experiments by delegating to main_{slice}.py.

Each dataset slice maps to a dedicated UniClean entry point under
baselines/uniclean/uniclean_cleaners/:

  full              → main_full
  de                → main_de
  russia            → main_ru
  poi_Library       → main_library
  poi_ShoppingCenter → main_shopping_center

Runtime experiments always use main_full on sampled full-dataset rows.
"""

import argparse
import importlib
import os
import signal
import sys

import pandas as pd

EXPERIMENTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, EXPERIMENTS_DIR)

from runner_utils import (
    load_config,
    list_effectiveness_datasets,
    list_runtime_datasets,
    setup_run_dir,
    PeakMemoryTracker,
    log,
    log_error,
    get_memory_limit_mb,
    init_log_file,
)
from evaluate import evaluate, record_runtime, diff_repaired

UNICLEAN_DIR = os.path.normpath(
    os.path.join(EXPERIMENTS_DIR, "../baselines/uniclean/uniclean_cleaners")
)

SLICE_TO_MAIN = {
    "full": "main_full",
    "de": "main_de",
    "russia": "main_ru",
    "poi_Library": "main_library",
    "poi_ShoppingCenter": "main_shopping_center",
}


def _main_module_for_dataset(dataset: dict) -> str:
    slice_name = dataset.get("slice") or dataset["name"]
    if slice_name in SLICE_TO_MAIN:
        return SLICE_TO_MAIN[slice_name]
    name = dataset["name"]
    if name.startswith("de_"):
        return "main_de"
    if name.startswith("russia_"):
        return "main_ru"
    if name.startswith("poi_Library"):
        return "main_library"
    if name.startswith("poi_ShoppingCenter"):
        return "main_shopping_center"
    return "main_full"


def _cleaned_csv_path(save_path: str, table_name: str) -> str:
    return os.path.join(save_path, table_name, f"{table_name}Cleaned.csv")


def _call_main(
    module_name: str,
    dirty_path: str,
    clean_path: str,
    save_path: str,
    table_name: str,
) -> None:
    """Invoke main_{slice}.main() with harness dataset paths."""
    if UNICLEAN_DIR not in sys.path:
        sys.path.insert(0, UNICLEAN_DIR)

    argv_backup = sys.argv[:]
    cwd_backup = os.getcwd()
    sys.argv = [
        f"{module_name}.py",
        "--file_load", os.path.abspath(dirty_path),
        "--clean_path", os.path.abspath(clean_path),
        "--save_path", os.path.abspath(save_path),
        "--table_name", table_name,
    ]
    try:
        os.chdir(UNICLEAN_DIR)
        mod = importlib.import_module(module_name)
        importlib.reload(mod)
        mod.main()
    finally:
        sys.argv = argv_backup
        os.chdir(cwd_backup)


def _align_repaired(dirty_df: pd.DataFrame, repaired_df: pd.DataFrame) -> pd.DataFrame:
    if "index" in repaired_df.columns and "index" not in dirty_df.columns:
        repaired_df = repaired_df.drop(columns=["index"])
    for col in dirty_df.columns:
        if col not in repaired_df.columns:
            repaired_df[col] = dirty_df[col]
    return repaired_df[dirty_df.columns]


def run_uniclean_effectiveness(dataset: dict, cfg: dict, results_base: str, rep: int = 1) -> bool:
    module_name = _main_module_for_dataset(dataset)
    table_name = dataset["name"]
    run_dir = setup_run_dir(results_base, "uniclean", dataset["name"])
    time_limit = cfg["experiment"]["time_limit_seconds"]

    log(f"UniClean | {dataset['name']} | {module_name}")

    dirty_df = pd.read_csv(dataset["dirty"], dtype=str, keep_default_na=False)
    clean_df = pd.read_csv(dataset["clean"], dtype=str, keep_default_na=False)

    timed_out = False
    failed = False
    tracker = PeakMemoryTracker(limit_mb=get_memory_limit_mb(cfg))

    try:
        with tracker:
            def _timeout(signum, frame):
                raise TimeoutError()

            signal.signal(signal.SIGALRM, _timeout)
            signal.alarm(time_limit)
            try:
                _call_main(
                    module_name,
                    dataset["dirty"],
                    dataset["clean"],
                    run_dir,
                    table_name,
                )
            finally:
                signal.alarm(0)
    except TimeoutError:
        timed_out = True
        log_error(f"  UniClean timed out on {dataset['name']}")
    except Exception as exc:
        failed = True
        log_error(f"  UniClean failed on {dataset['name']}: {exc}")

    run_config = {
        "system": "uniclean",
        "dataset": dataset["name"],
        "slice": dataset.get("slice", ""),
        "error_rate": dataset.get("error_rate", ""),
        "mode": "effectiveness",
        "main_module": module_name,
        "timed_out": timed_out,
        "failed": failed,
        "repetition": rep,
    }

    cleaned_path = _cleaned_csv_path(run_dir, table_name)
    if timed_out or failed or not os.path.exists(cleaned_path):
        record_runtime(run_dir, run_config, tracker.elapsed, tracker.peak_mb)
        return False

    repaired_df = pd.read_csv(cleaned_path, dtype=str, keep_default_na=False)
    repaired_df = _align_repaired(dirty_df, repaired_df)
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
    return True


def run_uniclean_runtime(dataset: dict, cfg: dict, results_base: str) -> bool:
    """Runtime benchmark: sample rows and run main_full."""
    import tempfile

    module_name = "main_full"
    table_name = dataset["name"]
    run_dir = setup_run_dir(results_base, "uniclean_runtime", dataset["name"])
    time_limit = cfg["experiment"]["time_limit_seconds"]

    log(f"UniClean runtime | {dataset['name']} | n={dataset['n_records']}")

    dirty_full = pd.read_csv(dataset["dirty"], dtype=str, keep_default_na=False)
    clean_full = pd.read_csv(dataset["clean"], dtype=str, keep_default_na=False)
    n = min(dataset["n_records"], len(dirty_full))
    dirty_sample = dirty_full.head(n)
    clean_sample = clean_full.head(n)

    timed_out = False
    failed = False
    tracker = PeakMemoryTracker(limit_mb=get_memory_limit_mb(cfg))

    with tempfile.TemporaryDirectory(prefix="uniclean_rt_") as tmpdir:
        tmp_dirty = os.path.join(tmpdir, "dirty.csv")
        tmp_clean = os.path.join(tmpdir, "clean.csv")
        dirty_sample.to_csv(tmp_dirty, index=False)
        clean_sample.to_csv(tmp_clean, index=False)

        try:
            with tracker:
                def _timeout(signum, frame):
                    raise TimeoutError()

                signal.signal(signal.SIGALRM, _timeout)
                signal.alarm(time_limit)
                try:
                    _call_main(module_name, tmp_dirty, tmp_clean, run_dir, table_name)
                finally:
                    signal.alarm(0)
        except TimeoutError:
            timed_out = True
            log_error(f"  UniClean runtime timed out on {dataset['name']}")
        except Exception as exc:
            failed = True
            log_error(f"  UniClean runtime failed on {dataset['name']}: {exc}")

    run_config = {
        "system": "uniclean",
        "dataset": dataset["name"],
        "n_records": dataset["n_records"],
        "mode": "runtime",
        "main_module": module_name,
        "timed_out": timed_out,
        "failed": failed,
    }
    record_runtime(run_dir, run_config, tracker.elapsed, tracker.peak_mb)
    return not (timed_out or failed)


def main():
    parser = argparse.ArgumentParser(description="Run UniClean via main_{slice}.py entry points.")
    parser.add_argument("--mode", choices=["effectiveness", "runtime"], required=True)
    parser.add_argument("--config", default=os.path.join(EXPERIMENTS_DIR, "config.json"))
    parser.add_argument("--datasets-dir", default=os.path.join(EXPERIMENTS_DIR, "experiment_datasets"))
    parser.add_argument("--results-dir", default=os.path.join(EXPERIMENTS_DIR, "results"))
    parser.add_argument(
        "--filter-datasets",
        default=None,
        help="Comma-separated substrings; only datasets whose name contains at least one are run",
    )
    args = parser.parse_args()

    cfg = load_config(args.config)
    os.makedirs(args.results_dir, exist_ok=True)
    init_log_file(os.path.join(args.results_dir, f"uniclean_{args.mode}.log"))

    if not cfg["systems"]["uniclean"]["enabled"]:
        log("UniClean disabled in config")
        return

    if args.mode == "effectiveness":
        n_reps = cfg.get("experiment", {}).get("n_effectiveness_runs", 3)
        datasets = list_effectiveness_datasets(cfg, args.datasets_dir)
        if args.filter_datasets:
            filters = [f.strip() for f in args.filter_datasets.split(",") if f.strip()]
            datasets = [ds for ds in datasets if any(f in ds["name"] for f in filters)]
        log(f"Found {len(datasets)} effectiveness datasets, {n_reps} repetitions")
        for rep in range(1, n_reps + 1):
            log(f"=== Effectiveness repetition {rep}/{n_reps} ===")
            for ds in datasets:
                run_uniclean_effectiveness(ds, cfg, args.results_dir, rep=rep)
    else:
        datasets = list_runtime_datasets(cfg, args.datasets_dir)
        if args.filter_datasets:
            filters = [f.strip() for f in args.filter_datasets.split(",") if f.strip()]
            datasets = [ds for ds in datasets if any(f in ds["name"] for f in filters)]
        for ds in datasets:
            run_uniclean_runtime(ds, cfg, args.results_dir)


if __name__ == "__main__":
    main()
