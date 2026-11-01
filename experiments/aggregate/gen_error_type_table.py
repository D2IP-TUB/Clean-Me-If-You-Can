"""
Evaluate all systems on poi_Library and poi_ShoppingCenter,
average across 3 runs, and produce:
  - per-system avg CSV files in results/datawig (datawig already done)
  - experiments_data_results/results/error_type_table.tex  (filled LaTeX table)

Error-type → table column mapping
  Missing           → Missing
  Special_Character → Spec. Chars
  Language          → Lang.
  Abbreviation      → Abbrev.
  Token_Subset      → Tok. Subset
  Typo              → Typo
  Formatting        → Formatting
  Semantic          → Semantic
  Unresolved_Type   → Unresolved
"""

import os
import sys
import json
import pandas as pd
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from paths import (  # noqa: E402
    AGGREGATE_DIR,
    EXTERNAL_BASELINE_RESULTS_DIR,
    RESULTS_DIR,
    cell_labels_csv,
)

MAIN_RESULTS = RESULTS_DIR
EXT_RESULTS = EXTERNAL_BASELINE_RESULTS_DIR

CELL_ERROR_TYPES = {
    "poi_Library": cell_labels_csv("poi_Library"),
    "poi_ShoppingCenter": cell_labels_csv("poi_ShoppingCenter"),
}

# (system_name, results_root_dir, dataset_prefix_override, rerun_root)
# prefix_override: remaps dataset key → directory prefix for that system
# rerun_root: if set, runs found here take priority over results_root
SYSTEMS = [
    ("Raha",      os.path.join(EXT_RESULTS,  "raha"),      None,  None),
    ("Horizon",   os.path.join(EXT_RESULTS,  "horizon"),   None,  None),
    ("DataWig",   os.path.join(MAIN_RESULTS, "datawig"),   None,  None),
    ("HoloClean", os.path.join(EXT_RESULTS,  "holoclean"),
        {"poi_Library": "poiLibrary", "poi_ShoppingCenter": "poiShoppingCenter"}, None),
    ("Glocks",    os.path.join(MAIN_RESULTS, "glocks"),    None,
        os.path.join(MAIN_RESULTS, "glocks", "glocks")),
]
# UniClean has no results – kept as placeholder
UNICLEAN_PLACEHOLDER = "UniClean"

sys.path.insert(0, AGGREGATE_DIR)
from eval_by_error_type import load_cell_error_types, evaluate  # noqa: E402

# ---------------------------------------------------------------------------
# Column order for the table (12 error-type columns)
# index key → CSV error_type value
# ---------------------------------------------------------------------------
COL_MAP = [
    ("Missing",          "Missing"),
    ("Spec. Chars",      "Special_Character"),
    ("Lang.",            "Language"),
    ("Abbrev.",          "Abbreviation"),
    ("Tok. Subset",      "Token_Subset"),
    ("Typo",             "Typo"),
    ("Formatting",       "Formatting"),
    ("Semantic",         "Semantic"),
    ("Unresolved",       "Unresolved_Type"),
]
COL_HEADERS = [c[0] for c in COL_MAP]  # may be updated in main()
SCORE_COLS  = ["det_tp","det_fp","det_fn","det_precision","det_recall","det_f1",
               "cor_tp","cor_fp","cor_fn","cor_precision","cor_recall","cor_f1"]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def find_run_dirs(results_root: str, dataset_prefix: str,
                  rerun_root: str | None = None) -> list[str]:
    """Return up to 3 most-recent run dirs, preferring rerun_root over results_root."""
    def _scan(root: str) -> list[str]:
        if not os.path.isdir(root):
            return []
        return sorted(
            os.path.join(root, e)
            for e in os.listdir(root)
            if e.startswith(dataset_prefix + "_")
            and os.path.isdir(os.path.join(root, e))
        )

    rerun_dirs = _scan(rerun_root) if rerun_root else []
    # If reruns exist for this prefix, use them exclusively (same logic as avg_glocks_results.py)
    dirs = rerun_dirs if rerun_dirs else _scan(results_root)
    if len(dirs) > 3:
        dirs = dirs[-3:]
    return dirs


def resolve_prefix(ds: str, prefix_map: dict | None) -> str:
    """Return the actual directory prefix for a dataset, using override map if given."""
    if prefix_map and ds in prefix_map:
        return prefix_map[ds]
    return ds


def avg_over_runs(run_dirs: list[str], cell_dict: dict) -> pd.DataFrame | None:
    """Return averaged error-type metrics DataFrame, or None if no valid runs."""
    dfs = []
    for rdir in run_dirs:
        cells_csv = os.path.join(rdir, "cells.csv")
        if not os.path.isfile(cells_csv):
            continue
        dfs.append(evaluate(cells_csv, cell_dict))
    if not dfs:
        return None
    combined = pd.concat(dfs, ignore_index=True)
    sum_cols = ["n_cells","det_tp","det_fp","det_fn","cor_tp","cor_fp","cor_fn"]
    float_cols = [c for c in SCORE_COLS if c not in sum_cols]
    avg_float = combined.groupby("error_type")[float_cols].mean().round(4)
    sum_ints  = combined.groupby("error_type")[sum_cols].sum()
    result = pd.concat([sum_ints, avg_float], axis=1).reset_index()
    return result


def lookup_f1(df: pd.DataFrame | None, error_type: str | None, metric: str) -> str:
    """Return formatted metric string for a given error_type, or '--'."""
    if df is None or error_type is None:
        return "--"
    row = df[df["error_type"] == error_type]
    if row.empty:
        return "--"
    val = row[metric].iloc[0]
    if pd.isna(val):
        return "--"
    return f"{val:.3f}"


def lookup_prf(df: pd.DataFrame | None, error_type: str | None,
               p_col: str, r_col: str, f_col: str) -> str:
    """Return 'p/r/f' string (2 dp each) for a given error_type, or '--'."""
    if df is None or error_type is None:
        return "--"
    row = df[df["error_type"] == error_type]
    if row.empty:
        return "--"
    def fmt(c: str) -> str:
        v = row[c].iloc[0]
        return "--" if pd.isna(v) else f"{v:.2f}"
    return f"{fmt(p_col)}/{fmt(r_col)}/{fmt(f_col)}"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    datasets = ["poi_Library", "poi_ShoppingCenter"]

    # Pre-load cell dictionaries
    cell_dicts = {}
    for ds, path in CELL_ERROR_TYPES.items():
        print(f"Loading cell_error_types for {ds} …")
        cell_dicts[ds] = load_cell_error_types(path)
        print(f"  {len(cell_dicts[ds]):,} entries")

    # Compute averaged metrics for every (system, dataset)
    # results[system_name][dataset] = DataFrame or None
    results: dict[str, dict[str, pd.DataFrame | None]] = {}

    for sys_name, sys_root, prefix_map, rerun_root in SYSTEMS:
        results[sys_name] = {}
        for ds in datasets:
            actual_prefix = resolve_prefix(ds, prefix_map)
            run_dirs = find_run_dirs(sys_root, actual_prefix, rerun_root)
            print(f"  {sys_name} / {ds}: {len(run_dirs)} run(s)")
            avg_df = avg_over_runs(run_dirs, cell_dicts[ds])
            results[sys_name][ds] = avg_df

            if avg_df is not None:
                sys_key = sys_name.lower().replace("'", "")
                local_dir = os.path.join(MAIN_RESULTS, sys_key)
                if os.path.isdir(local_dir):
                    out_csv = os.path.join(local_dir, f"{ds}_avg_error_type_metrics.csv")
                else:
                    out_csv = os.path.join(sys_root, f"{ds}_avg_error_type_metrics.csv")
                avg_df.to_csv(out_csv, index=False)
                print(f"    Saved: {out_csv}")

    # UniClean: all --
    results[UNICLEAN_PLACEHOLDER] = {ds: None for ds in datasets}

    # -----------------------------------------------------------------------
    # Build LaTeX table
    # -----------------------------------------------------------------------

    def fmt_row(sys_name: str, ds: str, metric: str) -> str:
        df = results[sys_name][ds]
        vals = " & ".join(lookup_f1(df, et, metric) for _, et in COL_MAP)
        return f"      & {sys_name:<12} & {vals} \\\\"

    det_systems = [("Raha", "det_recall"), ("Horizon", "det_recall"), ("DataWig", "det_recall"),
                   ("HoloClean", "det_recall"), ("Glocks", "det_recall"), (UNICLEAN_PLACEHOLDER, "det_recall")]
    cor_systems = [("Baran" if s == "Raha" else s, "cor_f1") for s, _ in det_systems]
    results["Baran"] = {}
    baran_root = os.path.join(EXT_RESULTS, "baran")
    for ds in datasets:
        run_dirs = find_run_dirs(baran_root, ds)
        print(f"  Baran / {ds}: {len(run_dirs)} run(s)")
        avg_df = avg_over_runs(run_dirs, cell_dicts[ds])
        results["Baran"][ds] = avg_df
        if avg_df is not None:
            out_csv = os.path.join(baran_root, f"{ds}_avg_error_type_metrics.csv")
            avg_df.to_csv(out_csv, index=False)
            print(f"    Saved: {out_csv}")

    cor_systems = [("Baran", "cor_f1"), ("Horizon", "cor_f1"), ("DataWig", "cor_f1"),
                   ("HoloClean", "cor_f1"), ("Glocks", "cor_f1"), (UNICLEAN_PLACEHOLDER, "cor_f1")]

    col_header_str = " & ".join(
        f"\\makecell{{{h}}}" if " " in h else h
        for h in COL_HEADERS
    )

    def section(ds_label: str, ds_key: str) -> str:
        # Exclude the UniClean placeholder (no results)
        active_det = [(s, m) for s, m in det_systems if s != UNICLEAN_PLACEHOLDER]
        active_cor = [(s, m) for s, m in cor_systems if s != UNICLEAN_PLACEHOLDER]

        n_det  = len(active_det)    # 5
        n_cor  = len(active_cor)    # 5  (one row per system, P/R/F1 in each cell)
        total  = n_det + n_cor      # 10
        n_cols = 4 + len(COL_HEADERS)

        lines = []
        lines.append(f"% =====================  {ds_label}  =====================")
        lines.append(f"\\multirow{{{total}}}{{*}}{{\\rotatebox[origin=c]{{90}}{{{ds_label}}}}}")

        # Detection block: one row per system, recall only
        for i, (sys_name, _) in enumerate(active_det):
            df = results[sys_name][ds_key]
            vals = " & ".join(lookup_f1(df, et, "det_recall") for _, et in COL_MAP)
            task_col   = f"\\multirow{{{n_det}}}{{*}}{{Detection}}" if i == 0 else ""
            metric_col = f"\\multirow{{{n_det}}}{{*}}{{Recall}}"    if i == 0 else ""
            lines.append(f"  & {task_col}  & {sys_name:<12} & {metric_col} & {vals} \\\\")

        lines.append(f"  \\cmidrule{{2-{n_cols}}}")

        # Correction block: one row per system, P/R/F1 merged into each cell
        for i, (sys_name, _) in enumerate(active_cor):
            df = results[sys_name][ds_key]
            vals = " & ".join(lookup_f1(df, et, "cor_f1") for _, et in COL_MAP)
            task_col   = f"\\multirow{{{n_cor}}}{{*}}{{Correction}}" if i == 0 else ""
            metric_col = f"\\multirow{{{n_cor}}}{{*}}{{F1}}"         if i == 0 else ""
            lines.append(f"  & {task_col}  & {sys_name:<12} & {metric_col} & {vals} \\\\")

        return "\n".join(lines)

    header_cols = " & ".join(
        f"\\textbf{{{h}}}" if h in ("Missing",) else h
        for h in COL_HEADERS
    )

    tex = r"""\begin{table*}[t]
\centering
\caption{Error detection (recall) and correction (F1) performance across error types.}
\label{tab:error_types}
\scriptsize
\setlength{\tabcolsep}{3pt}
\renewcommand{\arraystretch}{1.0}
\begin{tabular}{c l l l """ + "c" * len(COL_HEADERS) + r"""}
\toprule
\textbf{Dataset} & \textbf{Task} & \textbf{Method} & \textbf{Metric}
& """ + " & ".join(COL_HEADERS) + r""" \\
\midrule

""" + section("Library", "poi_Library") + r"""

\midrule

""" + section("ShoppingCenter", "poi_ShoppingCenter") + r"""

\bottomrule
\end{tabular}
\end{table*}
"""

    out_tex = os.path.join(RESULTS_DIR, "error_type_table.tex")
    with open(out_tex, "w") as f:
        f.write(tex)
    print(f"\nLaTeX table written to: {out_tex}")
    print(tex)


if __name__ == "__main__":
    main()
