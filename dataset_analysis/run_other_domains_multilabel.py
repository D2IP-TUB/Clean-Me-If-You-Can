#!/usr/bin/env python3
"""Run the multi-label taxonomy on books and movies.

Reads ../data/<domain>/{dirty,clean}.csv. Columns that exist on only one
side are dropped before classification.

    python run_other_domains_multilabel.py
    python run_other_domains_multilabel.py --only books
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent / "error_taxonomy"))
from analyze_error_types_multilabel import run_dataset_aligned  # noqa: E402

BASE = Path(__file__).resolve().parent
DATA = BASE.parent / "data"
OUT = BASE / "output" / "multilabel"

N_WORKERS = os.cpu_count() or 8
CHUNK_ROWS = 20_000

ALWAYS_DROP = {"id", "_id", "source_subset", "provenance_graph_iri", "graph_iri"}


class Domain:
    def __init__(self, label, dirty_path, clean_path, text_cols, lang_guard_off_cols=None):
        self.label = label
        self.dirty_path = Path(dirty_path)
        self.clean_path = Path(clean_path)
        self.lang_cols = set(text_cols)
        self.parsing_cols = set(text_cols)
        self.abbrev_cols = set(text_cols)
        self.lang_guard_off_cols = set(lang_guard_off_cols or ())

    def ready(self) -> bool:
        return self.dirty_path.is_file() and self.clean_path.is_file()


DOMAINS = [
    Domain(
        label="books",
        dirty_path=DATA / "books" / "dirty.csv",
        clean_path=DATA / "books" / "clean.csv",
        text_cols={"title", "author", "publisher"},
    ),
    Domain(
        label="movies",
        dirty_path=DATA / "movies" / "dirty.csv",
        clean_path=DATA / "movies" / "clean.csv",
        text_cols={"title", "director", "actor", "genre"},
        # A translated title often keeps one proper noun, so the shared-token
        # guard would hide the language difference.
        lang_guard_off_cols={"title"},
    ),
]


def align(dirty_path: Path, clean_path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    dirty = pd.read_csv(dirty_path, low_memory=False, dtype=str, keep_default_na=False)
    clean = pd.read_csv(clean_path, low_memory=False, dtype=str, keep_default_na=False)
    dirty = dirty.drop(columns=[c for c in ALWAYS_DROP if c in dirty.columns])
    clean = clean.drop(columns=[c for c in ALWAYS_DROP if c in clean.columns])
    common = [c for c in dirty.columns if c in clean.columns]
    dirty_only = [c for c in dirty.columns if c not in clean.columns]
    clean_only = [c for c in clean.columns if c not in dirty.columns]
    if dirty_only:
        print(f"  dropping dirty-only columns: {dirty_only}")
    if clean_only:
        print(f"  dropping clean-only columns: {clean_only}")
    return dirty[common], clean[common]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--only", nargs="*", default=None, help="Run only these labels")
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    domains = [d for d in DOMAINS if args.only is None or d.label in args.only]
    if not domains:
        print("No matching domains.", file=sys.stderr)
        sys.exit(1)

    missing = [d.label for d in domains if not d.ready()]
    if missing and len(missing) == len(domains):
        print("No domain files under ../data/{books,movies}/.", file=sys.stderr)
        sys.exit(1)

    for d in domains:
        if not d.ready():
            print(f"SKIP {d.label}: missing {d.dirty_path} or {d.clean_path}", file=sys.stderr)
            continue
        print(f"\n{'=' * 60}\n[{time.strftime('%H:%M:%S')}] {d.label}", flush=True)
        t0 = time.time()
        dirty, clean = align(d.dirty_path, d.clean_path)
        run_dataset_aligned(
            d.label, dirty, clean, str(OUT / d.label),
            n_workers=N_WORKERS, chunk_rows=CHUNK_ROWS,
            lang_cols=d.lang_cols, parsing_cols=d.parsing_cols, abbrev_cols=d.abbrev_cols,
            lang_guard_off_cols=d.lang_guard_off_cols,
        )
        print(f"  [{d.label}] finished in {time.time() - t0:.1f}s", flush=True)


if __name__ == "__main__":
    main()
