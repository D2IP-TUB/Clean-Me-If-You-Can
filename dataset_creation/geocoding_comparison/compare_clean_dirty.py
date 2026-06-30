#!/usr/bin/env python3
"""
Compare clean vs dirty validation results.

This script compares the validation results between clean and dirty
versions of the same stratified sample.
"""

import pandas as pd
from pathlib import Path


def compare_results(clean_run, dirty_run):
    """
    Compare validation results between clean and dirty datasets.
    
    Args:
        clean_run: Path to clean validation run folder
        dirty_run: Path to dirty validation run folder
    """
    
    print("="*80)
    print("CLEAN vs DIRTY VALIDATION COMPARISON")
    print("="*80)
    
    # Load both CSV files
    clean_csv = Path(clean_run) / 'validated.csv'
    dirty_csv = Path(dirty_run) / 'validated.csv'
    
    print(f"\nClean run: {clean_run}")
    print(f"Dirty run: {dirty_run}")
    
    clean_df = pd.read_csv(clean_csv)
    dirty_df = pd.read_csv(dirty_csv)
    
    print(f"\nClean records: {len(clean_df):,}")
    print(f"Dirty records: {len(dirty_df):,}")
    
    # Overall comparison
    print("\n" + "="*80)
    print("OVERALL VALIDATION RESULTS")
    print("="*80)
    
    def get_stats(df, label):
        total = len(df)
        valid = len(df[df['status'] == 'VALID'])
        needs_review = len(df[df['status'] == 'NEEDS_REVIEW'])
        invalid = len(df[df['status'] == 'INVALID'])
        error = len(df[df['status'] == 'ERROR'])
        complete = len(df[df['complete'] == True])
        
        print(f"\n{label}:")
        print(f"  Total:           {total:>5}")
        print(f"  ✅ Valid:         {valid:>5} ({valid/total*100:>5.1f}%)")
        print(f"  ⚠️  Needs Review:  {needs_review:>5} ({needs_review/total*100:>5.1f}%)")
        print(f"  ❌ Invalid:       {invalid:>5} ({invalid/total*100:>5.1f}%)")
        print(f"  🔴 Errors:        {error:>5} ({error/total*100:>5.1f}%)")
        print(f"  📍 Complete:      {complete:>5} ({complete/total*100:>5.1f}%)")
        
        return {
            'total': total,
            'valid': valid,
            'valid_pct': valid/total*100,
            'needs_review': needs_review,
            'needs_review_pct': needs_review/total*100,
            'invalid': invalid,
            'invalid_pct': invalid/total*100,
            'error': error,
            'error_pct': error/total*100,
            'complete': complete,
            'complete_pct': complete/total*100
        }
    
    clean_stats = get_stats(clean_df, "CLEAN Dataset")
    dirty_stats = get_stats(dirty_df, "DIRTY Dataset")
    
    # Calculate differences
    print("\n" + "="*80)
    print("DIFFERENCE (Dirty - Clean)")
    print("="*80)
    print(f"  Valid:         {dirty_stats['valid'] - clean_stats['valid']:+5d} ({dirty_stats['valid_pct'] - clean_stats['valid_pct']:+6.1f}%)")
    print(f"  Needs Review:  {dirty_stats['needs_review'] - clean_stats['needs_review']:+5d} ({dirty_stats['needs_review_pct'] - clean_stats['needs_review_pct']:+6.1f}%)")
    print(f"  Invalid:       {dirty_stats['invalid'] - clean_stats['invalid']:+5d} ({dirty_stats['invalid_pct'] - clean_stats['invalid_pct']:+6.1f}%)")
    print(f"  Errors:        {dirty_stats['error'] - clean_stats['error']:+5d} ({dirty_stats['error_pct'] - clean_stats['error_pct']:+6.1f}%)")
    print(f"  Complete:      {dirty_stats['complete'] - clean_stats['complete']:+5d} ({dirty_stats['complete_pct'] - clean_stats['complete_pct']:+6.1f}%)")
    
    # Merge dataframes on ID to compare individual records
    print("\n" + "="*80)
    print("RECORD-LEVEL COMPARISON")
    print("="*80)
    
    # Merge on ID
    merged = clean_df.merge(dirty_df, on='id', suffixes=('_clean', '_dirty'))
    
    # Records with different status
    status_changed = merged[merged['status_clean'] != merged['status_dirty']]
    
    print(f"\nTotal records: {len(merged):,}")
    print(f"Status changed: {len(status_changed):,} ({len(status_changed)/len(merged)*100:.1f}%)")
    
    if len(status_changed) > 0:
        print("\nStatus changes breakdown:")
        for idx, row in status_changed.iterrows():
            print(f"  ID {row['id']}: {row['status_clean']} → {row['status_dirty']}")
            if len(status_changed) > 20:
                print(f"  ... and {len(status_changed) - 20} more")
                break
    
    # Analyze status transitions
    print("\n" + "="*80)
    print("STATUS TRANSITION MATRIX")
    print("="*80)
    
    transition_matrix = pd.crosstab(
        merged['status_clean'], 
        merged['status_dirty'],
        margins=True
    )
    
    print("\nClean (rows) vs Dirty (columns):")
    print(transition_matrix)
    
    # Quality degradation analysis
    print("\n" + "="*80)
    print("QUALITY IMPACT ANALYSIS")
    print("="*80)
    
    # Count improvements and degradations
    improvements = 0
    degradations = 0
    unchanged = 0
    
    status_order = {'VALID': 3, 'NEEDS_REVIEW': 2, 'INVALID': 1, 'ERROR': 0}
    
    for idx, row in merged.iterrows():
        clean_score = status_order.get(row['status_clean'], 0)
        dirty_score = status_order.get(row['status_dirty'], 0)
        
        if dirty_score > clean_score:
            improvements += 1
        elif dirty_score < clean_score:
            degradations += 1
        else:
            unchanged += 1
    
    print(f"\nQuality changes:")
    print(f"  ⬆️  Improved:    {improvements:>5} ({improvements/len(merged)*100:>5.1f}%)")
    print(f"  ⬇️  Degraded:    {degradations:>5} ({degradations/len(merged)*100:>5.1f}%)")
    print(f"  ➡️  Unchanged:   {unchanged:>5} ({unchanged/len(merged)*100:>5.1f}%)")
    
    # Net quality impact
    net_impact = improvements - degradations
    print(f"\n  📊 Net impact:  {net_impact:+5d} ({net_impact/len(merged)*100:+6.1f}%)")
    
    if net_impact > 0:
        print("  ✅ Dirty data performed BETTER overall")
    elif net_impact < 0:
        print("  ❌ Clean data performed BETTER overall")
    else:
        print("  ➡️  No net difference")
    
    # Save comparison
    output_file = Path('validation_comparison.csv')
    comparison_df = merged[['id', 'name_clean', 'status_clean', 'status_dirty', 
                            'complete_clean', 'complete_dirty', 
                            'original_address_clean', 'original_address_dirty']]
    comparison_df.to_csv(output_file, index=False)
    print(f"\n✅ Detailed comparison saved to: {output_file}")
    
    print("="*80)
    
    return merged


if __name__ == "__main__":
    clean_run = "output/run_20251202_171627_clean_1000_stratified"
    dirty_run = "output/run_20251202_180424_dirty_1000_stratified"
    
    compare_results(clean_run, dirty_run)
