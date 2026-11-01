#!/usr/bin/env python3
"""Drop columns and put ground truth back into cells of selected error types.

    python benchmark_customization_scripts/customize_slice.py \
        --dirty data/slices/de/named/dirty.csv \
        --clean data/slices/de/named/clean.csv \
        --drop-columns country_code \
        --exclude-preset representational \
        --output-dir benchmark_customization_scripts/data/de
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from multiprocessing import get_context
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "dataset_analysis" / "error_taxonomy"))

from analyze_error_types import (  # noqa: E402
    ERROR_TYPES,
    PLACE_COLS,
    classify_cached,
    normalize_cell,
    region_holds_locality,
    require_libpostal,
    _dictionary_expansions,
    _gazetteer,
    _place_type_words,
    _street_type_words,
    _subdivision_names_and_codes,
)

CHUNK_ROWS = 20_000

# Same content written another way: punctuation, abbreviation, token order,
# phonetic spelling, number form.
REPRESENTATIONAL = ("Special_Character", "Abbreviation", "Formatting")

DOMAINS = {
    "address": {
        "lang": {"name", "road", "locality", "region", "country", "house_number"},
        "parsing": {"name", "road", "locality", "region", "country", "postcode"},
        "abbrev": {"name", "road", "locality", "region", "country", "country_code"},
        "lingua_off": {"locality"},
        "word_level": {"name", "road", "locality", "region", "country", "house_number"},
        "guard_off": set(),
    },
    "books": {
        "lang": {"title", "author", "publisher"},
        "parsing": {"title", "author", "publisher"},
        "abbrev": {"title", "author", "publisher"},
        "lingua_off": set(),
        "word_level": set(),
        "guard_off": set(),
    },
    "movies": {
        "lang": {"title", "director", "actor", "genre"},
        "parsing": {"title", "director", "actor", "genre"},
        "abbrev": {"title", "director", "actor", "genre"},
        "lingua_off": set(),
        "word_level": set(),
        "guard_off": {"title"},
    },
}

_DIRTY = None
_CLEAN = None
_COLS: list[str] = []
_EXCLUDE: set[str] = set()
_CFG: dict = {}


def resolve_types(names: list[str]) -> list[str]:
    known = {t.lower(): t for t in ERROR_TYPES}
    out = []
    for name in names:
        key = name.strip().lower()
        if not key:
            continue
        label = known.get(key)
        if label is None:
            raise SystemExit(
                f"Unknown error type {name!r}. Known types: {', '.join(ERROR_TYPES)}."
            )
        if label not in out:
            out.append(label)
    return out


def load_pair(dirty_path: Path, clean_path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    dirty = pd.read_csv(dirty_path, low_memory=False, dtype=str, keep_default_na=False)
    clean = pd.read_csv(clean_path, low_memory=False, dtype=str, keep_default_na=False)
    return dirty, clean


def align(dirty: pd.DataFrame, clean: pd.DataFrame, drop_columns: list[str]) -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    if len(dirty) != len(clean):
        raise SystemExit(f"Row counts differ: dirty={len(dirty)} clean={len(clean)}.")
    if "id" in dirty.columns and "id" in clean.columns and not dirty["id"].equals(clean["id"]):
        raise SystemExit("The id columns of dirty and clean do not match.")

    missing = [c for c in drop_columns if c not in dirty.columns and c not in clean.columns]
    if missing:
        have = list(dict.fromkeys(list(dirty.columns) + list(clean.columns)))
        raise SystemExit(f"Columns not in the input: {', '.join(missing)}. Columns: {', '.join(have)}.")

    dirty = dirty.drop(columns=[c for c in drop_columns if c in dirty.columns])
    clean = clean.drop(columns=[c for c in drop_columns if c in clean.columns])
    shared = [c for c in dirty.columns if c in clean.columns]
    dirty_only = [c for c in dirty.columns if c not in clean.columns]
    clean_only = [c for c in clean.columns if c not in dirty.columns]
    if dirty_only:
        print(f"dropping dirty-only columns: {', '.join(dirty_only)}")
    if clean_only:
        print(f"dropping clean-only columns: {', '.join(clean_only)}")
    return dirty[shared].reset_index(drop=True), clean[shared].reset_index(drop=True), shared


def _cell_labels(val, tru, col: str, dirty_loc, clean_loc) -> frozenset:
    cfg = _CFG
    v = normalize_cell(val)
    t = normalize_cell(tru)
    labels = classify_cached(
        v, t, col,
        col in cfg["lang"],
        col in cfg["parsing"],
        col in cfg["abbrev"],
        None if col not in cfg["guard_off"] else False,
        col not in cfg["lingua_off"],
        col in cfg["word_level"],
    )
    if col == "region" and "locality" in _COLS:
        labels = region_holds_locality(
            labels, v, t, normalize_cell(dirty_loc), normalize_cell(clean_loc),
        )
    return labels


def _process_range(bounds: tuple[int, int]):
    start, end = bounds
    dirty, clean, cols = _DIRTY, _CLEAN, _COLS
    restored = []
    counts = Counter()
    locality = "locality" in cols
    if locality:
        dl = dirty["locality"].to_numpy()
        cl = clean["locality"].to_numpy()
    for col in cols:
        dv = dirty[col].to_numpy()
        cv = clean[col].to_numpy()
        for i in range(start, end):
            loc_d = dl[i] if locality else ""
            loc_c = cl[i] if locality else ""
            labels = _cell_labels(dv[i], cv[i], col, loc_d, loc_c)
            if not labels:
                counts["Unresolved_Type"] += 1
            else:
                for label in labels:
                    counts[label] += 1
            # Restore only when every label is one of the excluded types.
            # A cell that also carries another label stays dirty.
            if labels and labels <= _EXCLUDE:
                restored.append((i, col))
    return restored, counts


def _warm(columns: list[str], cfg: dict) -> None:
    if cfg["abbrev"] & set(columns):
        require_libpostal()
        _dictionary_expansions()
        _street_type_words()
        _place_type_words()
        _subdivision_names_and_codes()
    if PLACE_COLS & set(columns):
        _gazetteer()


def restore(dirty: pd.DataFrame, clean: pd.DataFrame, exclude: set[str], cfg: dict, workers: int):
    global _DIRTY, _CLEAN, _COLS, _EXCLUDE, _CFG
    _DIRTY, _CLEAN = dirty, clean
    _COLS = list(dirty.columns)
    _EXCLUDE = exclude
    _CFG = cfg
    if not exclude:
        return dirty.copy(), {}, {}
    _warm(_COLS, cfg)

    n = len(dirty)
    ranges = [(s, min(s + CHUNK_ROWS, n)) for s in range(0, n, CHUNK_ROWS)] or [(0, 0)]
    restored_at = defaultdict(list)
    counts = Counter()

    def fold(restored, part_counts):
        counts.update(part_counts)
        for i, col in restored:
            restored_at[col].append(i)

    if not exclude or workers <= 1 or n == 0:
        for bounds in ranges:
            fold(*_process_range(bounds))
    else:
        ctx = get_context("fork")
        with ctx.Pool(workers) as pool:
            for restored, part_counts in pool.imap_unordered(_process_range, ranges, chunksize=1):
                fold(restored, part_counts)

    out = dirty.copy()
    restored_counts = {}
    for col, idx in restored_at.items():
        out.loc[idx, col] = clean.loc[idx, col].to_numpy()
        restored_counts[col] = len(idx)
    return out, dict(counts), restored_counts


def customize(dirty, clean, drop_columns, exclude_types, domain="address", workers=1):
    if domain not in DOMAINS:
        raise SystemExit(f"Unknown domain {domain!r}. Choose from: {', '.join(DOMAINS)}.")
    dirty, clean, columns = align(dirty, clean, list(drop_columns))
    exclude = set(resolve_types(list(exclude_types)))
    customized, type_counts, restored_by_column = restore(
        dirty, clean, exclude, DOMAINS[domain], workers,
    )
    report = {
        "domain": domain,
        "rows": len(customized),
        "columns": columns,
        "dropped_columns": list(drop_columns),
        "excluded_types": sorted(exclude),
        "type_counts": (
            {t: type_counts.get(t, 0) for t in ERROR_TYPES} if exclude else None
        ),
        "cells_restored": sum(restored_by_column.values()),
        "restored_by_column": restored_by_column,
    }
    return customized, clean, report


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dirty", required=True, type=Path)
    p.add_argument("--clean", required=True, type=Path)
    p.add_argument("--output-dir", required=True, type=Path)
    p.add_argument("--drop-columns", nargs="*", default=[])
    p.add_argument("--exclude-types", nargs="*", default=[])
    p.add_argument(
        "--exclude-preset",
        choices=["representational"],
        help="representational = Special_Character, Abbreviation, Formatting",
    )
    p.add_argument("--domain", choices=sorted(DOMAINS), default="address")
    p.add_argument("--workers", type=int, default=os.cpu_count() or 1)
    args = p.parse_args()

    exclude = list(args.exclude_types)
    if args.exclude_preset == "representational":
        exclude.extend(REPRESENTATIONAL)
    if not args.drop_columns and not exclude:
        raise SystemExit("Pass --drop-columns, --exclude-types, or --exclude-preset.")

    dirty, clean = load_pair(args.dirty, args.clean)
    dirty, clean, report = customize(
        dirty, clean, args.drop_columns, exclude, args.domain, args.workers,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    dirty.to_csv(args.output_dir / "dirty.csv", index=False)
    clean.to_csv(args.output_dir / "clean.csv", index=False)
    (args.output_dir / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(
        f"wrote {args.output_dir}  rows={report['rows']}  "
        f"restored={report['cells_restored']}"
    )


if __name__ == "__main__":
    main()
