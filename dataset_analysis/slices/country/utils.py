import copy
import csv
import pandas as pd
import pickle as pkl
import re
from pathlib import Path


# Address fields according to the PostalAddress schema (below the country level)
address_fields = ["name", "house_number", "road", "postcode", "locality", "region"]

# Schema alignment between the address details in the Nominatim responses the PostalAddress schema (including the label attribute)
nominatim_fields = ["name", "housenumber", "street", "postcode", "city", "state"]
address_mapping = {address_fields[i]: nominatim_fields[i] for i in range(len(address_fields))}
address_mapping["label"] = "label"

# Valid patterns for the house number
house_number_patterns = [
    '^\\d+$',  # only the number, e.g., 12
    '^\\d+ ?[A-Z]([-/+–][A-Z])?$', '^\\d+ ?[a-z]([-/+–][a-z])?$',  # number and letter(s), with possible space, e.g., '12A'
    '^\\d+ \\d+[-/+–]\\d+$',  # number and further numbers, with a space in between, e.g., '12 1/2'
    '^\\d+[A-Z]?[-/+–]\\d+[A-Z]?$', '^\\d+[a-z]?[-/+–]\\d+[a-z]?$',  # multiple numbers with a connector, e.g., '12-14'
    '^\\d+[A-Z]? [-/+–] \\d+[A-Z]?$', '^\\d+[a-z]? [-/+–] \\d+[a-z]?$',  # same, but with spaces before and after, e.g., '12 - 14'
    '^\\d+[A-Z]?(,\\d+[A-Z]?)*$', '^\\d+[a-z]?(,\\d+[a-z]?)*$',  # multiple numbers with the comma, e.g., '12,14,16'
    '^\\d+[A-Z]?(, \\d+[A-Z]?)*$', '^\\d+[a-z]?(, \\d+[a-z]?)*$',  # same, but with a space after each comma, e.g., '12, 14, 16'
    '^\\d+[A-Z]?(;\\d+[A-Z]?)*$', '^\\d+[a-z]?(;\\d+[a-z]?)*$',  # same as above, but with the semicolon (without spaces)
    '^\\d+[A-Z]?(; \\d+[A-Z]?)*$', '^\\d+[a-z]?(; \\d+[a-z]?)*$',  # same as above, but with the semicolon (with spaces)
    '^\\d+[A-Z]?( \\d+[A-Z]?)+$', '^\\d+[a-z]?( \\d+[a-z]?)+$'  # multiple numbers separated by a space, e.g., '12 14'
]


def remove_newline(input_string):
    """
    Remove newline characters ("\n", "\r", "\u2028", "\u2029") from the input string

    Args:
    input_string (str): the input string from which newline characters have to be removed

    Returns:
    output_string: the string without newline characters
    """

    output_string = input_string.replace("\n", " ").replace("\r", " ").replace("\u2028", " ").replace("\u2029", " ")

    return output_string


def load_csv_dataset(input_file):
    """
    Load the dataset from the CSV file as a list of dictionaries.

    Args:
    input_file (str): path to the input file

    Returns:
    data: list of dictionaries (one for each record)
    """

    # Parse the path to the input file
    input_path = Path(input_file)

    # Check that the path is valid
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_file}")

    # Load the dataset
    rows = list()
    reader = csv.reader(open(input_file, encoding="utf-8"))
    for row in reader:
        rows.append(row)
    header = rows[0]
    data = [{header[i]: int(x[i]) if header[i] == "_id" else x[i] for i in range(len(header))} for x in rows[1:]]

    return data


def load_valid_data(address_file, response_file):
    """
    Load the validation data as a list of dictionaries.

    Args:
    address_file (str): path to the input pickle file mapping the unique addresses to the record identifiers (dictionary)
    response_file (str): path to the input pickle file storing the Nominatim response for each unique address (dictionary)

    Returns:
    data: a dictionary mapping each record identifier to the corresponding parsed address
    """

    # Parse the paths to the input files
    address_path = Path(address_file)
    response_path = Path(response_file)

    # Check that the paths are valid
    if not address_path.exists():
        raise FileNotFoundError(f"Input file not found: {address_file}")
    if not response_path.exists():
        raise FileNotFoundError(f"Input file not found: {response_file}")

    # Load the input files
    addresses = pkl.load(open(address_path, "rb"))
    responses = pkl.load(open(response_path, "rb"))

    # Parse the Nominatim responses, iterating on the dictionary keys
    parsed_responses = dict()

    for k in responses:

        # Skip invalid responses
        if responses[k] is None or len(responses[k]["features"]) == 0:
            parsed_responses[k] = None
            continue

        # Extract the address details from the response
        address_details = responses[k]["features"][0]["properties"]["geocoding"]
        parsed_responses[k] = {k: remove_newline(address_details[v]) if v in address_details else ""
                               for (k, v) in address_mapping.items()}

    # Associate each record identifier to the corresponding parsed address
    data = {i: copy.deepcopy(parsed_responses[k]) for k in addresses for i in addresses[k]}

    return data


def load_slice_data(clean_file, dirty_file, address_file, response_file, country_code):
    """
    Load the datasets (clean, dirty, validation) and select the records for the current slice.

    Args:

    clean_file (str): path to the input CSV file storing the clean addresses
    dirty_file (str): path to the input CSV file storing the dirty addresses
    address_file (str): path to the input pickle file mapping the unique addresses to the record identifiers (dictionary)
    response_file (str): path to the input pickle file storing the Nominatim response for each unique address (dictionary)
    country_code (str): country code for the current slice

    Returns:
    slice_clean_data: list of dictionaries (one for each record) for the slice
    slice_dirty_data: list of dictionaries (one for each record) for the slice
    slice_valid_data: a dictionary mapping each record identifier for the slice to the corresponding parsed address
    """

    # Parse the paths to the input files
    clean_path = Path(clean_file)
    dirty_path = Path(dirty_file)
    address_path = Path(address_file)
    response_path = Path(response_file)

    # Check that the paths are valid
    if not clean_path.exists():
        raise FileNotFoundError(f"Input file not found: {clean_file}")
    if not dirty_path.exists():
        raise FileNotFoundError(f"Input file not found: {dirty_file}")
    if not address_path.exists():
        raise FileNotFoundError(f"Input file not found: {address_file}")
    if not response_path.exists():
        raise FileNotFoundError(f"Input file not found: {response_file}")

    # Load the clean dataset and select the records for the slice
    clean_data = load_csv_dataset(clean_path)
    slice_clean_data = [x for x in clean_data if x["country_code"] == country_code]
    slice_ids = {x["_id"] for x in slice_clean_data}

    # Load the dirty dataset and select the records for the slice
    dirty_data = load_csv_dataset(dirty_path)
    slice_dirty_data = [x for x in dirty_data if x["_id"] in slice_ids]

    # Load the validation dataset
    slice_valid_data = load_valid_data(address_path, response_path)

    return slice_clean_data, slice_dirty_data, slice_valid_data


def load_localities(input_file, locality_mapping):
    """
    Load the certified localities.

    Args:
    input_file (str): path to the CSV file containing the certified localities
    locality_mapping (dict): dictionary mapping locality and region to the corresponding attribute from the input file

    Returns:
    localities: a dictionary associating each region with the corresponding localities
    """

    # Parse the path to the input file
    input_path = Path(input_file)

    # Check that the path is valid
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_file}")

    # Load the certified localities and rename the locality and region attributes based on the mapping
    loc_df = pd.read_csv(input_path, sep=";")
    loc_df = loc_df.rename(columns={locality_mapping["locality"]: "locality", locality_mapping["region"]: "region"})

    # Create a dictionary associating to each region the corresponding localities
    localities = {k: set() for k in list(set(loc_df["region"]))}
    for l in loc_df[["locality", "region"]].to_dict(orient="records"):
        localities[l["region"]].add(l["locality"])

    return localities


def check_record_validity(clean_record, valid_record, localities):
    """
    Check the validity of the input record.

    Args:
    clean_record (dict): clean record to validate (as a dictionary following the PostalAddress schema)
    valid_record (dict): validation record (as a dictionary following the PostalAddress schema)
    localities (dict): dictionary associating each region with the corresponding localities

    Returns:
    valid: a boolean value denoting whether the record is valid or not
    """

    # If the validation record is invalid, return False
    if valid_record is None:
        return False

    # Check whether all address fields are consistent between the two records
    clean_vals = tuple([clean_record[a] for a in address_fields])
    valid_vals = tuple([valid_record[a] for a in address_fields])
    if clean_vals != valid_vals:
        return False

    # Check whether the house number follows a valid pattern
    if not any(re.search(p, clean_record["house_number"]) for p in house_number_patterns):
        return False

    # Check whether the locality is valid
    if clean_record["locality"] not in localities[clean_record["region"]]:
        return False

    return True


def save_csv(data, output_file):
    """
    Save the dataset as a CSV file.

    Args:
    data (list): the dataset (as a list of dictionaries)
    output_file (str): path to the output file

    Returns:
    success: a Boolean value (True by default)
    """

    # Parse the paths to the input files
    output_path = Path(output_file)

    try:
        col_names = data[0].keys()
        csv_writer = csv.DictWriter(open(output_path, "w", encoding="utf-8", newline="\n"), fieldnames=col_names)
        csv_writer.writeheader()
        csv_writer.writerows(data)

    except Exception as e:
        print(f"Error: {e}")
        return False

    return True    

