#!/usr/bin/env python3

"""
Script to generate the validated US slice from the original dataset.

Usage: python prepare_us_slice.py
Use the dedicated config.py file to specify the paths to the required files.
"""


import config
import Levenshtein
import re
import utils
import pandas as pd
from pathlib import Path


country_code = "us"


def load_localities(path_localities, locality_mapping):

    # Load the certified localities
    localities = utils.load_localities(path_localities, locality_mapping)

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


def check_record_validity(clean_record, valid_record, localities):

    # Check record validity with the standard criteria
    is_valid = utils.check_record_validity(clean_record, valid_record, localities)

    if not is_valid:
        return is_valid

    # If the record is marked as valid, perform additional slice-specific checks on road and name
    if not all(c.isalnum() or c.isspace() or c in {"-", ".", "'"} for c in clean_record["road"]):
        return False
    if bool(re.search(r"[A-Za-z0-9]-\s", clean_record["road"])) or bool(re.search(r"\s-[A-Za-z0-9]", clean_record["road"])):
        return False
    if not check_name_validity(clean_record["name"]):
        return False

    return is_valid


def make_locality_consistent(uncertain_addresses, valid_data, localities):

    # Addresses certified
    certified_addresses = list()
    num_updates = 0

    # Iterate on the addresses
    for k in uncertain_addresses:
        x = uncertain_addresses[k]

        # Ignore if the validation record is invalid or the postcode is inconsistent
        if valid_data[x["_id"]] is None or x["postcode"] != valid_data[x["_id"]]["postcode"]:
            continue

        # Extract the locality hierarchy from the validation record - ignore if the current locality is not there
        hierarchy = set(valid_data[x["_id"]]["label"].split(", ")[3:-3])
        if x["locality"] not in hierarchy:
            continue

        # Handle frequent prefixes and abbreviations
        if x["locality"].startswith("City of"):
            hierarchy.add(x["locality"].removeprefix("City of").strip())
        if "Saint " in x["locality"]:
            hierarchy.add(x["locality"].replace("Saint ", "St. "))

        # Filter the localities from the hierarchy appearing in the set of certified localities for the region
        candidates = hierarchy.intersection(localities[x["region"]])

        # If there is exactly one match, assign it as the correct locality to both the clean and the valid records
        if len(candidates) == 1:
            x["locality"] = candidates.pop()
            valid_data[x["_id"]]["locality"] = x["locality"]
            num_updates += 1

            # Check the validity of the current record and add it to the list of certified records if it passes the check
            if check_record_validity(x, valid_data[x["_id"]], localities):
                certified_addresses.append(x)

    print(f"Locality consistency - Validated records: {len(certified_addresses)} (out of {num_updates} updated records)")

    return certified_addresses


def make_road_consistent(uncertain_addresses, valid_data, localities):

    # Addresses certified
    certified_addresses = list()
    num_updates = 0

    # Iterate on the addresses
    for k in uncertain_addresses:
        x = uncertain_addresses[k]

        # Ignore if the validation record is invalid or the postcode is inconsistent
        if valid_data[x["_id"]] is None or x["postcode"] != valid_data[x["_id"]]["postcode"]:
            continue

        if x["road"] != valid_data[x["_id"]]["road"] and valid_data[x["_id"]]["road"] != "":
            clean_val = x["road"].lower()
            valid_val = valid_data[x["_id"]]["road"].lower()

            # If the values are similar, pick the one from the validated record as the correct one
            if Levenshtein.distance(clean_val, valid_val) <= 3 or f"{clean_val} " in valid_val:
                x["road"] = valid_data[x["_id"]]["road"]
                num_updates += 1

                # Check the validity of the current record and add it to the list of certified records if it passes the check
                if check_record_validity(x, valid_data[x["_id"]], localities):
                    certified_addresses.append(x)

    print(f"Road consistency - Validated records: {len(certified_addresses)} (out of {num_updates} updated records)")

    return certified_addresses


def make_name_consistent(uncertain_addresses, valid_data, localities):

    # Addresses certified
    certified_addresses = list()
    num_updates = 0

    # Iterate on the addresses
    for k in uncertain_addresses:
        x = uncertain_addresses[k]

        # Ignore if the validation record is invalid or the postcode is inconsistent
        if valid_data[x["_id"]] is None or x["postcode"] != valid_data[x["_id"]]["postcode"]:
            continue

        if x["name"] != valid_data[x["_id"]]["name"] and valid_data[x["_id"]]["name"] != "":
            clean_val = x["name"].lower()
            valid_val = valid_data[x["_id"]]["name"].lower()

            # Check which of the two versions are valid - if none is valid, continue
            is_valid = [check_name_validity(v) for v in [clean_val, valid_val]]
            if not any(is_valid):
                continue

            # Check whether the clean and valid values are similar or one of the two names is contained in the other
            if Levenshtein.distance(clean_val, valid_val) <= 3 or clean_val in valid_val or valid_val in clean_val:

                # If only one of the two versions is valid, pick that one; otherwise, go for the one from the validation record
                if is_valid.count(True) == 1:
                    correct_val = x["name"] if is_valid[0] else valid_data[x["_id"]]["name"]
                else:
                    correct_val = valid_data[x["_id"]]["name"]

                # Assign the correct name to both the clean and the valid records
                x["name"] = correct_val
                valid_data[x["_id"]]["name"] = correct_val
                num_updates += 1

                # Check the validity of the current record and add it to the list of certified records if it passes the check
                if check_record_validity(x, valid_data[x["_id"]], localities):
                    certified_addresses.append(x)

    print(f"Name consistency - Validated records: {len(certified_addresses)} (out of {num_updates} updated records)")

    return certified_addresses


def make_house_number_consistent(uncertain_addresses, valid_data, localities):

    # Addresses certified
    certified_addresses = list()
    num_updates = 0

    # Iterate on the addresses
    for k in uncertain_addresses:
        x = uncertain_addresses[k]

        # Ignore if the validation record is invalid or the postcode is inconsistent
        if valid_data[x["_id"]] is None or x["postcode"] != valid_data[x["_id"]]["postcode"]:
            continue

        # Check whether name and road are the same, then check the house numbers (net of capitalization and different formatting)
        clean_vals = (x["name"], x["road"])
        valid_vals = (valid_data[x["_id"]]["name"], valid_data[x["_id"]]["road"])
        if clean_vals == valid_vals and x["house_number"] != valid_data[x["_id"]]["house_number"]:
            clean_num = re.sub(r"[^a-zA-Z0-9]", "", x["house_number"].lower())
            valid_num = re.sub(r"[^a-zA-Z0-9]", "", valid_data[x["_id"]]["house_number"].lower())

            # If the house numbers are formatted differently but represent the same content, pick the one from the validation record
            if clean_num == valid_num:
                house_number = None
                if any(re.search(p, valid_data[x["_id"]]["house_number"]) for p in utils.house_number_patterns):
                    house_number = valid_data[x["_id"]]["house_number"]
                elif any(re.search(p, x["house_number"]) for p in utils.house_number_patterns):
                    house_number = x["house_number"]
                if house_number is not None:
                    x["house_number"] = house_number
                    valid_data[x["_id"]]["house_number"] = house_number
                    num_updates += 1

                    # Check the validity of the current record and add it to the list of certified records if it passes the check
                    if check_record_validity(x, valid_data[x["_id"]], localities):
                        certified_addresses.append(x)

    print(f"House number consistency - Validated records: {len(certified_addresses)} (out of {num_updates} updated records)")

    return certified_addresses


def main():

    # Parse slice-specific parameters
    path_clean = config.path_clean_data
    path_dirty = config.path_dirty_data
    path_addresses = config.slice_params[country_code]["path_addresses"]
    path_responses = config.slice_params[country_code]["path_responses"]
    path_localities = config.slice_params[country_code]["path_localities"]
    locality_mapping = config.slice_params[country_code]["locality_mapping"]
    path_clean_final = config.slice_params[country_code]["path_clean_final"]
    path_dirty_final = config.slice_params[country_code]["path_dirty_final"]

    # Load the datasets (clean, dirty, validation) and select the records for the slice
    slice_clean_data, slice_dirty_data, slice_valid_data = utils.load_slice_data(path_clean, path_dirty, path_addresses,
                                                                                 path_responses, country_code)
    print(f"Records in the current slice: {len(slice_clean_data)}")

    # Load the certified localities
    localities = load_localities(path_localities, locality_mapping)

    certified_addresses = list()
    uncertain_addresses = dict()

    # Validate the addresses without editing them
    for x in slice_clean_data:
        if check_record_validity(x, slice_valid_data[x["_id"]], localities):
            certified_addresses.append(x)
        else:
            uncertain_addresses[x["_id"]] = x
    print(f"Records validated in their original format: {len(certified_addresses)}")

    # Validate the locality and update the list of certified addresses (and the dictionary of uncertain ones)
    added_addresses = make_locality_consistent(uncertain_addresses, slice_valid_data, localities)
    certified_addresses += added_addresses
    for k in [x["_id"] for x in added_addresses]:
        del uncertain_addresses[k]

    # Validate the road and update the list of certified addresses (and the dictionary of uncertain ones)
    added_addresses = make_road_consistent(uncertain_addresses, slice_valid_data, localities)
    certified_addresses += added_addresses
    for k in [x["_id"] for x in added_addresses]:
        del uncertain_addresses[k]

    # Validate the name and update the list of certified addresses (and the dictionary of uncertain ones)
    added_addresses = make_name_consistent(uncertain_addresses, slice_valid_data, localities)
    certified_addresses += added_addresses
    for k in [x["_id"] for x in added_addresses]:
        del uncertain_addresses[k]

    # Validate the house number and update the list of certified addresses (and the dictionary of uncertain ones)
    added_addresses = make_house_number_consistent(uncertain_addresses, slice_valid_data, localities)
    certified_addresses += added_addresses
    for k in [x["_id"] for x in added_addresses]:
        del uncertain_addresses[k]

    print(f"Total number of validated records: {len(certified_addresses)}")

    # Sort certified addresses by the record identifier
    certified_addresses = sorted(certified_addresses, key=lambda x: x["_id"])

    # Save the clean and the dirty datasets
    utils.save_csv(certified_addresses, path_clean_final)
    certified_ids = {x["_id"] for x in certified_addresses}
    dirty_addresses = sorted([x for x in slice_dirty_data if x["_id"] in certified_ids], key=lambda x: x["_id"])
    utils.save_csv(dirty_addresses, path_dirty_final)


if __name__ == "__main__":
    main()
