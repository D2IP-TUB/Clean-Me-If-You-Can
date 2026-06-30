#!/usr/bin/env python3
"""
Create a TRUE stratified sample from the full dataset.

This script creates a proportional stratified sample where each country
is represented proportionally to its occurrence in the full dataset.
"""

import argparse
import pandas as pd
import sys
from pathlib import Path


def create_stratified_sample(input_csv: str, output_csv: str, stats_csv: str):
    total_sample_size = 1000  # Total records to sample
    random_seed = 42  # For reproducibility
    min_per_country = 1  # Minimum records per country (if it appears at all)
    
    print("="*80)
    print("TRUE STRATIFIED SAMPLE CREATOR")
    print("="*80)
    print(f"Input: {input_csv}")
    print(f"Total sample size: {total_sample_size}")
    print(f"Method: Proportional stratified sampling")
    print("="*80)
    
    # Load the full dataset
    print("\nLoading dataset...")
    df = pd.read_csv(input_csv)
    total_records = len(df)
    print(f"Total records: {total_records:,}")
    
    # Get country distribution
    print("\nAnalyzing country distribution...")
    country_counts = df['country'].value_counts()
    total_countries = len(country_counts)
    print(f"Total countries: {total_countries}")
    
    # Calculate proportional sample sizes
    print(f"\nCalculating proportional sample sizes for {total_sample_size} total records...")
    
    samples = []
    stats = []
    actual_total = 0
    
    # Calculate exact proportions
    sample_plan = []
    for country, count in country_counts.items():
        proportion = count / total_records
        exact_sample = proportion * total_sample_size
        allocated_sample = max(min_per_country, round(exact_sample))
        
        sample_plan.append({
            'country': country,
            'available': count,
            'proportion': proportion,
            'exact_sample': exact_sample,
            'allocated': allocated_sample
        })
    
    # Sort by allocated (largest first) and adjust to hit exact total
    sample_plan_df = pd.DataFrame(sample_plan)
    sample_plan_df = sample_plan_df.sort_values('allocated', ascending=False)
    
    # Adjust to ensure we get exactly the target sample size
    current_total = sample_plan_df['allocated'].sum()
    diff = total_sample_size - current_total
    
    if diff != 0:
        # Distribute the difference to the largest countries
        print(f"Adjusting allocation (diff: {diff:+d})...")
        for i in range(abs(diff)):
            idx = i % len(sample_plan_df)
            if diff > 0:
                sample_plan_df.loc[sample_plan_df.index[idx], 'allocated'] += 1
            else:
                if sample_plan_df.loc[sample_plan_df.index[idx], 'allocated'] > min_per_country:
                    sample_plan_df.loc[sample_plan_df.index[idx], 'allocated'] -= 1
    
    # Sort back by proportion for display
    sample_plan_df = sample_plan_df.sort_values('proportion', ascending=False)
    
    print(f"\nSampling plan (showing top 20 countries):")
    print(f"{'Country':<40} {'Available':>10} {'%':>6} {'Sample':>7}")
    print("-" * 80)
    
    for idx, row in sample_plan_df.head(20).iterrows():
        pct = row['proportion'] * 100
        print(f"{row['country']:<40} {row['available']:>10,} {pct:>5.2f}% {int(row['allocated']):>7}")
    
    if len(sample_plan_df) > 20:
        remaining = len(sample_plan_df) - 20
        remaining_sample = sample_plan_df.tail(len(sample_plan_df) - 20)['allocated'].sum()
        print(f"{'... and ' + str(remaining) + ' more countries':<40} {'':<10} {'':<6} {int(remaining_sample):>7}")
    
    # Perform stratified sampling
    print(f"\nPerforming stratified sampling...")
    
    for idx, row in sample_plan_df.iterrows():
        country = row['country']
        available = row['available']
        to_sample = int(row['allocated'])
        
        country_df = df[df['country'] == country]
        
        if available >= to_sample:
            sample = country_df.sample(n=to_sample, random_state=random_seed)
            sampled = to_sample
            status = "OK"
        else:
            sample = country_df
            sampled = available
            status = f"ALL (only {available} available)"
        
        samples.append(sample)
        actual_total += sampled
        
        stats.append({
            'country': country,
            'available': available,
            'proportion_%': round(row['proportion'] * 100, 2),
            'target_sample': to_sample,
            'actual_sample': sampled,
            'status': status
        })
    
    # Combine all samples
    print("\nCombining samples...")
    final_sample = pd.concat(samples, ignore_index=True)
    
    # Shuffle to mix countries
    print("Shuffling...")
    final_sample = final_sample.sample(frac=1, random_state=random_seed).reset_index(drop=True)
    
    # Save sample
    print(f"\nSaving sample to {output_csv}...")
    final_sample.to_csv(output_csv, index=False)
    
    # Save statistics
    print(f"Saving statistics to {stats_csv}...")
    stats_df = pd.DataFrame(stats)
    stats_df.to_csv(stats_csv, index=False)
    
    # Final summary
    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)
    print(f"Total sampled records: {len(final_sample):,}")
    print(f"Target sample size: {total_sample_size:,}")
    print(f"Countries included: {len(samples)}")
    print(f"Sampling method: Proportional stratified")
    print(f"Output file: {output_csv}")
    print(f"Stats file: {stats_csv}")
    print("="*80)
    
    # Verify proportions
    print("\nVerifying proportions (top 10 countries):")
    sample_counts = final_sample['country'].value_counts()
    for country in country_counts.head(10).index:
        original_pct = (country_counts[country] / total_records) * 100
        sample_pct = (sample_counts.get(country, 0) / len(final_sample)) * 100
        print(f"  {country:40s}: Original {original_pct:5.2f}% → Sample {sample_pct:5.2f}%")
    
    print("="*80)
    
    return final_sample, stats_df

if __name__ == "__main__":
    here = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description="Create a proportional stratified sample.")
    parser.add_argument(
        "--input",
        default=str(here.parent.parent / "data" / "dirty-full-named.csv"),
        help="Full dirty CSV to sample from",
    )
    parser.add_argument(
        "--output",
        default=str(here / "datasets" / "stratified_sample_1000_dirty.csv"),
        help="Output sampled CSV",
    )
    parser.add_argument(
        "--stats",
        default=str(here / "datasets" / "stratified_sample_1000_stats_dirty.csv"),
        help="Output sampling statistics CSV",
    )
    args = parser.parse_args()
    create_stratified_sample(args.input, args.output, args.stats)
