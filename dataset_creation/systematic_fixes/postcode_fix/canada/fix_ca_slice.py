#!/usr/bin/env python3
"""Write NAR keep_dirty postcodes into the Canada clean slice."""

from __future__ import annotations

import argparse
import csv
from collections import Counter
from pathlib import Path

from compare_nar import address_key as _nar_address_key
from nar_join import _paired_csv_rows, postal_code, province_abbr
from paths import RESULTS, SLICES

FIX_COL = "postcode_fix"

DIRTY_DEFAULT = SLICES / "slice_ca_dirty.csv"
CLEAN_DEFAULT = SLICES / "slice_ca_clean.csv"
NAR_DEFAULT = RESULTS / "unique_nar.csv"
OUT_DIRTY_DEFAULT = SLICES / "slice_ca_dirty_fixed.csv"
OUT_CLEAN_DEFAULT = SLICES / "slice_ca_clean_fixed.csv"


def format_clean_pc(pc: str) -> str:
    a = postal_code(pc)
    if len(a) != 6:
        compact = "".join(c for c in (pc or "").upper() if c.isalnum())
        if len(compact) > 6:
            a = postal_code(compact[-6:])
    if len(a) == 6:
        return f"{a[:3]} {a[3:]}"
    return ""


def is_fight(dirty_postcode: str, clean_postcode: str) -> bool:
    return postal_code(dirty_postcode or "") != postal_code(clean_postcode or "")


def _query_row(dirty: dict, clean: dict) -> dict:
    return {
        "house_number": (clean.get("house_number") or dirty.get("house_number") or "").strip(),
        "road": (clean.get("road") or dirty.get("road") or "").strip(),
        "locality": (clean.get("locality") or dirty.get("locality") or "").strip(),
        "state": province_abbr(clean.get("region") or "") or province_abbr(dirty.get("region") or ""),
        "clean_zip": clean.get("postcode") or "",
        "dirty_zip": dirty.get("postcode") or "",
    }


def address_key(dirty: dict, clean: dict) -> tuple[str, ...]:
    return _nar_address_key(_query_row(dirty, clean))


def choose_fix(nar_decision: str) -> str:
    if nar_decision == "keep_clean":
        return "keep_clean, NAR"
    if nar_decision == "keep_dirty":
        return "keep_dirty, NAR"
    return ""


def load_nar_by_id(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    with path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            i = row.get("id") or ""
            if i:
                out[i] = row.get("nar_decision") or ""
    return out


def _lineterminator(path: Path) -> str:
    with path.open("rb") as f:
        sample = f.read(4096)
    return "\r\n" if b"\r\n" in sample else "\n"


def _index_keys(
    dirty_csv: Path,
    clean_csv: Path,
    nar_by_id: dict[str, str],
) -> dict[tuple[str, ...], dict]:
    lookup: dict[tuple[str, ...], dict] = {}
    n = 0
    with dirty_csv.open(newline="", encoding="utf-8") as fd, \
         clean_csv.open(newline="", encoding="utf-8") as fc:
        for dirty, clean in _paired_csv_rows(fd, fc):
            n += 1
            if n % 100000 == 0:
                print(f"  index {n:,}", flush=True)
            i = dirty.get("id") or ""
            if i != (clean.get("id") or ""):
                raise SystemExit(f"id mismatch at row {n}: {i} vs {clean.get('id')}")
            if i not in nar_by_id:
                continue
            lookup[address_key(dirty, clean)] = {"nar": nar_by_id[i]}
    return lookup


def _apply_clean(dirty: dict, clean: dict, lookup: dict[tuple[str, ...], dict]) -> tuple[dict, str]:
    out = {k: (v if v is not None else "") for k, v in clean.items()}
    for k, v in out.items():
        if not isinstance(v, str):
            out[k] = str(v)
    rec = lookup.get(address_key(dirty, clean)) or {}
    action = choose_fix(rec.get("nar") or "")
    dirty_pc = dirty.get("postcode") or ""
    clean_pc = out.get("postcode") or ""
    if not is_fight(dirty_pc, clean_pc):
        action = ""
    if action.startswith("keep_dirty"):
        formatted = format_clean_pc(dirty_pc)
        if formatted:
            out["postcode"] = formatted
        else:
            action = ""
    spaced = format_clean_pc(out.get("postcode") or "")
    if spaced:
        out["postcode"] = spaced
    out[FIX_COL] = action
    return out, action


def rewrite_pair(
    dirty_csv: Path,
    clean_csv: Path,
    nar_csv: Path,
    out_dirty: Path,
    out_clean: Path,
) -> Counter:
    print("loading NAR decisions...", flush=True)
    nar_by_id = load_nar_by_id(nar_csv)
    print(f"  NAR ids {len(nar_by_id):,}", flush=True)
    print("indexing unique-address keys from slice...", flush=True)
    lookup = _index_keys(dirty_csv, clean_csv, nar_by_id)
    print(f"  keyed addresses {len(lookup):,}", flush=True)

    term = _lineterminator(clean_csv)
    out_dirty.parent.mkdir(parents=True, exist_ok=True)
    counts: Counter = Counter()
    n = 0
    with dirty_csv.open(newline="", encoding="utf-8") as fd, \
         clean_csv.open(newline="", encoding="utf-8") as fc, \
         out_dirty.open("w", newline="", encoding="utf-8") as fod, \
         out_clean.open("w", newline="", encoding="utf-8") as foc:
        di = csv.DictReader(fd)
        ci = csv.DictReader(fc)
        dirty_fields = list(di.fieldnames or [])
        clean_fields = list(ci.fieldnames or [])
        if FIX_COL not in clean_fields:
            clean_fields = clean_fields + [FIX_COL]
        wd = csv.DictWriter(fod, fieldnames=dirty_fields, lineterminator=term, extrasaction="ignore")
        wc = csv.DictWriter(foc, fieldnames=clean_fields, lineterminator=term, extrasaction="ignore")
        wd.writeheader()
        wc.writeheader()
        sentinel = object()
        while True:
            d = next(di, sentinel)
            c = next(ci, sentinel)
            if d is sentinel and c is sentinel:
                break
            if d is sentinel or c is sentinel:
                raise SystemExit("dirty/clean row count mismatch")
            n += 1
            if (d.get("id") or "") != (c.get("id") or ""):
                raise SystemExit(f"id mismatch at row {n}: {d.get('id')} vs {c.get('id')}")
            dirty_out = {k: (d.get(k) or "") for k in dirty_fields}
            for k, v in dirty_out.items():
                if not isinstance(v, str):
                    dirty_out[k] = str(v)
            clean_out, action = _apply_clean(d, c, lookup)
            wd.writerow(dirty_out)
            wc.writerow({k: clean_out.get(k, "") for k in clean_fields})
            counts[action or "unchanged"] += 1
            if n % 100000 == 0:
                print(f"  write {n:,}", flush=True)
    print(f"wrote {n:,} rows → {out_clean}", flush=True)
    return counts


def main() -> None:
    p = argparse.ArgumentParser(description="Fix Canada slice clean postcodes from local NAR")
    p.add_argument("--dirty", default=str(DIRTY_DEFAULT))
    p.add_argument("--clean", default=str(CLEAN_DEFAULT))
    p.add_argument("--nar", default=str(NAR_DEFAULT))
    p.add_argument("--out-dirty", default=str(OUT_DIRTY_DEFAULT))
    p.add_argument("--out-clean", default=str(OUT_CLEAN_DEFAULT))
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    dirty = Path(args.dirty)
    clean = Path(args.clean)
    if args.dry_run:
        nar_by_id = load_nar_by_id(Path(args.nar))
        lookup = _index_keys(dirty, clean, nar_by_id)
        counts: Counter = Counter()
        n = 0
        with dirty.open(newline="", encoding="utf-8") as fd, \
             clean.open(newline="", encoding="utf-8") as fc:
            for d, c in _paired_csv_rows(fd, fc):
                n += 1
                _, action = _apply_clean(d, c, lookup)
                counts[action or "unchanged"] += 1
        print(f"dry-run {n:,} rows")
        for k, v in counts.most_common():
            print(f"  {k}: {v:,}")
        return
    counts = rewrite_pair(
        dirty, clean, Path(args.nar), Path(args.out_dirty), Path(args.out_clean),
    )
    for k, v in counts.most_common():
        print(f"  {k}: {v:,}")


if __name__ == "__main__":
    main()
