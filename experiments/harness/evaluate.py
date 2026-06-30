"""
Unified evaluation module for all data cleaning systems.

All metrics are computed using the same logic as raha.dataset.Dataset.get_data_cleaning_evaluation,
ensuring consistency across systems. Labeled tuples are included in evaluation (matching Raha behaviour).
"""

import csv
import html
import json
import os
import re
from datetime import datetime
from typing import Dict, Optional, Set, Tuple


# ---------------------------------------------------------------------------
# Value normalizer — identical to raha.dataset.Dataset.value_normalizer
# ---------------------------------------------------------------------------

def normalize(value: str) -> str:
    value = html.unescape(str(value))
    value = re.sub(r"[\t\n ]+", " ", value)
    value = value.strip("\t\n ")
    return value


# ---------------------------------------------------------------------------
# Core helpers
# ---------------------------------------------------------------------------

def get_actual_errors(dirty_df, clean_df) -> Dict[Tuple[int, int], str]:
    """
    Return {(row, col_idx): clean_value} for every cell where dirty != clean
    after normalization.  Mirrors raha.dataset.Dataset.get_actual_errors_dictionary.
    """
    if dirty_df.shape != clean_df.shape:
        import sys
        sys.stderr.write(
            f"Warning: dirty {dirty_df.shape} and clean {clean_df.shape} shapes differ!\n"
        )
    errors = {}
    for j in range(dirty_df.shape[1]):
        for i in range(dirty_df.shape[0]):
            d_val = normalize(dirty_df.iloc[i, j])
            c_val = normalize(clean_df.iloc[i, j])
            if d_val != c_val:
                errors[(i, j)] = c_val
    return errors


def diff_repaired(dirty_df, repaired_df) -> Dict[Tuple[int, int], str]:
    """
    Return {(row, col_idx): repaired_value} for all cells changed by a system
    that outputs a full repaired CSV (Horizon, HoloClean, UniClean).
    Mirrors raha.dataset.Dataset.get_correction_dictionary.
    """
    changed = {}
    for j in range(dirty_df.shape[1]):
        for i in range(dirty_df.shape[0]):
            d_val = normalize(dirty_df.iloc[i, j])
            r_val = normalize(repaired_df.iloc[i, j])
            if d_val != r_val:
                changed[(i, j)] = r_val
    return changed


# ---------------------------------------------------------------------------
# Main evaluation function
# ---------------------------------------------------------------------------

def evaluate(
    dirty_df,
    clean_df,
    detected_cells: Dict[Tuple[int, int], str],
    corrected_cells: Optional[Dict[Tuple[int, int], str]],
    labeled_rows: Set[int],
    out_dir: str,
    run_config: dict,
    runtime_seconds: float = 0.0,
    peak_memory_mb: float = 0.0,
) -> dict:
    """
    Evaluate detection and (optionally) correction results.

    Parameters
    ----------
    dirty_df        : pandas DataFrame — dirty data (already loaded, column order matters)
    clean_df        : pandas DataFrame — clean ground truth
    detected_cells  : {(row, col_idx): proposed_value_or_""} — system's detection output
    corrected_cells : {(row, col_idx): corrected_value} or None
    labeled_rows    : set of row indices used for training (saved in output but NOT excluded)
    out_dir         : directory where cells.csv, summary.csv, run_config.json are written
    run_config      : arbitrary dict — saved verbatim as run_config.json
    runtime_seconds : wall-clock time of the system run
    peak_memory_mb  : peak RSS memory in MB during the run

    Returns
    -------
    dict with det_precision, det_recall, det_f1, cor_precision, cor_recall, cor_f1, etc.
    """
    os.makedirs(out_dir, exist_ok=True)

    actual_errors = get_actual_errors(dirty_df, clean_df)
    n_actual = len(actual_errors)
    n_rows, n_cols = dirty_df.shape
    col_names = list(dirty_df.columns)

    if corrected_cells is None:
        corrected_cells = {}

    # ---- cell-level evaluation (mirrors get_data_cleaning_evaluation exactly) ----
    ed_tp = 0.0
    ec_tp = 0.0
    output_size = float(len(detected_cells))  # denominator for precision

    for cell, proposed in detected_cells.items():
        if cell in actual_errors:
            ed_tp += 1.0
            # correction: normalize proposed before comparing to the (already normalized) clean value
            if proposed != "" and normalize(proposed) == actual_errors[cell]:
                ec_tp += 1.0

    # For correction systems: only count corrections on actual error cells (clean cells ignored)
    cor_output_size = float(sum(1 for cell in corrected_cells if cell in actual_errors))
    ec_tp_sep = 0.0
    for cell, proposed in corrected_cells.items():
        if cell in actual_errors and normalize(proposed) == actual_errors[cell]:
            ec_tp_sep += 1.0

    # Detection metrics
    ed_p = 0.0 if output_size == 0 else ed_tp / output_size
    ed_r = 0.0 if n_actual == 0 else ed_tp / n_actual
    ed_f = 0.0 if (ed_p + ed_r) == 0 else (2 * ed_p * ed_r) / (ed_p + ed_r)

    # Correction metrics — prefer separate corrected_cells if provided
    if corrected_cells:
        ec_p = 0.0 if cor_output_size == 0 else ec_tp_sep / cor_output_size
        ec_r = 0.0 if n_actual == 0 else ec_tp_sep / n_actual
    else:
        ec_p = 0.0 if output_size == 0 else ec_tp / output_size
        ec_r = 0.0 if n_actual == 0 else ec_tp / n_actual
    ec_f = 0.0 if (ec_p + ec_r) == 0 else (2 * ec_p * ec_r) / (ec_p + ec_r)

    # ---- write cells.csv ----
    cells_path = os.path.join(out_dir, "cells.csv")
    with open(cells_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "row_id", "col_name", "col_idx",
            "dirty_value", "clean_value",
            "is_actual_error", "is_labeled_tuple",
            "det_predicted", "det_proposed_value",
            "det_tp", "det_fp", "det_fn",
            "cor_proposed_value",
            "cor_tp", "cor_fp", "cor_fn",
        ])
        for i in range(n_rows):
            for j in range(n_cols):
                cell = (i, j)
                dirty_val = normalize(dirty_df.iloc[i, j])
                clean_val = normalize(clean_df.iloc[i, j])
                is_error = cell in actual_errors
                is_labeled = i in labeled_rows
                det_pred = cell in detected_cells
                det_proposed = detected_cells.get(cell, "")
                cor_proposed = corrected_cells.get(cell, "")

                det_tp_flag = int(det_pred and is_error)
                det_fp_flag = int(det_pred and not is_error)
                det_fn_flag = int(not det_pred and is_error)

                if cor_proposed:
                    if is_error:
                        # Correction on an actual error cell
                        cor_tp_flag = int(cor_proposed == clean_val)
                        cor_fp_flag = int(cor_proposed != clean_val)  # wrong correction
                        cor_fn_flag = int(cor_proposed != clean_val)  # not correctly fixed
                    else:
                        # Correction on a clean cell: ignored entirely
                        cor_tp_flag = 0
                        cor_fp_flag = 0
                        cor_fn_flag = 0
                else:
                    cor_tp_flag = 0
                    cor_fp_flag = 0
                    cor_fn_flag = int(is_error)

                writer.writerow([
                    i, col_names[j], j,
                    dirty_val, clean_val,
                    int(is_error), int(is_labeled),
                    int(det_pred), det_proposed,
                    det_tp_flag, det_fp_flag, det_fn_flag,
                    cor_proposed,
                    cor_tp_flag, cor_fp_flag, cor_fn_flag,
                ])

    # ---- write summary.csv ----
    summary = {
        "dataset":        run_config.get("dataset", ""),
        "system":         run_config.get("system", ""),
        "error_rate":     run_config.get("error_rate", ""),
        "timestamp":      datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "n_rows":         n_rows,
        "n_cols":         n_cols,
        "n_actual_errors": n_actual,
        "n_detected":     len(detected_cells),
        "n_corrected":    len(corrected_cells),
        "n_labeled_rows": len(labeled_rows),
        "det_precision":  round(ed_p, 6),
        "det_recall":     round(ed_r, 6),
        "det_f1":         round(ed_f, 6),
        "cor_precision":  round(ec_p, 6),
        "cor_recall":     round(ec_r, 6),
        "cor_f1":         round(ec_f, 6),
        "runtime_seconds": round(runtime_seconds, 4),
        "peak_memory_mb":  round(peak_memory_mb, 2),
    }
    summary_path = os.path.join(out_dir, "summary.csv")
    _write_or_append_csv(summary_path, summary)

    # ---- write run_config.json ----
    with open(os.path.join(out_dir, "run_config.json"), "w") as f:
        json.dump(run_config, f, indent=2, default=str)

    return summary


# ---------------------------------------------------------------------------
# Runtime-only record (no evaluation)
# ---------------------------------------------------------------------------

def record_runtime(
    out_dir: str,
    run_config: dict,
    runtime_seconds: float,
    peak_memory_mb: float,
) -> dict:
    """Write a summary.csv with timing/memory only — used for runtime experiments."""
    os.makedirs(out_dir, exist_ok=True)
    summary = {
        "dataset":         run_config.get("dataset", ""),
        "system":          run_config.get("system", ""),
        "n_records":       run_config.get("n_records", ""),
        "timestamp":       datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "runtime_seconds": round(runtime_seconds, 4),
        "peak_memory_mb":  round(peak_memory_mb, 2),
    }
    summary_path = os.path.join(out_dir, "summary.csv")
    _write_or_append_csv(summary_path, summary)
    with open(os.path.join(out_dir, "run_config.json"), "w") as f:
        json.dump(run_config, f, indent=2, default=str)
    return summary


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _write_or_append_csv(path: str, row: dict):
    file_exists = os.path.exists(path)
    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(row.keys()))
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)
