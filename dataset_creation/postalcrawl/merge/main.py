"""Merge pack output CSVs across WDC subsets and extraction formats.

After packing schema.org and microformat (vCard) extractions separately, this
step concatenates per-subset outputs into six combined tables (named/unnamed ×
values/targets/provenance).

Example
-------
    python -m postalcrawl.merge.main \\
        --schema-org-dir ./data/pack_schema_org \\
        --microformat-dir ./data/pack_microformat \\
        --out-dir ./data/merged_pack
"""

from __future__ import annotations

import argparse
from pathlib import Path

import polars as pl

FILES = ["values_experiment.csv", "targets_experiment.csv", "provenance.csv"]
SPLITS = {"named": "named", "unnamed": "unnamed"}


def collect_csvs(
    pack_dirs: list[Path],
    split_subdir: str,
    filename: str,
) -> list[pl.DataFrame]:
    frames: list[pl.DataFrame] = []
    for root in pack_dirs:
        if not root.is_dir():
            print(f"  [SKIP] pack dir missing: {root}")
            continue
        for subset_dir in sorted(root.iterdir()):
            if not subset_dir.is_dir():
                continue
            csv_path = subset_dir / split_subdir / filename
            if not csv_path.exists():
                print(f"  [SKIP] {csv_path}")
                continue
            df = pl.read_csv(csv_path, infer_schema_length=0)
            df = df.with_columns(
                pl.lit(subset_dir.name).alias("source_subset"),
                pl.lit(root.name).alias("source_pack"),
            )
            frames.append(df)
            print(f"  [OK]   {csv_path}  ({len(df)} rows)")
    return frames


def merge_pack_outputs(pack_dirs: list[Path], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    for split_name, split_subdir in SPLITS.items():
        print(f"\n=== {split_name.upper()} ({split_subdir}) ===")
        for filename in FILES:
            print(f"\n--- {filename} ---")
            frames = collect_csvs(pack_dirs, split_subdir, filename)
            if not frames:
                print(f"  No files found for {split_name}/{filename}")
                continue
            merged = pl.concat(frames, how="diagonal")
            out_path = out_dir / f"merged_{split_name}_{filename}"
            merged.write_csv(out_path)
            print(f"\n=> {out_path}  ({len(merged)} total rows)")

    print(f"\nDone. Output in {out_dir}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--schema-org-dir",
        type=Path,
        required=True,
        help="Pack output root for schema.org WDC subsets",
    )
    parser.add_argument(
        "--microformat-dir",
        type=Path,
        required=True,
        help="Pack output root for html-mf-adr / vCard microformat subset",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("./data/merged_pack"),
        help="Directory for merged CSV outputs",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    merge_pack_outputs(
        pack_dirs=[args.schema_org_dir, args.microformat_dir],
        out_dir=args.out_dir,
    )


if __name__ == "__main__":
    main()
