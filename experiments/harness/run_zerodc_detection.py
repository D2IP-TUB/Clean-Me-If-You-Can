"""
run_zerodc_detection.py — harness wrapper for ZeroDC's detection stage ONLY.

ZeroDC/detection.py learns per-column Python detection rules with an LLM.
Each column gets 5 refinement rounds; every round an (oracle) user labels one
suspected-dirty and one suspected-clean cell (~10 labelled cells per column),
which are fed back to the LLM to repair the rules.

This runner:
  1. Writes dirty.csv, an "oracle clean" csv, and a 0/1 ground-truth mask.
     The oracle clean csv keeps the dirty value wherever harness normalize()
     says dirty == clean (capitalisation / whitespace only), so the simulated
     user feedback agrees with how every other system is scored.
  2. Runs ZeroDC/detection.py as a subprocess (cwd = ZeroDC dir).
  3. Maps <dataset>_final_detection.csv to detected cells and calls evaluate()
     with corrected_cells=None (detection-only metrics).

Results: results/zerodc_detection/<dataset>_<timestamp>/
"""

import argparse
import json
import os
import shutil
import sys

import pandas as pd

EXPERIMENTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, EXPERIMENTS_DIR)

from runner_utils import (  # noqa: E402
    load_config, list_effectiveness_datasets, setup_run_dir, PeakMemoryTracker,
    run_with_timeout, log, log_error, get_memory_limit_mb, init_log_file, resolve,
)
from evaluate import evaluate, get_actual_errors, normalize, record_runtime  # noqa: E402

SYSTEM_NAME = "zerodc_detection"
SMOKE_SYSTEM_NAME = "zerodc_detection_smoke"  # --max-rows runs; not picked up by collect_results.py
GEMINI_OPENAI_BASE = "https://generativelanguage.googleapis.com/v1beta/openai/"


def _zerodc_dir(cfg: dict) -> str:
    rel = cfg.get("systems", {}).get("zerodc", {}).get("zerodc_dir", "../baselines/ZeroDC")
    return resolve(cfg, rel)


def _write_inputs(dirty_df, clean_df, work_dir):
    """Return (dirty_path, clean_oracle_path, mask_path, n_err)."""
    clean_oracle = clean_df.copy()
    mask = pd.DataFrame(0, index=range(len(dirty_df)), columns=dirty_df.columns)
    n_err = 0
    for j in range(dirty_df.shape[1]):
        for i in range(dirty_df.shape[0]):
            d, c = str(dirty_df.iat[i, j]), str(clean_df.iat[i, j])
            if normalize(d) != normalize(c):
                mask.iat[i, j] = 1
                n_err += 1
            else:
                clean_oracle.iat[i, j] = d  # treat case/whitespace-only diffs as clean
    dirty_path = os.path.join(work_dir, "dirty.csv")
    clean_path = os.path.join(work_dir, "clean_oracle.csv")
    mask_path = os.path.join(work_dir, "perfect_error_detection.csv")
    dirty_df.to_csv(dirty_path, index=False, encoding="utf-8")
    clean_oracle.to_csv(clean_path, index=False, encoding="utf-8")
    mask.to_csv(mask_path, index=False, encoding="utf-8")
    return dirty_path, clean_path, mask_path, n_err


def _label_counts(feedback_log_path) -> dict:
    """Actual labelled cells / distinct rows from the feedback log (budget audit)."""
    cells, rows = set(), set()
    if os.path.exists(feedback_log_path):
        try:
            fb = json.load(open(feedback_log_path, encoding="utf-8"))
            for col, iterations in fb.items():
                for it in iterations:
                    for s in it.get("samples", []):
                        if isinstance(s.get("row_idx"), int):
                            cells.add((col, s["row_idx"]))
                            rows.add(s["row_idx"])
        except Exception:
            pass
    return {"labeled_cells": len(cells), "labeled_distinct_rows": len(rows)}


def _labeled_cells(feedback_log_path, columns) -> set:
    """{(row, col_idx)} of every cell the simulated user labelled."""
    cells = set()
    col_idx = {c: j for j, c in enumerate(columns)}
    if os.path.exists(feedback_log_path):
        try:
            fb = json.load(open(feedback_log_path, encoding="utf-8"))
            for col, iterations in fb.items():
                for it in iterations:
                    for s in it.get("samples", []):
                        if isinstance(s.get("row_idx"), int) and col in col_idx:
                            cells.add((s["row_idx"], col_idx[col]))
        except Exception:
            pass
    return cells


def _labeled_rows(feedback_log_path) -> set:
    rows = set()
    if not os.path.exists(feedback_log_path):
        return rows
    try:
        fb = json.load(open(feedback_log_path, encoding="utf-8"))
        for iterations in fb.values():
            for it in iterations:
                for s in it.get("samples", []):
                    if isinstance(s.get("row_idx"), int):
                        rows.add(s["row_idx"])
    except Exception:
        pass
    return rows


def run_one(dataset: dict, cfg: dict, args, results_base: str, rep: int = 1):
    time_limit = None  # LLM jobs: no 10 h wall-clock cap
    system_name = SMOKE_SYSTEM_NAME if args.max_rows else SYSTEM_NAME
    run_dir = setup_run_dir(results_base, system_name, dataset["name"])
    work_dir = os.path.join(run_dir, "zerodc_io")
    os.makedirs(work_dir, exist_ok=True)
    log(f"ZeroDC detection | {dataset['name']} | model={args.model}")

    dirty_df = pd.read_csv(dataset["dirty"], dtype=str, keep_default_na=False)
    clean_df = pd.read_csv(dataset["clean"], dtype=str, keep_default_na=False)
    if args.max_rows and len(dirty_df) > args.max_rows:
        dirty_df = dirty_df.iloc[: args.max_rows].reset_index(drop=True)
        clean_df = clean_df.iloc[: args.max_rows].reset_index(drop=True)
        log(f"  [smoke] truncated to first {args.max_rows} rows")

    dirty_path, clean_path, mask_path, n_err = _write_inputs(dirty_df, clean_df, work_dir)
    log(f"  actual error cells (harness-normalised): {n_err}")

    env = os.environ.copy()
    key = env.get(args.api_key_env) or env.get("GOOGLE_GENAI_API_KEY")
    if not key:
        log_error(f"  No API key in ${args.api_key_env}; skipping.")
        return
    env["ZERODC_API_KEY"] = key
    env["PYTHONIOENCODING"] = "utf-8"
    env["MPLBACKEND"] = "Agg"

    name = "ds"
    cmd = [
        sys.executable, "detection.py",
        "--dataset", name,
        "--dirty_path", os.path.abspath(dirty_path),
        "--clean_path", os.path.abspath(clean_path),
        "--detection_path", os.path.abspath(mask_path),
        "--out_dir", os.path.abspath(work_dir),
        "--model", args.model,
        "--api_base", args.api_base,
        "--api_key_env", "ZERODC_API_KEY",
        "--embed_backend", args.embed_backend,
        "--max_workers", str(args.max_workers),
        "--rounds", str(args.rounds),
    ]
    # Always read verbatim (no pandas NA guessing). With --empty-as null, only cells that are exactly ''
    # become the string 'null' (ZeroDC's prompts/sampling are built around that token).
    cmd.append("--keep_empty")
    if args.empty_as == "null":
        cmd += ["--empty_token", "null"]

    tracker = PeakMemoryTracker(limit_mb=get_memory_limit_mb(cfg))
    result, failed = {}, False
    try:
        with tracker:
            result = run_with_timeout(
                cmd=cmd, cwd=_zerodc_dir(cfg), env=env, time_limit=time_limit,
                stdout_log=os.path.join(work_dir, "zerodc_stdout.log"),
                stderr_log=os.path.join(work_dir, "zerodc_stderr.log"),
                memory_limit_mb=get_memory_limit_mb(cfg),
            )
        if result.get("returncode", 1) != 0:
            failed = True
            log_error(f"  detection.py exited {result.get('returncode')} (see {work_dir}/zerodc_stderr.log)")
    except Exception as e:  # noqa: BLE001
        failed = True
        log_error(f"  ZeroDC detection failed: {e}")

    run_config = {
        "system": system_name,
        "dataset": dataset["name"],
        "error_rate": dataset["error_rate"],
        "slice": dataset["slice"],
        "mode": "effectiveness",
        "task": "detection",
        "llm_model": args.model,
        "api_base": args.api_base,
        "timed_out": bool(result.get("timed_out")),
        "oom": bool(result.get("oom")),
        "failed": failed,
        "repetition": rep,
        "max_rows": args.max_rows,
        "rounds": args.rounds,
        "empty_cells_as": args.empty_as,
        "label_override": not args.no_label_override,
        "oracle_labels": f"{args.rounds} dirty + {args.rounds} clean cells per column via simulated user",
    }

    det_path = os.path.join(work_dir, f"{name}_final_detection.csv")
    runtime = result.get("runtime_seconds", tracker.elapsed)
    peak = result.get("peak_memory_mb", tracker.peak_mb)
    if not os.path.exists(det_path):
        record_runtime(run_dir, run_config, runtime, peak)
        log(f"  -> {run_dir} (no final_detection.csv; failed run)")
        return

    run_config.update(_label_counts(os.path.join(work_dir, f"{name}_feedback_log.json")))
    log(f"  labels used: {run_config['labeled_cells']} cells over "
        f"{run_config['labeled_distinct_rows']} distinct rows")
    det = pd.read_csv(det_path)
    detected = {}
    for j in range(det.shape[1]):
        col = det.iloc[:, j].fillna(0).astype(int).values
        for i in range(len(col)):
            if col[i] == 1:
                detected[(i, j)] = ""

    # Raha (detection.py: `i in labeled_tuples and extended_labeled_cells[(i, j)]`) replaces the
    # classifier's prediction on user-labelled cells with the user's label. Do the same here:
    # a labelled cell is detected iff it is truly an error. Labelled cells stay in the evaluation
    # (nothing is excluded), exactly as in evaluate().
    actual = get_actual_errors(dirty_df, clean_df)
    raw_tp = sum(1 for c in detected if c in actual)
    run_config["raw_n_detected"] = len(detected)
    run_config["raw_det_precision"] = raw_tp / len(detected) if detected else 0.0
    run_config["raw_det_recall"] = raw_tp / len(actual) if actual else 0.0
    _p, _r = run_config["raw_det_precision"], run_config["raw_det_recall"]
    run_config["raw_det_f1"] = 2 * _p * _r / (_p + _r) if (_p + _r) else 0.0
    if not args.no_label_override:
        lab_cells = _labeled_cells(os.path.join(work_dir, f"{name}_feedback_log.json"), dirty_df.columns)
        flipped = 0
        for cell in lab_cells:
            is_err = cell in actual
            if is_err and cell not in detected:
                detected[cell] = ""
                flipped += 1
            elif not is_err and cell in detected:
                del detected[cell]
                flipped += 1
        run_config["label_override_flipped_cells"] = flipped
        log(f"  label override: {len(lab_cells)} labelled cells, {flipped} predictions changed")

    skip_path = os.path.join(work_dir, "skipped_columns.json")
    if os.path.exists(skip_path):
        run_config["skipped_columns"] = json.load(open(skip_path, encoding="utf-8"))
        log(f"  skipped initial rules: {list(run_config['skipped_columns'])}")

    for fname in (f"{name}_rules.json", "initial_rules.json", f"{name}_feedback_log.json",
                  f"{name}_final_detection.csv", "skipped_columns.json",
                  "zerodc_stdout.log", "zerodc_stderr.log"):
        src = os.path.join(work_dir, fname)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(run_dir, fname))

    evaluate(
        dirty_df=dirty_df, clean_df=clean_df,
        detected_cells=detected, corrected_cells=None,
        labeled_rows=_labeled_rows(os.path.join(work_dir, f"{name}_feedback_log.json")),
        out_dir=run_dir, run_config=run_config,
        runtime_seconds=runtime, peak_memory_mb=peak,
    )
    log(f"  -> {run_dir}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--config", default=os.path.join(EXPERIMENTS_DIR, "config.json"))
    p.add_argument("--datasets-dir", default=os.path.join(EXPERIMENTS_DIR, "experiment_datasets"))
    p.add_argument("--results-dir", default=os.path.join(EXPERIMENTS_DIR, "results"))
    p.add_argument("--filter-datasets", default=None,
                   help="Comma-separated substrings; only matching dataset names run")
    p.add_argument("--reps", type=int, default=1)
    p.add_argument("--first-rep", type=int, default=1)
    p.add_argument("--model", default="gemini-2.5-flash-lite",
                   help="Same model as the earlier ZeroDCcorrection run by default")
    p.add_argument("--api-base", default=GEMINI_OPENAI_BASE)
    p.add_argument("--api-key-env", default="GOOGLE_API_KEY")
    p.add_argument("--embed-backend", choices=["onnx", "torch"], default="torch",
                   help="torch = CPU-safe; onnx uses the bundled fp16 model_O4.onnx (GPU-oriented)")
    p.add_argument("--max-workers", type=int, default=8)
    p.add_argument("--rounds", type=int, default=10,
                   help="Feedback rounds per column; each labels 1 dirty + 1 clean cell. "
                        "10 -> 20 cells/column = 160 cells on 8 columns = a 20-tuple budget "
                        "in cell terms (Raha: 20 tuples x 8 columns).")
    p.add_argument("--empty-as", choices=["empty", "null"], default="null",
                   help="null (default, upstream ZeroDC behaviour): empty cells are shown to ZeroDC as the "
                        "string 'null'; empty: they stay ''. Scoring always uses the real '' data.")
    p.add_argument("--no-label-override", action="store_true",
                   help="Do not overwrite predictions on user-labelled cells with their true label "
                        "(Raha does overwrite; default here is to match Raha)")
    p.add_argument("--max-rows", type=int, default=0, help="Smoke test: truncate to first N rows")
    p.add_argument("--list", action="store_true", help="List datasets and exit")
    args = p.parse_args()

    cfg = load_config(args.config)
    os.makedirs(args.results_dir, exist_ok=True)
    init_log_file(os.path.join(args.results_dir, f"{SYSTEM_NAME}_effectiveness.log"))

    datasets = list_effectiveness_datasets(cfg, args.datasets_dir)
    if args.filter_datasets:
        fl = [f.strip() for f in args.filter_datasets.split(",") if f.strip()]
        datasets = [d for d in datasets if any(f in d["name"] for f in fl)]
    if args.list:
        for d in datasets:
            print(d["name"])
        return
    log(f"Found {len(datasets)} datasets")
    for rep in range(args.first_rep, args.first_rep + args.reps):
        for ds in datasets:
            run_one(ds, cfg, args, args.results_dir, rep=rep)


if __name__ == "__main__":
    main()
