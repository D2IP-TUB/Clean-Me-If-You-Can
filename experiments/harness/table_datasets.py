#!/usr/bin/env python3
"""
table_datasets.py — generate the LaTeX dataset-overview table for the paper.

Scans experiment_datasets/ (or a custom path) for effectiveness and runtime
datasets, computes actual cell-level error rates from dirty/clean CSV pairs
(using the same normalizer as evaluate.py / count_errors.py), then prints
a ready-to-paste LaTeX table.
"""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from paths import EXPERIMENT_DATASETS_DIR

# Default path — override with a positional argument
DEFAULT_DATASETS_DIR = Path(EXPERIMENT_DATASETS_DIR)

# Display labels for runtime sizes
RUNTIME_LABELS = {
    "full_full":    (r"\dsname{} (All)", None),   # None → infer from file
    "full_1000000": (r"\dsname{} (1M)",  1_000_000),
    "full_500000":  (r"\dsname{} (500k)", 500_000),
    "full_100000":  (r"\dsname{} (100k)", 100_000),
    "full_10000":   (r"\dsname{} (10k)",  10_000),
}
RUNTIME_ORDER = ["full_full", "full_1000000", "full_500000", "full_100000", "full_10000"]

# Display labels for effectiveness slices
EFFECTIVENESS_SLICE_LABELS = {
    "full":  r"\dsname{}",
    "de":    r"\deslice{}",
}

# POI display names (folder suffix → LaTeX label)
POI_LABELS = {
    "Library":       r"\textsf{Library}",
    "ShoppingCenter": r"\textsf{Shopping Centers}",
}


# ---------------------------------------------------------------------------
# Normalizer — identical to evaluate.py / count_errors.py
# ---------------------------------------------------------------------------
def _normalize(value: str) -> str:
    value = html.unescape(str(value))
    value = re.sub(r"[\t\n ]+", " ", value)
    return value.strip("\t\n ")


def compute_error_rate(dirty_path: Path, clean_path: Path) -> tuple[float, int, int]:
    """Return (error_rate, n_rows, n_cols) for a dirty/clean pair."""
    dirty = pd.read_csv(dirty_path, dtype=str, keep_default_na=False)
    clean = pd.read_csv(clean_path, dtype=str, keep_default_na=False)

    dirty = dirty.map(_normalize)
    clean = clean.map(_normalize)

    # Align column names in case they differ
    clean.columns = dirty.columns

    n_rows, n_cols = dirty.shape
    n_cells = n_rows * n_cols
    errors = int((dirty != clean).sum().sum())
    rate = errors / n_cells if n_cells > 0 else 0.0
    return rate, n_rows, n_cols


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def fmt_rows(n: int) -> str:
    return f"{n:,}"


def fmt_rate(r: float) -> str:
    return f"{r:.2f}"


def _read_pair(folder: Path) -> tuple[float, int, int] | None:
    dirty = folder / "dirty.csv"
    clean = folder / "clean.csv"
    if not dirty.exists() or not clean.exists():
        print(f"  [warn] missing dirty/clean in {folder}", file=sys.stderr)
        return None
    return compute_error_rate(dirty, clean)


# ---------------------------------------------------------------------------
# Data collection
# ---------------------------------------------------------------------------
def collect_effectiveness(eff_dir: Path) -> dict:
    """
    Returns a dict keyed by slice name with entries:
      { "label": str, "rates": [float], "n_rows": int, "n_cols": int }
    for named slices and POI slices.
    """
    slices = {}

    for subdir in sorted(eff_dir.iterdir()):
        if not subdir.is_dir():
            continue
        name = subdir.name

        if name.startswith("poi_"):
            # POI slice — single dirty/clean pair directly in the folder
            poi_key = name[len("poi_"):]
            label = POI_LABELS.get(poi_key, rf"\textsf{{{poi_key}}}")
            result = _read_pair(subdir)
            if result:
                rate, n_rows, n_cols = result
                slices[name] = {
                    "label": label,
                    "rates": [rate],
                    "n_rows": n_rows,
                    "n_cols": n_cols,
                    "is_poi": True,
                }
        else:
            # Named slice — contains sample_<name>_<rate>/ subdirs
            label = EFFECTIVENESS_SLICE_LABELS.get(name, rf"\textsf{{{name}}}")
            rates, n_rows, n_cols = [], None, None
            for sample_dir in sorted(subdir.iterdir()):
                if not sample_dir.is_dir():
                    continue
                result = _read_pair(sample_dir)
                if result:
                    r, nr, nc = result
                    rates.append(r)
                    if n_rows is None:
                        n_rows, n_cols = nr, nc
            if rates:
                slices[name] = {
                    "label": label,
                    "rates": sorted(rates),
                    "n_rows": n_rows,
                    "n_cols": n_cols,
                    "is_poi": False,
                }

    return slices


def collect_runtime(rt_dir: Path) -> list[dict]:
    """Returns list of dicts ordered by RUNTIME_ORDER."""
    rows = []
    for key in RUNTIME_ORDER:
        folder = rt_dir / key
        if not folder.exists():
            continue
        result = _read_pair(folder)
        if result is None:
            continue
        rate, n_rows, n_cols = result
        label, expected_rows = RUNTIME_LABELS[key]
        rows.append({
            "label": label,
            "rate": rate,
            "n_rows": n_rows,
            "n_cols": n_cols,
        })
    return rows


# ---------------------------------------------------------------------------
# LaTeX rendering
# ---------------------------------------------------------------------------
SLICE_ORDER = ["full", "de"]
POI_ORDER = ["poi_Library", "poi_ShoppingCenter"]


def render_latex(eff_slices: dict, runtime_rows: list[dict]) -> str:
    lines = []
    a = lines.append

    a(r"\begin{table}[t!]")
    a(r"\centering")
    a(r"\small")
    a(r"\caption{Overview of dataset samples used in the experiments.}")
    a(r"\label{tab:dataset_slices}")
    a(r"\renewcommand{\arraystretch}{1.1}")
    a(r"\begin{tabular}{lccr}")
    a(r"\hline")
    a(r"\textbf{Dataset} & \textbf{Error Rate} & \textbf{\#Rows} & \textbf{\#Columns} \\")
    a(r"\hline")
    a(r"\multicolumn{4}{c}{\textit{Effectiveness Experiments}} \\")
    a(r"\hline")

    # Named slices
    for key in SLICE_ORDER:
        if key not in eff_slices:
            continue
        s = eff_slices[key]
        rates_str = ", ".join(fmt_rate(r) for r in s["rates"])
        a(rf"{s['label']} & {rates_str} & {fmt_rows(s['n_rows'])} & {s['n_cols']} \\")

    # POI slices
    for key in POI_ORDER:
        if key not in eff_slices:
            continue
        s = eff_slices[key]
        rates_str = fmt_rate(s["rates"][0])
        a(rf"{s['label']} & {rates_str} & {fmt_rows(s['n_rows'])} & {s['n_cols']} \\")

    a(r"\hline")
    a(r"\multicolumn{4}{c}{\textit{Scalability Experiments}} \\")
    a(r"\hline")

    for row in runtime_rows:
        a(rf"{row['label']} & {fmt_rate(row['rate'])} & {fmt_rows(row['n_rows'])} & {row['n_cols']} \\")

    a(r"\hline")
    a(r"\end{tabular}")
    a(r"\end{table}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    datasets_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_DATASETS_DIR

    if not datasets_dir.exists():
        print(f"ERROR: {datasets_dir} does not exist.", file=sys.stderr)
        sys.exit(1)

    print(f"Scanning: {datasets_dir}", file=sys.stderr)

    eff_dir = datasets_dir / "effectiveness"
    rt_dir  = datasets_dir / "runtime"

    print("Computing error rates for effectiveness datasets...", file=sys.stderr)
    eff_slices = collect_effectiveness(eff_dir) if eff_dir.exists() else {}

    print("Computing error rates for runtime datasets...", file=sys.stderr)
    runtime_rows = collect_runtime(rt_dir) if rt_dir.exists() else []

    table = render_latex(eff_slices, runtime_rows)
    print(table)


if __name__ == "__main__":
    main()
