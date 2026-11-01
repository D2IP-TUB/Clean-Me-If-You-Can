#!/usr/bin/env python3
"""Multiprocessing driver for the multi-label error taxonomy.

Rule decisions live in analyze_error_types.classify. This module counts
labels, cardinality, and co-occurrence. A cell is counted under every
label it carries.
"""

from __future__ import annotations

import csv
import json
import os
import sys
import time
from collections import Counter
from multiprocessing import get_context

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from analyze_error_types import (  # noqa: E402
    normalize_cell,
    classify_cached,
    region_holds_locality,
    require_libpostal,
    _dictionary_expansions,
    _gazetteer,
    _place_type_words,
    _street_type_words,
    _subdivision_names_and_codes,
    PLACE_COLS,
    LABELS,
)

LANG_COLS = {"name", "road", "locality", "region", "country", "house_number"}
PARS_COLS = {"name", "road", "locality", "region", "country", "postcode"}
ABBR_COLS = {"name", "road", "locality", "region", "country", "country_code"}
DROP_COLS = {"id", "_id", "provenance_graph_iri", "graph_iri"}


# ---------------- Worker (fork-based, reads module-level globals) ----------------

_DIRTY: pd.DataFrame | None = None
_CLEAN: pd.DataFrame | None = None
_COLS: list[str] = []
_LANG_COLS: set = LANG_COLS
_PARS_COLS: set = PARS_COLS
_ABBR_COLS: set = ABBR_COLS
_LANG_GUARD_OFF_COLS: set = set()
_LANG_LINGUA_OFF_COLS: set = set()
_LANG_WORD_LEVEL_COLS: set = set()
_EXAMPLE_CAP = 4


def _process_range(args):
    start, end = args
    dirty, clean, cols = _DIRTY, _CLEAN, _COLS
    lang_cols, pars_cols, abbr_cols = _LANG_COLS, _PARS_COLS, _ABBR_COLS
    lang_guard_off_cols = _LANG_GUARD_OFF_COLS
    lang_lingua_off_cols = _LANG_LINGUA_OFF_COLS
    lang_word_level_cols = _LANG_WORD_LEVEL_COLS

    state_counts = Counter()
    label_counts = Counter()
    per_col_label_counts = {c: Counter() for c in cols}
    cardinality_counts = Counter()
    pair_counts = Counter()
    examples: dict[frozenset, list] = {}

    for c in cols:
        ul, up, ua = c in lang_cols, c in pars_cols, c in abbr_cols
        lg = None if c not in lang_guard_off_cols else False
        lu = c not in lang_lingua_off_cols
        lw = c in lang_word_level_cols
        dv = dirty[c].to_numpy()[start:end]
        cv = clean[c].to_numpy()[start:end]
        with_loc = c == "region" and "locality" in cols
        if with_loc:
            dl = dirty["locality"].to_numpy()[start:end]
            cl = clean["locality"].to_numpy()[start:end]
        for i in range(len(dv)):
            v = normalize_cell(dv[i])
            t = normalize_cell(cv[i])
            all_labels = classify_cached(v, t, c, ul, up, ua, lg, lu, lw)
            if with_loc:
                all_labels = region_holds_locality(all_labels, v, t, normalize_cell(dl[i]),
                                                   normalize_cell(cl[i]))

            if "Clean" in all_labels:
                state_counts["Clean"] += 1
                continue
            if "Missing" in all_labels:
                state_counts["Missing"] += 1
                continue
            state_counts["Error"] += 1
            labels = all_labels
            k = len(labels)
            cardinality_counts[k] += 1
            if k == 0:
                continue
            for lb in labels:
                label_counts[lb] += 1
                per_col_label_counts[c][lb] += 1
            if k >= 2:
                sl = sorted(labels)
                for ii in range(len(sl)):
                    for jj in range(ii + 1, len(sl)):
                        pair_counts[(sl[ii], sl[jj])] += 1
            bucket = examples.setdefault(labels, [])
            if len(bucket) < _EXAMPLE_CAP:
                bucket.append((c, v, t))

    return {
        "state_counts": state_counts,
        "label_counts": label_counts,
        "per_col_label_counts": per_col_label_counts,
        "cardinality_counts": cardinality_counts,
        "pair_counts": pair_counts,
        "examples": examples,
    }


def _merge_examples(dst: dict, src: dict, cap: int = _EXAMPLE_CAP):
    for k, v in src.items():
        bucket = dst.setdefault(k, [])
        if len(bucket) < cap:
            bucket.extend(v[: cap - len(bucket)])


def analyze_multilabel(dirty: pd.DataFrame, clean: pd.DataFrame, label: str,
                        n_workers: int = 1, chunk_rows: int = 20_000,
                        progress: bool = True,
                        lang_cols: set | None = None,
                        parsing_cols: set | None = None,
                        abbrev_cols: set | None = None,
                        lang_guard_off_cols: set | None = None,
                        lang_lingua_off_cols: set | None = None,
                        lang_word_level_cols: set | None = None) -> dict:
    """Multiprocessing driver. Mutates module globals so forked workers inherit the
    (read-only) dataframes via copy-on-write, avoiding pickling tens of millions of
    cells across the process boundary.
    """
    require_libpostal()
    _dictionary_expansions()
    _street_type_words()
    _place_type_words()
    _subdivision_names_and_codes()
    if PLACE_COLS & set(dirty.columns):
        _gazetteer()

    global _DIRTY, _CLEAN, _COLS, _LANG_COLS, _PARS_COLS, _ABBR_COLS
    global _LANG_GUARD_OFF_COLS, _LANG_LINGUA_OFF_COLS, _LANG_WORD_LEVEL_COLS
    _LANG_GUARD_OFF_COLS = lang_guard_off_cols if lang_guard_off_cols is not None else set()
    _LANG_LINGUA_OFF_COLS = lang_lingua_off_cols if lang_lingua_off_cols is not None else set()
    _LANG_WORD_LEVEL_COLS = (lang_word_level_cols
                              if lang_word_level_cols is not None else set())
    _DIRTY, _CLEAN = dirty, clean
    _COLS = list(dirty.columns)
    _LANG_COLS = lang_cols if lang_cols is not None else LANG_COLS
    _PARS_COLS = parsing_cols if parsing_cols is not None else PARS_COLS
    _ABBR_COLS = abbrev_cols if abbrev_cols is not None else ABBR_COLS
    n_rows = len(dirty)

    ranges = [(s, min(s + chunk_rows, n_rows)) for s in range(0, n_rows, chunk_rows)]

    state_counts = Counter()
    label_counts = Counter()
    per_col_label_counts = {c: Counter() for c in _COLS}
    cardinality_counts = Counter()
    pair_counts = Counter()
    examples: dict[frozenset, list] = {}

    t0 = time.time()
    done = 0

    def _fold(res):
        nonlocal done
        state_counts.update(res["state_counts"])
        label_counts.update(res["label_counts"])
        for c, cnt in res["per_col_label_counts"].items():
            per_col_label_counts[c].update(cnt)
        cardinality_counts.update(res["cardinality_counts"])
        pair_counts.update(res["pair_counts"])
        _merge_examples(examples, res["examples"])
        done += 1
        if progress and (done % max(1, len(ranges) // 20) == 0 or done == len(ranges)):
            elapsed = time.time() - t0
            pct = done / len(ranges) * 100
            print(f"    [{label}] {done}/{len(ranges)} chunks ({pct:.0f}%) "
                  f"elapsed={elapsed:.0f}s", flush=True)

    if n_workers <= 1:
        for r in ranges:
            _fold(_process_range(r))
    else:
        ctx = get_context("fork")
        with ctx.Pool(n_workers) as pool:
            for res in pool.imap_unordered(_process_range, ranges, chunksize=1):
                _fold(res)

    total_cells = n_rows * len(_COLS)
    unlabeled = cardinality_counts.get(0, 0)

    return {
        "label": label,
        "n_rows": n_rows,
        "n_cols": len(_COLS),
        "columns": _COLS,
        "total_cells": total_cells,
        "state_counts": dict(state_counts),
        "label_counts": dict(label_counts),
        "per_col_label_counts": {c: dict(cnt) for c, cnt in per_col_label_counts.items()},
        "cardinality_counts": {str(k): v for k, v in cardinality_counts.items()},
        "pair_counts": {f"{a}|{b}": v for (a, b), v in pair_counts.items()},
        "unlabeled_count": unlabeled,
        "examples": {
            "|".join(sorted(k)) if k else "Unlabeled": v for k, v in examples.items()
        },
    }


def load_pair(dirty_path: str, clean_path: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    dirty = pd.read_csv(dirty_path, low_memory=False, dtype=str, keep_default_na=False)
    clean = pd.read_csv(clean_path, low_memory=False, dtype=str, keep_default_na=False)
    for col in DROP_COLS:
        if col in dirty.columns:
            dirty = dirty.drop(columns=[col])
        if col in clean.columns:
            clean = clean.drop(columns=[col])
    if list(dirty.columns) != list(clean.columns):
        raise ValueError(f"Column mismatch: {dirty.columns.tolist()} vs {clean.columns.tolist()}")
    return dirty, clean


def _run_and_write(dirty: pd.DataFrame, clean: pd.DataFrame, label: str, outdir: str,
                    n_workers: int, chunk_rows: int,
                    lang_cols: set | None, parsing_cols: set | None,
                    abbrev_cols: set | None,
                    lang_guard_off_cols: set | None = None,
                    lang_lingua_off_cols: set | None = None,
                    lang_word_level_cols: set | None = None) -> dict:
    os.makedirs(outdir, exist_ok=True)
    print(f"  {len(dirty):,} rows x {len(dirty.columns)} cols", flush=True)

    result = analyze_multilabel(dirty, clean, label, n_workers=n_workers, chunk_rows=chunk_rows,
                                 lang_cols=lang_cols, parsing_cols=parsing_cols,
                                 abbrev_cols=abbrev_cols,
                                 lang_guard_off_cols=lang_guard_off_cols,
                                 lang_lingua_off_cols=lang_lingua_off_cols,
                                 lang_word_level_cols=lang_word_level_cols)

    with open(os.path.join(outdir, "summary.json"), "w") as f:
        json.dump(result, f, indent=2)

    examples_path = os.path.join(outdir, "examples.csv")
    with open(examples_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["label_combination", "feature", "dirty_value", "clean_value"])
        for combo, rows in result["examples"].items():
            for (c, v, t) in rows:
                w.writerow([combo, c, v, t])

    print(f"  DONE {label}: states={result['state_counts']}", flush=True)
    return result


def run_dataset(label: str, dirty_path: str, clean_path: str, outdir: str,
                 n_workers: int = 1, chunk_rows: int = 20_000,
                 lang_cols: set | None = None, parsing_cols: set | None = None,
                 abbrev_cols: set | None = None,
                 lang_guard_off_cols: set | None = None,
                 lang_lingua_off_cols: set | None = None,
                 lang_word_level_cols: set | None = None) -> dict:
    """Load a dirty/clean pair and write summary.json plus examples.csv.

    Drops id and graph-iri columns. If the two files do not share columns,
    align them first and call run_dataset_aligned.
    """
    print(f"[{time.strftime('%H:%M:%S')}] {label}: loading...", flush=True)
    dirty, clean = load_pair(dirty_path, clean_path)
    return _run_and_write(dirty, clean, label, outdir, n_workers, chunk_rows,
                           lang_cols, parsing_cols, abbrev_cols,
                           lang_guard_off_cols=lang_guard_off_cols,
                           lang_lingua_off_cols=lang_lingua_off_cols,
                           lang_word_level_cols=lang_word_level_cols)


def run_dataset_aligned(label: str, dirty: pd.DataFrame, clean: pd.DataFrame, outdir: str,
                         n_workers: int = 1, chunk_rows: int = 20_000,
                         lang_cols: set | None = None, parsing_cols: set | None = None,
                         abbrev_cols: set | None = None,
                         lang_guard_off_cols: set | None = None,
                         lang_lingua_off_cols: set | None = None,
                         lang_word_level_cols: set | None = None) -> dict:
    """Same as `run_dataset` but takes already-loaded, already column-aligned
    dataframes — for domains where dirty/clean don't share columns natively.
    """
    if list(dirty.columns) != list(clean.columns):
        raise ValueError(f"Column mismatch: {dirty.columns.tolist()} vs {clean.columns.tolist()}")
    print(f"[{time.strftime('%H:%M:%S')}] {label}: starting...", flush=True)
    return _run_and_write(dirty, clean, label, outdir, n_workers, chunk_rows,
                           lang_cols, parsing_cols, abbrev_cols,
                           lang_guard_off_cols=lang_guard_off_cols,
                           lang_lingua_off_cols=lang_lingua_off_cols,
                           lang_word_level_cols=lang_word_level_cols)


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--values", required=True, help="dirty CSV")
    p.add_argument("--targets", required=True, help="clean CSV")
    p.add_argument("--label", default="dataset")
    p.add_argument("--output_dir", default="output/multilabel_single_run")
    p.add_argument("--workers", type=int, default=os.cpu_count() or 1)
    p.add_argument("--chunk_rows", type=int, default=20_000)
    args = p.parse_args()

    run_dataset(args.label, args.values, args.targets, args.output_dir,
                n_workers=args.workers, chunk_rows=args.chunk_rows)
