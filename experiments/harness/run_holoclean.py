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
import json
import os
import sys

import pandas as pd

EXPERIMENTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, EXPERIMENTS_DIR)

HOLOCLEAN_ROOT = os.path.normpath(os.path.join(EXPERIMENTS_DIR, "../baselines/holoclean"))
sys.path.insert(0, HOLOCLEAN_ROOT)

from runner_utils import (
    load_config, list_effectiveness_datasets, list_runtime_datasets,
    setup_run_dir, PeakMemoryTracker, purge_holoclean_db, log, log_error,
    get_memory_limit_mb, init_log_file,
)
from evaluate import evaluate, evaluate_detection, record_runtime, diff_repaired, normalize

_HOLOCLEAN_FDS_FALLBACK = os.path.normpath(
    os.path.join(EXPERIMENTS_DIR, "../rules/fds/fds_full_full_holoclean.txt")
)

# Postgres btree v4 rejects index entries larger than 2704 bytes. Index tuple
# overhead (~12B) is on top of the cell value, so a 2700B cell still fails
# (2712 > 2704). Leave clear headroom; truncate only for the HoloClean load.
_PG_BTREE_MAX_BYTES = 2704
_HOLOCLEAN_CELL_MAX_BYTES = 2500


def _truncate_utf8(value: str, max_bytes: int = _HOLOCLEAN_CELL_MAX_BYTES) -> str:
    """Truncate a string to at most max_bytes UTF-8 without splitting a codepoint."""
    raw = str(value).encode("utf-8")
    if len(raw) <= max_bytes:
        return str(value)
    truncated = raw[:max_bytes]
    while truncated:
        try:
            return truncated.decode("utf-8")
        except UnicodeDecodeError:
            truncated = truncated[:-1]
    return ""


# HoloClean stores each cell's domain as values joined with "|||". A cell that
# contains "|" (e.g. house_number "7 |") becomes "7 ||||…" and splits into "7 "
# plus an empty token; FreqFeaturizer then KeyErrors on '7 '.
_HOLOCLEAN_PIPE_REPL = "/"


def _prepare_holoclean_dirty(dirty_df: pd.DataFrame, out_csv: str) -> dict:
    """
    Write a HoloClean input CSV with cells truncated to fit Postgres btree indexes.
    Returns {n_truncated, cells, n_pipe_replaced, pipe_cells}.

    Cells are first passed through evaluate.normalize (HTML-unescape, whitespace collapse,
    strip, lower-case) so HoloClean sees the same case-insensitive values as the shared
    evaluation and Raha/Baran: a case-only difference is not an error.
    """
    out = dirty_df.copy().applymap(normalize)
    cells = []
    pipe_cells = []
    for j, col in enumerate(out.columns):
        for i in range(len(out)):
            val = str(out.iat[i, j])
            if "|" in val:
                val = val.replace("|", _HOLOCLEAN_PIPE_REPL)
                out.iat[i, j] = val
                pipe_cells.append((i, col))
            nbytes = len(val.encode("utf-8"))
            if nbytes <= _HOLOCLEAN_CELL_MAX_BYTES:
                continue
            new_val = _truncate_utf8(val)
            out.iat[i, j] = new_val
            cells.append((i, col, nbytes, len(new_val.encode("utf-8"))))
    out.to_csv(out_csv, index=False, encoding="utf-8")
    return {
        "n_truncated": len(cells),
        "cells": cells,
        "n_pipe_replaced": len(pipe_cells),
        "pipe_cells": pipe_cells,
    }


def _restore_untouched_preprocessed(
    dirty_df: pd.DataFrame,
    load_df: pd.DataFrame,
    repaired_df: pd.DataFrame,
    changed_cells: list,
) -> pd.DataFrame:
    """
    If HoloClean left a preprocessed cell as-is (equal to the load value),
    put the original dirty value back so evaluation does not count our preprocess
    as a HoloClean correction.

    *changed_cells* is a list of (row, col) or (row, col, …).
    """
    if not changed_cells:
        return repaired_df
    out = repaired_df.copy()
    for item in changed_cells:
        i, col = item[0], item[1]
        if col not in out.columns:
            continue
        if str(out.at[i, col]) == str(load_df.at[i, col]):
            out.at[i, col] = dirty_df.at[i, col]
    return out


def _db_cfg(sys_cfg: dict) -> dict:
    """Accept nested systems.holoclean.db or flat systems.holoclean.db_* keys."""
    if "db" in sys_cfg and isinstance(sys_cfg["db"], dict):
        raw = dict(sys_cfg["db"])
    else:
        raw = {
            "db_name": sys_cfg.get("db_name", "holo"),
            "db_user": sys_cfg.get("db_user", "holocleanuser"),
            "db_pwd_env": sys_cfg.get("db_pwd_env", "HOLOCLEAN_DB_PWD"),
            "db_pwd": sys_cfg.get("db_pwd"),
            "db_host": sys_cfg.get("db_host", "localhost"),
            "db_port": sys_cfg.get("db_port", "5432"),
        }
    return raw


def _db_password(db_cfg: dict) -> str:
    """
    Resolve DB password without prompting.
    Prefer config db_pwd, then env (db_pwd_env), then HoloClean's documented default.
    """
    if db_cfg.get("db_pwd"):
        return str(db_cfg["db_pwd"])
    env_name = db_cfg.get("db_pwd_env", "HOLOCLEAN_DB_PWD")
    from_env = os.environ.get(env_name, "")
    if from_env:
        return from_env
    # HoloClean README / create_pd_user default — never leave empty (psql would prompt).
    return "abcd1234"


def _sql_safe_name(name: str) -> str:
    """HoloClean uses the dataset name as a Postgres table name."""
    return name.replace(".", "_").replace("-", "_")


def _holoclean_fds_path(dataset_name: str, fds_dir: str) -> str:
    """Return FD file for dataset, mapping any subset to its canonical full-dataset FDs."""
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
    candidates = [
        os.path.join(fds_dir, f"fds_{canonical}_holoclean.txt"),
        os.path.join(EXPERIMENTS_DIR, "../rules/fds", f"fds_{canonical}_holoclean.txt"),
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return _HOLOCLEAN_FDS_FALLBACK


def _run_holoclean_session(dirty_path: str, dataset_name: str, fds_path: str, sys_cfg: dict):
    """
    Runs a full HoloClean pipeline on dirty_path.
    Returns repaired DataFrame or None on failure.
    """
    import holoclean
    from holoclean.detect import NullDetector, ViolationDetector
    from holoclean.repair.featurize import OccurAttrFeaturizer, FreqFeaturizer, ConstraintFeaturizer

    db_cfg = _db_cfg(sys_cfg)
    hc = holoclean.HoloClean(
        db_name=db_cfg["db_name"],
        db_user=db_cfg["db_user"],
        db_pwd=_db_password(db_cfg),
        db_host=db_cfg.get("db_host", "localhost"),
        db_port=db_cfg.get("db_port", 5432),
        threads=sys_cfg.get("threads", 4),
        timeout=sys_cfg.get("timeout", 3 * 60),
        verbose=False,
    ).session

    hc.load_data(_sql_safe_name(dataset_name), dirty_path)
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

    repaired = hc.ds.repaired_data
    # Dataset.repaired_data is a Table wrapper; evaluation needs a DataFrame.
    repaired_df = repaired.df if hasattr(repaired, "df") else repaired
    return repaired_df


def _dk_cells_from_session(hc, col_names):
    """Map HoloClean dk_cells (_tid_, attribute) to {(row, col_idx): ''}."""
    from holoclean.dataset.dataset import AuxTables

    table = hc.ds.aux_table.get(AuxTables.dk_cells)
    if table is None or getattr(table, "df", None) is None or table.df.empty:
        return {}, 0
    name_to_idx = {name: j for j, name in enumerate(col_names)}
    detected = {}
    n_unmapped = 0
    for rec in table.df.to_dict("records"):
        attr = rec.get("attribute")
        tid = rec.get("_tid_")
        if attr not in name_to_idx or tid is None:
            n_unmapped += 1
            continue
        detected[(int(tid), name_to_idx[attr])] = ""
    return detected, n_unmapped


def _empty_cells(dirty_df):
    """Cells whose normalized dirty value is empty — what NullDetector is meant to catch."""
    empty = {}
    for j in range(dirty_df.shape[1]):
        for i in range(dirty_df.shape[0]):
            if normalize(dirty_df.iloc[i, j]) == "":
                empty[(i, j)] = ""
    return empty


def _run_holoclean_detect_only(dirty_path: str, dataset_name: str, fds_path: str, sys_cfg: dict, col_names):
    """Load data + DCs, run NullDetector + ViolationDetector, return (dk_cells, n_unmapped)."""
    import holoclean
    from holoclean.detect import NullDetector, ViolationDetector

    db_cfg = _db_cfg(sys_cfg)
    hc = holoclean.HoloClean(
        db_name=db_cfg["db_name"],
        db_user=db_cfg["db_user"],
        db_pwd=_db_password(db_cfg),
        db_host=db_cfg.get("db_host", "localhost"),
        db_port=db_cfg.get("db_port", 5432),
        threads=sys_cfg.get("threads", 4),
        timeout=sys_cfg.get("timeout", 3 * 60),
        verbose=False,
    ).session

    hc.load_data(_sql_safe_name(dataset_name), dirty_path)
    hc.load_dcs(fds_path)
    hc.ds.set_constraints(hc.get_dcs())
    hc.detect_errors([NullDetector(), ViolationDetector()])
    return _dk_cells_from_session(hc, col_names)


def run_holoclean_detection(dataset: dict, cfg: dict, results_base: str, fds_dir: str, rep: int = 1):
    """Score HoloClean's native detection set (no repair)."""
    sys_cfg = cfg["systems"]["holoclean"]
    db_cfg = _db_cfg(sys_cfg)
    time_limit = cfg["experiment"]["time_limit_seconds"]
    fds_path = _holoclean_fds_path(dataset["name"], fds_dir)

    run_dir = setup_run_dir(results_base, "holoclean_detection", dataset["name"])
    log(f"HoloClean detection | {dataset['name']} | fds={os.path.basename(fds_path)}")

    dirty_df = pd.read_csv(dataset["dirty"], dtype=str, keep_default_na=False)
    clean_df = pd.read_csv(dataset["clean"], dtype=str, keep_default_na=False)
    load_csv = os.path.join(run_dir, "holoclean_dirty_load.csv")
    trunc_info = _prepare_holoclean_dirty(dirty_df, load_csv)
    if trunc_info["n_truncated"]:
        log(f"  Truncated {trunc_info['n_truncated']} oversize cell(s) for PG btree")
    if trunc_info.get("n_pipe_replaced"):
        log(f"  Replaced '|' in {trunc_info['n_pipe_replaced']} cell(s) (HoloClean domain delimiter)")

    purge_holoclean_db(
        db_cfg["db_name"],
        db_user=db_cfg["db_user"],
        db_host=db_cfg.get("db_host", "localhost"),
        db_port=str(db_cfg.get("db_port", "5432")),
        db_pwd=_db_password(db_cfg),
    )

    import signal
    timed_out = False
    detected = None
    n_unmapped = 0
    tracker = PeakMemoryTracker(limit_mb=get_memory_limit_mb(cfg))
    try:
        with tracker:
            def _timeout(signum, frame):
                raise TimeoutError()
            signal.signal(signal.SIGALRM, _timeout)
            signal.alarm(time_limit)
            try:
                detected, n_unmapped = _run_holoclean_detect_only(
                    load_csv, dataset["name"], fds_path, sys_cfg, list(dirty_df.columns)
                )
            finally:
                signal.alarm(0)
    except TimeoutError:
        timed_out = True
        log_error(f"  HoloClean detection timed out on {dataset['name']}")
    except Exception as e:
        log_error(f"  HoloClean detection failed on {dataset['name']}: {e}")

    empty = _empty_cells(dirty_df)
    official = detected or {}
    plus_empty = dict(empty)
    plus_empty.update(official)

    run_config = {
        "system": "holoclean_detection",
        "dataset": dataset["name"],
        "error_rate": dataset["error_rate"],
        "slice": dataset["slice"],
        "mode": "detection",
        "timed_out": timed_out,
        "repetition": rep,
        "fds_path": fds_path,
        "pg_btree_truncated_cells": trunc_info["n_truncated"],
        "n_pipe_replaced": trunc_info.get("n_pipe_replaced", 0),
        "n_dk_unmapped": n_unmapped,
        "n_detected_official": len(official),
        "n_empty_cells": len(empty),
        "n_detected_plus_empty": len(plus_empty),
        "n_official_that_are_empty": sum(1 for c in official if c in empty),
    }

    detections_path = os.path.join(run_dir, "detections.json")
    with open(detections_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "official": [list(c) for c in sorted(official)],
                "empty_cells": [list(c) for c in sorted(empty)],
            },
            f,
        )

    if detected is None or timed_out:
        record_runtime(run_dir, run_config, tracker.elapsed, tracker.peak_mb)
        with open(os.path.join(run_dir, "run_config.json"), "w") as f:
            json.dump(run_config, f, indent=2, default=str)
        return

    evaluate_detection(
        dirty_df=dirty_df,
        clean_df=clean_df,
        detected_cells=official,
        labeled_rows=set(),
        out_dir=run_dir,
        run_config=run_config,
        runtime_seconds=tracker.elapsed,
        peak_memory_mb=tracker.peak_mb,
    )

    plus_dir = os.path.join(run_dir, "plus_empty_nulls")
    plus_cfg = dict(run_config)
    plus_cfg["system"] = "holoclean_detection_plus_empty"
    plus_cfg["detection_variant"] = "official_union_empty"
    evaluate_detection(
        dirty_df=dirty_df,
        clean_df=clean_df,
        detected_cells=plus_empty,
        labeled_rows=set(),
        out_dir=plus_dir,
        run_config=plus_cfg,
        runtime_seconds=tracker.elapsed,
        peak_memory_mb=tracker.peak_mb,
    )
    log(
        f"  official={len(official)} empty={len(empty)} plus_empty={len(plus_empty)} "
        f"unmapped={n_unmapped} {tracker.elapsed:.1f}s -> {run_dir}"
    )


def run_holoclean_effectiveness(dataset: dict, cfg: dict, results_base: str, fds_dir: str, rep: int = 1):
    sys_cfg = cfg["systems"]["holoclean"]
    db_cfg = _db_cfg(sys_cfg)
    time_limit = cfg["experiment"]["time_limit_seconds"]

    run_dir = setup_run_dir(results_base, "holoclean", dataset["name"])
    log(f"HoloClean | {dataset['name']}")

    dirty_df = pd.read_csv(dataset["dirty"], dtype=str, keep_default_na=False)
    clean_df = pd.read_csv(dataset["clean"], dtype=str, keep_default_na=False)

    # Truncate rare oversize cells so Postgres btree CREATE INDEX succeeds (movies).
    load_csv = os.path.join(run_dir, "holoclean_dirty_load.csv")
    trunc_info = _prepare_holoclean_dirty(dirty_df, load_csv)
    load_df = pd.read_csv(load_csv, dtype=str, keep_default_na=False)
    if trunc_info["n_truncated"]:
        log(
            f"  Truncated {trunc_info['n_truncated']} oversize cell(s) for PG btree "
            f"(max {_HOLOCLEAN_CELL_MAX_BYTES} bytes): "
            + ", ".join(f"{c}@{r} {o}->{n}B" for r, c, o, n in trunc_info["cells"])
        )
    if trunc_info.get("n_pipe_replaced"):
        log(f"  Replaced '|' in {trunc_info['n_pipe_replaced']} cell(s) (HoloClean domain delimiter)")

    purge_holoclean_db(
        db_cfg["db_name"],
        db_user=db_cfg["db_user"],
        db_host=db_cfg.get("db_host", "localhost"),
        db_port=str(db_cfg.get("db_port", "5432")),
        db_pwd=_db_password(db_cfg),
    )

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
                repaired_df = _run_holoclean_session(
                    load_csv, dataset["name"], _holoclean_fds_path(dataset["name"], fds_dir), sys_cfg
                )
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
        "pg_btree_truncated_cells": trunc_info["n_truncated"],
        "n_pipe_replaced": trunc_info.get("n_pipe_replaced", 0),
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
    repaired_df = _restore_untouched_preprocessed(
        dirty_df, load_df, repaired_df, trunc_info["cells"] + trunc_info.get("pipe_cells", [])
    )

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


def run_holoclean_runtime(dataset: dict, cfg: dict, results_base: str, fds_dir: str, rep: int = 1):
    """Time HoloClean on dirty.csv. clean.csv is GT only (not an input)."""
    sys_cfg = cfg["systems"]["holoclean"]
    db_cfg = _db_cfg(sys_cfg)
    time_limit = cfg["experiment"]["time_limit_seconds"]
    fds_path = _holoclean_fds_path(dataset["name"], fds_dir)

    import signal
    run_dir = setup_run_dir(results_base, "holoclean_runtime", dataset["name"])
    log(f"HoloClean runtime | {dataset['name']} | n={dataset['n_records']} | rep={rep}")

    purge_holoclean_db(
        db_cfg["db_name"],
        db_user=db_cfg["db_user"],
        db_host=db_cfg.get("db_host", "localhost"),
        db_port=str(db_cfg.get("db_port", "5432")),
        db_pwd=_db_password(db_cfg),
    )

    load_csv = os.path.join(run_dir, "holoclean_load.csv")
    src_df = pd.read_csv(dataset["dirty"], dtype=str, keep_default_na=False)
    trunc_info = _prepare_holoclean_dirty(src_df, load_csv)
    if trunc_info["n_truncated"]:
        log(f"  Truncated {trunc_info['n_truncated']} oversize cell(s) for PG btree")
    if trunc_info.get("n_pipe_replaced"):
        log(f"  Replaced '|' in {trunc_info['n_pipe_replaced']} cell(s) (HoloClean domain delimiter)")

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
                _run_holoclean_session(load_csv, dataset["name"], fds_path, sys_cfg)
            finally:
                signal.alarm(0)
    except TimeoutError:
        timed_out = True
    except MemoryError as e:
        oom = True
        log_error(f"  HoloClean OOM on {dataset['name']}: {e}")
    except Exception as e:
        log_error(f"  HoloClean failed: {e}")

    run_config = {
        "system": "holoclean",
        "dataset": dataset["name"],
        "n_records": dataset["n_records"],
        "mode": "runtime",
        "repetition": rep,
        "timed_out": timed_out,
        "oom": oom,
        "pg_btree_truncated_cells": trunc_info["n_truncated"],
        "n_pipe_replaced": trunc_info.get("n_pipe_replaced", 0),
    }
    record_runtime(run_dir, run_config, tracker.elapsed, tracker.peak_mb)
    log(f"  -> {tracker.elapsed:.1f}s  {tracker.peak_mb:.0f}MB  timed_out={timed_out}  oom={oom}")
    return timed_out or oom


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["effectiveness", "runtime", "detection"], required=True)
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
    init_log_file(os.path.join(args.results_dir, f"holoclean_{args.mode}.log"))
    if not cfg["systems"]["holoclean"]["enabled"]:
        log("HoloClean disabled in config")
        return

    fds_dir = os.path.join(args.datasets_dir, "fds")

    if args.mode == "detection":
        datasets = list_effectiveness_datasets(cfg, args.datasets_dir)
        if args.filter_datasets:
            filters = [f.strip() for f in args.filter_datasets.split(",") if f.strip()]
            datasets = [ds for ds in datasets if any(f in ds["name"] for f in filters)]
        log(f"Found {len(datasets)} detection datasets")
        for ds in datasets:
            run_holoclean_detection(ds, cfg, args.results_dir, fds_dir, rep=1)
    elif args.mode == "effectiveness":
        n_reps = args.reps if args.reps is not None else cfg.get("experiment", {}).get("n_effectiveness_runs", 3)
        last_rep = args.first_rep + n_reps - 1
        datasets = list_effectiveness_datasets(cfg, args.datasets_dir)
        if args.filter_datasets:
            filters = [f.strip() for f in args.filter_datasets.split(",") if f.strip()]
            datasets = [ds for ds in datasets if any(f in ds["name"] for f in filters)]
        log(f"Found {len(datasets)} effectiveness datasets, repetitions {args.first_rep}-{last_rep}")
        for rep in range(args.first_rep, last_rep + 1):
            log(f"=== Effectiveness repetition {rep}/{last_rep} ===")
            for ds in datasets:
                run_holoclean_effectiveness(ds, cfg, args.results_dir, fds_dir, rep=rep)
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
                if run_holoclean_runtime(ds, cfg, args.results_dir, fds_dir, rep=rep):
                    log("HoloClean timeout/OOM — skipping remaining sizes and repetitions")
                    return


if __name__ == "__main__":
    main()
