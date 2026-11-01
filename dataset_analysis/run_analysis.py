#!/usr/bin/env python3
"""Run the multi-label error taxonomy on every dataset under ../data.

Writes output/multilabel/<label>/summary.json and a multi-label
error-type table under output/. The checked-in error_type_table.csv
is left unchanged.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent / "error_taxonomy"))
from analyze_error_types import canonicalize_summary  # noqa: E402
from analyze_error_types_multilabel import run_dataset  # noqa: E402

BASE = Path(__file__).resolve().parent
DATA = BASE.parent / "data"
OUT = BASE / "output"
ML_OUT = OUT / "multilabel"

LANG_COLS = {"name", "road", "locality", "region", "country", "house_number"}
PARS_COLS = {"name", "road", "locality", "region", "country", "postcode"}
ABBR_COLS = {"name", "road", "locality", "region", "country", "country_code"}

N_WORKERS = os.cpu_count() or 8
CHUNK_ROWS = 20_000


def discover_datasets() -> list[tuple[str, str, str | None, Path, Path]]:
    """Return (table_label, ml_label, latex_cmd, dirty_path, clean_path)."""
    datasets: list[tuple[str, str, str | None, Path, Path]] = [
        (
            "full_unnamed", "full_unnamed", "\\dsnoname{}",
            DATA / "full_unnamed" / "dirty.csv",
            DATA / "full_unnamed" / "clean.csv",
        ),
        (
            "full_named", "full_named", "\\dsname{}",
            DATA / "full_named" / "dirty.csv",
            DATA / "full_named" / "clean.csv",
        ),
        (
            "slice_us", "slice_us", "\\usslice{}",
            DATA / "slices" / "us" / "named" / "dirty.csv",
            DATA / "slices" / "us" / "named" / "clean.csv",
        ),
        (
            "slice_de", "slice_de", "\\deslice{}",
            DATA / "slices" / "de" / "named" / "dirty.csv",
            DATA / "slices" / "de" / "named" / "clean.csv",
        ),
        (
            "slice_ru", "slice_ru", "\\ruslice{}",
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
                datasets.append((poi.name, f"facility_{poi.name}", None, dirty, clean))

    return datasets


def run_one(table_label: str, ml_label: str, dirty_path: Path, clean_path: Path) -> dict:
    print(f"\n{'=' * 60}", flush=True)
    print(f"[{time.strftime('%H:%M:%S')}] Analyzing: {table_label}", flush=True)
    print(f"  dirty: {dirty_path}", flush=True)
    print(f"  clean: {clean_path}", flush=True)
    t0 = time.time()

    outdir = ML_OUT / ml_label
    result = run_dataset(
        table_label, str(dirty_path), str(clean_path), str(outdir),
        n_workers=N_WORKERS, chunk_rows=CHUNK_ROWS,
        lang_cols=LANG_COLS, parsing_cols=PARS_COLS, abbrev_cols=ABBR_COLS,
        lang_lingua_off_cols={"locality"},
        lang_word_level_cols=LANG_COLS,
    )

    dt = time.time() - t0
    print(f"  DONE: {table_label} — {dt:.1f}s", flush=True)
    total_cells = result["total_cells"]
    state = result["state_counts"]
    labels = result["label_counts"]
    for name in ("Clean", "Missing", "Error"):
        cnt = state.get(name, 0)
        print(f"    {name:20s}: {cnt:>10,}  ({cnt / total_cells * 100:.2f}%)", flush=True)
    for name in TYPE_KEYS:
        cnt = labels.get(name, 0)
        print(f"    {name:20s}: {cnt:>10,}  ({cnt / total_cells * 100:.2f}%)", flush=True)

    return result


def pct(count: int, total: int) -> float:
    return count / total * 100.0 if total else 0.0


def fmt_pct(p: float) -> str:
    return f"{p:.1f}\\%"


def fmt_int(n: int) -> str:
    return f"{n:,}".replace(",", "{,}")


TYPE_KEYS = [
    "Special_Character",
    "Language",
    "Abbreviation",
    "Token_Subset",
    "Typo",
    "Formatting",
    "Semantic",
]


def make_row(label: str, n_rows: int, state: dict, labels: dict, total_cells: int) -> dict:
    row = {
        "label": label,
        "n_rows": n_rows,
        "Clean": pct(state.get("Clean", 0), total_cells),
        "Missing": pct(state.get("Missing", 0), total_cells),
        "Error": pct(state.get("Error", 0), total_cells),
    }
    for key in TYPE_KEYS:
        row[key] = pct(labels.get(key, 0), total_cells)
    return row


def latex_row(row: dict, label_cmd: str | None = None) -> str:
    lbl = label_cmd if label_cmd else row["label"].replace("_", "\\_")
    cols = [
        lbl,
        fmt_int(row["n_rows"]),
        fmt_pct(row["Clean"]),
        fmt_pct(row["Missing"]),
        fmt_pct(row["Error"]),
        fmt_pct(row["Special_Character"]),
        fmt_pct(row["Language"]),
        fmt_pct(row["Abbreviation"]),
        fmt_pct(row["Token_Subset"]),
        fmt_pct(row["Typo"]),
        fmt_pct(row["Formatting"]),
        fmt_pct(row["Semantic"]),
    ]
    return " & ".join(cols) + " \\\\"


def load_summary_row(table_label: str, ml_label: str) -> dict | None:
    """Rebuild one table row from an existing summary.json."""
    path = ML_OUT / ml_label / "summary.json"
    if not path.is_file():
        return None
    with open(path) as f:
        s = canonicalize_summary(json.load(f))
    state = s.get("state_counts") or {}
    labels = s.get("label_counts") or {}
    total = s.get("total_cells") or sum(state.values())
    return make_row(table_label, s["n_rows"], state, labels, total)


def main() -> None:
    from_summaries = "--from-summaries" in sys.argv
    OUT.mkdir(parents=True, exist_ok=True)
    ML_OUT.mkdir(parents=True, exist_ok=True)

    if not DATA.is_dir() or not any(DATA.iterdir()):
        print(
            f"ERROR: data directory not found or empty: {DATA}\n"
            "Download the published datasets from Zenodo "
            "(https://zenodo.org/records/20841898) and place them under ../data/\n"
            "See dataset_analysis/README.md for the expected directory layout.",
            file=sys.stderr,
        )
        sys.exit(1)

    datasets = discover_datasets()

    missing = [(lbl, d, c) for lbl, _, _, d, c in datasets if not d.is_file() or not c.is_file()]
    if missing:
        print("SKIPPING datasets with missing files (not staged under ../data/):", file=sys.stderr)
        for lbl, d, c in missing:
            print(f"  {lbl}: {d} / {c}", file=sys.stderr)
        missing_labels = {lbl for lbl, _, _ in missing}
        datasets = [ds for ds in datasets if ds[0] not in missing_labels]
        if not datasets:
            print("ERROR: no datasets available to run.", file=sys.stderr)
            sys.exit(1)

    results: list[dict] = []
    manifest: list[dict] = []
    progress_csv = OUT / "error_type_results_progress.csv"
    t_start = time.time()

    for table_label, ml_label, cmd, dirty_path, clean_path in datasets:
        t0 = time.time()
        if from_summaries:
            row = load_summary_row(table_label, ml_label)
            if row is None:
                print(f"  [--from-summaries] no summary.json for {ml_label}, skipping",
                      file=sys.stderr)
                continue
            print(f"  [--from-summaries] {table_label}")
        else:
            ml_result = run_one(table_label, ml_label, dirty_path, clean_path)
            dt = time.time() - t0
            manifest.append({"label": ml_label, "outdir": str(ML_OUT / ml_label),
                             "seconds": round(dt, 1)})
            with open(ML_OUT / "manifest.json", "w") as f:
                json.dump(manifest, f, indent=2)
            row = make_row(table_label, ml_result["n_rows"],
                           ml_result["state_counts"], ml_result["label_counts"],
                           ml_result["total_cells"])
        row["cmd"] = cmd
        results.append(row)
        pd.DataFrame([{k: v for k, v in r.items() if k != "cmd"} for r in results]).to_csv(
            progress_csv, index=False
        )

    print(f"\nAll datasets done in {time.time() - t_start:.1f}s. "
          f"Multi-label outputs under {ML_OUT}")

    out_csv = OUT / "error_type_results_all.csv"
    pd.DataFrame([{k: v for k, v in r.items() if k != "cmd"} for r in results]).to_csv(
        out_csv, index=False
    )
    print(f"Results saved to {out_csv}")

    header = r"""\begin{table*}[t]
\centering
\scriptsize
\setlength{\tabcolsep}{4pt}
\caption{Address datasets and their multi-label error-type distributions (percentages of total cells). Clean, Missing, and Error partition the cells. A cell can carry more than one error label, so the type columns can sum to more than Error.}
\label{tab:facility-error-summary}
\resizebox{\textwidth}{!}{%
\begin{tabular}{lrrrrrrrrrrrr}
\toprule
Slice & Num-rows & Clean & Missing & Error & Special Chars & Language & Abbreviation & Token Subset & Typo & Formatting & Semantic \\
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
    print(f"LaTeX table saved to {latex_path}")
    print(
        "Checked-in dataset_analysis/error_type_table.csv is left unchanged. "
        "It is the multi-label table and includes books and movies."
    )

    published_csv = OUT / "error_type_table.csv"
    pd.DataFrame(
        [
            {
                "slice": r["label"],
                "n_rows": r["n_rows"],
                "clean_pct": round(r["Clean"], 3),
                "missing_pct": round(r["Missing"], 3),
                "error_pct": round(r["Error"], 3),
                "special_character_pct": round(r["Special_Character"], 3),
                "language_pct": round(r["Language"], 3),
                "abbreviation_pct": round(r["Abbreviation"], 3),
                "token_subset_pct": round(r["Token_Subset"], 3),
                "typo_pct": round(r["Typo"], 3),
                "formatting_pct": round(r["Formatting"], 3),
                "semantic_pct": round(r["Semantic"], 3),
            }
            for r in results
        ]
    ).to_csv(published_csv, index=False)
    print(f"Multi-label CSV saved to {published_csv}")


if __name__ == "__main__":
    main()
