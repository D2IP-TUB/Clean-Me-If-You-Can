import csv
import re
import sys
from pathlib import Path

# Raise the CSV field size limit to handle very large fields
csv.field_size_limit(sys.maxsize)


# Address fields according to the PostalAddress schema (below the country level)
address_fields = ["name", "house_number", "road", "postcode", "locality", "region"]

# Output columns for the final slice files (named variant; unnamed omits 'name')
output_fields = ["id", "name", "road", "house_number", "postcode", "locality", "region", "country", "country_code", "provenance_graph_iri"]

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
    data = [{header[i]: x[i] for i in range(len(header))} for x in rows[1:]]

    return data


def load_slice_data(clean_file, dirty_file, country_code, path_provenance=None):
    """
    Load the datasets (clean, dirty) and select the records for the current slice.

    Args:
    clean_file (str): path to the input CSV file storing the clean addresses
    dirty_file (str): path to the input CSV file storing the dirty addresses
    country_code (str or None): country code for the current slice; pass None to load all records
    path_provenance (str, optional): path to the provenance CSV file

    Returns:
    slice_clean_data: list of dictionaries (one for each record) for the slice
    slice_dirty_data: list of dictionaries (one for each record) for the slice
    """

    # Parse the paths to the input files
    clean_path = Path(clean_file)
    dirty_path = Path(dirty_file)

    # Check that the paths are valid
    if not clean_path.exists():
        raise FileNotFoundError(f"Input file not found: {clean_file}")
    if not dirty_path.exists():
        raise FileNotFoundError(f"Input file not found: {dirty_file}")

    # Load the clean dataset and optionally filter by country_code
    clean_data = load_csv_dataset(clean_path)
    if country_code is None:
        slice_clean_data = clean_data
    else:
        slice_clean_data = [x for x in clean_data if x["country_code"] == country_code]
    sliceids = {x["id"] for x in slice_clean_data}

    # Load the dirty dataset and select the records for the slice
    dirty_data = load_csv_dataset(dirty_path)
    slice_dirty_data = [x for x in dirty_data if x["id"] in sliceids]

    # Join provenance_graph_iri if a provenance file is provided
    if path_provenance is not None:
        provenance_path = Path(path_provenance)
        if not provenance_path.exists():
            raise FileNotFoundError(f"Provenance file not found: {path_provenance}")
        provenance_data = load_csv_dataset(provenance_path)
        provenance_map = {row["id"]: row["provenance_graph_iri"] for row in provenance_data}
        for record in slice_clean_data:
            record["provenance_graph_iri"] = provenance_map.get(record["id"], "")
        for record in slice_dirty_data:
            record["provenance_graph_iri"] = provenance_map.get(record["id"], "")

    return slice_clean_data, slice_dirty_data


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
    loc_key = locality_mapping["locality"]
    reg_key = locality_mapping["region"]
    reader = csv.DictReader(open(input_path, encoding="utf-8"), delimiter=";")

    # Create a dictionary associating to each region the corresponding localities
    localities = {}
    for row in reader:
        region = row[reg_key]
        locality = row[loc_key]
        if region not in localities:
            localities[region] = set()
        localities[region].add(locality)

    return localities


def check_record_validity(clean_record, localities):
    """
    Check the validity of the input record.

    Args:
    clean_record (dict): clean record to validate (as a dictionary following the PostalAddress schema)
    localities (dict): dictionary associating each region with the corresponding localities

    Returns:
    reason: None if the record is valid, or a string describing the reason for rejection
    """

    # Check whether the house number follows a valid pattern
    if not any(re.search(p, clean_record["house_number"]) for p in house_number_patterns):
        return f"invalid house number: {clean_record['house_number']!r}"

    # Check whether the locality is valid
    if clean_record["region"] not in localities:
        return f"unknown region: {clean_record['region']!r}"
    if clean_record["locality"] not in localities[clean_record["region"]]:
        return f"uncertified locality: {clean_record['locality']!r} (region: {clean_record['region']!r})"

    return None


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
    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        # Keep only the output_fields columns (skipping any that are absent, e.g. 'name' for unnamed data)
        available_fields = [f for f in output_fields if f in data[0]]

        csv_writer = csv.DictWriter(
            open(output_path, "w", encoding="utf-8", newline="\n"),
            fieldnames=available_fields,
            extrasaction="ignore",
        )
        csv_writer.writeheader()
        csv_writer.writerows(data)

    except Exception as e:
        print(f"Error: {e}")
        return False

    return True


def deduplicate_by_dirty(clean_records, dirty_records):
    """
    Remove exact duplicates from dirty_records (comparing all columns except 'id'),
    keeping the first occurrence. Then remove the corresponding records from
    clean_records so that clean and dirty stay aligned by id.

    Args:
    clean_records (list): list of dicts for the clean slice
    dirty_records (list): list of dicts for the dirty slice

    Returns:
    dedup_clean (list): clean records with duplicate-dirty ids removed
    dedup_dirty (list): dirty records with duplicates removed
    removed_ids (list): ids that were dropped due to duplication in dirty
    """

    seen_signatures = {}
    dedup_dirty = []
    removed_ids = []

    # Compare only the output fields (minus 'id') so that extra input columns
    # like source_subset / source_pack don't prevent duplicate detection
    sig_fields = [f for f in output_fields if f != "id"]

    for record in dirty_records:
        signature = tuple((k, record.get(k, "")) for k in sig_fields)
        if signature not in seen_signatures:
            seen_signatures[signature] = record["id"]
            dedup_dirty.append(record)
        else:
            removed_ids.append(record["id"])

    kept_ids = {r["id"] for r in dedup_dirty}
    dedup_clean = [r for r in clean_records if r["id"] in kept_ids]

    return dedup_clean, dedup_dirty, removed_ids


def save_duplicates_csv(removed_ids, output_file):
    """
    Save the IDs removed as dirty duplicates to a single-column CSV file.

    Args:
    removed_ids (list): list of id strings that were dropped as duplicates
    output_file (str): path to the output file

    Returns:
    success: a Boolean value (True by default)
    """

    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        csv_writer = csv.DictWriter(
            open(output_path, "w", encoding="utf-8", newline="\n"),
            fieldnames=["id"],
        )
        csv_writer.writeheader()
        csv_writer.writerows({"id": id_} for id_ in removed_ids)

    except Exception as e:
        print(f"Error: {e}")
        return False

    return True


def save_skipped_csv(skipped, output_file):
    """
    Save the skipped records (id + reason) as a CSV file.

    Args:
    skipped (list): list of dicts with keys 'id' and 'reason'
    output_file (str): path to the output file

    Returns:
    success: a Boolean value (True by default)
    """

    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        csv_writer = csv.DictWriter(
            open(output_path, "w", encoding="utf-8", newline="\n"),
            fieldnames=["id", "reason"],
        )
        csv_writer.writeheader()
        csv_writer.writerows(skipped)

    except Exception as e:
        print(f"Error: {e}")
        return False

    return True

