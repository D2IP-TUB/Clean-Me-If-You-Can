#!/usr/bin/env python3
"""
Run v3 error-type analysis on all datasets and produce Table 4 + LaTeX output.

Requires datasets under ../data/ (see dataset_analysis/README.md).
"""
from __future__ import annotations

import os
import sys
import time
from collections import Counter
from pathlib import Path

import pandas as pd

from error_taxonomy.analyze_error_types import ERROR_TYPES, analyze

BASE = Path(__file__).resolve().parent
DATA = BASE.parent / "data"
OUT = BASE / "output"

DROP_COLS = ["id", "_id", "provenance_graph_iri", "graph_iri"]
LANG_COLS = ["name", "road", "locality", "region", "country", "house_number"]
PARS_COLS = ["name", "road", "locality", "region", "country", "postcode"]
ABBR_COLS = ["name", "road", "locality", "region", "country", "country_code"]
CHUNK_SIZE = 50_000


def load_pair(dirty_path: Path, clean_path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    dirty = pd.read_csv(dirty_path, low_memory=False, dtype=str).fillna("")
    clean = pd.read_csv(clean_path, low_memory=False, dtype=str).fillna("")
    for col in DROP_COLS:
        if col in dirty.columns:
            dirty = dirty.drop(columns=[col])
        if col in clean.columns:
            clean = clean.drop(columns=[col])
    if list(dirty.columns) != list(clean.columns):
        raise ValueError(
            f"Column mismatch: {dirty.columns.tolist()} vs {clean.columns.tolist()}"
        )
    return dirty, clean


def run_analysis(label: str, dirty_path: Path, clean_path: Path) -> tuple[int, dict, int]:
    print(f"\n{'=' * 60}", flush=True)
    print(f"[{time.strftime('%H:%M:%S')}] Analyzing: {label}", flush=True)
    print(f"  dirty: {dirty_path}", flush=True)
    print(f"  clean: {clean_path}", flush=True)
    t0 = time.time()

    dirty, clean = load_pair(dirty_path, clean_path)
    n_rows = len(dirty)
    n_cols = len(dirty.columns)
    total_cells = n_rows * n_cols
    print(
        f"  Loaded {n_rows:,} rows × {n_cols} cols = {total_cells:,} cells",
        flush=True,
    )

    lang_cols = [c for c in LANG_COLS if c in dirty.columns]
    pars_cols = [c for c in PARS_COLS if c in dirty.columns]
    abbr_cols = [c for c in ABBR_COLS if c in dirty.columns]

    agg_counts: Counter = Counter()
    n_chunks = (n_rows + CHUNK_SIZE - 1) // CHUNK_SIZE
    print(f"  Processing {n_chunks} chunks...", flush=True)

    for i in range(n_chunks):
        t_chunk = time.time()
        start = i * CHUNK_SIZE
        end = min(start + CHUNK_SIZE, n_rows)
        d_chunk = dirty.iloc[start:end].reset_index(drop=True)
        c_chunk = clean.iloc[start:end].reset_index(drop=True)

        overall_df, _, _cell_dict = analyze(
            c_chunk,
            d_chunk,
            language_cols=lang_cols,
            parsing_cols=pars_cols,
            abbrev_cols=abbr_cols,
            dumper=None,
        )
        for et, cnt in zip(overall_df["error_type"], overall_df["count"]):
            agg_counts[et] += int(cnt)

        elapsed = time.time() - t0
        rows_done = end
        eta = (n_rows - rows_done) / (rows_done / elapsed) if rows_done and elapsed else 0
        print(
            f"  chunk {i + 1}/{n_chunks}: rows {start:,}-{end:,} "
            f"({rows_done / n_rows * 100:.1f}%) chunk={time.time() - t_chunk:.1f}s "
            f"ETA={eta:.0f}s",
            flush=True,
        )

    print(f"  DONE: {label} — {time.time() - t0:.1f}s", flush=True)
    for et in ERROR_TYPES:
        cnt = agg_counts.get(et, 0)
        print(f"    {et:20s}: {cnt:>10,}  ({cnt / total_cells * 100:.2f}%)", flush=True)

    return n_rows, dict(agg_counts), total_cells


def pct(count: int, total: int) -> float:
    return count / total * 100.0 if total else 0.0


def fmt_pct(p: float) -> str:
    return f"{p:.1f}\\%"


def fmt_int(n: int) -> str:
    return f"{n:,}".replace(",", "{,}")


def make_row(label: str, n_rows: int, counts: dict, total_cells: int) -> dict:
    return {
        "label": label,
        "n_rows": n_rows,
        "Clean": pct(counts.get("Clean", 0), total_cells),
        "Missing": pct(counts.get("Missing", 0), total_cells),
        "Parsing_n": counts.get("Parsing", 0),
        "Parsing_p": pct(counts.get("Parsing", 0), total_cells),
        "Capitalization": pct(counts.get("Capitalization", 0), total_cells),
        "Special_Character": pct(counts.get("Special_Character", 0), total_cells),
        "Name_Reformat": pct(counts.get("Name_Reformat", 0), total_cells),
        "Language": pct(counts.get("Language", 0), total_cells),
        "Abbreviation": pct(counts.get("Abbreviation", 0), total_cells),
        "Token_Subset": pct(counts.get("Token_Subset", 0), total_cells),
        "Typo": pct(counts.get("Typo", 0), total_cells),
        "Word_Substitution": pct(
            counts.get("Word_Substitution", 0) + counts.get("Word_Variant", 0),
            total_cells,
        ),
        "Misc": pct(counts.get("Misc", 0), total_cells),
    }


def latex_row(row: dict, label_cmd: str | None = None) -> str:
    lbl = label_cmd if label_cmd else row["label"].replace("_", "\\_")
    cols = [
        lbl,
        fmt_int(row["n_rows"]),
        fmt_pct(row["Clean"]),
        fmt_pct(row["Missing"]),
        str(row["Parsing_n"]),
        f"{row['Parsing_p']:.3f}\\%",
        fmt_pct(row["Capitalization"]),
        fmt_pct(row["Special_Character"]),
        fmt_pct(row["Name_Reformat"]),
        fmt_pct(row["Language"]),
        fmt_pct(row["Abbreviation"]),
        fmt_pct(row["Token_Subset"]),
        fmt_pct(row["Typo"]),
        fmt_pct(row["Word_Substitution"]),
        fmt_pct(row["Misc"]),
    ]
    return " & ".join(cols) + " \\\\"


def discover_datasets() -> list[tuple[str, str | None, Path, Path]]:
    """Return (label, latex_cmd, dirty_path, clean_path) for all datasets."""
    datasets: list[tuple[str, str | None, Path, Path]] = [
        (
            "full_unnamed",
            "\\dsnoname{}",
            DATA / "full_unnamed" / "dirty.csv",
            DATA / "full_unnamed" / "clean.csv",
        ),
        (
            "full_named",
            "\\dsname{}",
            DATA / "full_named" / "dirty.csv",
            DATA / "full_named" / "clean.csv",
        ),
        (
            "slice_us",
            "\\usslice{}",
            DATA / "slices" / "us" / "named" / "dirty.csv",
            DATA / "slices" / "us" / "named" / "clean.csv",
        ),
        (
            "slice_de",
            "\\deslice{}",
            DATA / "slices" / "de" / "named" / "dirty.csv",
            DATA / "slices" / "de" / "named" / "clean.csv",
        ),
        (
            "slice_ru",
            "\\ruslice{}",
            DATA / "slices" / "ru" / "named" / "dirty.csv",
            DATA / "slices" / "ru" / "named" / "clean.csv",
        ),
    ]

    subsets_dir = DATA / "subsets"
    if subsets_dir.is_dir():
        for poi in sorted(subsets_dir.iterdir()):
            named = poi / "named"
            dirty = named / "dirty.csv"
            clean = named / "clean.csv"
            if dirty.is_file() and clean.is_file():
                datasets.append((poi.name, None, dirty, clean))

    return datasets


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    if not DATA.is_dir() or not any(DATA.iterdir()):
        print(
            f"ERROR: data directory not found or empty: {DATA}\n"
            "Download the published datasets from HuggingFace and place them under ../data/\n"
            "See dataset_analysis/README.md for the expected directory layout.",
            file=sys.stderr,
        )
        sys.exit(1)

    datasets = discover_datasets()

    missing = [(lbl, d, c) for lbl, _, d, c in datasets if not d.is_file() or not c.is_file()]
    if missing:
        print("Missing dataset files (stage them under ../data/ first):", file=sys.stderr)
        for lbl, d, c in missing:
            print(f"  {lbl}: {d} / {c}", file=sys.stderr)
        sys.exit(1)

    results: list[dict] = []
    progress_csv = OUT / "error_type_results_progress.csv"

    for label, cmd, dirty_path, clean_path in datasets:
        n_rows, counts, total_cells = run_analysis(label, dirty_path, clean_path)
        row = make_row(label, n_rows, counts, total_cells)
        row["cmd"] = cmd
        results.append(row)
        pd.DataFrame([{k: v for k, v in r.items() if k != "cmd"} for r in results]).to_csv(
            progress_csv, index=False
        )

    out_csv = OUT / "error_type_results_all.csv"
    pd.DataFrame([{k: v for k, v in r.items() if k != "cmd"} for r in results]).to_csv(
        out_csv, index=False
    )
    print(f"\nResults saved to {out_csv}")

    # LaTeX table (Table 4)
    header = r"""\begin{table*}[t]
\centering
\scriptsize
\setlength{\tabcolsep}{4pt}
\caption{Dataset variations and their error-type distributions (percentages of total cells). \emph{Parsing} is reported as an absolute count due to its negligible overall frequency. \emph{Word Subst.} aggregates lexical substitutions and word variants.}
\label{tab:facility-error-summary}
\resizebox{\textwidth}{!}{%
\begin{tabular}{lrrrrrrrrrrrrrr}
\toprule
Slice & Num-rows & Clean & Missing & Parsing (\#) & Parsing (\%) & Capitalization & Special Chars & Name Reformat & Language & Abbreviation & Token Subset & Typo & Word Subst. & Misc \\
\midrule"""

    footer = r"""\bottomrule
\end{tabular}}
\end{table*}"""

    latex_path = OUT / "error_type_table.tex"
    main_labels = ["full_unnamed", "full_named", "slice_us", "slice_de", "slice_ru"]
    main_rows = [r for r in results if r["label"] in main_labels]
    main_rows.sort(key=lambda r: main_labels.index(r["label"]))
    subset_rows = [r for r in results if r["label"] not in main_labels]

    lines = [header]
    for r in main_rows[:2]:
        lines.append(latex_row(r, r["cmd"]))
    lines.append(r"\midrule")
    for r in main_rows[2:]:
        lines.append(latex_row(r, r["cmd"]))
    lines.append(r"\midrule")
    for r in subset_rows:
        lines.append(latex_row(r))
    lines.append(footer)

    latex_text = "\n".join(lines) + "\n"
    latex_path.write_text(latex_text)
    published_tex = BASE / "error_type_table.tex"
    published_tex.write_text(latex_text)
    print(f"LaTeX table saved to {latex_path} and {published_tex}")

    published_csv = BASE / "error_type_table.csv"
    pd.DataFrame(
        [
            {
                "slice": r["label"],
                "n_rows": r["n_rows"],
                "clean_pct": round(r["Clean"], 3),
                "missing_pct": round(r["Missing"], 3),
                "parsing_n": r["Parsing_n"],
                "parsing_pct": round(r["Parsing_p"], 3),
                "capitalization_pct": round(r["Capitalization"], 3),
                "special_character_pct": round(r["Special_Character"], 3),
                "name_reformat_pct": round(r["Name_Reformat"], 3),
                "language_pct": round(r["Language"], 3),
                "abbreviation_pct": round(r["Abbreviation"], 3),
                "token_subset_pct": round(r["Token_Subset"], 3),
                "typo_pct": round(r["Typo"], 3),
                "word_substitution_pct": round(r["Word_Substitution"], 3),
                "misc_pct": round(r["Misc"], 3),
            }
            for r in results
        ]
    ).to_csv(published_csv, index=False)
    print(f"Published CSV saved to {published_csv}")


if __name__ == "__main__":
    main()
