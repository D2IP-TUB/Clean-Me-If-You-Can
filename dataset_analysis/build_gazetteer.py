#!/usr/bin/env python3
"""Build the place-name gazetteer used for locality, region, and country.

Reads GeoNames allCountries.txt, alternateNamesV2.txt, and countryInfo.txt,
keeps names that occur in the address corpora, and writes
error_taxonomy/geodata/gazetteer.pkl.
"""
from __future__ import annotations

import argparse
import csv
import pickle
import re
import sys
from pathlib import Path

import pandas as pd

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE / "error_taxonomy"))
from analyze_error_types import (  # noqa: E402
    GAZETTEER_PATH, PLACE_COLS, _COMPOSITE_NAME_SPLIT_RE, _place_fold_key, _place_key,
    normalize_cell,
)
from run_analysis import discover_datasets  # noqa: E402

# Feature classes that can be a locality, region or country: administrative
# areas, populated places, islands ("Tenerife") and named regions.
KEEP_CLASSES = {"A", "P"}
KEEP_CODES = {("T", c) for c in ("ISL", "ISLS", "ISLF", "ISLT", "ATOL", "PEN")} | \
             {("L", c) for c in ("RGN", "RGNE", "AREA")}

_LANG_RE = re.compile(r"^([a-z]{2,3})(?:-[A-Za-z]+)?$")

csv.field_size_limit(sys.maxsize)


def needed_names(extra_csvs: tuple[Path, ...] = ()) -> set[str]:
    names: set[str] = set()
    corpora = [(None, None, None, p, p) for p in extra_csvs] + discover_datasets()
    for _, _, _, dirty, clean in corpora:
        for path in (dirty, clean):
            if not path.is_file():
                continue
            header = pd.read_csv(path, nrows=0).columns
            cols = [c for c in PLACE_COLS if c in header]
            if not cols:
                continue
            df = pd.read_csv(path, usecols=cols, dtype=str, keep_default_na=False)
            for c in cols:
                for s in df[c].unique():
                    s = normalize_cell(s)
                    if not s:
                        continue
                    names.add(_place_key(s))
                    for part in _COMPOSITE_NAME_SPLIT_RE.split(s):
                        if part.strip():
                            names.add(_place_key(part))
        print(f"  {dirty.parent.name}: {len(names):,} distinct names so far", flush=True)
    return names


def build(geonames: Path, out: Path, extra_csvs: tuple[Path, ...] = ()) -> None:
    names = needed_names(extra_csvs)
    folded_needed = {_place_fold_key(n) for n in names}
    # key -> {geonameid: [languages, primary languages, acronym]}
    exact: dict[str, dict[int, list]] = {}
    folded: dict[str, dict[int, list]] = {}

    def add(name: str, gid: int, lang: str | None, acronym: bool, preferred: bool) -> None:
        for key, needed, index in ((_place_key(name), names, exact),
                                   (_place_fold_key(name), folded_needed, folded)):
            if key not in needed:
                continue
            entry = index.setdefault(key, {}).setdefault(gid, [set(), set(), True, []])
            if lang:
                entry[0].add(lang)
                if preferred:
                    entry[1].add(lang)
                entry[3].append(lang)
            # An acronym of the place only if EVERY listing of it is one
            # ("ABD" for the USA in Turkish).
            entry[2] = entry[2] and acronym

    kept: set[int] = set()
    # geonameid -> (feature class, feature code, population), to decide which
    # place an ambiguous name means ("New York": city, state or county).
    features: dict[int, tuple] = {}
    with open(geonames / "allCountries.txt", encoding="utf-8", newline="") as fh:
        for row in csv.reader(fh, delimiter="\t", quoting=csv.QUOTE_NONE):
            fclass, fcode = row[6], row[7]
            if fclass not in KEEP_CLASSES and (fclass, fcode) not in KEEP_CODES:
                continue
            gid = int(row[0])
            kept.add(gid)
            features[gid] = (fclass, fcode, int(row[14] or 0))
            add(row[1], gid, None, False, False)
            add(row[2], gid, None, False, False)
    print(f"  features kept: {len(kept):,}", flush=True)

    # ISO 3166 codes as acronyms of their country ("RU" / "Россия").
    with open(geonames / "countryInfo.txt", encoding="utf-8") as fh:
        for line in fh:
            if line.startswith("#"):
                continue
            row = line.rstrip("\n").split("\t")
            if len(row) > 16 and row[16].isdigit():
                for code in (row[0], row[1]):
                    add(code, int(row[16]), None, True, False)

    with open(geonames / "alternateNamesV2.txt", encoding="utf-8", newline="") as fh:
        for row in csv.reader(fh, delimiter="\t", quoting=csv.QUOTE_NONE):
            gid = int(row[1])
            if gid not in kept:
                continue
            tag, name = row[2], row[3]
            letters = name.replace(".", "")
            acronym = name.isupper() and letters.isalpha() and 2 <= len(letters) <= 5
            m = _LANG_RE.match(tag)
            if m:
                add(name, gid, m.group(1), acronym, row[4] == "1")
            elif tag == "abbr":
                add(name, gid, None, True, False)
            # other code types (post, iata, link, ...) are not names

    gids = {g for d in (exact, folded) for e in d.values() for g in e}
    per_lang: dict[tuple[int, str], set] = {}
    with open(geonames / "alternateNamesV2.txt", encoding="utf-8", newline="") as fh:
        for row in csv.reader(fh, delimiter="\t", quoting=csv.QUOTE_NONE):
            gid = int(row[1])
            if gid not in gids or row[6] == "1" or row[7] == "1":
                continue
            m = _LANG_RE.match(row[2])
            if m:
                per_lang.setdefault((gid, m.group(1)), set()).add(_place_key(row[3]))

    def freeze(index):
        out_ = {}
        for key, d in index.items():
            out_[key] = {}
            for gid, (langs, pref, acr, listed) in d.items():
                primary = set(pref) | {l for l in listed if len(per_lang.get((gid, l), ())) == 1}
                out_[key][gid] = (frozenset(langs), frozenset(primary), acr, frozenset(pref))
        return out_

    data = {"exact": freeze(exact), "folded": freeze(folded),
            "features": {g: features[g] for g in gids if g in features}}
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "wb") as fh:
        pickle.dump(data, fh, protocol=pickle.HIGHEST_PROTOCOL)
    print(f"wrote {out}: {len(data['exact']):,} of {len(names):,} names found in GeoNames "
          f"({len(data['folded']):,} accent-folded keys)")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--geonames", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=Path(GAZETTEER_PATH))
    ap.add_argument("--corpus", type=Path, action="append", default=[],
                    help="Extra CSV whose place columns (locality/region/country) "
                         "to index, in addition to the datasets run_analysis.py "
                         "discovers. Repeatable (give dirty and clean files).")
    args = ap.parse_args()
    build(args.geonames, args.out, tuple(args.corpus))


if __name__ == "__main__":
    main()
