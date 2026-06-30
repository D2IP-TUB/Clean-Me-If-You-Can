#!/usr/bin/env python3

"""
Run the prepare_full_dataset pipeline on every per-subset folder inside a
pack_output directory, producing clean/dirty/duplicates CSVs per subset.

For each subset and each variant (named / unnamed) the script:
  1. Loads targets_experiment.csv (clean) + values_experiment.csv (dirty)
  2. Joins provenance_graph_iri from provenance.csv
  3. Removes record IDs that were rejected by the country-slice validation
  4. Removes exact dirty duplicates (compared on output_fields minus 'id')
  5. Saves clean.csv, dirty.csv, duplicates.csv

Output structure (default — subsets mode):
  <output-dir>/
    AdministrativeArea/
      named/   clean.csv  dirty.csv  duplicates.csv
      unnamed/ clean.csv  dirty.csv  duplicates.csv
    City/
      ...

Output structure (--flat — for packs that have named/ and unnamed/ at the root):
  <output-dir>/
    named/   clean.csv  dirty.csv  duplicates.csv
    unnamed/ clean.csv  dirty.csv  duplicates.csv

Usage:
  python prepare_subset_datasets.py \\
      --pack-dir   ./data/pack_output \\
      --output-dir ./data/merged_pack_output

  python prepare_subset_datasets.py --flat \\
      --pack-dir   ./data/mfr \\
      --output-dir ./data/mfr_processed
"""

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config
import utils

csv.field_size_limit(sys.maxsize)

SKIPPED_FILES = {
    "named": [str(p) for p in config.full_dataset_params["named"]["path_skipped_files"]],
    "unnamed": [str(p) for p in config.full_dataset_params["unnamed"]["path_skipped_files"]],
}


def load_skipped_ids(paths):
    skipped = set()
    for p in paths:
        path = Path(p)
        if not path.exists():
            print(f"  WARNING: skipped file not found, ignoring: {p}")
            continue
        with open(path, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                skipped.add(row["id"])
    return skipped


def process_variant(variant_dir: Path, label: str, output_variant_dir: Path, skipped_ids: set):
    """Core processing for a single variant directory."""
    targets_path = variant_dir / "targets_experiment.csv"
    values_path  = variant_dir / "values_experiment.csv"
    prov_path    = variant_dir / "provenance.csv"

    if not targets_path.exists() or not values_path.exists():
        print(f"  Skipping {label}: missing targets or values file")
        return

    prov_arg = str(prov_path) if prov_path.exists() else None
    if prov_arg is None:
        print(f"  WARNING: {label}: provenance.csv not found, skipping provenance join")

    clean_data, dirty_data = utils.load_slice_data(
        str(targets_path), str(values_path), country_code=None, path_provenance=prov_arg
    )
    print(f"  {label}: {len(clean_data)} records loaded")

    clean_data = [r for r in clean_data if r["id"] not in skipped_ids]
    clean_ids  = {r["id"] for r in clean_data}
    dirty_data = [r for r in dirty_data if r["id"] in clean_ids]
    print(f"  {label}: {len(clean_data)} after removing skipped IDs")

    clean_data, dirty_data, dup_ids = utils.deduplicate_by_dirty(clean_data, dirty_data)
    print(f"  {label}: {len(dup_ids)} dirty duplicates removed → {len(clean_data)} remain")

    clean_data = sorted(clean_data, key=lambda x: x["id"])
    dirty_data = sorted(dirty_data, key=lambda x: x["id"])

    output_variant_dir.mkdir(parents=True, exist_ok=True)
    utils.save_csv(clean_data, str(output_variant_dir / "clean.csv"))
    utils.save_csv(dirty_data, str(output_variant_dir / "dirty.csv"))
    utils.save_duplicates_csv(dup_ids, str(output_variant_dir / "duplicates.csv"))


def process_subset_variant(subset_dir: Path, variant: str, output_variant_dir: Path, skipped_ids: set):
    variant_dir = subset_dir / variant
    process_variant(variant_dir, f"{subset_dir.name}/{variant}", output_variant_dir, skipped_ids)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pack-dir",   required=True, help="Path to pack_output directory")
    parser.add_argument("--output-dir", required=True, help="Path to output directory")
    parser.add_argument("--flat", action="store_true",
                        help="Pack dir has named/ and unnamed/ directly at the root (no subset folders)")
    args = parser.parse_args()

    pack_dir   = Path(args.pack_dir)
    output_dir = Path(args.output_dir)

    if not pack_dir.exists():
        print(f"ERROR: pack directory not found: {pack_dir}")
        sys.exit(1)

    output_dir.mkdir(parents=True, exist_ok=True)

    # Load skipped IDs once per variant
    skipped = {v: load_skipped_ids(SKIPPED_FILES[v]) for v in ("named", "unnamed")}
    print(f"Skipped IDs — named: {len(skipped['named'])}, unnamed: {len(skipped['unnamed'])}")

    if args.flat:
        print(f"\n=== {pack_dir.name} (flat) ===")
        for variant in ("named", "unnamed"):
            process_variant(
                pack_dir / variant,
                f"{pack_dir.name}/{variant}",
                output_dir / variant,
                skipped[variant],
            )
    else:
        subsets = sorted([d for d in pack_dir.iterdir() if d.is_dir()])
        for subset_dir in subsets:
            print(f"\n=== {subset_dir.name} ===")
            for variant in ("named", "unnamed"):
                process_subset_variant(
                    subset_dir,
                variant,
                output_dir / subset_dir.name / variant,
                skipped[variant],
            )

    print("\nDone.")


if __name__ == "__main__":
    main()
