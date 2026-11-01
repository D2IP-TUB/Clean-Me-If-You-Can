"""
derive_country_slice.py — cut a country slice out of a full dirty/clean pair.

Rows are selected by the *clean* file's country_code (the dirty file's country_code is
frequently blank), and the same rows (by position, ids verified identical) are taken from
the dirty file. All columns are kept as-is.

Example (Russia):
  python derive_country_slice.py --dirty ../../data/full_named/dirty.csv \
      --clean ../../data/full_named/clean.csv --country-code ru \
      --out-dirty ../../data/slices/ru/named/dirty.csv \
      --out-clean ../../data/slices/ru/named/clean.csv
"""

import argparse
import os

import pandas as pd


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dirty", required=True)
    ap.add_argument("--clean", required=True)
    ap.add_argument("--country-code", required=True)
    ap.add_argument("--out-dirty", required=True)
    ap.add_argument("--out-clean", required=True)
    ap.add_argument("--id-col", default="id")
    args = ap.parse_args()

    d = pd.read_csv(args.dirty, dtype=str, keep_default_na=False)
    c = pd.read_csv(args.clean, dtype=str, keep_default_na=False)
    assert len(d) == len(c), f"row count mismatch: {len(d)} vs {len(c)}"
    assert (d[args.id_col].values == c[args.id_col].values).all(), "dirty/clean ids not aligned"

    mask = (c["country_code"].str.strip().str.lower() == args.country_code.lower()).values
    d_out, c_out = d[mask], c[mask]
    print(f"{args.country_code}: {mask.sum()} of {len(c)} rows")

    for p in (args.out_dirty, args.out_clean):
        os.makedirs(os.path.dirname(os.path.abspath(p)), exist_ok=True)
    d_out.to_csv(args.out_dirty, index=False)
    c_out.to_csv(args.out_clean, index=False)
    print(f"wrote {args.out_dirty}\nwrote {args.out_clean}")


if __name__ == "__main__":
    main()
