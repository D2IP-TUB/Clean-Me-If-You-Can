#!/usr/bin/env python3
"""
Shared utilities for ZeroDCcorrection experiments.
Contains common functions used by both run_experiments.py and run_batch_experiments.py.
"""

import os
import re
import pandas as pd


def extract_metrics_from_output(output_path):
    """
    Extract all metrics from the output.txt file.
    This reads the metrics that were already calculated by correction.py.
    """
    output_txt_path = os.path.join(output_path, 'output.txt')
    
    if not os.path.exists(output_txt_path):
        print(f"Warning: output.txt not found in {output_path}")
        return None
    
    try:
        with open(output_txt_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Extract human_repair_num from the path or content
        human_repair_num_match = re.search(r'Human repair samples:\s*(\d+)', content)
        if human_repair_num_match:
            human_repair_num = int(human_repair_num_match.group(1))
        else:
            # Fallback: extract from path
            human_repair_num = int(os.path.basename(output_path).replace('human_repair_', ''))
        
        # Extract metrics using regex
        total_errors = int(re.search(r'Total errors in dirty data:\s*(\d+)', content).group(1))
        total_corrections = int(re.search(r'Total corrections attempted:\s*(\d+)', content).group(1))
        correct_corrections = int(re.search(r'Correct corrections:\s*(\d+)', content).group(1))
        
        # Extract precision, recall, F1
        precision_match = re.search(r'Precision:\s*([\d.]+)', content)
        precision = float(precision_match.group(1))
        
        recall_match = re.search(r'Recall:\s*([\d.]+)', content)
        recall = float(recall_match.group(1))
        
        f1_match = re.search(r'F1-Score:\s*([\d.]+)', content)
        f1 = float(f1_match.group(1))
        
        # Extract execution time
        time_match = re.search(r'Total execution time:\s*([\d.]+)\s*seconds', content)
        execution_time = float(time_match.group(1)) if time_match else 0.0
        
        # Calculate TP, FP, FN from the extracted values
        tp = correct_corrections
        fp = total_corrections - correct_corrections
        fn = total_errors - correct_corrections
        
        return {
            'human_repair_num': human_repair_num,
            'tp': tp,
            'fp': fp,
            'fn': fn,
            'total_errors': total_errors,
            'total_corrections': total_corrections,
            'precision': precision,
            'recall': recall,
            'f1': f1,
            'execution_time': execution_time
        }
    except Exception as e:
        print(f"Error extracting metrics from {output_txt_path}: {e}")
        return None


def aggregate_results(results_list, output_csv_path):
    """
    Aggregate results from multiple runs into a CSV file.
    Calculates overall metrics by summing TP/FP/FN across datasets first.
    """
    if not results_list:
        print("No results to aggregate")
        return
    
    df = pd.DataFrame(results_list)
    df = df.sort_values(['dataset', 'human_repair_num'])
    df.to_csv(output_csv_path, index=False)
    print(f"\nResults saved to: {output_csv_path}")
    
    # Print summary statistics
    print("\n" + "="*80)
    print("SUMMARY STATISTICS")
    print("="*80)
    
    # Group by human_repair_num and sum TP/FP/FN, then calculate overall metrics
    if len(df) > 0:
        grouped = df.groupby('human_repair_num').agg({
            'tp': 'sum',
            'fp': 'sum',
            'fn': 'sum',
            'total_errors': 'sum',
            'total_corrections': 'sum',
            'execution_time': 'mean'
        })
        
        # Calculate overall precision, recall, F1 from summed TP/FP/FN
        grouped['precision'] = grouped['tp'] / (grouped['tp'] + grouped['fp'])
        grouped['recall'] = grouped['tp'] / (grouped['tp'] + grouped['fn'])
        grouped['f1'] = 2 * (grouped['precision'] * grouped['recall']) / (grouped['precision'] + grouped['recall'])
        
        # Reorder columns
        grouped = grouped[['tp', 'fp', 'fn', 'total_errors', 'total_corrections', 
                          'precision', 'recall', 'f1', 'execution_time']].round(4)
        
        print("\nOverall metrics by human_repair_num (aggregated across all datasets):")
        print(grouped)
        
        # Save summary
        summary_path = output_csv_path.replace('.csv', '_summary.csv')
        grouped.to_csv(summary_path)
        print(f"\nSummary saved to: {summary_path}")


def collect_existing_results(datasets_path, results_base_path):
    """
    Collect results from existing experiment runs.
    Returns a list of result dictionaries.
    """
    # Get all datasets
    datasets = [d for d in os.listdir(datasets_path) 
                if os.path.isdir(os.path.join(datasets_path, d))]
    datasets.sort()
    
    all_results = []
    
    for dataset_name in datasets:
        dataset_results_path = os.path.join(results_base_path, dataset_name)
        
        if not os.path.exists(dataset_results_path):
            continue
        
        # Find all human_repair_num directories
        for dir_name in os.listdir(dataset_results_path):
            if dir_name.startswith('human_repair_'):
                try:
                    output_path = os.path.join(dataset_results_path, dir_name)
                    corrected_path = os.path.join(output_path, 'corrections.csv')
                    
                    if os.path.exists(corrected_path):
                        metrics = extract_metrics_from_output(output_path)
                        
                        if metrics:
                            result = {
                                'dataset': dataset_name,
                                'human_repair_num': metrics['human_repair_num'],
                                'tp': metrics['tp'],
                                'fp': metrics['fp'],
                                'fn': metrics['fn'],
                                'total_errors': metrics['total_errors'],
                                'total_corrections': metrics['total_corrections'],
                                'precision': metrics['precision'],
                                'recall': metrics['recall'],
                                'f1': metrics['f1'],
                                'execution_time': metrics['execution_time']
                            }
                            
                            all_results.append(result)
                            print(f"Collected: {dataset_name} - human_repair_num={metrics['human_repair_num']}")
                except (ValueError, AttributeError) as e:
                    print(f"Warning: Could not process {dir_name}: {e}")
                    continue
    
    return all_results
