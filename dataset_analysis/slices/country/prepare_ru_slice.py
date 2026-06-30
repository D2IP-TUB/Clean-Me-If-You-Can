#!/usr/bin/env python3
"""Extract Russia addresses from full_named by country_code == RU."""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=Path(__file__).resolve().parents[3] / "data" / "full_named",
        help="Directory with full_named dirty.csv and clean.csv",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).resolve().parents[3] / "data" / "slices" / "ru" / "named",
    )
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)

    clean = pd.read_csv(args.input_dir / "clean.csv", dtype=str, low_memory=False)
    clean_ru = clean[clean["country_code"].str.strip().str.upper() == "RU"]
    clean_ru.to_csv(args.output_dir / "clean.csv", index=False)
    print(f"clean: {len(clean_ru):,} rows → {args.output_dir / 'clean.csv'}")

    ru_ids = set(clean_ru["id"])
    dirty = pd.read_csv(args.input_dir / "dirty.csv", dtype=str, low_memory=False)
    dirty_ru = dirty[dirty["id"].isin(ru_ids)]
    dirty_ru.to_csv(args.output_dir / "dirty.csv", index=False)
    print(f"dirty: {len(dirty_ru):,} rows → {args.output_dir / 'dirty.csv'}")


if __name__ == "__main__":
    main()
