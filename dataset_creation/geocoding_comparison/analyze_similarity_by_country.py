#!/usr/bin/env python3
"""
Analyze similarity scores by country.

This script calculates average similarity metrics per country for both
clean and dirty datasets.
"""

import pandas as pd
from pathlib import Path
import json


def analyze_by_country(clean_run, clean_dataset, dirty_run, dirty_dataset):
    """
    Analyze similarity scores by country for clean and dirty datasets.
    
    Args:
        clean_run: Path to clean validation run folder
        clean_dataset: Path to clean dataset CSV
        dirty_run: Path to dirty validation run folder
        dirty_dataset: Path to dirty dataset CSV
    """
    
    print("="*80)
    print("SIMILARITY ANALYSIS BY COUNTRY")
    print("="*80)
    
    # Load clean similarity results
    print("\n1. Loading clean similarity results...")
    clean_sim_file = Path(clean_run) / 'similarity_analysis.csv'
    clean_sim_df = pd.read_csv(clean_sim_file)
    print(f"   Clean records: {len(clean_sim_df):,}")
    print(f"   Countries found: {clean_sim_df['country'].nunique()}")
    
    # Load dirty similarity results
    print("\n2. Loading dirty similarity results...")
    dirty_sim_file = Path(dirty_run) / 'similarity_analysis.csv'
    dirty_sim_df = pd.read_csv(dirty_sim_file)
    print(f"   Dirty records: {len(dirty_sim_df):,}")
    
    # Use clean country mapping for dirty data (map by ID)
    print("\n3. Mapping countries from clean to dirty dataset...")
    id_to_country = clean_sim_df.set_index('id')['country'].to_dict()
    dirty_sim_df['country'] = dirty_sim_df['id'].map(id_to_country)
    print(f"   Countries mapped: {dirty_sim_df['country'].notna().sum():,}")
    
    # Calculate statistics by country
    print("\n4. Calculating statistics by country...")
    
    metrics = ['jaccard', 'levenshtein', 'jaro_winkler', 'cosine', 'sequence_matcher']
    
    # Clean dataset stats by country
    clean_country_stats = []
    for country in sorted(clean_sim_df['country'].dropna().unique()):
        country_df = clean_sim_df[clean_sim_df['country'] == country]
        
        stats = {
            'country': country,
            'dataset': 'clean',
            'count': len(country_df),
            'valid_count': len(country_df[country_df['status'] == 'VALID']),
            'invalid_count': len(country_df[country_df['status'] == 'INVALID']),
        }
        
        for metric in metrics:
            stats[f'{metric}_mean'] = country_df[metric].mean()
            stats[f'{metric}_median'] = country_df[metric].median()
            stats[f'{metric}_std'] = country_df[metric].std()
        
        clean_country_stats.append(stats)
    
    # Dirty dataset stats by country
    dirty_country_stats = []
    for country in sorted(dirty_sim_df['country'].dropna().unique()):
        country_df = dirty_sim_df[dirty_sim_df['country'] == country]
        
        stats = {
            'country': country,
            'dataset': 'dirty',
            'count': len(country_df),
            'valid_count': len(country_df[country_df['status'] == 'VALID']),
            'invalid_count': len(country_df[country_df['status'] == 'INVALID']),
        }
        
        for metric in metrics:
            stats[f'{metric}_mean'] = country_df[metric].mean()
            stats[f'{metric}_median'] = country_df[metric].median()
            stats[f'{metric}_std'] = country_df[metric].std()
        
        dirty_country_stats.append(stats)
    
    # Create DataFrames
    clean_stats_df = pd.DataFrame(clean_country_stats)
    dirty_stats_df = pd.DataFrame(dirty_country_stats)
    
    # Combine for comparison
    combined_df = pd.concat([clean_stats_df, dirty_stats_df], ignore_index=True)
    
    # Save detailed results
    output_file = Path(clean_run).parent.parent / 'similarity_by_country.csv'
    combined_df.to_csv(output_file, index=False)
    print(f"\n✅ Detailed results saved to: {output_file}")
    
    # Display summary
    print("\n" + "="*80)
    print("CLEAN DATASET - SIMILARITY BY COUNTRY")
    print("="*80)
    print(f"\n{'Country':<40} {'Count':>6} {'Jaccard':>8} {'Leven.':>8} {'Jaro-W':>8} {'Cosine':>8} {'SeqMat':>8}")
    print("-" * 110)
    
    for _, row in clean_stats_df.sort_values('sequence_matcher_mean', ascending=False).iterrows():
        print(f"{row['country']:<40} {int(row['count']):>6} "
              f"{row['jaccard_mean']:>8.3f} {row['levenshtein_mean']:>8.3f} "
              f"{row['jaro_winkler_mean']:>8.3f} {row['cosine_mean']:>8.3f} "
              f"{row['sequence_matcher_mean']:>8.3f}")
    
    print("\n" + "="*80)
    print("DIRTY DATASET - SIMILARITY BY COUNTRY")
    print("="*80)
    print(f"\n{'Country':<40} {'Count':>6} {'Jaccard':>8} {'Leven.':>8} {'Jaro-W':>8} {'Cosine':>8} {'SeqMat':>8}")
    print("-" * 110)
    
    for _, row in dirty_stats_df.sort_values('sequence_matcher_mean', ascending=False).iterrows():
        print(f"{row['country']:<40} {int(row['count']):>6} "
              f"{row['jaccard_mean']:>8.3f} {row['levenshtein_mean']:>8.3f} "
              f"{row['jaro_winkler_mean']:>8.3f} {row['cosine_mean']:>8.3f} "
              f"{row['sequence_matcher_mean']:>8.3f}")
    
    # Comparison by country
    print("\n" + "="*80)
    print("CLEAN vs DIRTY COMPARISON BY COUNTRY")
    print("="*80)
    print(f"\n{'Country':<40} {'Clean SeqMat':>12} {'Dirty SeqMat':>12} {'Difference':>12}")
    print("-" * 80)
    
    comparison = []
    for country in sorted(clean_stats_df['country'].unique()):
        clean_row = clean_stats_df[clean_stats_df['country'] == country].iloc[0]
        dirty_row = dirty_stats_df[dirty_stats_df['country'] == country]
        
        if len(dirty_row) > 0:
            dirty_row = dirty_row.iloc[0]
            diff = dirty_row['sequence_matcher_mean'] - clean_row['sequence_matcher_mean']
            diff_pct = (diff / clean_row['sequence_matcher_mean']) * 100
            
            comparison.append({
                'country': country,
                'clean_seq': clean_row['sequence_matcher_mean'],
                'dirty_seq': dirty_row['sequence_matcher_mean'],
                'diff': diff,
                'diff_pct': diff_pct
            })
            
            print(f"{country:<40} {clean_row['sequence_matcher_mean']:>12.3f} "
                  f"{dirty_row['sequence_matcher_mean']:>12.3f} {diff:>11.3f} ({diff_pct:+.1f}%)")
    
    comparison_df = pd.DataFrame(comparison)
    
    # Top and bottom performers
    print("\n" + "="*80)
    print("TOP 5 COUNTRIES - HIGHEST SIMILARITY (Clean Dataset)")
    print("="*80)
    
    top_clean = clean_stats_df.nlargest(5, 'sequence_matcher_mean')
    for _, row in top_clean.iterrows():
        print(f"  {row['country']:<40} Sequence Matcher: {row['sequence_matcher_mean']:.3f}")
    
    print("\n" + "="*80)
    print("BOTTOM 5 COUNTRIES - LOWEST SIMILARITY (Clean Dataset)")
    print("="*80)
    
    bottom_clean = clean_stats_df.nsmallest(5, 'sequence_matcher_mean')
    for _, row in bottom_clean.iterrows():
        print(f"  {row['country']:<40} Sequence Matcher: {row['sequence_matcher_mean']:.3f}")
    
    print("\n" + "="*80)
    print("BIGGEST QUALITY DROPS (Clean → Dirty)")
    print("="*80)
    
    biggest_drops = comparison_df.nsmallest(5, 'diff')
    for _, row in biggest_drops.iterrows():
        print(f"  {row['country']:<40} {row['diff']:+.3f} ({row['diff_pct']:+.1f}%)")
    
    print("\n" + "="*80)
    print("BIGGEST QUALITY IMPROVEMENTS (Clean → Dirty)")
    print("="*80)
    
    biggest_gains = comparison_df.nlargest(5, 'diff')
    for _, row in biggest_gains.iterrows():
        print(f"  {row['country']:<40} {row['diff']:+.3f} ({row['diff_pct']:+.1f}%)")
    
    # Save comparison
    comparison_file = Path(clean_run).parent.parent / 'similarity_comparison_by_country.csv'
    comparison_df.to_csv(comparison_file, index=False)
    print(f"\n✅ Comparison saved to: {comparison_file}")
    
    print("\n" + "="*80)
    
    return clean_stats_df, dirty_stats_df, comparison_df


if __name__ == "__main__":
    clean_run = "output/run_20251202_171627_clean_1000_stratified"
    clean_dataset = "../datasets/stratified_sample_~1000.csv"
    dirty_run = "output/run_20251202_180424_dirty_1000_stratified"
    dirty_dataset = "../datasets/stratified_sample_~1000-dirty.csv"
    
    clean_stats, dirty_stats, comparison = analyze_by_country(
        clean_run, clean_dataset, dirty_run, dirty_dataset
    )
