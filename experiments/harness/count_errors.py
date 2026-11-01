#!/usr/bin/env python3
"""
Script to count errors between clean.csv and dirty.csv files in subdirectories.
"""

import html
import os
import re
import sys
from pathlib import Path

import pandas as pd


def value_normalizer(value):
    """
    This method takes a value and minimally normalizes it.
    """
    value = html.unescape(value)
    value = re.sub(r"[\t\n ]+", " ", value)
    value = value.strip("\t\n ")
    return value.lower()


def compare_csv_files(clean_path, dirty_path):
    """
    Compare two CSV files and count the number of cell differences.
    Reads files using pandas and compares all values as strings.
    
    Args:
        clean_path: Path to the clean CSV file
        dirty_path: Path to the dirty CSV file
        
    Returns:
        Dictionary with comparison statistics or None if dimensions mismatch
    """
    try:
        # Read CSV files with pandas and convert all values to strings
        clean_df = pd.read_csv(clean_path, dtype=str, keep_default_na=False)
        dirty_df = pd.read_csv(dirty_path, dtype=str, keep_default_na=False)
        
        # Apply value normalization to all cells
        clean_df = clean_df.map(value_normalizer)
        dirty_df = dirty_df.map(value_normalizer)
        
        # Get dimensions
        clean_rows, clean_cols = clean_df.shape
        dirty_rows, dirty_cols = dirty_df.shape
        
        # Check if number of rows are different
        if clean_rows != dirty_rows:
            print(f"  ERROR: Row count mismatch - clean: {clean_rows}, dirty: {dirty_rows}")
            return None
        
        # Check if number of columns are different
        if clean_cols != dirty_cols:
            print(f"  ERROR: Column count mismatch - clean: {clean_cols}, dirty: {dirty_cols}")
            return None
        
        # Count differences by cell directly on DataFrames
        dirty_df.columns = clean_df.columns  # Ensure columns are aligned
        cell_errors = (clean_df != dirty_df)
        total_errors = cell_errors.sum().sum()
        
        # Count rows with at least one error
        erroneous_rows = cell_errors.any(axis=1).sum()
        
        # Count columns with at least one error
        erroneous_cols = cell_errors.any(axis=0).sum()
        
        # Calculate metrics
        n_rows = clean_rows
        n_cols = clean_cols
        n_cells = n_rows * n_cols
        
        return {
            'total_errors': int(total_errors),
            'erroneous_rows': int(erroneous_rows),
            'erroneous_cols': int(erroneous_cols),
            'n_rows': int(n_rows),
            'n_cols': int(n_cols),
            'n_cells': int(n_cells)
        }
    
    except Exception as e:
        print(f"Error comparing files {clean_path} and {dirty_path}: {e}")
        return None


def count_errors_in_lake(directory_path):
    """
    Iterate through subdirectories and count total errors between clean and dirty CSV files.
    
    Args:
        directory_path: Path to the directory containing subdirectories with CSV files
        
    Returns:
        Dictionary with comprehensive statistics about the data lake
    """
    directory = Path(directory_path)
    
    if not directory.exists():
        print(f"Error: Directory '{directory_path}' does not exist.")
        return None
    
    if not directory.is_dir():
        print(f"Error: '{directory_path}' is not a directory.")
        return None
    
    # Initialize accumulators
    total_errors = 0
    total_erroneous_rows = 0
    total_erroneous_cols = 0
    total_rows = 0
    total_cols = 0
    total_n_cells = 0
    datasets_processed = 0
    datasets_skipped = 0
    datasets_with_dimension_mismatch = 0
    
    # Iterate through subdirectories
    for subdir in sorted(directory.iterdir()):
        if not subdir.is_dir():
            continue
        
        clean_csv = subdir / "clean.csv"
        dirty_csv = subdir / "dirty.csv"
        
        # Check if both files exist
        if clean_csv.exists() and dirty_csv.exists():
            print(f"Processing: {subdir.name}")
            result = compare_csv_files(clean_csv, dirty_csv)
            if result is None:
                datasets_with_dimension_mismatch += 1
            else:
                total_errors += result['total_errors']
                total_erroneous_rows += result['erroneous_rows']
                total_erroneous_cols += result['erroneous_cols']
                total_rows += result['n_rows']
                total_cols += result['n_cols']
                total_n_cells += result['n_cells']
                datasets_processed += 1
                print(f"  Errors found: {result['total_errors']}")
        else:
            datasets_skipped += 1
            missing = []
            if not clean_csv.exists():
                missing.append("clean.csv")
            if not dirty_csv.exists():
                missing.append("dirty.csv")
            print(f"Skipping {subdir.name}: Missing {', '.join(missing)}")
    
    # Calculate derived metrics
    total_datasets = datasets_processed
    sandbox_name = directory.name
    
    if total_datasets > 0:
        avg_rows = total_rows / total_datasets
        avg_cols = total_cols / total_datasets
    else:
        avg_rows = 0
        avg_cols = 0
    
    if total_n_cells > 0:
        error_rate_cells = total_errors / total_n_cells
    else:
        error_rate_cells = 0
    
    if total_rows > 0:
        error_rate_rows = total_erroneous_rows / total_rows
    else:
        error_rate_rows = 0
    
    if total_cols > 0:
        error_rate_cols = total_erroneous_cols / total_cols
    else:
        error_rate_cols = 0
    
    # Calculate average errors per erroneous row
    if total_erroneous_rows > 0:
        avg_errors_per_erroneous_row = total_errors / total_erroneous_rows
    else:
        avg_errors_per_erroneous_row = 0
    
    # Prepare results dictionary
    results = {
        'sandbox_name': sandbox_name,
        'error_rate_cells': error_rate_cells,
        'error_rate_rows': error_rate_rows,
        'error_rate_cols': error_rate_cols,
        'avg_errors_per_erroneous_row': avg_errors_per_erroneous_row,
        'avg_rows': avg_rows,
        'avg_cols': avg_cols,
        'total_n_cells': total_n_cells,
        'total_errors': total_errors,
        'total_error_cells_injected': total_errors,  # Same as total_errors
        'total_erroneous_rows': total_erroneous_rows,
        'total_erroneous_cols': total_erroneous_cols,
        'total_rows': total_rows,
        'total_cols': total_cols,
        'total_datasets': total_datasets
    }
    
    # Print summary
    print("\n" + "="*60)
    print(f"Summary for: {sandbox_name}")
    print(f"  Datasets processed: {datasets_processed}")
    print(f"  Datasets with dimension mismatch: {datasets_with_dimension_mismatch}")
    print(f"  Datasets skipped: {datasets_skipped}")
    print(f"  Total rows: {total_rows:,}")
    print(f"  Total cols: {total_cols:,}")
    print(f"  Total cells: {total_n_cells:,}")
    print(f"  Total errors: {total_errors:,}")
    print(f"  Total erroneous rows: {total_erroneous_rows:,}")
    print(f"  Total erroneous cols: {total_erroneous_cols:,}")
    print(f"  Avg errors per erroneous row: {results['avg_errors_per_erroneous_row']:.2f}")
    print(f"  Error rate (cells): {error_rate_cells:.6f}")
    print(f"  Error rate (rows): {error_rate_rows:.6f}")
    print(f"  Error rate (cols): {error_rate_cols:.6f}")
    print(f"  Average rows per dataset: {avg_rows:.2f}")
    print(f"  Average cols per dataset: {avg_cols:.2f}")
    print("="*60)
    
    return results


EXPERIMENT_DATASETS_DEFAULT = str(
    Path(__file__).resolve().parent / "experiment_datasets" / "effectiveness"
)


def run_all(root: str):
    """Walk root recursively, find every dirty+clean pair, print a stats table."""
    root_path = Path(root).resolve()
    if not root_path.exists():
        print(f"Error: '{root}' does not exist.")
        sys.exit(1)

    # Collect all dirs that contain both dirty.csv and clean.csv
    pairs = []
    for dirpath, dirnames, filenames in os.walk(root_path):
        if "dirty.csv" in filenames and "clean.csv" in filenames:
            pairs.append(Path(dirpath))
    pairs.sort()

    if not pairs:
        print(f"No dirty/clean pairs found under {root_path}")
        return

    col_w = max(len(str(p.relative_to(root_path))) for p in pairs) + 2
    header = f"{'Dataset':<{col_w}} {'rows':>7} {'cells':>10} {'errors':>8} {'cell_err%':>10} {'row_err%':>9}"
    print(header)
    print("-" * len(header))

    for d in pairs:
        rel = str(d.relative_to(root_path))
        result = compare_csv_files(d / "clean.csv", d / "dirty.csv")
        if result is None:
            print(f"{rel:<{col_w}} [dimension mismatch]")
            continue
        cell_pct = 100.0 * result["total_errors"] / result["n_cells"] if result["n_cells"] else 0
        row_pct  = 100.0 * result["erroneous_rows"] / result["n_rows"] if result["n_rows"] else 0
        print(
            f"{rel:<{col_w}} "
            f"{result['n_rows']:>7,} "
            f"{result['n_cells']:>10,} "
            f"{result['total_errors']:>8,} "
            f"{cell_pct:>9.2f}% "
            f"{row_pct:>8.2f}%"
        )


def main():
    """Main function to run the script."""
    if len(sys.argv) == 1:
        # No argument: scan the full experiment_datasets tree
        run_all(EXPERIMENT_DATASETS_DEFAULT)
    elif len(sys.argv) == 2:
        path = sys.argv[1]
        # If the given path contains dirty+clean directly, use the old single-dir mode;
        # otherwise walk the tree.
        p = Path(path)
        if (p / "dirty.csv").exists() and (p / "clean.csv").exists():
            results = count_errors_in_lake(path)
            if results:
                print("\n" + "=" * 60)
                print("Results in CSV format:")
                print(",".join(results.keys()))
                print(",".join(str(v) for v in results.values()))
                print("=" * 60)
        else:
            run_all(path)
    else:
        print("Usage: python count_errors.py [directory_path]")
        print("  No argument  → scan experiment_datasets tree")
        print("  directory    → scan that directory tree (or single dataset folder)")
        sys.exit(1)


if __name__ == "__main__":
    main()
