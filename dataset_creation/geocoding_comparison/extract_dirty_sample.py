#!/usr/bin/env python3
"""
Extract dirty versions of stratified sample records.

This script takes the IDs from stratified_sample_1000.csv and extracts
the corresponding records from dirty-full-named.csv.
"""

import pandas as pd
from pathlib import Path


def extract_dirty_sample():
    # File paths
    datasets_dir = Path('../datasets')
    clean_sample_file = datasets_dir / 'stratified_sample_~1000.csv'
    dirty_full_file = datasets_dir / 'dirty-full-named.csv'
    output_file = datasets_dir / 'stratified_sample_~1000-dirty.csv'
    
    print("="*80)
    print("EXTRACT DIRTY VERSIONS OF STRATIFIED SAMPLE")
    print("="*80)
    
    # Load the stratified sample to get the IDs
    print(f"\n1. Loading clean stratified sample: {clean_sample_file}")
    sample_df = pd.read_csv(clean_sample_file)
    print(f"   Records: {len(sample_df):,}")
    print(f"   Columns: {list(sample_df.columns)}")
    
    # Get the list of IDs
    sample_ids = set(sample_df['_id'].values)
    print(f"   Unique IDs: {len(sample_ids):,}")
    
    # Load the dirty dataset
    print(f"\n2. Loading dirty dataset: {dirty_full_file}")
    dirty_df = pd.read_csv(dirty_full_file)
    print(f"   Total records: {len(dirty_df):,}")
    
    # Filter dirty dataset to only include records with matching IDs
    print(f"\n3. Extracting matching records from dirty dataset...")
    dirty_sample = dirty_df[dirty_df['_id'].isin(sample_ids)].copy()
    print(f"   Found: {len(dirty_sample):,} matching records")
    
    # Verify all IDs were found
    found_ids = set(dirty_sample['_id'].values)
    missing_ids = sample_ids - found_ids
    
    if missing_ids:
        print(f"   ⚠️  Warning: {len(missing_ids)} IDs not found in dirty dataset")
        print(f"   Missing IDs: {sorted(missing_ids)[:10]}{'...' if len(missing_ids) > 10 else ''}")
    else:
        print(f"   ✅ All IDs found!")
    
    # Sort by _id to maintain consistent order
    dirty_sample = dirty_sample.sort_values('_id').reset_index(drop=True)
    
    # Save to new file
    print(f"\n4. Saving to {output_file}...")
    dirty_sample.to_csv(output_file, index=False)
    
    file_size = output_file.stat().st_size / 1024  # KB
    print(f"   ✅ File saved ({file_size:.1f} KB)")
    
    # Summary
    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)
    print(f"Input (clean):  {clean_sample_file.name}")
    print(f"               {len(sample_df):,} records")
    print(f"\nSource (dirty): {dirty_full_file.name}")
    print(f"               {len(dirty_df):,} records")
    print(f"\nOutput (dirty): {output_file.name}")
    print(f"               {len(dirty_sample):,} records")
    print(f"               {list(dirty_sample.columns)}")
    
    # Verification - show comparison
    print("\n" + "="*80)
    print("VERIFICATION - Sample Comparison (first 3 records)")
    print("="*80)
    
    # Get first 3 matching IDs
    common_ids = sorted(sample_ids)[:3]
    
    for _id in common_ids:
        clean_record = sample_df[sample_df['_id'] == _id].iloc[0]
        dirty_record = dirty_sample[dirty_sample['_id'] == _id].iloc[0]
        
        print(f"\nID: {_id}")
        print(f"  Clean: {clean_record.get('road', 'N/A')}, {clean_record.get('locality', 'N/A')}, {clean_record.get('country', 'N/A')}")
        print(f"  Dirty: {dirty_record.get('road', 'N/A')}, {dirty_record.get('locality', 'N/A')}, {dirty_record.get('country', 'N/A')}")
    
    print("\n" + "="*80)
    
    return dirty_sample


if __name__ == "__main__":
    extract_dirty_sample()
