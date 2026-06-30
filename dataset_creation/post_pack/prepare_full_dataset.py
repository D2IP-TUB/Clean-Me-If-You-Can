#!/usr/bin/env python3

"""
Script to generate the full validated dataset from the merged pack output.

Applies the same post-processing as the country slices:
  - Joins provenance_graph_iri from the provenance file
  - Keeps only the output_fields columns
  - Removes records whose IDs were skipped in any country slice
  - Removes exact dirty duplicates (compared on output_fields minus id) and
    drops the corresponding clean records to keep the two files row-aligned

Usage:
  python prepare_full_dataset.py --variant named
  python prepare_full_dataset.py --variant unnamed
"""

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config
import utils

csv.field_size_limit(sys.maxsize)


def load_skipped_ids(skipped_files):
    """
    Load the union of skipped IDs from one or more skipped CSV files.

    Args:
    skipped_files (list): paths to skipped CSV files (each with an 'id' column)

    Returns:
    skipped_ids: set of id strings
    """
    skipped_ids = set()
    for path in skipped_files:
        p = Path(path)
        if not p.exists():
            print(f"Warning: skipped file not found, ignoring: {path}")
            continue
        with open(p, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                skipped_ids.add(row["id"])
    return skipped_ids


def main():

    parser = argparse.ArgumentParser()
    parser.add_argument("--variant", choices=["named", "unnamed"], required=True,
                        help="Which dataset variant to process: 'named' or 'unnamed'")
    args = parser.parse_args()
    variant = args.variant

    inputs = config.variant_inputs[variant]
    params = config.full_dataset_params[variant]

    path_clean      = inputs["path_clean_data"]
    path_dirty      = inputs["path_dirty_data"]
    path_provenance = inputs["path_provenance_data"]
    path_skipped_files   = params["path_skipped_files"]
    path_clean_final     = params["path_clean_final"]
    path_dirty_final     = params["path_dirty_final"]
    path_duplicates_final = params["path_duplicates_final"]

    # Load clean and dirty datasets with provenance joined
    print(f"Processing variant: {variant}")
    print("Loading datasets...")
    clean_data, dirty_data = utils.load_slice_data(path_clean, path_dirty, None, path_provenance)
    print(f"Total clean records loaded: {len(clean_data)}")

    # Load skipped IDs from all country slices and remove them
    skipped_ids = load_skipped_ids(path_skipped_files)
    print(f"Skipped IDs to remove: {len(skipped_ids)}")

    clean_data = [r for r in clean_data if r["id"] not in skipped_ids]
    print(f"Clean records after removing skipped: {len(clean_data)}")

    # Align dirty to clean
    clean_ids = {r["id"] for r in clean_data}
    dirty_data = [r for r in dirty_data if r["id"] in clean_ids]

    # Remove exact dirty duplicates (on output_fields minus id), drop same records from clean
    clean_data, dirty_data, dup_removed_ids = utils.deduplicate_by_dirty(clean_data, dirty_data)
    print(f"Records removed as dirty duplicates: {len(dup_removed_ids)}")
    print(f"Records after deduplication — clean: {len(clean_data)}, dirty: {len(dirty_data)}")

    # Sort both by id to guarantee row-level alignment
    clean_data = sorted(clean_data, key=lambda x: x["id"])
    dirty_data = sorted(dirty_data, key=lambda x: x["id"])

    # Save outputs
    utils.save_csv(clean_data, path_clean_final)
    utils.save_csv(dirty_data, path_dirty_final)
    utils.save_duplicates_csv(dup_removed_ids, path_duplicates_final)

    print("Done.")


if __name__ == "__main__":
    main()
