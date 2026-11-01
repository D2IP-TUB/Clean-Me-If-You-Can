"""Postcode disagreement categories."""


from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from paths import NAMED, RESULTS

CATEGORIES = (
    "A_match",
    "B_missing_dirty",
    "C_precision",
    "D_same_area",
    "E_far",
    "F_malformed",
)

_SEP = re.compile(r"[^A-Za-z0-9]+")
_META = re.compile(
    r"(region:|dataset:|record_id:|http://|https://|confidence:|update_time:)",
    re.I,
)
_CA = re.compile(r"^[ABCEGHJ-NPRSTVXY]\d[ABCEGHJ-NPRSTV-Z](\d[ABCEGHJ-NPRSTV-Z]\d)?$")
_US_ZIP = re.compile(r"^\d{5}(\d{4})?$")
_GB = re.compile(r"^[A-Z]{1,2}\d[A-Z\d]?\d[A-Z]{2}$")
_IE = re.compile(r"^[A-Z]\d{2}[A-Z0-9]{4}$")
_NL = re.compile(r"^\d{4}[A-Z]{2}$")


def alnum(pc: str) -> str:
    return _SEP.sub("", pc or "").upper()


def classify_postcode(dirty: str, clean: str, country_code: str = "") -> str:
    """Classify a dirty/clean postcode pair.

    A_match          same code after stripping separators
    B_missing_dirty  dirty empty, clean filled
    C_precision      one code is a proper prefix of the other (ZIP+4, LDU vs FSA)
    D_same_area      same area key, different unit (FSA, ZIP3, GB outward, …)
    E_far            real codes that do not share an area key
    F_malformed      not a plausible postcode, or leaked metadata
    """
    d_raw = (dirty or "").strip()
    c_raw = (clean or "").strip()
    cc = (country_code or "").strip().lower()

    if not d_raw and c_raw:
        return "B_missing_dirty"
    if not d_raw or not c_raw:
        return "F_malformed"

    if _is_malformed(d_raw, cc) or _is_malformed(c_raw, cc):
        return "F_malformed"

    nd, nc = alnum(d_raw), alnum(c_raw)
    if nd == nc:
        return "A_match"
    if _is_precision(nd, nc, cc):
        return "C_precision"
    if _same_area(nd, nc, cc):
        return "D_same_area"
    return "E_far"


def _is_malformed(pc: str, cc: str) -> bool:
    if _META.search(pc) or len(pc) > 16:
        return True
    n = alnum(pc)
    if not n or len(n) > 12:
        return True
    if cc == "us":
        return _US_ZIP.match(n) is None
    if cc == "ca":
        return _CA.match(n) is None
    if cc == "gb":
        return _GB.match(n) is None
    if cc == "ie":
        return _IE.match(n) is None
    if cc == "nl":
        return _NL.match(n) is None
    if cc in {"de", "fr", "it", "es", "at"}:
        return not (n.isdigit() and 4 <= len(n) <= 5)
    if cc in {"au", "ru", "ua"}:
        return not (n.isdigit() and 4 <= len(n) <= 6)
    return not n.isalnum()


def _is_precision(nd: str, nc: str, cc: str) -> bool:
    if nd == nc:
        return False
    shorter, longer = (nd, nc) if len(nd) < len(nc) else (nc, nd)
    if not longer.startswith(shorter):
        return False
    if cc == "us":
        return len(shorter) == 5 and len(longer) == 9
    if cc == "ca":
        return len(shorter) == 3 and len(longer) == 6
    return len(shorter) >= 3


def _area_key(n: str, cc: str) -> str:
    if cc == "us":
        return n[:3] if len(n) >= 3 else n
    if cc == "ca":
        return n[:3] if len(n) >= 3 else n
    if cc == "gb":
        return n[:-3] if len(n) >= 5 else n
    if cc == "ie":
        return n[:3] if len(n) >= 3 else n
    if cc == "nl":
        return n[:4] if len(n) >= 4 else n
    if cc in {"de", "fr", "it", "es", "at", "ch"}:
        return n[:2] if len(n) >= 2 else n
    if cc in {"au", "ru", "ua", "pl", "br"}:
        return n[:3] if len(n) >= 3 else n
    return n[:3] if len(n) >= 4 else n[: max(2, len(n) // 2)]


def _same_area(nd: str, nc: str, cc: str) -> bool:
    return bool(nd) and _area_key(nd, cc) == _area_key(nc, cc)


def classify_files(dirty_csv: Path, clean_csv: Path):
    counts = Counter()
    by_cc = defaultdict(Counter)
    n = 0
    with dirty_csv.open(newline="", encoding="utf-8", errors="replace") as fd, \
         clean_csv.open(newline="", encoding="utf-8", errors="replace") as fc:
        rd, rc = csv.DictReader(fd), csv.DictReader(fc)
        for drow, crow in zip(rd, rc):
            n += 1
            if n % 500000 == 0:
                print(f"  {n:,}", flush=True)
            if drow["id"] != crow["id"]:
                raise SystemExit(f"id mismatch at row {n}: {drow['id']} vs {crow['id']}")
            cc = (crow.get("country_code") or drow.get("country_code") or "").lower()
            cat = classify_postcode(drow.get("postcode", ""), crow.get("postcode", ""), cc)
            counts[cat] += 1
            by_cc[cc or "(empty)"][cat] += 1
    return n, counts, by_cc


def main():
    p = argparse.ArgumentParser(description="Rule-based postcode category counts")
    p.add_argument(
        "--dirty",
        default=str(NAMED / "full_dirty.csv"),
    )
    p.add_argument(
        "--clean",
        default=str(NAMED / "full_clean.csv"),
    )
    p.add_argument(
        "--out",
        default=str(RESULTS / "postcode_category_counts.json"),
    )
    args = p.parse_args()
    print("classifying...", flush=True)
    n, counts, by_cc = classify_files(Path(args.dirty), Path(args.clean))
    top_cc = sorted(by_cc, key=lambda c: sum(by_cc[c].values()), reverse=True)[:15]
    result = {
        "n": n,
        "counts": {k: counts.get(k, 0) for k in CATEGORIES},
        "by_country": {
            cc: {k: by_cc[cc].get(k, 0) for k in CATEGORIES} for cc in top_cc
        },
    }
    Path(args.out).write_text(json.dumps(result, indent=2))
    print(f"n={n:,}")
    width = max(len(k) for k in CATEGORIES)
    for k in CATEGORIES:
        c = counts.get(k, 0)
        pct = 100.0 * c / n if n else 0
        print(f"  {k:<{width}}  {c:>10,}  {pct:5.1f}%")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
