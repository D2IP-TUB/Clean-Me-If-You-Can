#!/usr/bin/env python3
"""
Batch generate error detection files for all datasets in a directory.
Reuses the existing generate_error_detection.py ErrorDetectionGenerator class.
"""

import os
import sys
from generate_error_detection import ErrorDetectionGenerator


def batch_generate(datasets_path):
    """Generate error detection files for all datasets in the given path."""
    generator = ErrorDetectionGenerator()
    
    if not os.path.isdir(datasets_path):
        print(f"Error: {datasets_path} is not a valid directory")
        sys.exit(1)
    
    # Get all subdirectories
    datasets = sorted([d for d in os.listdir(datasets_path) 
                      if os.path.isdir(os.path.join(datasets_path, d))])
    
    print(f"Found {len(datasets)} datasets in {datasets_path}")
    print("=" * 80)
    
    success = 0
    skipped = 0
    failed = 0
    
    for i, dataset_name in enumerate(datasets, 1):
        dataset_dir = os.path.join(datasets_path, dataset_name)
        clean_file = os.path.join(dataset_dir, 'clean.csv')
        dirty_file = os.path.join(dataset_dir, 'dirty.csv')
        output_file = os.path.join(dataset_dir, 'perfect_error_detection.csv')
        
        # Check if files exist
        if not os.path.exists(clean_file) or not os.path.exists(dirty_file):
            print(f"[{i}/{len(datasets)}] SKIP: {dataset_name} (missing clean.csv or dirty.csv)")
            skipped += 1
            continue
        
        # Skip if output already exists
        if os.path.exists(output_file):
            print(f"[{i}/{len(datasets)}] SKIP: {dataset_name} (already exists)")
            skipped += 1
            continue
        
        print(f"[{i}/{len(datasets)}] Processing: {dataset_name}")
        
        try:
            generator.generate_error_detection_file(dirty_file, clean_file, output_file)
            print(f"     ✓ SUCCESS\n")
            success += 1
        except Exception as e:
            print(f"     ✗ FAILED: {str(e)}\n")
            failed += 1
    
    print("=" * 80)
    print(f"Summary:")
    print(f"  Total datasets: {len(datasets)}")
    print(f"  Successfully generated: {success}")
    print(f"  Skipped: {skipped}")
    print(f"  Failed: {failed}")
    print("=" * 80)


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Batch generate error detection files for all datasets'
    )
    parser.add_argument(
        'datasets_path',
        help='Path to directory containing dataset subdirectories'
    )
    
    args = parser.parse_args()
    batch_generate(args.datasets_path)
