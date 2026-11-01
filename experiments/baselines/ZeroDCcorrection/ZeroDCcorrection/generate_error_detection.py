#!/usr/bin/env python3
########################################
# Error Detection File Generator
# Generates binary error detection files by comparing clean and dirty CSV files
########################################

import html
import re
import sys
import os
import argparse
import pandas


########################################
class ErrorDetectionGenerator:
    """
    Generates binary error detection files by comparing clean and dirty datasets.
    """

    @staticmethod
    def value_normalizer(value):
        """
        This method takes a value and minimally normalizes it.
        """
        value = html.unescape(value)
        value = re.sub("[\t\n ]+", " ", value, re.UNICODE)
        value = value.strip("\t\n ")
        return value

    def read_csv_dataset(self, dataset_path):
        """
        This method reads a dataset from a csv file path.
        """
        dataframe = pandas.read_csv(dataset_path, sep=",", header="infer", encoding="utf-8", dtype=str,
                                    keep_default_na=False, low_memory=False).map(self.value_normalizer)
        return dataframe

    def get_dataframes_difference(self, dirty_df, clean_df):
        """
        This method compares two dataframes and returns the different cells as a set.
        Returns a set of (row_index, column_index) tuples for cells that differ.
        """
        if dirty_df.shape != clean_df.shape:
            sys.stderr.write(f"Warning: Dataframes have different shapes: dirty={dirty_df.shape}, clean={clean_df.shape}\n")
            # Use the minimum shape to avoid index errors
            min_rows = min(dirty_df.shape[0], clean_df.shape[0])
            min_cols = min(dirty_df.shape[1], clean_df.shape[1])
        else:
            min_rows = dirty_df.shape[0]
            min_cols = dirty_df.shape[1]
        
        error_cells = set()
        
        # Compare each cell
        for i in range(min_rows):
            for j in range(min_cols):
                dirty_value = dirty_df.iloc[i, j]
                clean_value = clean_df.iloc[i, j]
                
                # Mark as error if values differ
                if dirty_value != clean_value:
                    error_cells.add((i, j))
        
        return error_cells

    def generate_error_detection_file(self, dirty_path, clean_path, output_path):
        """
        Generate a binary error detection file by comparing dirty and clean datasets.
        
        Args:
            dirty_path: Path to the dirty CSV file
            clean_path: Path to the clean CSV file
            output_path: Path where the error detection file will be saved
        """
        print(f"Reading dirty dataset from: {dirty_path}")
        dirty_df = self.read_csv_dataset(dirty_path)
        
        print(f"Reading clean dataset from: {clean_path}")
        clean_df = self.read_csv_dataset(clean_path)
        
        print(f"Comparing datasets...")
        error_cells = self.get_dataframes_difference(dirty_df, clean_df)
        
        print(f"Found {len(error_cells)} error cells")
        
        # Create binary error detection dataframe
        # Initialize with zeros (all clean)
        error_detection_df = pandas.DataFrame(
            0, 
            index=range(dirty_df.shape[0]), 
            columns=dirty_df.columns
        )
        
        # Mark error cells with 1
        for (row_idx, col_idx) in error_cells:
            error_detection_df.iloc[row_idx, col_idx] = 1
        
        # Save to CSV
        print(f"Saving error detection file to: {output_path}")
        error_detection_df.to_csv(output_path, sep=",", header=True, index=False, encoding="utf-8")
        
        print(f"Done! Error rate: {len(error_cells) / (dirty_df.shape[0] * dirty_df.shape[1]):.4%}")
        
        return error_detection_df


########################################
def process_directory(directory_path, output_suffix="_error_detection.csv"):
    """
    Process a directory to find clean and dirty CSV files and generate error detection files.
    
    Expected naming conventions:
    - Dirty files: *_dirty.csv
    - Clean files: *_clean.csv
    - Output files: *_dirty_error_detection.csv 
    
    Args:
        directory_path: Path to the directory containing CSV files
        output_suffix: Suffix for output files (default: "_error_detection.csv")
    """
    generator = ErrorDetectionGenerator()
    
    if not os.path.isdir(directory_path):
        print(f"Error: {directory_path} is not a valid directory")
        return
    
    # Find all dirty CSV files
    dirty_files = []
    for filename in os.listdir(directory_path):
        if filename.endswith("_dirty.csv"):
            dirty_files.append(filename)
    
    if not dirty_files:
        print(f"No *_dirty.csv files found in {directory_path}")
        return
    
    print(f"Found {len(dirty_files)} dirty file(s) to process\n")
    
    # Process each dirty file
    for dirty_filename in dirty_files:
        # Derive the base name and clean filename
        base_name = dirty_filename.replace("_dirty.csv", "")
        clean_filename = f"{base_name}_clean.csv"
        output_filename = f"{base_name}_dirty{output_suffix}"
        
        dirty_path = os.path.join(directory_path, dirty_filename)
        clean_path = os.path.join(directory_path, clean_filename)
        output_path = os.path.join(directory_path, output_filename)
        
        # Check if clean file exists
        if not os.path.exists(clean_path):
            print(f"Warning: Clean file not found for {dirty_filename}")
            print(f"  Expected: {clean_path}")
            print(f"  Skipping...\n")
            continue
        
        # Check if output file already exists
        if os.path.exists(output_path):
            response = input(f"Output file already exists: {output_filename}\n  Overwrite? (y/n): ")
            if response.lower() != 'y':
                print(f"  Skipping...\n")
                continue
        
        print(f"Processing: {base_name}")
        print(f"=" * 60)
        
        try:
            generator.generate_error_detection_file(dirty_path, clean_path, output_path)
            print(f"✓ Successfully created: {output_filename}\n")
        except Exception as e:
            print(f"✗ Error processing {dirty_filename}: {str(e)}\n")


########################################
def main():
    parser = argparse.ArgumentParser(
        description="Generate binary error detection files by comparing clean and dirty CSV datasets",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Process all files in a directory
  python generate_error_detection.py /path/to/datasets/flights

  # Process with custom output suffix
  python generate_error_detection.py /path/to/datasets/flights --suffix "_errors.csv"

  # Process a specific pair of files
  python generate_error_detection.py --dirty dirty.csv --clean clean.csv --output errors.csv

The script expects files named with conventions:
  - Dirty files: *_dirty.csv
  - Clean files: *_clean.csv
  - Output files: *_dirty_error_detection.csv

The output file contains:
  - Same structure as input files (same columns and rows)
  - Binary values: 1 for error cells, 0 for clean cells
        """
    )
    
    parser.add_argument(
        "directory",
        nargs="?",
        help="Directory containing clean and dirty CSV files"
    )
    
    parser.add_argument(
        "--dirty",
        help="Path to a specific dirty CSV file"
    )
    
    parser.add_argument(
        "--clean",
        help="Path to a specific clean CSV file"
    )
    
    parser.add_argument(
        "--output", "-o",
        help="Path for the output error detection file"
    )
    
    parser.add_argument(
        "--suffix",
        default="_error_detection.csv",
        help="Suffix for output files when processing a directory (default: _error_detection.csv)"
    )
    
    args = parser.parse_args()
    
    # Check if specific files are provided
    if args.dirty and args.clean:
        if not args.output:
            # Generate output filename from dirty filename
            base = os.path.splitext(args.dirty)[0]
            args.output = f"{base}_error_detection.csv"
        
        print("Processing specific files...")
        print("=" * 60)
        generator = ErrorDetectionGenerator()
        
        try:
            generator.generate_error_detection_file(args.dirty, args.clean, args.output)
            print(f"✓ Successfully created: {args.output}")
        except Exception as e:
            print(f"✗ Error: {str(e)}")
            sys.exit(1)
    
    # Otherwise, process directory
    elif args.directory:
        process_directory(args.directory, args.suffix)
    
    else:
        parser.print_help()
        sys.exit(1)


########################################
if __name__ == "__main__":
    main()
########################################
