#!/usr/bin/env python3
"""
run_experiments.py — UniClean effectiveness and runtime experiments for the
address data cleaning benchmark.

Output per run: results_experiments/uniclean/<dataset>_<ts>/
  <dataset>_total_evaluation.txt  — det/cor precision, recall, F1
  <dataset>Cleaned.csv            — repaired CSV (via save_cleaned_data)
  runtime_summary.csv             — wall time + peak memory (runtime mode only)

Evaluation is delegated entirely to util.evaluate_cleaning_performance, which
calls getScore.calculate_all_metrics — the same path used by main_full.main().
Spark session is obtained from main_full.build_spark_session() so the OOM-safe
config (80g, codegen limit, G1GC, offHeap) is never duplicated.

Modes:
  effectiveness   Run on all dirty/clean pairs under effectiveness/, evaluate.
  runtime         Sample the full dataset at multiple sizes (N repetitions each).

Usage:
  # effectiveness — 1 rep, auto-discover all datasets under ../../effectiveness/
  python run_experiments.py --mode effectiveness

  # effectiveness — 3 reps
  python run_experiments.py --mode effectiveness --n-reps 3

  # runtime — auto-infers full/ sample; 3 reps
  python run_experiments.py --mode runtime --n-reps 3

  # runtime — explicit paths and sizes
  python run_experiments.py --mode runtime \\
      --full-dirty ../../effectiveness/full/sample_full_0.51/dirty.csv \\
      --full-clean ../../effectiveness/full/sample_full_0.51/clean.csv \\
      --sizes 10000 100000 500000 1000000
"""

import argparse
import csv
import json
import os
import shutil
import signal
import sys
import threading
import time
from datetime import datetime

import pandas as pd
import psutil

# ---------------------------------------------------------------------------
# Paths — uniclean_cleaners/ must be on sys.path so that util, main_full, etc.
# are importable without installing the package.
# ---------------------------------------------------------------------------
THIS_DIR = os.path.dirname(os.path.abspath(__file__))
UNICLEAN_DIR = os.path.join(THIS_DIR, "uniclean_cleaners")
EFFECTIVENESS_DIR = os.path.normpath(os.path.join(THIS_DIR, "../../effectiveness"))
RESULTS_DIR = os.path.join(THIS_DIR, "results_experiments")

sys.path.insert(0, UNICLEAN_DIR)

# Lazy imports (PySpark may not be initialised yet at module load time)
# util and main_full are imported inside functions that need them.


# ---------------------------------------------------------------------------
# Dataset discovery
# ---------------------------------------------------------------------------
def list_effectiveness_datasets(eff_dir: str) -> list:
    """Walk effectiveness/{slice}/{sample?}/dirty.csv + clean.csv."""
    entries = []
    if not os.path.isdir(eff_dir):
        raise FileNotFoundError(f"Effectiveness dir not found: {eff_dir}")
    for slice_name in sorted(os.listdir(eff_dir)):
        slice_dir = os.path.join(eff_dir, slice_name)
        if not os.path.isdir(slice_dir):
            continue
        # POI slices: dirty/clean directly inside the slice dir
        dirty = os.path.join(slice_dir, "dirty.csv")
        clean = os.path.join(slice_dir, "clean.csv")
        if os.path.exists(dirty) and os.path.exists(clean):
            entries.append({"name": slice_name, "slice": slice_name,
                            "error_rate": "native", "dirty": dirty, "clean": clean})
            continue
        # Per-error-rate subdirectories (e.g. sample_de_0.05)
        for sub in sorted(os.listdir(slice_dir)):
            sub_dir = os.path.join(slice_dir, sub)
            if not os.path.isdir(sub_dir):
                continue
            dirty = os.path.join(sub_dir, "dirty.csv")
            clean = os.path.join(sub_dir, "clean.csv")
            if os.path.exists(dirty) and os.path.exists(clean):
                parts = sub.rsplit("_", 1)
                try:
                    rate = float(parts[-1])
                except ValueError:
                    rate = "native"
                entries.append({"name": f"{slice_name}_{sub}", "slice": slice_name,
                                "error_rate": rate, "dirty": dirty, "clean": clean})
    return entries


# ---------------------------------------------------------------------------
# Spark session — delegates to main_full.build_spark_session() so we use
# the exact same OOM-safe config (80g, codegen limit, G1GC, offHeap, etc.)
# ---------------------------------------------------------------------------
def _get_spark(spark_memory: str = "80g"):
    import main_full  # noqa: PLC0415
    return main_full.build_spark_session(
        app_name="UniClean-address-experiments",
        memory=spark_memory,
    )


# ---------------------------------------------------------------------------
# Spark cleaning runner — produces a single repaired CSV on disk
# ---------------------------------------------------------------------------
def _run_spark_cleaners(dirty_path: str, spark, out_dir: str, slice_name: str = "") -> str:
    """Delegate to the appropriate dataset module's clean_file()."""
    import main_full  # noqa: PLC0415
    if slice_name.startswith("de"):
        import main_de  # noqa: PLC0415
        return main_full.clean_file(dirty_path, out_dir, spark, cleaner_list=main_de.cleaners)
    if slice_name.startswith("russia"):
        import main_ru  # noqa: PLC0415
        return main_full.clean_file(dirty_path, out_dir, spark, cleaner_list=main_ru.cleaners)
    return main_full.clean_file(dirty_path, out_dir, spark)


# ---------------------------------------------------------------------------
# Peak-memory + wall-time tracker
# ---------------------------------------------------------------------------
class PeakMemoryTracker:
    def __init__(self, interval: float = 0.2):
        self.interval = interval
        self.peak_mb = 0.0
        self.elapsed = 0.0
        self._stop = threading.Event()
        self._proc = psutil.Process()

    def _run(self):
        while not self._stop.is_set():
            try:
                mem = self._proc.memory_info().rss / 1024 / 1024
                if mem > self.peak_mb:
                    self.peak_mb = mem
            except Exception:  # noqa: BLE001
                pass
            self._stop.wait(self.interval)

    def __enter__(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self._start = time.time()
        return self

    def __exit__(self, *_):
        self._stop.set()
        self._thread.join(timeout=2)
        self.elapsed = time.time() - self._start


# ---------------------------------------------------------------------------
# Run directory
# ---------------------------------------------------------------------------
def setup_run_dir(results_base: str, system: str, dataset_name: str) -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = os.path.join(results_base, system, f"{dataset_name}_{ts}")
    os.makedirs(run_dir, exist_ok=True)
    return run_dir


# ---------------------------------------------------------------------------
# Effectiveness run
# ---------------------------------------------------------------------------
def run_effectiveness(
    dataset: dict,
    results_base: str,
    spark_memory: str = "80g",
    time_limit: int = 3600,
    rep: int = 1,
):
    from util import evaluate_cleaning_performance  # noqa: PLC0415

    run_dir = setup_run_dir(results_base, "uniclean", dataset["name"])
    print(f"[effectiveness] {dataset['name']}  error_rate={dataset['error_rate']}  rep={rep}")

    timed_out = False
    repaired_path = None
    spark = None
    tracker = PeakMemoryTracker()

    try:
        spark = _get_spark(spark_memory)
        with tracker:
            def _timeout(signum, frame):
                raise TimeoutError()
            signal.signal(signal.SIGALRM, _timeout)
            signal.alarm(time_limit)
            try:
                repaired_path = _run_spark_cleaners(dataset["dirty"], spark, run_dir, dataset["slice"])
            finally:
                signal.alarm(0)
    except TimeoutError:
        timed_out = True
        print(f"  [timeout] {dataset['name']}", file=sys.stderr)
    except Exception as exc:  # noqa: BLE001
        print(f"  [error] {dataset['name']}: {exc}", file=sys.stderr)
    finally:
        if spark:
            try:
                spark.stop()
            except Exception:  # noqa: BLE001
                pass

    with open(os.path.join(run_dir, "run_config.json"), "w") as f:
        json.dump({"system": "uniclean", "dataset": dataset["name"],
                   "slice": dataset["slice"], "error_rate": dataset["error_rate"],
                   "mode": "effectiveness", "timed_out": timed_out,
                   "repetition": rep, "runtime_seconds": round(tracker.elapsed, 3),
                   "peak_memory_mb": round(tracker.peak_mb, 1)}, f, indent=2, default=str)

    if repaired_path is None or not os.path.exists(repaired_path) or timed_out:
        print(f"  [no output]  t={tracker.elapsed:.1f}s  -> {run_dir}")
        return

    # evaluate_cleaning_performance handles: inject_missing_values, index alignment,
    # normalize_cleaned_against_clean, getScore metrics, print_results — everything.
    evaluate_cleaning_performance(
        clean_path=dataset["clean"],
        dirty_path=dataset["dirty"],
        cleaned_path=repaired_path,
        elapsed_time=tracker.elapsed,
        output_path=run_dir,
        table_name=dataset["name"],
    )
    print(f"  t={tracker.elapsed:.1f}s  mem={tracker.peak_mb:.0f}MB  -> {run_dir}")


# ---------------------------------------------------------------------------
# Runtime run — only measures wall time + peak memory, no evaluation
# ---------------------------------------------------------------------------
def run_runtime(
    full_dirty: str,
    full_clean: str,
    sizes: list,
    results_base: str,
    spark_memory: str = "80g",
    time_limit: int = 3600,
    n_reps: int = 3,
):
    import main_full  # noqa: PLC0415

    dirty_full = pd.read_csv(full_dirty, dtype=str, keep_default_na=False)

    rt_summary_path = os.path.join(results_base, "uniclean_runtime", "runtime_summary.csv")
    os.makedirs(os.path.dirname(rt_summary_path), exist_ok=True)

    for size in sizes:
        n = min(size, len(dirty_full))
        dirty_sample = dirty_full.head(n).copy()

        for rep in range(1, n_reps + 1):
            run_dir = setup_run_dir(results_base, "uniclean_runtime", f"size{n}")
            print(f"[runtime] n={n}  rep={rep}")

            tmp_dirty = os.path.join(run_dir, "dirty_sample.csv")
            dirty_sample.to_csv(tmp_dirty, index=False)

            timed_out = False
            oom = False
            spark = None
            tracker = PeakMemoryTracker()

            try:
                spark = _get_spark(spark_memory)
                with tracker:
                    def _timeout(signum, frame):
                        raise TimeoutError()
                    signal.signal(signal.SIGALRM, _timeout)
                    signal.alarm(time_limit)
                    try:
                        _run_spark_cleaners(tmp_dirty, spark, run_dir)
                    finally:
                        signal.alarm(0)
            except TimeoutError:
                timed_out = True
            except MemoryError as exc:
                oom = True
                print(f"  [OOM] n={n}: {exc}", file=sys.stderr)
            except Exception as exc:  # noqa: BLE001
                print(f"  [error] n={n}: {exc}", file=sys.stderr)
            finally:
                if spark:
                    try:
                        spark.stop()
                    except Exception:  # noqa: BLE001
                        pass

            row = {
                "n_records":       n,
                "runtime_seconds": round(tracker.elapsed, 3),
                "peak_memory_mb":  round(tracker.peak_mb, 1),
                "timed_out":       timed_out,
                "oom":             oom,
                "repetition":      rep,
                "timestamp":       datetime.now().isoformat(),
            }
            file_exists = os.path.exists(rt_summary_path)
            with open(rt_summary_path, "a", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=list(row.keys()))
                if not file_exists:
                    writer.writeheader()
                writer.writerow(row)

            with open(os.path.join(run_dir, "run_config.json"), "w") as f:
                json.dump({"system": "uniclean", "n_records": n, "mode": "runtime",
                           "timed_out": timed_out, "oom": oom, "repetition": rep},
                          f, indent=2, default=str)

            print(f"  t={tracker.elapsed:.1f}s  mem={tracker.peak_mb:.0f}MB  "
                  f"timed_out={timed_out}  oom={oom}  -> {run_dir}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="UniClean address dataset effectiveness / runtime experiments.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--mode", choices=["effectiveness", "runtime"], required=True)
    parser.add_argument("--datasets-dir", default=EFFECTIVENESS_DIR,
                        help="Root of the effectiveness/ directory.")
    parser.add_argument("--results-dir", default=RESULTS_DIR)
    parser.add_argument("--spark-memory", default="80g",
                        help="Spark driver memory (e.g. 8g, 32g, 80g).")
    parser.add_argument("--time-limit", type=int, default=3600,
                        help="Per-run wall-clock time limit in seconds.")
    parser.add_argument("--n-reps", type=int, default=1,
                        help="Number of repetitions per dataset / size.")
    parser.add_argument("--filter", default=None,
                        help="Only run datasets whose name contains this substring (e.g. '0.51').")
    # Runtime-only
    parser.add_argument("--full-dirty", default=None,
                        help="Path to full dirty.csv for runtime sampling.")
    parser.add_argument("--full-clean", default=None,
                        help="Path to full clean.csv for runtime sampling.")
    parser.add_argument("--sizes", type=int, nargs="+",
                        default=[5000, 10000, 50000, 100000, 500000],
                        help="Dataset sizes to sample for the runtime experiment.")
    args = parser.parse_args()

    os.makedirs(args.results_dir, exist_ok=True)

    if args.mode == "effectiveness":
        datasets = list_effectiveness_datasets(args.datasets_dir)
        if args.filter:
            datasets = [d for d in datasets if args.filter in d["name"]]
        print(f"Found {len(datasets)} effectiveness dataset(s), {args.n_reps} rep(s)")
        for rep in range(1, args.n_reps + 1):
            print(f"=== Effectiveness repetition {rep}/{args.n_reps} ===")
            for ds in datasets:
                run_effectiveness(ds, args.results_dir, args.spark_memory, args.time_limit, rep)

    else:  # runtime
        full_dirty = args.full_dirty
        full_clean = args.full_clean
        # Auto-infer from the largest full/ sample if not specified
        if not full_dirty or not full_clean:
            full_dir = os.path.join(args.datasets_dir, "full")
            if os.path.isdir(full_dir):
                subs = sorted(os.listdir(full_dir))
                if subs:
                    last = os.path.join(full_dir, subs[-1])
                    full_dirty = full_dirty or os.path.join(last, "dirty.csv")
                    full_clean = full_clean or os.path.join(last, "clean.csv")
        if not full_dirty or not os.path.exists(full_dirty):
            parser.error(
                "--full-dirty is required for runtime mode "
                "(or effectiveness/full/*/dirty.csv must exist under --datasets-dir)"
            )
        run_runtime(full_dirty, full_clean, args.sizes, args.results_dir,
                    args.spark_memory, args.time_limit, args.n_reps)


if __name__ == "__main__":
    main()
