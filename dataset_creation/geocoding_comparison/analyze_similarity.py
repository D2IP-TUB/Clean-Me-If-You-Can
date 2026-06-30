#!/usr/bin/env python3
"""
Address Similarity Analysis

Compares ground truth addresses with Google-validated addresses using
multiple similarity metrics.
"""

import pandas as pd
import json
from pathlib import Path
from difflib import SequenceMatcher
import re


def jaccard_similarity(str1, str2):
    """
    Jaccard similarity: Size of intersection / size of union of token sets.
    
    Example:
        str1 = "102 Main Street"
        str2 = "102 Main St"
        tokens1 = {'102', 'Main', 'Street'}
        tokens2 = {'102', 'Main', 'St'}
        intersection = {'102', 'Main'} = 2
        union = {'102', 'Main', 'Street', 'St'} = 4
        jaccard = 2/4 = 0.50
    """
    tokens1 = set(str1.split())
    tokens2 = set(str2.split())
    
    if len(tokens1) == 0 and len(tokens2) == 0:
        return 1.0
    
    intersection = len(tokens1.intersection(tokens2))
    union = len(tokens1.union(tokens2))
    
    return intersection / union if union > 0 else 0.0


def levenshtein_distance(str1, str2):
    """
    Levenshtein distance: Minimum number of single-character edits.
    Returns normalized similarity (1 - distance/max_length).
    
    Example:
        str1 = "kitten"
        str2 = "sitting"
        edits needed: k→s, e→i, insert g = 3 edits
        distance = 3
        max_len = 7
        similarity = 1 - (3/7) = 0.571
    """
    if str1 == str2:
        return 1.0
    
    len1, len2 = len(str1), len(str2)
    
    if len1 == 0 or len2 == 0:
        return 0.0
    
    # Create distance matrix
    matrix = [[0] * (len2 + 1) for _ in range(len1 + 1)]
    
    # Initialize first column and row
    for i in range(len1 + 1):
        matrix[i][0] = i
    for j in range(len2 + 1):
        matrix[0][j] = j
    
    # Calculate distances
    for i in range(1, len1 + 1):
        for j in range(1, len2 + 1):
            cost = 0 if str1[i-1] == str2[j-1] else 1
            matrix[i][j] = min(
                matrix[i-1][j] + 1,      # deletion
                matrix[i][j-1] + 1,      # insertion
                matrix[i-1][j-1] + cost  # substitution
            )
    
    distance = matrix[len1][len2]
    max_len = max(len1, len2)
    
    return 1 - (distance / max_len) if max_len > 0 else 0.0


def jaro_winkler_similarity(str1, str2):
    """
    Jaro-Winkler similarity: Variant of Jaro distance with prefix bonus.
    Better for short strings with common prefixes.
    
    Example:
        str1 = "MARTHA"
        str2 = "MARHTA"
        Common characters in positions, transpositions counted
        Jaro ≈ 0.944
        Common prefix "MAR" → Winkler boost → 0.961
    """
    if str1 == str2:
        return 1.0
    
    len1, len2 = len(str1), len(str2)
    
    if len1 == 0 or len2 == 0:
        return 0.0
    
    # Maximum allowed distance for matching
    match_distance = max(len1, len2) // 2 - 1
    if match_distance < 0:
        match_distance = 0
    
    matches1 = [False] * len1
    matches2 = [False] * len2
    
    matches = 0
    transpositions = 0
    
    # Find matches
    for i in range(len1):
        start = max(0, i - match_distance)
        end = min(i + match_distance + 1, len2)
        
        for j in range(start, end):
            if matches2[j] or str1[i] != str2[j]:
                continue
            matches1[i] = matches2[j] = True
            matches += 1
            break
    
    if matches == 0:
        return 0.0
    
    # Count transpositions
    k = 0
    for i in range(len1):
        if not matches1[i]:
            continue
        while not matches2[k]:
            k += 1
        if str1[i] != str2[k]:
            transpositions += 1
        k += 1
    
    # Calculate Jaro similarity
    jaro = (matches / len1 + matches / len2 + 
            (matches - transpositions / 2) / matches) / 3
    
    # Calculate common prefix (up to 4 characters)
    prefix = 0
    for i in range(min(len1, len2, 4)):
        if str1[i] == str2[i]:
            prefix += 1
        else:
            break
    
    # Jaro-Winkler similarity
    jaro_winkler = jaro + prefix * 0.1 * (1 - jaro)
    
    return jaro_winkler


def cosine_similarity(str1, str2):
    """
    Cosine similarity: Measures angle between token frequency vectors.
    
    Example:
        str1 = "the quick brown fox"
        str2 = "the fast brown dog"
        vector1 = {the:1, quick:1, brown:1, fox:1}
        vector2 = {the:1, fast:1, brown:1, dog:1}
        dot_product = 2 (the, brown match)
        magnitude1 = sqrt(4) = 2
        magnitude2 = sqrt(4) = 2
        cosine = 2 / (2*2) = 0.50
    """
    tokens1 = str1.split()
    tokens2 = str2.split()
    
    if len(tokens1) == 0 or len(tokens2) == 0:
        return 0.0
    
    # Build frequency vectors
    all_tokens = set(tokens1 + tokens2)
    vec1 = [tokens1.count(token) for token in all_tokens]
    vec2 = [tokens2.count(token) for token in all_tokens]
    
    # Calculate dot product
    dot_product = sum(v1 * v2 for v1, v2 in zip(vec1, vec2))
    
    # Calculate magnitudes
    magnitude1 = sum(v ** 2 for v in vec1) ** 0.5
    magnitude2 = sum(v ** 2 for v in vec2) ** 0.5
    
    if magnitude1 == 0 or magnitude2 == 0:
        return 0.0
    
    return dot_product / (magnitude1 * magnitude2)


def sequence_matcher_ratio(str1, str2):
    """
    SequenceMatcher ratio: Python's difflib ratio based on longest matching subsequence.
    
    Example:
        str1 = "abcd"
        str2 = "abxd"
        Matching characters: a, b, d = 3
        Total characters: 8
        ratio = 2 * 3 / 8 = 0.75
    """
    return SequenceMatcher(None, str1, str2).ratio()


def calculate_all_similarities(str1, str2):
    """Calculate all similarity metrics between two strings."""
    return {
        'jaccard': jaccard_similarity(str1, str2),
        'levenshtein': levenshtein_distance(str1, str2),
        'jaro_winkler': jaro_winkler_similarity(str1, str2),
        'cosine': cosine_similarity(str1, str2),
        'sequence_matcher': sequence_matcher_ratio(str1, str2)
    }


def combine_address_components(row):
    """
    Combine address components into a single string (no commas, just spaces).
    Format: house_number road locality postcode country
    """
    components = []
    
    # Add each component if it exists and is not NaN
    for field in ['house_number', 'road', 'locality', 'postcode', 'country']:
        value = row.get(field, '')
        if pd.notna(value) and str(value).strip():
            components.append(str(value).strip())
    
    return ' '.join(components)


def analyze_similarity(run_folder, dataset_file):
    """
    Analyze similarity between ground truth and Google-validated addresses.
    
    Args:
        run_folder: Path to validation run folder
        dataset_file: Path to original dataset CSV
    """
    
    print("="*80)
    print("ADDRESS SIMILARITY ANALYSIS")
    print("="*80)
    print(f"Run folder: {run_folder}")
    print(f"Dataset: {dataset_file}")
    print("="*80)
    
    # Load dataset
    print("\nLoading dataset...")
    dataset_df = pd.read_csv(dataset_file)
    print(f"Dataset records: {len(dataset_df):,}")
    
    # Load validation results
    validation_csv = Path(run_folder) / 'validated.csv'
    print(f"\nLoading validation results...")
    validation_df = pd.read_csv(validation_csv)
    print(f"Validation records: {len(validation_df):,}")
    
    # Merge on ID
    print("\nMerging datasets...")
    merged = validation_df.merge(dataset_df, left_on='id', right_on='_id', how='inner')
    print(f"Merged records: {len(merged):,}")
    
    # Filter: only VALID and INVALID (skip ERROR)
    print("\nFiltering records...")
    filtered = merged[merged['status'].isin(['VALID', 'INVALID'])].copy()
    print(f"VALID + INVALID records: {len(filtered):,}")
    print(f"  VALID: {len(filtered[filtered['status'] == 'VALID']):,}")
    print(f"  INVALID: {len(filtered[filtered['status'] == 'INVALID']):,}")
    
    # Combine ground truth address components
    print("\nCombining ground truth address components...")
    filtered['ground_truth'] = filtered.apply(combine_address_components, axis=1)
    
    # Use formatted_address from Google (remove commas for fair comparison)
    filtered['google_address'] = filtered['formatted_address'].fillna('').str.replace(',', '', regex=False)
    
    print("\nSample addresses:")
    for idx in range(min(3, len(filtered))):
        row = filtered.iloc[idx]
        print(f"\n  [{row['id']}] {row['name_x']}")
        print(f"    Ground Truth: {row['ground_truth']}")
        print(f"    Google:       {row['google_address']}")
    
    # Calculate similarities
    print("\n" + "="*80)
    print("CALCULATING SIMILARITIES...")
    print("="*80)
    
    results = []
    
    for idx, row in filtered.iterrows():
        gt = row['ground_truth']
        google = row['google_address']
        
        # Full address similarity
        full_sim = calculate_all_similarities(gt, google)
        
        # Individual component similarities
        component_sims = {}
        components = ['house_number', 'road', 'locality', 'postcode', 'country']
        
        for comp in components:
            gt_comp = str(row.get(comp, '')).strip() if pd.notna(row.get(comp)) else ''
            
            # Extract from Google's formatted address (best effort)
            # For individual components, we'll use the original ground truth vs formatted
            # Since Google doesn't return individual components separately in our data
            google_comp = google  # We'll use the full address for now
            
            if gt_comp:
                component_sims[f'{comp}_jaccard'] = jaccard_similarity(gt_comp, google_comp)
                component_sims[f'{comp}_levenshtein'] = levenshtein_distance(gt_comp, google_comp)
        
        result = {
            'id': row['id'],
            'name': row['name_x'],
            'status': row['status'],
            'country': row['country'],
            'ground_truth': gt,
            'google_address': google,
            # Full address similarities
            'jaccard': full_sim['jaccard'],
            'levenshtein': full_sim['levenshtein'],
            'jaro_winkler': full_sim['jaro_winkler'],
            'cosine': full_sim['cosine'],
            'sequence_matcher': full_sim['sequence_matcher'],
        }
        
        # Add component similarities
        result.update(component_sims)
        
        results.append(result)
        
        if (idx + 1) % 100 == 0:
            print(f"  Processed {idx + 1}/{len(filtered)} records...")
    
    print(f"✅ Completed {len(results)} records")
    
    # Create results DataFrame
    results_df = pd.DataFrame(results)
    
    # Save detailed results
    output_file = Path(run_folder) / 'similarity_analysis.csv'
    results_df.to_csv(output_file, index=False)
    print(f"\n✅ Detailed results saved to: {output_file}")
    
    # Calculate statistics
    print("\n" + "="*80)
    print("SIMILARITY STATISTICS")
    print("="*80)
    
    metrics = ['jaccard', 'levenshtein', 'jaro_winkler', 'cosine', 'sequence_matcher']
    
    print(f"\n{'Metric':<20} {'Mean':<8} {'Median':<8} {'Min':<8} {'Max':<8} {'Std':<8}")
    print("-" * 80)
    
    stats = {}
    for metric in metrics:
        mean_val = results_df[metric].mean()
        median_val = results_df[metric].median()
        min_val = results_df[metric].min()
        max_val = results_df[metric].max()
        std_val = results_df[metric].std()
        
        print(f"{metric:<20} {mean_val:<8.3f} {median_val:<8.3f} {min_val:<8.3f} {max_val:<8.3f} {std_val:<8.3f}")
        
        stats[metric] = {
            'mean': mean_val,
            'median': median_val,
            'min': min_val,
            'max': max_val,
            'std': std_val
        }
    
    # By status
    print("\n" + "="*80)
    print("SIMILARITY BY STATUS")
    print("="*80)
    
    for status in ['VALID', 'INVALID']:
        status_df = results_df[results_df['status'] == status]
        if len(status_df) == 0:
            continue
            
        print(f"\n{status} ({len(status_df)} records):")
        print(f"{'Metric':<20} {'Mean':<8} {'Median':<8}")
        print("-" * 40)
        
        for metric in metrics:
            mean_val = status_df[metric].mean()
            median_val = status_df[metric].median()
            print(f"{metric:<20} {mean_val:<8.3f} {median_val:<8.3f}")
    
    # Save summary statistics
    stats_output = Path(run_folder) / 'similarity_statistics.json'
    with open(stats_output, 'w') as f:
        json.dump(stats, f, indent=2)
    print(f"\n✅ Statistics saved to: {stats_output}")
    
    print("\n" + "="*80)
    
    return results_df, stats


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 2:
        run_folder = sys.argv[1]
        dataset_file = sys.argv[2]
    else:
        run_folder = "output/run_20251202_171627_clean_1000_stratified"
        dataset_file = "../datasets/stratified_sample_~1000.csv"
    
    results, stats = analyze_similarity(run_folder, dataset_file)
