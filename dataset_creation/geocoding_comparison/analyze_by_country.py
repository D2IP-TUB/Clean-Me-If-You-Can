#!/usr/bin/env python3
"""
Analyze validation results by country.

This script analyzes the address validation results to show
error rates and validation quality per country.
"""

import pandas as pd
import json
from pathlib import Path
from collections import defaultdict


def analyze_validation_results(run_folder):
    """
    Analyze validation results by country.
    
    Args:
        run_folder: Path to the run folder (e.g., output/run_20251202_170705)
    """
    run_path = Path(run_folder)
    csv_file = run_path / 'validated.csv'
    
    if not csv_file.exists():
        print(f"❌ Error: {csv_file} not found")
        return
    
    print("="*80)
    print("ADDRESS VALIDATION ANALYSIS BY COUNTRY")
    print("="*80)
    print(f"Run folder: {run_folder}")
    print("="*80)
    
    # Load validation results
    print("\nLoading validation results...")
    df = pd.read_csv(csv_file)
    print(f"Total records: {len(df):,}")
    
    # Add country name from original address (extract from end)
    # Format: "..., country"
    df['country'] = df['original_address'].str.split(', ').str[-1]
    
    print(f"Countries found: {df['country'].nunique()}")
    
    # Analyze by country
    print("\n" + "="*80)
    print("VALIDATION RESULTS BY COUNTRY")
    print("="*80)
    
    country_stats = []
    
    for country in sorted(df['country'].unique()):
        country_df = df[df['country'] == country]
        total = len(country_df)
        
        # Count by status
        valid = len(country_df[country_df['status'] == 'VALID'])
        needs_review = len(country_df[country_df['status'] == 'NEEDS_REVIEW'])
        invalid = len(country_df[country_df['status'] == 'INVALID'])
        error = len(country_df[country_df['status'] == 'ERROR'])
        
        # Calculate percentages
        valid_pct = (valid / total * 100) if total > 0 else 0
        needs_review_pct = (needs_review / total * 100) if total > 0 else 0
        invalid_pct = (invalid / total * 100) if total > 0 else 0
        error_pct = (error / total * 100) if total > 0 else 0
        
        # Erroneous = NEEDS_REVIEW + INVALID + ERROR
        erroneous = needs_review + invalid + error
        erroneous_pct = (erroneous / total * 100) if total > 0 else 0
        
        country_stats.append({
            'country': country,
            'total': total,
            'valid': valid,
            'valid_%': round(valid_pct, 1),
            'needs_review': needs_review,
            'needs_review_%': round(needs_review_pct, 1),
            'invalid': invalid,
            'invalid_%': round(invalid_pct, 1),
            'error': error,
            'error_%': round(error_pct, 1),
            'erroneous_total': erroneous,
            'erroneous_%': round(erroneous_pct, 1)
        })
    
    # Create DataFrame and sort by erroneous percentage (descending)
    stats_df = pd.DataFrame(country_stats)
    stats_df = stats_df.sort_values('erroneous_%', ascending=False)
    
    # Display summary table
    print(f"\n{'Country':<40} {'Total':>6} {'Valid':>6} {'Error':>6} {'Invalid':>6} {'Review':>6} {'Erroneous':>10}")
    print("-" * 115)
    
    for _, row in stats_df.iterrows():
        print(f"{row['country']:<40} "
              f"{row['total']:>6} "
              f"{row['valid']:>5} ({row['valid_%']:>4.1f}%) "
              f"{row['error']:>5} ({row['error_%']:>4.1f}%) "
              f"{row['invalid']:>5} ({row['invalid_%']:>4.1f}%) "
              f"{row['needs_review']:>5} ({row['needs_review_%']:>4.1f}%) "
              f"{row['erroneous_total']:>5} ({row['erroneous_%']:>4.1f}%)")
    
    # Overall statistics
    print("\n" + "="*80)
    print("OVERALL STATISTICS")
    print("="*80)
    
    total_all = len(df)
    valid_all = len(df[df['status'] == 'VALID'])
    needs_review_all = len(df[df['status'] == 'NEEDS_REVIEW'])
    invalid_all = len(df[df['status'] == 'INVALID'])
    error_all = len(df[df['status'] == 'ERROR'])
    erroneous_all = needs_review_all + invalid_all + error_all
    
    print(f"Total addresses:     {total_all:>6}")
    print(f"✅ Valid:             {valid_all:>6} ({valid_all/total_all*100:>5.1f}%)")
    print(f"⚠️  Needs Review:      {needs_review_all:>6} ({needs_review_all/total_all*100:>5.1f}%)")
    print(f"❌ Invalid:           {invalid_all:>6} ({invalid_all/total_all*100:>5.1f}%)")
    print(f"🔴 Errors:            {error_all:>6} ({error_all/total_all*100:>5.1f}%)")
    print(f"{'='*30}")
    print(f"📊 Total Erroneous:   {erroneous_all:>6} ({erroneous_all/total_all*100:>5.1f}%)")
    
    # Save detailed statistics
    output_file = run_path / 'country_analysis.csv'
    stats_df.to_csv(output_file, index=False)
    print(f"\n✅ Detailed statistics saved to: {output_file}")
    
    # Top 10 countries with highest error rates
    print("\n" + "="*80)
    print("TOP 10 COUNTRIES WITH HIGHEST ERROR RATES")
    print("="*80)
    
    top_errors = stats_df.nlargest(10, 'erroneous_%')
    print(f"\n{'Rank':<6} {'Country':<40} {'Total':>6} {'Erroneous':>10} {'Rate':>8}")
    print("-" * 80)
    
    for i, (_, row) in enumerate(top_errors.iterrows(), 1):
        print(f"{i:<6} {row['country']:<40} {row['total']:>6} "
              f"{row['erroneous_total']:>10} {row['erroneous_%']:>7.1f}%")
    
    # Countries with 100% success rate
    perfect = stats_df[stats_df['erroneous_%'] == 0]
    if len(perfect) > 0:
        print("\n" + "="*80)
        print(f"✅ COUNTRIES WITH 0% ERROR RATE ({len(perfect)} countries)")
        print("="*80)
        for _, row in perfect.iterrows():
            print(f"  • {row['country']:<40} ({row['total']} addresses)")
    
    # Generate visual summary
    print("\n" + "="*80)
    print("ERROR RATE DISTRIBUTION")
    print("="*80)
    
    # Bin countries by error rate
    bins = [
        (0, 0, "Perfect (0%)"),
        (0, 5, "Excellent (0-5%)"),
        (5, 10, "Good (5-10%)"),
        (10, 20, "Fair (10-20%)"),
        (20, 100, "Poor (>20%)")
    ]
    
    for min_val, max_val, label in bins:
        if min_val == 0 and max_val == 0:
            count = len(stats_df[stats_df['erroneous_%'] == 0])
        else:
            count = len(stats_df[(stats_df['erroneous_%'] > min_val) & (stats_df['erroneous_%'] <= max_val)])
        
        total_addresses = stats_df[(stats_df['erroneous_%'] > min_val) & (stats_df['erroneous_%'] <= max_val)]['total'].sum()
        
        bar = "█" * (count // 2) if count > 0 else ""
        print(f"{label:<20} {count:>3} countries {bar} ({total_addresses} addresses)")
    
    print("="*80)
    
    return stats_df


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        run_folder = sys.argv[1]
    else:
        # Use the latest run folder
        run_folder = "output/run_20251202_170705"
    
    analyze_validation_results(run_folder)
