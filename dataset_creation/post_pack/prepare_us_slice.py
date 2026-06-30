#!/usr/bin/env python3

"""
Script to generate the validated US slice from the original dataset.

Usage: python prepare_us_slice.py
Use the dedicated config.py file to specify the paths to the required files.
"""


import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config
import re
import utils


country_code = "us"


def load_localities(path_localities, locality_mapping, path_localities_subdivisions=None, locality_mapping_subdivisions=None):

    # Load the certified localities (incorporated places + CDPs)
    localities = utils.load_localities(path_localities, locality_mapping)

    # Normalize locality names in the certified set (strip administrative suffixes/prefixes)
    localities = {
        region: {_normalize_locality(loc) for loc in locs}
        for region, locs in localities.items()
    }

    # Merge in county-subdivisions (MCDs: townships, CT/MA towns, NJ/PA boroughs, etc.)
    if path_localities_subdivisions and locality_mapping_subdivisions:
        subdivisions = utils.load_localities(path_localities_subdivisions, locality_mapping_subdivisions)
        subdivisions = {
            region: {_normalize_locality(loc) for loc in locs if ',' not in loc}
            for region, locs in subdivisions.items()
        }
        for region, locs in subdivisions.items():
            if region in localities:
                localities[region] |= locs
            else:
                localities[region] = locs

    # Further processing to refine the regions and the localities
    localities["Northern Mariana Islands"] = localities.pop("Commonwealth of the Northern Mariana Islands")
    for region in localities:
        for locality in localities[region]:
            if "balance" in locality:
                new_locality = re.split(r"[ -/]+", locality)[0]
                localities[region] = localities[region].difference({locality}).union({new_locality})

    return localities


def check_name_validity(name):

    frequent_symbols = {"&", "'", "-", ".", ",", "/", "(", ")", "’", "+", ":", "@", "–", "!", "#", "|", "´", '"'}

    if not all(c.isalnum() or c.isspace() or c in frequent_symbols for c in name):
        return False
    if not any(c.isalpha() for c in name) or not name[0].isalnum():
        return False
    if len(name.split()) > 10:
        return False

    return True


_locality_prefixes = ("City of ", "Town of ", "Village of ", "Township of ", "Borough of ", "County of ")

# Longer suffixes must come before shorter ones to avoid partial stripping
_locality_suffixes = (" Charter Township", " Township", " Village", " City", " Town", " CDP")


def _normalize_locality(locality):
    # Expand abbreviated "St. " to "Saint " for consistent matching
    locality = re.sub(r'\bSt\.\s+', 'Saint ', locality)
    for prefix in _locality_prefixes:
        if locality.startswith(prefix):
            return locality[len(prefix):]
    for suffix in _locality_suffixes:
        if locality.endswith(suffix):
            return locality[:-len(suffix)]
    return locality


def check_record_validity(clean_record, localities):

    # Normalize the locality by stripping known administrative prefixes before lookup
    record = clean_record.copy()
    record["locality"] = _normalize_locality(clean_record["locality"])

    # Check record validity with the standard criteria
    reason = utils.check_record_validity(record, localities)

    if reason is not None:
        return reason

    # If the record passes standard checks, perform additional slice-specific checks on road and name
    if not all(c.isalnum() or c.isspace() or c in {"-", ".", "'"} for c in record["road"]):
        return f"invalid road characters: {clean_record['road']!r}"
    if bool(re.search(r"[A-Za-z0-9]-\s", record["road"])) or bool(re.search(r"\s-[A-Za-z0-9]", record["road"])):
        return f"road contains invalid hyphen spacing: {clean_record['road']!r}"
    if "name" in record and not check_name_validity(record["name"]):
        return f"invalid name: {clean_record['name']!r}"

    return None


def main():

    # Parse slice-specific parameters
    path_clean = config.path_clean_data
    path_dirty = config.path_dirty_data
    path_localities = config.slice_params[country_code]["path_localities"]
    locality_mapping = config.slice_params[country_code]["locality_mapping"]
    path_localities_subdivisions = config.slice_params[country_code].get("path_localities_subdivisions")
    locality_mapping_subdivisions = config.slice_params[country_code].get("locality_mapping_subdivisions")
    path_clean_final = config.slice_params[country_code]["path_clean_final"]
    path_dirty_final = config.slice_params[country_code]["path_dirty_final"]
    path_skipped_final = config.slice_params[country_code]["path_skipped_final"]
    path_duplicates_final = config.slice_params[country_code]["path_duplicates_final"]

    # Load the datasets (clean, dirty) and select the records for the slice
    slice_clean_data, slice_dirty_data = utils.load_slice_data(path_clean, path_dirty, country_code, config.path_provenance_data)
    print(f"Records in the current slice: {len(slice_clean_data)}")

    # Load the certified localities (places + county subdivisions)
    localities = load_localities(path_localities, locality_mapping, path_localities_subdivisions, locality_mapping_subdivisions)

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
    certified_ids = {x["id"] for x in certified_addresses}
    dirty_addresses = sorted([x for x in slice_dirty_data if x["id"] in certified_ids], key=lambda x: x["id"])

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
