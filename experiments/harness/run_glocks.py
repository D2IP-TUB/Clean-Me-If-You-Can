"""
run_glocks.py — run Glocks (LLM-based) detection + correction experiments.

Detection mode (p5-p8 prompts):
  Feed dirty record to LLM asking "yes or no" per field.
  "no" → error detected.  "yes" → field is correct.

Correction mode (p9-p12 prompts, oracle):
  Feed dirty record to LLM with oracle error fields marked.
  Cells where LLM proposed value ≠ dirty value are treated as corrections.

Parallel LLM calls via threading (max_threads from config).
API key is read from the environment variable named in config.systems.glocks.api_key_env.
"""

import argparse
import json
import os
import re
import sys
import threading
from typing import Optional

import pandas as pd

EXPERIMENTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, EXPERIMENTS_DIR)

from runner_utils import (
    load_config, list_effectiveness_datasets, list_runtime_datasets,
    setup_run_dir, PeakMemoryTracker, log, log_error,
    get_memory_limit_mb, init_log_file,
)
from evaluate import evaluate, record_runtime, get_actual_errors, normalize


def _insert_glocks_path(cfg: dict):
    glocks_dir = os.path.normpath(os.path.join(EXPERIMENTS_DIR, cfg["systems"]["glocks"]["glocks_dir"]))
    if glocks_dir not in sys.path:
        sys.path.insert(0, glocks_dir)


def _load_prompt_dict(cfg: dict, col_match: dict):
    """Load prompt.json and initialize prompt objects with address column mapping."""
    _insert_glocks_path(cfg)
    from prompt import initPromptDict

    prompt_file = os.path.normpath(
        os.path.join(EXPERIMENTS_DIR, cfg["systems"]["glocks"]["prompt_file"])
    )
    with open(prompt_file, encoding="utf-8") as f:
        prompt_connection_config = json.load(f)
    return initPromptDict(prompt_connection_config, col_match)


def _get_client(cfg: dict):
    _insert_glocks_path(cfg)
    from llmUtils import getClient

    sys_cfg = cfg["systems"]["glocks"]
    llm_package = sys_cfg["llm_package"]
    api_key = os.environ.get(sys_cfg["api_key_env"], "")
    base_url = sys_cfg.get("base_url", "")
    return getClient(llm_package, api_key, base_url)


def _build_col_match(cfg: dict) -> dict:
    """Build the colNameMatchingDict mapping CSV column → prompt variable."""
    all_cols = cfg["dataset"]["all_columns"]
    return {c: c for c in all_cols}


def _ask_row(
    llm_package: str,
    client,
    modelname: str,
    row: pd.Series,
    prompt_val,
    oracle_error_fields: Optional[list],
    results: list,
    idx: int,
    lock: threading.Lock,
):
    """Call LLM for one row, append (idx, parsed_dict) to results."""
    _insert_glocks_path_once(llm_package)
    from llmUtils import askModel
    from prompt import parseAnswer

    prompt_val.setValues(row)
    if oracle_error_fields is not None:
        prompt_val.setErrorFields(oracle_error_fields)
    else:
        # Detection mode: mark all data columns as potential errors
        all_data_cols = [c for c in row.index if c != "_id"]
        prompt_val.setErrorFields(all_data_cols)

    prompt_str = prompt_val.getPrompt()
    try:
        answer = askModel(llm_package, client, prompt_str, modelname)
        if not answer:
            raise ValueError("LLM returned empty answer")
        parsed = parseAnswer(answer, prompt_val, idx)
    except Exception as e:
        log_error(f"  Glocks LLM call failed for row {idx}: {e}")
        parsed = {}

    with lock:
        results.append((idx, parsed))


# Module-level flag to avoid repeated sys.path insert
_glocks_path_inserted = False


def _insert_glocks_path_once(cfg_or_marker):
    pass  # path already inserted before threading; no-op here


def _infer_slice(dataset_name: str) -> str:
    """Infer slice name from dataset name for datasets that lack a 'slice' key."""
    if dataset_name.startswith("de_"):
        return "de"
    if dataset_name.startswith("full_"):
        return "full"
    if dataset_name.startswith("poi_"):
        return dataset_name  # poi_Library, poi_ShoppingCenter, etc.
    return ""


def _prompt_ids(dataset: dict, sys_cfg: dict) -> tuple:
    """Return (detection_pid, correction_pid) for this dataset.

    Looks up prompt_id_map in config keyed by slice name, falling back to
    the top-level detection_prompt_id / correction_prompt_id.
    """
    pid_map = sys_cfg.get("prompt_id_map", {})
    slice_name = dataset.get("slice") or _infer_slice(dataset["name"])
    if slice_name in pid_map:
        entry = pid_map[slice_name]
        return entry["detection"], entry["correction"]
    return (
        sys_cfg.get("detection_prompt_id", "p6"),
        sys_cfg.get("correction_prompt_id", "p10"),
    )


# Detection prompts ask "yes or no" per field; correction prompts return proposed values.
# p5-p6: de/full; p14-p16: poi_Library/poi_ShoppingCenter/russia
_DETECTION_PROMPT_IDS = {"p5", "p6", "p14", "p15", "p16"}


def _process_parsed_row(
    parsed: dict,
    dirty_row: pd.Series,
    col_map: dict,
    col_names: list,
    prompt_id: str = "",
) -> tuple:
    """
    Interpret LLM output depending on prompt type.

    Detection prompts (p5-p8): LLM answers "yes" (correct) or "no" (error) per
    field.  A "no" answer flags the cell as a detected error.

    Correction prompts (p9-p12): LLM returns proposed corrected values.  Cells
    where the proposed value differs from the dirty value are recorded.

    Returns (detected: {(row_i, col_j): value}, corrected: {(row_i, col_j): value}).
    col_map: column_name → column_index in the DataFrame
    """
    is_detection = prompt_id in _DETECTION_PROMPT_IDS
    detected = {}
    corrected = {}
    row_i = parsed.get("id", -1)
    if row_i < 0:
        return detected, corrected

    for col_name, col_j in col_map.items():
        if col_name not in parsed:
            continue
        raw = parsed[col_name]
        if raw is None:
            continue

        if is_detection:
            # "no" → field is erroneous; "yes" → field is correct
            if str(raw).strip().lower() == "no":
                detected[(row_i, col_j)] = ""
        else:
            # Proposed corrected value — flag cell only if different from dirty
            proposed = normalize(str(raw))
            if not proposed:
                continue
            dirty_val = normalize(str(dirty_row[col_name])) if col_name in dirty_row.index else ""
            if proposed != dirty_val:
                corrected[(row_i, col_j)] = proposed

    return detected, corrected


# Max inline requests per batch job (Developer API limit)
_BATCH_CHUNK_SIZE = 10_000


def _run_glocks_rows_batch(
    dirty_df: pd.DataFrame,
    cfg: dict,
    oracle_errors_by_row: Optional[dict],
    prompt_id: str,
) -> tuple:
    """
    Batch-API version of _run_glocks_rows.
    Submits all rows as inline batch requests (50 % cheaper, async processing).
    Splits into chunks of _BATCH_CHUNK_SIZE if needed.
    Returns (detected_cells, corrected_cells).
    """
    import copy
    import time as _time

    _insert_glocks_path(cfg)
    from prompt import parseAnswer
    from google.genai import types as gtypes

    sys_cfg = cfg["systems"]["glocks"]
    modelname = sys_cfg["modelname"]
    col_match = _build_col_match(cfg)

    client = _get_client(cfg)
    prompt_dict = _load_prompt_dict(cfg, col_match)

    if prompt_id not in prompt_dict:
        log_error(f"Prompt ID '{prompt_id}' not in prompt.json")
        return {}, {}

    id_col = cfg["dataset"]["id_column"]
    col_name_to_idx = {c: dirty_df.columns.get_loc(c)
                       for c in dirty_df.columns if c != id_col}

    thinking_budget = sys_cfg.get("thinking_budget", 0)
    if thinking_budget < 0:
        gen_cfg = gtypes.GenerateContentConfig()
    else:
        gen_cfg = gtypes.GenerateContentConfig(
            thinking_config=gtypes.ThinkingConfig(thinking_budget=thinking_budget)
        )

    # Build one InlinedRequest per row
    inlined_requests = []
    for i in range(len(dirty_df)):
        pv = copy.deepcopy(prompt_dict[prompt_id])
        row = dirty_df.iloc[i]
        pv.setValues(row)
        if oracle_errors_by_row is not None:
            pv.setErrorFields(oracle_errors_by_row.get(i, []))
        else:
            pv.setErrorFields([c for c in row.index if c != "_id"])
        inlined_requests.append(
            gtypes.InlinedRequest(
                contents=pv.getPrompt(),
                metadata={"row_idx": str(i)},
                config=gen_cfg,
            )
        )

    # Submit in chunks, collect InlinedResponse objects in order
    all_responses: list = []
    total_pending_seconds = 0.0
    chunks = [inlined_requests[s:s + _BATCH_CHUNK_SIZE]
              for s in range(0, len(inlined_requests), _BATCH_CHUNK_SIZE)]
    log(f"  Submitting {len(inlined_requests)} rows as {len(chunks)} batch job(s) "
        f"(prompt={prompt_id})")

    for chunk_i, chunk in enumerate(chunks):
        job = client.batches.create(model=modelname, src=chunk)
        log(f"  Chunk {chunk_i + 1}/{len(chunks)} job: {job.name}")

        # Poll with capped exponential back-off.
        # Record timestamps to measure how long the job spent queued (PENDING).
        submit_time = _time.time()
        running_start = 0.0
        poll_interval = 30.0
        while not job.done:
            _time.sleep(poll_interval)
            job = client.batches.get(name=job.name)
            log(f"    state: {job.state}")
            if running_start == 0.0 and getattr(job.state, "name", str(job.state)) == "JOB_STATE_RUNNING":
                running_start = _time.time()
            poll_interval = min(poll_interval * 1.5, 300.0)
        # Pending duration = time from submission to first RUNNING observation.
        total_pending_seconds += (running_start - submit_time) if running_start > 0.0 else 0.0

        if getattr(job.state, "name", str(job.state)) != "JOB_STATE_SUCCEEDED":
            log_error(f"  Batch job {job.name} ended with state {job.state}: {job.error}")
            continue

        chunk_responses = job.dest.inlined_responses if (job.dest and job.dest.inlined_responses) else []
        if len(chunk_responses) != len(chunk):
            log_error(f"  Batch job {job.name}: expected {len(chunk)} responses, "
                      f"got {len(chunk_responses)} — results may be incomplete")
        all_responses.extend(chunk_responses)

    log(f"  Collected {len(all_responses)}/{len(inlined_requests)} responses total")
    if len(all_responses) != len(inlined_requests):
        log_error(f"  WARNING: response count mismatch — "
                  f"{len(inlined_requests) - len(all_responses)} rows will be missing from results")

    # Parse results
    detected_all: dict = {}
    corrected_all: dict = {}
    for resp in all_responses:
        row_idx = int(resp.metadata["row_idx"]) if resp.metadata else -1
        if row_idx < 0:
            continue
        if resp.error:
            log_error(f"  Batch row {row_idx} error: {resp.error}")
            continue

        answer = resp.response.text if resp.response else None
        if not answer:
            log_error(f"  Batch row {row_idx}: empty response")
            continue

        pv = copy.deepcopy(prompt_dict[prompt_id])
        pv.setValues(dirty_df.iloc[row_idx])
        try:
            parsed = parseAnswer(answer, pv, row_idx)
        except Exception as e:
            log_error(f"  Batch row {row_idx} parse error: {e}")
            continue

        det, cor = _process_parsed_row(
            parsed, dirty_df.iloc[row_idx], col_name_to_idx,
            list(dirty_df.columns), prompt_id=prompt_id,
        )
        detected_all.update(det)
        corrected_all.update(cor)

    return detected_all, corrected_all, total_pending_seconds


def _run_glocks_rows(
    dirty_df: pd.DataFrame,
    cfg: dict,
    oracle_errors_by_row: Optional[dict],
    prompt_id: str,
    max_threads: int,
) -> tuple:
    """
    Run Glocks LLM on all rows.
    oracle_errors_by_row: {row_i: [col_names]} or None for detection mode.
    Returns (detected_cells, corrected_cells).
    Dispatches to batch API when config.systems.glocks.use_batch_api is true.
    """
    sys_cfg = cfg["systems"]["glocks"]
    if sys_cfg.get("use_batch_api", False):
        return _run_glocks_rows_batch(dirty_df, cfg, oracle_errors_by_row, prompt_id)

    llm_package = sys_cfg["llm_package"]
    modelname = sys_cfg["modelname"]
    col_match = _build_col_match(cfg)

    client = _get_client(cfg)
    prompt_dict = _load_prompt_dict(cfg, col_match)

    data_cols = cfg["dataset"]["data_columns"]
    id_col = cfg["dataset"]["id_column"]
    col_name_to_idx = {c: dirty_df.columns.get_loc(c)
                       for c in dirty_df.columns if c != id_col}

    results = []
    lock = threading.Lock()

    def worker(i):
        if prompt_id not in prompt_dict:
            log_error(f"Prompt ID '{prompt_id}' not in prompt.json")
            return
        # Each thread needs its own copy to avoid shared state in promptVarDict
        import copy
        pv = copy.deepcopy(prompt_dict[prompt_id])
        row = dirty_df.iloc[i]
        oracle = oracle_errors_by_row.get(i, []) if oracle_errors_by_row is not None else None
        _ask_row(llm_package, client, modelname, row, pv, oracle, results, i, lock)

    n = len(dirty_df)
    for start in range(0, n, max_threads):
        batch = range(start, min(start + max_threads, n))
        threads = [threading.Thread(target=worker, args=(i,)) for i in batch]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

    detected_all = {}
    corrected_all = {}
    for row_i, parsed in results:
        det, cor = _process_parsed_row(
            parsed, dirty_df.iloc[row_i], col_name_to_idx, list(dirty_df.columns),
            prompt_id=prompt_id,
        )
        detected_all.update(det)
        corrected_all.update(cor)

    return detected_all, corrected_all, 0.0


def _load_corrected_from_cells_csv(results_base: str, dataset_name: str, dirty_df) -> Optional[dict]:
    """
    Find the most recent existing glocks run dir for *dataset_name* under
    *results_base* and reconstruct corrected_cells from its cells.csv.
    Returns None if no prior run exists.
    """
    glocks_dir = os.path.join(results_base, "glocks")
    if not os.path.isdir(glocks_dir):
        glocks_dir = results_base  # flat layout
    candidates = []
    for entry in os.listdir(glocks_dir):
        if not entry.startswith(dataset_name + "_"):
            continue
        cells_path = os.path.join(glocks_dir, entry, "cells.csv")
        if os.path.isfile(cells_path):
            candidates.append((entry, cells_path))
    if not candidates:
        # Also try flat layout (results_base directly)
        for entry in os.listdir(results_base):
            if not entry.startswith(dataset_name + "_"):
                continue
            cells_path = os.path.join(results_base, entry, "cells.csv")
            if os.path.isfile(cells_path):
                candidates.append((entry, cells_path))
    if not candidates:
        return None
    # Most recent by directory name (timestamp suffix)
    _, cells_path = sorted(candidates, key=lambda x: x[0])[-1]
    log(f"  Loading existing correction from {cells_path}")
    corrected = {}
    with open(cells_path, newline="", encoding="utf-8") as f:
        reader = __import__("csv").DictReader(f)
        for row in reader:
            val = row.get("cor_proposed_value", "").strip()
            if val:
                corrected[(int(row["row_id"]), int(row["col_idx"]))] = val
    return corrected


def run_glocks_effectiveness(dataset: dict, cfg: dict, results_base: str, rep: int = 1,
                             task: str = "both"):
    sys_cfg = cfg["systems"]["glocks"]
    detection_pid, correction_pid = _prompt_ids(dataset, sys_cfg)
    max_threads = sys_cfg.get("max_threads", 10)
    time_limit = cfg["experiment"]["time_limit_seconds"]

    run_dir = setup_run_dir(results_base, "glocks", dataset["name"])
    log(f"Glocks | {dataset['name']} | detect={detection_pid} correct={correction_pid} task={task}")

    dirty_df = pd.read_csv(dataset["dirty"], dtype=str, keep_default_na=False)
    clean_df = pd.read_csv(dataset["clean"], dtype=str, keep_default_na=False)

    # Correction run: oracle error fields per row
    actual_errors = get_actual_errors(dirty_df, clean_df)
    oracle_by_row: dict[int, list] = {}
    for (row_i, col_j), _ in actual_errors.items():
        col_name = dirty_df.columns[col_j]
        oracle_by_row.setdefault(row_i, []).append(col_name)

    import signal
    use_batch = sys_cfg.get("use_batch_api", False)
    det_timed_out = False
    cor_timed_out = False
    detected, corrected = {}, {}
    _pending_det = 0.0
    _pending_cor = 0.0
    tracker = PeakMemoryTracker(limit_mb=get_memory_limit_mb(cfg))

    def _timeout(signum, frame):
        raise TimeoutError()

    try:
        with tracker:
            if not use_batch:
                signal.signal(signal.SIGALRM, _timeout)

            # Detection pass
            if task in ("both", "detection"):
                if not use_batch:
                    signal.alarm(time_limit)
                try:
                    detected, _, _pending_det = _run_glocks_rows(dirty_df, cfg, None, detection_pid, max_threads)
                except TimeoutError:
                    det_timed_out = True
                    log_error(f"  Glocks detection timed out on {dataset['name']}")
                except Exception as e:
                    log_error(f"  Glocks detection failed on {dataset['name']}: {e}")
                finally:
                    if not use_batch:
                        signal.alarm(0)

            # Correction pass (or reload from existing cells.csv)
            if task == "both":
                if not use_batch:
                    signal.alarm(time_limit)
                try:
                    _, corrected, _pending_cor = _run_glocks_rows(dirty_df, cfg, oracle_by_row, correction_pid, max_threads)
                except TimeoutError:
                    cor_timed_out = True
                    log_error(f"  Glocks correction timed out on {dataset['name']}")
                except Exception as e:
                    log_error(f"  Glocks correction failed on {dataset['name']}: {e}")
                finally:
                    if not use_batch:
                        signal.alarm(0)
            elif task == "detection":
                existing = _load_corrected_from_cells_csv(results_base, dataset["name"], dirty_df)
                if existing is not None:
                    corrected = existing
                else:
                    log_error(f"  No existing correction found for {dataset['name']} — correction will be empty")

    except Exception as e:
        log_error(f"  Glocks failed on {dataset['name']}: {e}")

    timed_out = det_timed_out or cor_timed_out

    run_config = {
        "system": "glocks",
        "dataset": dataset["name"],
        "error_rate": dataset["error_rate"],
        "slice": dataset["slice"],
        "detection_prompt": detection_pid,
        "correction_prompt": correction_pid,
        "llm_package": sys_cfg["llm_package"],
        "model": sys_cfg["modelname"],
        "mode": "effectiveness",
        "timed_out": timed_out,
        "det_timed_out": det_timed_out,
        "cor_timed_out": cor_timed_out,
        "repetition": rep,
    }

    _runtime = tracker.elapsed - (_pending_det + _pending_cor)
    if det_timed_out and cor_timed_out:
        record_runtime(run_dir, run_config, _runtime, tracker.peak_mb)
        return

    evaluate(
        dirty_df=dirty_df,
        clean_df=clean_df,
        detected_cells=detected,
        corrected_cells=corrected,
        labeled_rows=set(),
        out_dir=run_dir,
        run_config=run_config,
        runtime_seconds=_runtime,
        peak_memory_mb=tracker.peak_mb,
    )
    log(f"  -> {run_dir}")


def run_glocks_runtime(dataset: dict, cfg: dict, results_base: str):
    sys_cfg = cfg["systems"]["glocks"]
    detection_pid, _ = _prompt_ids(dataset, sys_cfg)
    max_threads = sys_cfg.get("max_threads", 10)
    time_limit = cfg["experiment"]["time_limit_seconds"]

    run_dir = setup_run_dir(results_base, "glocks_runtime", dataset["name"])
    log(f"Glocks runtime | {dataset['name']} | n={dataset['n_records']}")

    dirty_df = pd.read_csv(dataset["dirty"], dtype=str, keep_default_na=False)

    import signal
    use_batch = sys_cfg.get("use_batch_api", False)
    timed_out = False
    oom = False
    _pending_s = 0.0
    tracker = PeakMemoryTracker(limit_mb=get_memory_limit_mb(cfg))
    try:
        with tracker:
            if not use_batch:
                def _timeout(signum, frame):
                    raise TimeoutError()
                signal.signal(signal.SIGALRM, _timeout)
                signal.alarm(time_limit)
            try:
                _, _, _pending_s = _run_glocks_rows(dirty_df, cfg, None, detection_pid, max_threads)
            finally:
                if not use_batch:
                    signal.alarm(0)
    except TimeoutError:
        timed_out = True
    except MemoryError as e:
        oom = True
        log_error(f"  Glocks OOM on {dataset['name']}: {e}")
    except Exception as e:
        log_error(f"  Glocks failed: {e}")

    run_config = {
        "system": "glocks",
        "dataset": dataset["name"],
        "n_records": dataset["n_records"],
        "llm_package": sys_cfg["llm_package"],
        "model": sys_cfg["modelname"],
        "mode": "runtime",
        "timed_out": timed_out,
        "oom": oom,
    }
    _runtime = tracker.elapsed - _pending_s
    record_runtime(run_dir, run_config, _runtime, tracker.peak_mb)
    log(f"  -> {_runtime:.1f}s  {tracker.peak_mb:.0f}MB  timed_out={timed_out}  oom={oom}")


def main():
    # Load API keys from .env (experiments dir first, then home dir)
    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(EXPERIMENTS_DIR, ".env"))
        load_dotenv(os.path.expanduser("~/.env"))
    except ImportError:
        pass

    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["effectiveness", "runtime"], required=True)
    parser.add_argument("--config", default=os.path.join(EXPERIMENTS_DIR, "config.json"))
    parser.add_argument("--datasets-dir", default=os.path.join(EXPERIMENTS_DIR, "experiment_datasets"))
    parser.add_argument("--results-dir", default=os.path.join(EXPERIMENTS_DIR, "results"))
    parser.add_argument("--slices", nargs="+", default=None,
                        help="Only run datasets whose slice matches one of these values, "
                             "e.g. --slices de full")
    parser.add_argument("--dataset", default=None,
                        help="Only run the dataset with this exact name, "
                             "e.g. --dataset full_sample_full_0.51")
    parser.add_argument("--task", choices=["both", "detection", "correction"], default="both",
                        help="Which LLM pass to run: 'both' (default), 'detection' only "
                             "(loads existing correction from cells.csv), or 'correction' only")
    args = parser.parse_args()

    cfg = load_config(args.config)
    os.makedirs(args.results_dir, exist_ok=True)
    init_log_file(os.path.join(args.results_dir, f"glocks_{args.mode}.log"))
    if not cfg["systems"]["glocks"]["enabled"]:
        log("Glocks disabled in config")
        return

    if args.mode == "effectiveness":
        n_reps = cfg.get("experiment", {}).get("n_effectiveness_runs", 3)
        datasets = list_effectiveness_datasets(cfg, args.datasets_dir)
        if args.slices:
            datasets = [d for d in datasets if d["slice"] in args.slices]
        if args.dataset:
            datasets = [d for d in datasets if d["name"] == args.dataset]
        log(f"Found {len(datasets)} effectiveness datasets, {n_reps} repetitions")
        for rep in range(1, n_reps + 1):
            log(f"=== Effectiveness repetition {rep}/{n_reps} ===")
            for ds in datasets:
                run_glocks_effectiveness(ds, cfg, args.results_dir, rep=rep, task=args.task)
    else:
        for ds in list_runtime_datasets(cfg, args.datasets_dir):
            run_glocks_runtime(ds, cfg, args.results_dir)


if __name__ == "__main__":
    main()
