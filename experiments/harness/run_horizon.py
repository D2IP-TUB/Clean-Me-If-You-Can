"""
run_horizon.py — compile and run the Java Horizon system.

Compiles src/*.java once (cached in build/), then for each dataset:
  java Graph dirty.csv clean.csv fds_address_indexed.txt 3

Horizon writes the repaired CSV as: {clean_path}.a{algo}.clean
We then diff dirty vs repaired to get detected+corrected cells.
"""

import argparse
import csv
import os
import shutil
import subprocess
import sys
import time

import pandas as pd

EXPERIMENTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, EXPERIMENTS_DIR)

from runner_utils import (
    load_config, list_effectiveness_datasets, list_runtime_datasets,
    setup_run_dir, run_with_timeout, log, log_error,
    get_memory_limit_mb, init_log_file,
)
from evaluate import evaluate, record_runtime, diff_repaired, normalize

BUILD_DIR = os.path.join(EXPERIMENTS_DIR, "horizon_build")


def _fds_path(dataset_name: str, fds_dir: str) -> str:
    """Return indexed FD file for dataset, mapping any subset to its canonical full-dataset FDs."""
    if dataset_name.startswith("de_"):
        canonical = "de_full"
    elif dataset_name.startswith("full_"):
        canonical = "full_full"
    elif dataset_name.startswith("russia_"):
        canonical = "russia_full"
    elif dataset_name.startswith("books_"):
        canonical = "books"
    elif dataset_name.startswith("movies_"):
        canonical = "movies"
    else:
        canonical = dataset_name  # poi_Library, poi_ShoppingCenter, etc.
    return os.path.join(fds_dir, f"fds_{canonical}_indexed.txt")


def _sanitize_csv_for_horizon(src_path: str, dst_path: str) -> None:
    """Write src_path with embedded newlines in field values replaced by a space.

    Horizon reads CSV files strictly line-by-line (BufferedReader.readLine) and
    its parseCsvLine cannot handle RFC-4180 multi-line quoted fields.  When such
    a field is encountered, parseCsvLine returns a truncated row with fewer
    columns than expected, causing ArrayIndexOutOfBoundsException in
    Pattern.addPattern (or a malformed output CSV).  Replacing the embedded
    newlines with a space     makes every logical row fit on one physical line.

    Data cells are also passed through evaluate.normalize (HTML-unescape, whitespace
    collapse, strip, lower-case) so Horizon sees the same case-insensitive values as the
    shared evaluation and as Raha/Baran (a case-only difference is not an error). The header
    row is left untouched.
    """
    with open(src_path, "r", encoding="utf-8", newline="") as fin, \
         open(dst_path, "w", encoding="utf-8", newline="") as fout:
        reader = csv.reader(fin)
        writer = csv.writer(fout, lineterminator="\n")
        for i, row in enumerate(reader):
            if i == 0:
                writer.writerow([val.replace("\r\n", " ").replace("\r", " ").replace("\n", " ") for val in row])
                continue
            writer.writerow([normalize(val.replace("\r\n", " ").replace("\r", " ")) for val in row])


def compile_horizon(cfg: dict) -> bool:
    """Compile Horizon Java sources. Returns True on success."""
    jar = os.path.normpath(os.path.join(EXPERIMENTS_DIR, cfg["systems"]["horizon"]["jar"]))
    src_dir = os.path.normpath(os.path.join(EXPERIMENTS_DIR, cfg["systems"]["horizon"]["src_dir"]))

    os.makedirs(BUILD_DIR, exist_ok=True)
    stamp = os.path.join(BUILD_DIR, ".compiled")

    # Re-compile if any source file is newer than the stamp
    if os.path.exists(stamp):
        stamp_time = os.path.getmtime(stamp)
        sources = [f for f in os.listdir(src_dir) if f.endswith(".java")]
        if all(os.path.getmtime(os.path.join(src_dir, s)) <= stamp_time for s in sources):
            log("Horizon already compiled, skipping")
            return True

    sources = [os.path.join(src_dir, f) for f in os.listdir(src_dir) if f.endswith(".java")]
    cmd = ["javac", "-cp", jar, "-d", BUILD_DIR] + sources
    log(f"Compiling Horizon: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        log_error(f"Horizon compilation failed:\n{result.stderr}")
        return False
    open(stamp, "w").close()
    log("Horizon compiled successfully")
    return True


def run_horizon_on_dataset(
    dirty_path: str,
    clean_path: str,
    fds_path: str,
    algo: int,
    cfg: dict,
    run_dir: str,
    time_limit: int,
    memory_limit_mb: float = None,
) -> dict:
    """
    Run Java Graph and return {runtime_seconds, peak_memory_mb, timed_out, oom, repaired_path}.
    Horizon writes repaired CSV to {clean_path}.a{algo}.clean
    """
    jar = os.path.normpath(os.path.join(EXPERIMENTS_DIR, cfg["systems"]["horizon"]["jar"]))
    # Use absolute paths so Java resolves them correctly regardless of cwd.
    abs_dirty = os.path.abspath(dirty_path)
    abs_clean = os.path.abspath(clean_path)
    abs_fds   = os.path.abspath(fds_path)
    cmd = [
        "java", "-cp", f"{BUILD_DIR}{os.pathsep}{jar}",
        "Graph",
        abs_dirty,
        abs_clean,
        abs_fds,
        str(algo),
    ]
    stdout_log = os.path.join(run_dir, "stdout.log")
    stderr_log = os.path.join(run_dir, "stderr.log")

    result = run_with_timeout(
        cmd=cmd,
        cwd=os.path.dirname(abs_dirty),
        env=os.environ.copy(),
        time_limit=time_limit,
        stdout_log=stdout_log,
        stderr_log=stderr_log,
        memory_limit_mb=memory_limit_mb,
    )

    repaired_path = f"{abs_clean}.a{algo}.clean"
    result["repaired_path"] = repaired_path
    return result


def run_horizon_effectiveness(
    dataset: dict,
    cfg: dict,
    results_base: str,
    fds_dir: str,
    rep: int = 1,
    time_limit: int = None,
) -> bool:
    """Return True on success, False on any failure.

    time_limit: seconds; None means no wall-clock limit (proc.wait forever).
    """
    sys_cfg = cfg["systems"]["horizon"]
    algo = sys_cfg["algo"]
    if time_limit is None:
        time_limit = cfg["experiment"]["time_limit_seconds"]

    fds_indexed = _fds_path(dataset["name"], fds_dir)
    if not os.path.exists(fds_indexed):
        # Preflight already reported this; callers track it — just return False silently.
        return False

    run_dir = setup_run_dir(results_base, "horizon", dataset["name"])
    log(f"Horizon | {dataset['name']}")

    # Sanitize dirty/clean CSVs: replace embedded newlines in field values with
    # a space so that Horizon's line-by-line CSV reader sees one row per line.
    sanitize_dir = os.path.join(run_dir, "sanitized")
    os.makedirs(sanitize_dir, exist_ok=True)
    sanitized_dirty = os.path.join(sanitize_dir, "dirty.csv")
    sanitized_clean = os.path.join(sanitize_dir, "clean.csv")
    _sanitize_csv_for_horizon(dataset["dirty"], sanitized_dirty)
    _sanitize_csv_for_horizon(dataset["clean"], sanitized_clean)

    result = run_horizon_on_dataset(
        sanitized_dirty, sanitized_clean, fds_indexed, algo, cfg, run_dir, time_limit,
        memory_limit_mb=get_memory_limit_mb(cfg),
    )

    run_config = {
        "system": "horizon",
        "dataset": dataset["name"],
        "error_rate": dataset["error_rate"],
        "slice": dataset["slice"],
        "algo": algo,
        "mode": "effectiveness",
        "timed_out": result["timed_out"],
        "oom": result["oom"],
        "repetition": rep,
    }

    if result["timed_out"] or result["oom"] or result["returncode"] != 0:
        if result["timed_out"]:
            log_error(f"  Horizon timed out on {dataset['name']}")
        elif result["oom"]:
            log_error(f"  Horizon OOM on {dataset['name']} ({result['peak_memory_mb']:.0f} MB)")
            stderr_log = os.path.join(run_dir, "stderr.log")
            hint = ""
            if os.path.exists(stderr_log):
                try:
                    lines = open(stderr_log).read().strip().splitlines()
                    # Show first meaningful line (skip blank / WARNING lines)
                    for ln in lines:
                        ln = ln.strip()
                        if ln and not ln.startswith("WARNING"):
                            hint = f" — {ln[:200]}"
                            break
                except OSError:
                    pass
            log_error(f"  Horizon crashed on {dataset['name']} (exit {result['returncode']}){hint}")
        record_runtime(run_dir, run_config, result["runtime_seconds"], result["peak_memory_mb"])
        return False

    repaired_path = result["repaired_path"]
    if not os.path.exists(repaired_path):
        log_error(f"  Horizon repaired file not found: {repaired_path}")
        return False

    dirty_df = pd.read_csv(sanitized_dirty, dtype=str, keep_default_na=False)
    clean_df = pd.read_csv(sanitized_clean, dtype=str, keep_default_na=False)
    repaired_df = pd.read_csv(repaired_path, dtype=str, keep_default_na=False, header=None)

    # Horizon writes no header — assign column names from dirty
    if len(repaired_df.columns) == len(dirty_df.columns):
        repaired_df.columns = dirty_df.columns
    else:
        log_error(f"  Column count mismatch: dirty={len(dirty_df.columns)} repaired={len(repaired_df.columns)}")
        return False

    changed_cells = diff_repaired(dirty_df, repaired_df)

    evaluate(
        dirty_df=dirty_df,
        clean_df=clean_df,
        detected_cells=changed_cells,
        corrected_cells=changed_cells,
        labeled_rows=set(),
        out_dir=run_dir,
        run_config=run_config,
        runtime_seconds=result["runtime_seconds"],
        peak_memory_mb=result["peak_memory_mb"],
    )
    log(f"  -> {run_dir}")
    return True


def run_horizon_runtime(dataset: dict, cfg: dict, results_base: str, fds_dir: str, rep: int = 1) -> bool:
    """Time Horizon on dirty.csv; clean.csv is the GT reference only."""
    sys_cfg = cfg["systems"]["horizon"]
    algo = sys_cfg["algo"]
    time_limit = cfg["experiment"]["time_limit_seconds"]

    fds_indexed = _fds_path(dataset["name"], fds_dir)
    if not os.path.exists(fds_indexed):
        return False  # already reported by preflight

    run_dir = setup_run_dir(results_base, "horizon_runtime", dataset["name"])
    log(f"Horizon runtime | {dataset['name']} | n={dataset['n_records']} | rep={rep}")

    sanitize_dir = os.path.join(run_dir, "sanitized")
    os.makedirs(sanitize_dir, exist_ok=True)
    sanitized_dirty = os.path.join(sanitize_dir, "dirty.csv")
    sanitized_clean = os.path.join(sanitize_dir, "clean.csv")
    _sanitize_csv_for_horizon(dataset["dirty"], sanitized_dirty)
    _sanitize_csv_for_horizon(dataset["clean"], sanitized_clean)

    result = run_horizon_on_dataset(
        sanitized_dirty, sanitized_clean, fds_indexed, algo, cfg, run_dir, time_limit,
        memory_limit_mb=get_memory_limit_mb(cfg),
    )

    repaired_path = result.get("repaired_path", "")
    if os.path.exists(repaired_path):
        os.remove(repaired_path)

    run_config = {
        "system": "horizon",
        "dataset": dataset["name"],
        "n_records": dataset["n_records"],
        "algo": algo,
        "mode": "runtime",
        "repetition": rep,
        "timed_out": result["timed_out"],
        "oom": result["oom"],
    }
    record_runtime(run_dir, run_config, result["runtime_seconds"], result["peak_memory_mb"])
    log(f"  -> {result['runtime_seconds']:.1f}s  {result['peak_memory_mb']:.0f}MB  oom={result['oom']}")
    if result["timed_out"] or result["oom"] or result["returncode"] != 0:
        return False
    return True


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
    parser.add_argument("--time-limit", type=int, default=None,
                        help="Override wall-clock seconds; use -1 for no limit")
    args = parser.parse_args()

    cfg = load_config(args.config)
    if args.time_limit is not None:
        # None disables the subprocess timeout; keep a sentinel in cfg only for logging.
        cfg.setdefault("experiment", {})["time_limit_seconds"] = (
            None if args.time_limit < 0 else args.time_limit
        )
    os.makedirs(args.results_dir, exist_ok=True)
    init_log_file(os.path.join(args.results_dir, f"horizon_{args.mode}.log"))
    if not cfg["systems"]["horizon"]["enabled"]:
        log("Horizon disabled in config")
        return

    if not compile_horizon(cfg):
        sys.exit(1)

    fds_dir = os.path.join(args.datasets_dir, "fds")

    if args.mode == "effectiveness":
        datasets = list_effectiveness_datasets(cfg, args.datasets_dir)
    else:
        datasets = list_runtime_datasets(cfg, args.datasets_dir)

    if args.filter_datasets:
        filters = [f.strip() for f in args.filter_datasets.split(",") if f.strip()]
        datasets = [ds for ds in datasets if any(f in ds["name"] for f in filters)]

    # ── Preflight: check all required FD index files before running anything ──
    missing_fds = [
        ds for ds in datasets if not os.path.exists(_fds_path(ds["name"], fds_dir))
    ]
    if missing_fds:
        log_error(
            f"{len(missing_fds)}/{len(datasets)} datasets are missing FD index files "
            "— run prepare_rules.py first:"
        )
        for ds in missing_fds:
            log_error(f"  missing: {_fds_path(ds['name'], fds_dir)}")
        if len(missing_fds) == len(datasets):
            log_error("All datasets missing FD files — aborting Horizon.")
            sys.exit(1)
        log(f"Skipping {len(missing_fds)} dataset(s); running the remaining {len(datasets) - len(missing_fds)}.")

    # ── Run ──────────────────────────────────────────────────────────────────
    n_ok = n_fail = 0
    if args.mode == "effectiveness":
        n_reps = args.reps if args.reps is not None else cfg.get("experiment", {}).get("n_effectiveness_runs", 3)
        last_rep = args.first_rep + n_reps - 1
        log(f"Found {len(datasets)} effectiveness datasets, repetitions {args.first_rep}-{last_rep}")
        eff_time_limit = cfg.get("experiment", {}).get("time_limit_seconds")
        if eff_time_limit is None:
            log("Horizon wall-clock time limit: none")
        else:
            log(f"Horizon wall-clock time limit: {eff_time_limit}s")
        for rep in range(args.first_rep, last_rep + 1):
            log(f"=== Effectiveness repetition {rep}/{last_rep} ===")
            for ds in datasets:
                if run_horizon_effectiveness(
                    ds, cfg, args.results_dir, fds_dir, rep=rep, time_limit=eff_time_limit
                ):
                    n_ok += 1
                else:
                    n_fail += 1
    else:
        n_reps = args.reps if args.reps is not None else cfg.get("experiment", {}).get("n_runtime_runs", 1)
        last_rep = args.first_rep + n_reps - 1
        log(f"Found {len(datasets)} runtime datasets, repetitions {args.first_rep}-{last_rep}")
        for rep in range(args.first_rep, last_rep + 1):
            log(f"=== Runtime repetition {rep}/{last_rep} ===")
            for ds in datasets:
                if run_horizon_runtime(ds, cfg, args.results_dir, fds_dir, rep=rep):
                    n_ok += 1
                else:
                    n_fail += 1
                    log("Horizon timeout/OOM/fail — skipping remaining sizes and repetitions")
                    break
            else:
                continue
            break

    log(f"Horizon {args.mode}: {n_ok} OK, {n_fail} failed/skipped out of {len(datasets)}")
    if n_fail > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
