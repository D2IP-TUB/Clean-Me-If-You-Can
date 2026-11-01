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
# Value normalizer — same whitespace cleanup as raha.dataset.Dataset.value_normalizer,
# then lower, so a case-only difference is not an error. Use lower, not casefold:
# casefold maps German ẞ to "ss", which would treat distinct spellings as equal.
# ---------------------------------------------------------------------------

def normalize(value: str) -> str:
    value = html.unescape(str(value))
    value = re.sub(r"[\t\n ]+", " ", value)
    value = value.strip("\t\n ")
    return value.lower()


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


def _prf(tp: float, n_pred: float, n_actual: float):
    """Precision / recall / F1. Empty prediction or no gold → zeros, not NaN."""
    p = 0.0 if n_pred == 0 else tp / n_pred
    r = 0.0 if n_actual == 0 else tp / n_actual
    f = 0.0 if (p + r) == 0 else (2 * p * r) / (p + r)
    return p, r, f


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
    dict with det_precision, det_recall, det_f1, cor_precision, cor_recall, cor_f1,
    plus per-column keys (det_f1_<col>, …). Also writes column_metrics.csv.
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
    ed_p, ed_r, ed_f = _prf(ed_tp, output_size, n_actual)

    # Correction metrics — prefer separate corrected_cells if provided
    if corrected_cells:
        ec_p, ec_r, ec_f = _prf(ec_tp_sep, cor_output_size, n_actual)
    else:
        ec_p, ec_r, ec_f = _prf(ec_tp, output_size, n_actual)

    # Per-column P/R/F1 (out-of-scope / untouched columns are explicit zeros)
    column_rows = []
    for j, name in enumerate(col_names):
        col_actual = {c: v for c, v in actual_errors.items() if c[1] == j}
        col_det = {c: v for c, v in detected_cells.items() if c[1] == j}
        col_cor = {c: v for c, v in corrected_cells.items() if c[1] == j}
        n_act = float(len(col_actual))
        n_det = float(len(col_det))
        ed_tp_c = float(sum(1 for c in col_det if c in col_actual))
        det_p, det_r, det_f = _prf(ed_tp_c, n_det, n_act)
        if corrected_cells:
            cor_out = float(sum(1 for c in col_cor if c in col_actual))
            ec_tp_c = float(sum(
                1 for c, prop in col_cor.items()
                if c in col_actual and normalize(prop) == col_actual[c]
            ))
            cor_p, cor_r, cor_f = _prf(ec_tp_c, cor_out, n_act)
        else:
            ec_tp_c = float(sum(
                1 for c, prop in col_det.items()
                if c in col_actual and prop != "" and normalize(prop) == col_actual[c]
            ))
            cor_p, cor_r, cor_f = _prf(ec_tp_c, n_det, n_act)
        column_rows.append({
            "column": name,
            "col_idx": j,
            "n_actual_errors": int(n_act),
            "n_detected": int(n_det),
            "n_corrected": len(col_cor),
            "det_precision": round(det_p, 6),
            "det_recall": round(det_r, 6),
            "det_f1": round(det_f, 6),
            "cor_precision": round(cor_p, 6),
            "cor_recall": round(cor_r, 6),
            "cor_f1": round(cor_f, 6),
        })

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
                        cor_ok = normalize(cor_proposed) == clean_val
                        cor_tp_flag = int(cor_ok)
                        cor_fp_flag = int(not cor_ok)  # wrong correction
                        cor_fn_flag = int(not cor_ok)  # not correctly fixed
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
    for crow in column_rows:
        name = crow["column"]
        summary[f"det_precision_{name}"] = crow["det_precision"]
        summary[f"det_recall_{name}"] = crow["det_recall"]
        summary[f"det_f1_{name}"] = crow["det_f1"]
        summary[f"cor_precision_{name}"] = crow["cor_precision"]
        summary[f"cor_recall_{name}"] = crow["cor_recall"]
        summary[f"cor_f1_{name}"] = crow["cor_f1"]
    summary_path = os.path.join(out_dir, "summary.csv")
    _write_or_append_csv(summary_path, summary)

    col_metrics_path = os.path.join(out_dir, "column_metrics.csv")
    if column_rows:
        with open(col_metrics_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(column_rows[0].keys()))
            writer.writeheader()
            writer.writerows(column_rows)

    # ---- write run_config.json ----
    with open(os.path.join(out_dir, "run_config.json"), "w") as f:
        json.dump(run_config, f, indent=2, default=str)

    return summary


def evaluate_detection(
    dirty_df,
    clean_df,
    detected_cells: Dict[Tuple[int, int], str],
    labeled_rows: Set[int],
    out_dir: str,
    run_config: dict,
    runtime_seconds: float = 0.0,
    peak_memory_mb: float = 0.0,
) -> dict:
    """
    Detection-only evaluation. Proposed values in detected_cells are ignored.
    No correction metrics are computed or written.
    """
    os.makedirs(out_dir, exist_ok=True)

    actual_errors = get_actual_errors(dirty_df, clean_df)
    n_actual = len(actual_errors)
    n_rows, n_cols = dirty_df.shape
    col_names = list(dirty_df.columns)
    output_size = float(len(detected_cells))
    ed_tp = float(sum(1 for cell in detected_cells if cell in actual_errors))
    ed_p, ed_r, ed_f = _prf(ed_tp, output_size, n_actual)

    column_rows = []
    for j, name in enumerate(col_names):
        col_actual = {c for c in actual_errors if c[1] == j}
        col_det = {c for c in detected_cells if c[1] == j}
        n_act = float(len(col_actual))
        n_det = float(len(col_det))
        ed_tp_c = float(len(col_det & col_actual))
        det_p, det_r, det_f = _prf(ed_tp_c, n_det, n_act)
        column_rows.append({
            "column": name,
            "col_idx": j,
            "n_actual_errors": int(n_act),
            "n_detected": int(n_det),
            "det_precision": round(det_p, 6),
            "det_recall": round(det_r, 6),
            "det_f1": round(det_f, 6),
        })

    cells_path = os.path.join(out_dir, "cells.csv")
    with open(cells_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "row_id", "col_name", "col_idx",
            "dirty_value", "clean_value",
            "is_actual_error", "is_labeled_tuple",
            "det_predicted", "det_signal",
            "det_tp", "det_fp", "det_fn",
        ])
        for i in range(n_rows):
            for j in range(n_cols):
                cell = (i, j)
                dirty_val = normalize(dirty_df.iloc[i, j])
                clean_val = normalize(clean_df.iloc[i, j])
                is_error = cell in actual_errors
                det_pred = cell in detected_cells
                writer.writerow([
                    i, col_names[j], j,
                    dirty_val, clean_val,
                    int(is_error), int(i in labeled_rows),
                    int(det_pred), detected_cells.get(cell, ""),
                    int(det_pred and is_error),
                    int(det_pred and not is_error),
                    int((not det_pred) and is_error),
                ])

    summary = {
        "dataset":         run_config.get("dataset", ""),
        "system":          run_config.get("system", ""),
        "error_rate":      run_config.get("error_rate", ""),
        "timestamp":       datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "n_rows":          n_rows,
        "n_cols":          n_cols,
        "n_actual_errors": n_actual,
        "n_detected":      len(detected_cells),
        "n_labeled_rows":  len(labeled_rows),
        "det_precision":   round(ed_p, 6),
        "det_recall":      round(ed_r, 6),
        "det_f1":          round(ed_f, 6),
        "runtime_seconds": round(runtime_seconds, 4),
        "peak_memory_mb":  round(peak_memory_mb, 2),
    }
    for crow in column_rows:
        name = crow["column"]
        summary[f"det_precision_{name}"] = crow["det_precision"]
        summary[f"det_recall_{name}"] = crow["det_recall"]
        summary[f"det_f1_{name}"] = crow["det_f1"]
    _write_or_append_csv(os.path.join(out_dir, "summary.csv"), summary)
    if column_rows:
        with open(os.path.join(out_dir, "column_metrics.csv"), "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(column_rows[0].keys()))
            writer.writeheader()
            writer.writerows(column_rows)
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
