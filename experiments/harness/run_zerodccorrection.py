"""
run_zerodccorrection.py — harness wrapper for ZeroDCcorrection (LLM error correction).

ZeroDCcorrection expects oracle error detection + a human-repair budget (clean rows).
This runner:
  1. Builds a perfect detection mask with harness normalize() (case ignored)
  2. Invokes ZeroDCcorrection/correction.py as a subprocess
  3. Maps corrections.csv back through evaluate()

Detection is oracle by design (ZeroDCcorrection's published setup); correction is the
measured task. System is off by default — enable in config when ready to spend
API budget. Does not implement Gemini Batch API (see notes in EXPERIMENTS_README
and conversation: ZeroDCcorrection's LangChain pipeline is multi-stage / stateful).
"""

import argparse
import ast
import json
import os
import re
import shutil
import sys

import pandas as pd

EXPERIMENTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, EXPERIMENTS_DIR)

from runner_utils import (
    load_config, list_effectiveness_datasets, list_runtime_datasets,
    setup_run_dir, PeakMemoryTracker, run_with_timeout, log, log_error,
    get_memory_limit_mb, init_log_file, resolve,
)
from evaluate import evaluate, record_runtime, diff_repaired, get_actual_errors, normalize


# Set from CLI in main(). Defaults reproduce the original ZeroDCcorrection runs exactly.
RUN_NAME = "zerodccorrection"          # results/<RUN_NAME>/... and run_config["system"]
PROMPT_DIR = None            # None -> correction.py default (prompt_templates-zerodc)


def _zerodccorrection_dir(cfg: dict) -> str:
    rel = cfg["systems"]["zerodccorrection"].get("zerodccorrection_dir", "../baselines/ZeroDCcorrection/ZeroDCcorrection")
    return resolve(cfg, rel)


def _write_oracle_detection(dirty_df: pd.DataFrame, clean_df: pd.DataFrame, path: str) -> int:
    """Binary 0/1 mask using harness normalize (lower, not casefold)."""
    det = pd.DataFrame(0, index=range(len(dirty_df)), columns=dirty_df.columns)
    n_err = 0
    for j in range(dirty_df.shape[1]):
        for i in range(dirty_df.shape[0]):
            if normalize(str(dirty_df.iloc[i, j])) != normalize(str(clean_df.iloc[i, j])):
                det.iloc[i, j] = 1
                n_err += 1
    det.to_csv(path, index=False, encoding="utf-8")
    return n_err


def _parse_repair_list(output_txt: str) -> set:
    """Parse 'Repair list indices: [...]' from ZeroDCcorrection output.txt if present."""
    if not os.path.exists(output_txt):
        return set()
    try:
        text = open(output_txt, encoding="utf-8").read()
    except OSError:
        return set()
    m = re.search(r"Repair list indices:\s*(\[[^\]]*\])", text)
    if not m:
        return set()
    try:
        vals = ast.literal_eval(m.group(1))
        return set(int(x) for x in vals)
    except (ValueError, SyntaxError, TypeError):
        return set()


def _prepare_api_env(sys_cfg: dict) -> dict:
    """Ensure GOOGLE_GENAI_API_KEY is set for correction.py's dotenv expectation."""
    env = os.environ.copy()
    api_key_env = sys_cfg.get("api_key_env", "GOOGLE_API_KEY")
    key = env.get(api_key_env) or env.get("GOOGLE_GENAI_API_KEY") or env.get("GOOGLE_API_KEY")
    if PROMPT_DIR:
        env["ZERODCCORRECTION_PROMPT_DIR"] = PROMPT_DIR
    if key:
        env["GOOGLE_GENAI_API_KEY"] = key
        env.setdefault(api_key_env, key)
    return env


def _run_zerodccorrection_subprocess(
    dirty_path: str,
    clean_path: str,
    detection_path: str,
    output_path: str,
    cfg: dict,
    time_limit: int,
) -> dict:
    sys_cfg = cfg["systems"]["zerodccorrection"]
    zdir = _zerodccorrection_dir(cfg)
    human_n = int(sys_cfg.get("human_repair_num", 20))
    # correction.py cwd is ZeroDCcorrection/; paths must be absolute.
    dirty_path = os.path.abspath(dirty_path)
    clean_path = os.path.abspath(clean_path)
    detection_path = os.path.abspath(detection_path)
    output_path = os.path.abspath(output_path)
    cmd = [
        sys.executable,
        "correction.py",
        "--clean_data_path", clean_path,
        "--dirty_data_path", dirty_path,
        "--detection_path", detection_path,
        "--output_path", output_path,
        "--human_repair_num", str(human_n),
    ]
    env = _prepare_api_env(sys_cfg)
    stdout_log = os.path.join(output_path, "zerodccorrection_stdout.log")
    stderr_log = os.path.join(output_path, "zerodccorrection_stderr.log")
    return run_with_timeout(
        cmd=cmd,
        cwd=zdir,
        env=env,
        time_limit=time_limit,
        stdout_log=stdout_log,
        stderr_log=stderr_log,
        memory_limit_mb=get_memory_limit_mb(cfg),
    )


def run_zerodccorrection_effectiveness(dataset: dict, cfg: dict, results_base: str, rep: int = 1):
    sys_cfg = cfg["systems"]["zerodccorrection"]
    human_n = int(sys_cfg.get("human_repair_num", 20))
    time_limit = None  # LLM jobs: no 10 h wall-clock cap

    run_dir = setup_run_dir(results_base, RUN_NAME, dataset["name"])
    work_dir = os.path.join(run_dir, "zerodccorrection_io")
    os.makedirs(work_dir, exist_ok=True)
    log(f"ZeroDCcorrection | {dataset['name']} | human_repair_num={human_n}")

    dirty_df = pd.read_csv(dataset["dirty"], dtype=str, keep_default_na=False)
    clean_df = pd.read_csv(dataset["clean"], dtype=str, keep_default_na=False)

    # Copy inputs into run dir so correction.py paths stay local to this run
    dirty_path = os.path.join(work_dir, "dirty.csv")
    clean_path = os.path.join(work_dir, "clean.csv")
    detection_path = os.path.join(work_dir, "perfect_error_detection.csv")
    dirty_df.to_csv(dirty_path, index=False, encoding="utf-8")
    clean_df.to_csv(clean_path, index=False, encoding="utf-8")
    n_oracle = _write_oracle_detection(dirty_df, clean_df, detection_path)
    log(f"  Oracle detection cells: {n_oracle}")

    api_env = _prepare_api_env(sys_cfg)
    if not api_env.get("GOOGLE_GENAI_API_KEY"):
        log_error(
            f"  No API key found (set {sys_cfg.get('api_key_env', 'GOOGLE_API_KEY')} "
            "or GOOGLE_GENAI_API_KEY). Skipping."
        )
        return

    timed_out = False
    oom = False
    failed = False
    tracker = PeakMemoryTracker(limit_mb=get_memory_limit_mb(cfg))
    result = {}
    try:
        with tracker:
            result = _run_zerodccorrection_subprocess(
                dirty_path, clean_path, detection_path, work_dir, cfg, time_limit
            )
        timed_out = bool(result.get("timed_out"))
        oom = bool(result.get("oom"))
        if result.get("returncode", 1) != 0 and not timed_out and not oom:
            failed = True
            log_error(
                f"  ZeroDCcorrection exited {result.get('returncode')} on {dataset['name']} "
                f"(see {work_dir}/zerodccorrection_stderr.log)"
            )
    except Exception as e:
        failed = True
        log_error(f"  ZeroDCcorrection failed on {dataset['name']}: {e}")

    run_config = {
        "system": RUN_NAME,
        "prompt_dir": PROMPT_DIR or "prompt_templates-zerodc",
        "dataset": dataset["name"],
        "error_rate": dataset["error_rate"],
        "slice": dataset["slice"],
        "human_repair_num": human_n,
        "oracle_detection": True,
        "mode": "effectiveness",
        "timed_out": timed_out,
        "oom": oom,
        "failed": failed,
        "repetition": rep,
    }

    corrections_path = os.path.join(work_dir, "corrections.csv")
    token_usage_path = os.path.join(work_dir, "token_usage.json")
    if not os.path.exists(corrections_path):
        # Still surface partial audit artifacts if present (expensive partial runs).
        if os.path.exists(token_usage_path):
            try:
                with open(token_usage_path, encoding="utf-8") as f:
                    run_config["token_usage"] = json.load(f)
            except Exception:
                pass
        record_runtime(
            run_dir, run_config,
            result.get("runtime_seconds", tracker.elapsed),
            result.get("peak_memory_mb", tracker.peak_mb),
        )
        log(f"  -> {run_dir} (no corrections.csv; check zerodccorrection_io/llm_calls.jsonl)")
        return

    # corrections.csv present: evaluate even if the subprocess exited non-zero
    # (e.g. optional Excel export crashed after writing corrections).
    if failed and not timed_out and not oom:
        log_error(
            f"  ZeroDCcorrection exited non-zero on {dataset['name']} but corrections.csv is present; "
            "evaluating recovered output"
        )
        run_config["recovered_from_nonzero_exit"] = True
        run_config["failed"] = False

    repaired_df = pd.read_csv(corrections_path, dtype=str, keep_default_na=False)
    # Align columns / length with dirty
    if list(repaired_df.columns) != list(dirty_df.columns):
        for col in dirty_df.columns:
            if col not in repaired_df.columns:
                repaired_df[col] = dirty_df[col]
        repaired_df = repaired_df[dirty_df.columns]
    if len(repaired_df) != len(dirty_df):
        log_error(
            f"  corrections.csv rows {len(repaired_df)} != dirty {len(dirty_df)}; truncating/padding"
        )
        repaired_df = repaired_df.reindex(range(len(dirty_df))).fillna("")
        for col in dirty_df.columns:
            repaired_df[col] = repaired_df[col].where(
                repaired_df[col].astype(str).str.len() > 0, dirty_df[col]
            )

    actual_errors = get_actual_errors(dirty_df, clean_df)
    # Oracle detection: every actual error cell is "detected"
    detected = {cell: actual_errors[cell] for cell in actual_errors}
    corrected = diff_repaired(dirty_df, repaired_df)
    labeled = _parse_repair_list(os.path.join(work_dir, "output.txt"))
    if not labeled:
        hr_path = os.path.join(work_dir, "human_repair_list.json")
        if os.path.exists(hr_path):
            try:
                labeled = set(json.load(open(hr_path, encoding="utf-8")).get("repair_list", []))
            except Exception:
                labeled = set()

    # Attach token audit + copy key artifacts to run_dir root for easy access
    if os.path.exists(token_usage_path):
        try:
            with open(token_usage_path, encoding="utf-8") as f:
                run_config["token_usage"] = json.load(f)
        except Exception as e:
            log_error(f"  Could not read token_usage.json: {e}")
    for name in (
        "token_usage.json",
        "llm_calls.jsonl",
        "repair_events.jsonl",
        "human_repair_list.json",
        "corrections.csv",
        "output.txt",
        "time_cost.txt",
        "specific_examples.txt",
        "codes.txt",
        "fds.txt",
    ):
        src = os.path.join(work_dir, name)
        if os.path.exists(src):
            try:
                shutil.copy2(src, os.path.join(run_dir, name))
            except OSError as e:
                log_error(f"  Could not copy {name}: {e}")

    evaluate(
        dirty_df=dirty_df,
        clean_df=clean_df,
        detected_cells=detected,
        corrected_cells=corrected,
        labeled_rows=labeled,
        out_dir=run_dir,
        run_config=run_config,
        runtime_seconds=result.get("runtime_seconds", tracker.elapsed),
        peak_memory_mb=result.get("peak_memory_mb", tracker.peak_mb),
    )
    log(f"  -> {run_dir}")
    if run_config.get("token_usage"):
        tu = run_config["token_usage"]
        log(
            f"  tokens est={tu.get('total_tokens_est')} api={tu.get('total_tokens_api')} "
            f"calls={tu.get('n_calls')} failed={tu.get('n_failed')}"
        )


def run_zerodccorrection_runtime(dataset: dict, cfg: dict, results_base: str):
    """Runtime-only: same pipeline, no evaluate metrics beyond record_runtime."""
    sys_cfg = cfg["systems"]["zerodccorrection"]
    time_limit = None  # LLM jobs: no 10 h wall-clock cap
    human_n = int(sys_cfg.get("human_repair_num", 20))

    run_dir = setup_run_dir(results_base, f"{RUN_NAME}_runtime", dataset["name"])
    work_dir = os.path.join(run_dir, "zerodccorrection_io")
    os.makedirs(work_dir, exist_ok=True)
    log(f"ZeroDCcorrection runtime | {dataset['name']} | n={dataset.get('n_records')}")

    dirty_df = pd.read_csv(dataset["dirty"], dtype=str, keep_default_na=False)
    clean_df = pd.read_csv(dataset["clean"], dtype=str, keep_default_na=False)
    dirty_path = os.path.join(work_dir, "dirty.csv")
    clean_path = os.path.join(work_dir, "clean.csv")
    detection_path = os.path.join(work_dir, "perfect_error_detection.csv")
    dirty_df.to_csv(dirty_path, index=False, encoding="utf-8")
    clean_df.to_csv(clean_path, index=False, encoding="utf-8")
    _write_oracle_detection(dirty_df, clean_df, detection_path)

    timed_out = False
    oom = False
    tracker = PeakMemoryTracker(limit_mb=get_memory_limit_mb(cfg))
    result = {}
    try:
        with tracker:
            result = _run_zerodccorrection_subprocess(
                dirty_path, clean_path, detection_path, work_dir, cfg, time_limit
            )
        timed_out = bool(result.get("timed_out"))
        oom = bool(result.get("oom"))
    except Exception as e:
        log_error(f"  ZeroDCcorrection runtime failed: {e}")

    run_config = {
        "system": RUN_NAME,
        "prompt_dir": PROMPT_DIR or "prompt_templates-zerodc",
        "dataset": dataset["name"],
        "n_records": dataset.get("n_records", len(dirty_df)),
        "human_repair_num": human_n,
        "mode": "runtime",
        "timed_out": timed_out,
        "oom": oom,
    }
    record_runtime(
        run_dir, run_config,
        result.get("runtime_seconds", tracker.elapsed),
        result.get("peak_memory_mb", tracker.peak_mb),
    )
    log(
        f"  -> {result.get('runtime_seconds', tracker.elapsed):.1f}s  "
        f"{result.get('peak_memory_mb', tracker.peak_mb):.0f}MB  "
        f"timed_out={timed_out}  oom={oom}"
    )


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
    parser.add_argument("--prompt-dir", default=None,
                        help="Prompt folder inside ZeroDCcorrection/ (e.g. prompt_templates-zerodc). "
                             "Default: prompt_templates-zerodc (use prompt_templates-old for the original prompts)")
    parser.add_argument("--run-name", default="zerodccorrection",
                        help="Results subfolder / system label (e.g. zerodccorrection_zerodcprompts)")
    parser.add_argument("--enable", action="store_true",
                        help="Run even if systems.zerodccorrection.enabled is false in config")
    args = parser.parse_args()

    global RUN_NAME, PROMPT_DIR
    RUN_NAME = args.run_name
    PROMPT_DIR = args.prompt_dir

    cfg = load_config(args.config)
    os.makedirs(args.results_dir, exist_ok=True)
    init_log_file(os.path.join(args.results_dir, f"{RUN_NAME}_{args.mode}.log"))
    if not args.enable and not cfg["systems"].get("zerodccorrection", {}).get("enabled"):
        log("ZeroDCcorrection disabled in config")
        return

    if args.mode == "effectiveness":
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
                run_zerodccorrection_effectiveness(ds, cfg, args.results_dir, rep=rep)
    else:
        datasets = list_runtime_datasets(cfg, args.datasets_dir)
        if args.filter_datasets:
            filters = [f.strip() for f in args.filter_datasets.split(",") if f.strip()]
            datasets = [ds for ds in datasets if any(f in ds["name"] for f in filters)]
        for ds in datasets:
            run_zerodccorrection_runtime(ds, cfg, args.results_dir)


if __name__ == "__main__":
    main()
