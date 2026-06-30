#!/usr/bin/env python3

"""
Script to generate the validated German slice from the original dataset.

Usage: python prepare_de_slice.py
Use the dedicated config.py file to specify the paths to the required files.
"""


import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config
import re
import utils


country_code = "de"


_loc_abbreviation_expansion = {"St": "Sankt", "Oldb": "Oldenburg", "OPf": "Oberpfalz", "Rhld": "Rheinland"}


def _normalize_locality(locality):
    loc_split = re.split(r'[ ./]+', locality.replace("(", "").replace(")", "").rstrip("."))
    return " ".join(_loc_abbreviation_expansion.get(t, t) for t in loc_split)


def load_localities(path_localities, locality_mapping):

    # Load the certified localities
    localities = utils.load_localities(path_localities, locality_mapping)

    # Normalize locality names in the certified set (expand abbreviations)
    localities = {
        region: {_normalize_locality(loc) for loc in locs}
        for region, locs in localities.items()
    }

    return localities


def check_name_validity(name):

    frequent_symbols = {"-", ".", "&", "'", ",", "(", ")", '"', "+", "/", "–", "|", "´", ":", "“", "!", "’", "„"}

    if not all(c.isalnum() or c.isspace() or c in frequent_symbols for c in name):
        return False
    if not any(c.isalpha() for c in name) or not name[0].isalnum():
        return False
    if len(name.split()) > 10:
        return False

    return True


def check_record_validity(clean_record, localities):

    # Normalize the locality before lookup
    record = clean_record.copy()
    record["locality"] = _normalize_locality(clean_record["locality"])

    # Check record validity with the standard criteria
    reason = utils.check_record_validity(record, localities)

    if reason is not None:
        return reason

    # If the record passes standard checks, perform additional slice-specific checks on road and name
    if not all(c.isalnum() or c.isspace() or c in {"-", ".", "'"} for c in clean_record["road"]):
        return f"invalid road characters: {clean_record['road']!r}"
    if clean_record["road"][-1].isdigit():
        if not re.match(r"(?:[A-Z]{1,2}|St)\s\d+$", clean_record["road"]):
            return f"road ends with digit but does not match a valid pattern: {clean_record['road']!r}"
    if "name" in clean_record and not check_name_validity(clean_record["name"]):
        return f"invalid name: {clean_record['name']!r}"

    return None


def main():

    # Parse slice-specific parameters
    path_clean = config.path_clean_data
    path_dirty = config.path_dirty_data
    path_localities = config.slice_params[country_code]["path_localities"]
    locality_mapping = config.slice_params[country_code]["locality_mapping"]
    path_clean_final = config.slice_params[country_code]["path_clean_final"]
    path_dirty_final = config.slice_params[country_code]["path_dirty_final"]
    path_skipped_final = config.slice_params[country_code]["path_skipped_final"]
    path_duplicates_final = config.slice_params[country_code]["path_duplicates_final"]

    # Load the datasets (clean, dirty) and select the records for the slice
    slice_clean_data, slice_dirty_data = utils.load_slice_data(path_clean, path_dirty, country_code, config.path_provenance_data)
    print(f"Records in the current slice: {len(slice_clean_data)}")

    # Load the certified localities
    localities = load_localities(path_localities, locality_mapping)

    # Validate the addresses
    certified_addresses = []
    skipped_records = []
    for x in slice_clean_data:
        reason = check_record_validity(x, localities)
        if reason is None:
            certified_addresses.append(x)
        else:
            print(f"Skipping record {x['id']}: {reason}")
            skipped_records.append({"id": x["id"], "reason": reason})
    print(f"Total number of validated records: {len(certified_addresses)}")
    print(f"Total number of skipped records: {len(skipped_records)}")

    # Sort certified addresses by the record identifier
    certified_addresses = sorted(certified_addresses, key=lambda x: x["id"])

    # Build the dirty slice aligned to the certified clean addresses
    certifiedids = {x["id"] for x in certified_addresses}
    dirty_addresses = sorted([x for x in slice_dirty_data if x["id"] in certifiedids], key=lambda x: x["id"])

    # Remove exact duplicates (excluding id) from dirty first, then drop the same records from clean
    certified_addresses, dirty_addresses, dup_removed_ids = utils.deduplicate_by_dirty(certified_addresses, dirty_addresses)
    print(f"Records removed as dirty duplicates: {len(dup_removed_ids)}")
    print(f"Records after deduplication — clean: {len(certified_addresses)}, dirty: {len(dirty_addresses)}")

    # Re-sort both by id to guarantee row-level alignment before saving
    certified_addresses = sorted(certified_addresses, key=lambda x: x["id"])
    dirty_addresses = sorted(dirty_addresses, key=lambda x: x["id"])

    utils.save_csv(certified_addresses, path_clean_final)
    utils.save_csv(dirty_addresses, path_dirty_final)

    # Save the skipped IDs with their rejection reasons
    utils.save_skipped_csv(skipped_records, path_skipped_final)

    # Save the IDs removed as dirty duplicates
    utils.save_duplicates_csv(dup_removed_ids, path_duplicates_final)


if __name__ == "__main__":
    main()
