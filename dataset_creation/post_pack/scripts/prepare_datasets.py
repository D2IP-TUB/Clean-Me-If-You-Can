#!/usr/bin/env python3

"""
Script to remove line terminator characters from CSV files and add ID column.

Usage: python prepare_datasets.py <input_file> [output_file]
If output_file is not specified, the input file will be modified in place.
"""

import argparse
import csv
import sys
from pathlib import Path
from tqdm import tqdm


def prepare_dataset(input_file, output_file=None):
    """
    Remove line terminator characters from the input CSV file and add ID column.

    Args:
    input_file (str): path to the input file
    output_file (str, optional): path to the output file (if None, the input file is modified in place)

    Returns:
    dict: statistics about the replacements made
    """

    # Parse the path to the input file
    input_path = Path(input_file)

    # Check that the path is valid
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_file}")

    # Parse the path to the output file (modify in place if None)
    if output_file is None:
        output_path = Path(input_file)
    else:
        output_path = Path(output_file)

    # Check that the path is valid
    if not output_path.exists():
        raise FileNotFoundError(f"Output file not found: {input_file}")

    print(f"Processing file: {input_path}")
    print(f"Output file: {output_path}")

    # Read the input file
    rows = list()
    reader = csv.reader(open(input_path, "r", encoding="utf-8"))
    for row in reader:
        rows.append(row)
    num_rows = len(rows)

    print(f"Total lines to process: {num_rows}")

    # Remove line terminators from the header and add the "_id" column name
    header = rows[0]
    header = ["_id"] + [x.replace("\n", " ").replace("\u2028", " ").replace("\u2029", " ") for x in header]

    # Remove line terminators from the data and add a progressive identifier
    data = rows[1:]
    num_data_rows = len(data)
    print(f"Processing {num_data_rows} data rows...")
    for i in tqdm(range(num_data_rows)):
        data[i] = [i] + [x.replace("\n", " ").replace("\u2028", " ").replace("\u2029", " ") for x in data[i]]
    print(f"Processing complete!")

    # Save header and data rows to the output file
    writer = csv.writer(open(output_path, "w", encoding="utf-8", newline="\n"))
    writer.writerows([header] + data)


def main():

    parser = argparse.ArgumentParser(formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("input_file", help="Path to the input CSV file")
    parser.add_argument("output_file", nargs="?", help="Path to the output CSV file (optional)")
    args = parser.parse_args()

    try:
        prepare_dataset(args.input_file, args.output_file)

    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
