#!/usr/bin/env python3
"""
Stratified Sampling from Dataset

Creates a stratified sample of addresses from the top 20 countries.
Samples 50 records from each country for a total of 1,000 addresses.
"""

import pandas as pd
import numpy as np
from pathlib import Path


# Top 20 countries (from the distribution analysis)
TOP_20_COUNTRIES = [
    "United States",
    "Deutschland",
    "Nederland",
    "United Kingdom",
    "France",
    "Italia",
    "Canada",
    "Österreich",
    "España",
    "Polska",
    "Schweiz/Suisse/Svizzera/Svizra",
    "Australia",
    "België / Belgique / Belgien",
    "Sverige",
    "Россия",
    "Brasil",
    "Suomi / Finland",
    "Magyarország",
    "Portugal",
    "New Zealand / Aotearoa"
]


def create_stratified_sample(
    input_csv: str,
    output_csv: str,
    countries: list,
    sample_per_country: int = 50,
    random_seed: int = 42
):
    """
    Create a stratified sample from the dataset.
    
    Args:
        input_csv: Path to the full dataset
        output_csv: Path to save the sampled data
        countries: List of country names to sample from
        sample_per_country: Number of records to sample per country
        random_seed: Random seed for reproducibility
    """
    
    print("="*80)
    print("STRATIFIED SAMPLING")
    print("="*80)
    print(f"Input:  {input_csv}")
    print(f"Output: {output_csv}")
    print(f"Sample size: {sample_per_country} per country")
    print(f"Countries: {len(countries)}")
    print(f"Total expected: {sample_per_country * len(countries)} records")
    print("="*80 + "\n")
    
    # Set random seed for reproducibility
    np.random.seed(random_seed)
    
    # Read the full dataset
    print("📖 Reading dataset...")
    df = pd.read_csv(input_csv)
    print(f"✓ Loaded {len(df):,} total records\n")
    
    # Display country column info
    print(f"Country column: 'country'")
    print(f"Unique countries in data: {df['country'].nunique()}\n")
    
    # Sample from each country
    sampled_data = []
    stats = []
    
    print("🎲 Sampling from each country...\n")
    
    for country in countries:
        # Filter data for this country
        country_data = df[df['country'] == country]
        available = len(country_data)
        
        if available == 0:
            print(f"  ⚠️  {country:<40} - Not found in dataset!")
            stats.append({
                'country': country,
                'available': 0,
                'sampled': 0,
                'status': 'NOT_FOUND'
            })
            continue
        
        # Sample (or take all if less than sample_per_country)
        sample_size = min(sample_per_country, available)
        sample = country_data.sample(n=sample_size, random_state=random_seed)
        sampled_data.append(sample)
        
        # Status
        if sample_size < sample_per_country:
            status = f"⚠️  {country:<40} - Sampled {sample_size:3d} (only {available:,} available)"
            stats.append({
                'country': country,
                'available': available,
                'sampled': sample_size,
                'status': 'PARTIAL'
            })
        else:
            status = f"✅ {country:<40} - Sampled {sample_size:3d} (from {available:,})"
            stats.append({
                'country': country,
                'available': available,
                'sampled': sample_size,
                'status': 'COMPLETE'
            })
        
        print(f"  {status}")
    
    # Combine all samples
    if not sampled_data:
        print("\n❌ No data sampled! Check country names.")
        return
    
    final_sample = pd.concat(sampled_data, ignore_index=True)
    
    # Shuffle the final sample
    final_sample = final_sample.sample(frac=1, random_state=random_seed).reset_index(drop=True)
    
    # Save to CSV
    print(f"\n💾 Saving sample to {output_csv}...")
    final_sample.to_csv(output_csv, index=False)
    
    # Print summary
    stats_df = pd.DataFrame(stats)
    total_sampled = stats_df['sampled'].sum()
    complete_count = (stats_df['status'] == 'COMPLETE').sum()
    partial_count = (stats_df['status'] == 'PARTIAL').sum()
    not_found_count = (stats_df['status'] == 'NOT_FOUND').sum()
    
    print("\n" + "="*80)
    print("SAMPLING SUMMARY")
    print("="*80)
    print(f"Total records sampled:    {total_sampled:,}")
    print(f"Target per country:       {sample_per_country}")
    print(f"Countries processed:      {len(countries)}")
    print(f"  ✅ Complete:            {complete_count} ({complete_count/len(countries)*100:.1f}%)")
    print(f"  ⚠️  Partial:             {partial_count} ({partial_count/len(countries)*100:.1f}%)")
    print(f"  ❌ Not found:           {not_found_count} ({not_found_count/len(countries)*100:.1f}%)")
    print(f"\nOutput file: {output_csv}")
    print(f"Output records: {len(final_sample):,}")
    print("="*80 + "\n")
    
    # Display column info
    print("Output columns:")
    for col in final_sample.columns:
        print(f"  • {col}")
    
    print(f"\n✅ Stratified sample created successfully!\n")
    
    return final_sample, stats_df


def main():
    """Main function."""
    
    # Paths
    input_csv = "../datasets/clean-full-named.csv"
    output_csv = "../datasets/stratified_sample_top20.csv"
    
    # Check if input exists
    if not Path(input_csv).exists():
        print(f"❌ Error: Input file not found: {input_csv}")
        print("Please adjust the path in the script.")
        return
    
    # Create sample
    sample_df, stats_df = create_stratified_sample(
        input_csv=input_csv,
        output_csv=output_csv,
        countries=TOP_20_COUNTRIES,
        sample_per_country=50,
        random_seed=42  # For reproducibility
    )
    
    # Save statistics
    stats_csv = "../datasets/stratified_sample_stats.csv"
    print(f"💾 Saving sampling statistics to {stats_csv}...")
    stats_df.to_csv(stats_csv, index=False)
    print(f"✓ Statistics saved\n")
    
    # Display first few records
    print("Sample preview (first 10 records):")
    print("="*80)
    print(sample_df[['_id', 'name', 'country', 'locality']].head(10).to_string(index=False))
    print("="*80 + "\n")


if __name__ == "__main__":
    main()
