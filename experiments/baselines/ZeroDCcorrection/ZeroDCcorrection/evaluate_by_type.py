#!/usr/bin/env python3
"""
Evaluate ZeroDCcorrection results grouped by error type (FD, NO, Typo).
- For isolated/disjoint/maximal datasets: error type from folder name
- For flattened_partial datasets: read lineage.csv and evaluate per-row

Outputs separate per-type results for each subdirectory in Final_Datasets.
"""
from pathlib import Path
import html
import os
import re
import sys
import csv
import argparse
from collections import defaultdict
import pandas as pd


def value_normalizer(value):
    """Minimal normalization matching count_errors.py."""
    value = html.unescape(value)
    value = re.sub("[\t\n ]+", " ", value, re.UNICODE)
    value = value.strip("\t\n ")
    return value


def read_csv(path):
    df = pd.read_csv(path, dtype=str, encoding='utf-8', keep_default_na=False)
    return df.map(value_normalizer)


def get_error_type_from_folder(table_dir):
    """Get error type from folder name suffix (e.g., __FD, __NO, __Typo)."""
    folder_name = os.path.basename(table_dir)

    if folder_name.endswith('__FD'):
        return 'FD'
    elif folder_name.endswith('__NO'):
        return 'NO'
    elif folder_name.endswith('__Typo'):
        return 'TYPO'

    if '__FD' in folder_name or '_FD_' in folder_name:
        return 'FD'
    if '__NO' in folder_name or '_NO_' in folder_name:
        return 'NO'
    if '__Typo' in folder_name or '_Typo_' in folder_name:
        return 'TYPO'

    return 'UNKNOWN'


def load_lineage(table_dir):
    """Load lineage.csv and return a dict mapping row_idx -> source_variant."""
    lineage_path = os.path.join(table_dir, 'lineage.csv')
    if not os.path.exists(lineage_path):
        return None

    row_to_type = {}
    with open(lineage_path, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            row_idx = int(row['row_idx'])
            variant = row.get('source_variant', '').strip().upper()
            if variant in ('FD', 'NO', 'TYPO'):
                row_to_type[row_idx] = variant
            else:
                row_to_type[row_idx] = 'UNKNOWN'
    return row_to_type


def evaluate_table_by_type(dataset_dir, repaired_path):
    """
    Evaluate a table and return per-error-type metrics.

    Args:
        dataset_dir: directory containing dirty.csv, clean.csv, lineage.csv
        repaired_path: path to the corrections.csv produced by ZeroDCcorrection

    Returns dict like:
        {
            'FD': {'tp': ..., 'tpfp': ..., 'tpfn': ...},
            'NO': {...},
            'TYPO': {...}
        }
    """
    dirty_path = os.path.join(dataset_dir, 'dirty.csv')
    clean_path = os.path.join(dataset_dir, 'clean.csv')

    dirty_df = read_csv(dirty_path)
    clean_df = read_csv(clean_path)

    dirty_df.columns = clean_df.columns

    has_repairs = repaired_path is not None and os.path.exists(repaired_path)
    if has_repairs:
        repaired_df = read_csv(repaired_path)
        if '_tid_' in repaired_df.columns:
            repaired_df = repaired_df.drop(columns=['_tid_'])
        repaired_df.columns = clean_df.columns

        if len(dirty_df) != len(repaired_df):
            print(f"  Warning: Row count mismatch in {os.path.basename(dataset_dir)}: "
                  f"dirty={len(dirty_df)}, repaired={len(repaired_df)}")
            min_rows = min(len(dirty_df), len(clean_df), len(repaired_df))
            dirty_df = dirty_df.iloc[:min_rows].reset_index(drop=True)
            clean_df = clean_df.iloc[:min_rows].reset_index(drop=True)
            repaired_df = repaired_df.iloc[:min_rows].reset_index(drop=True)

    row_to_type = load_lineage(dataset_dir)

    if row_to_type is None:
        folder_type = get_error_type_from_folder(dataset_dir)
        row_to_type = {i: folder_type for i in range(len(dirty_df))}

    error_mask = dirty_df.values != clean_df.values

    if has_repairs:
        correction_mask = dirty_df.values != repaired_df.values
        tp_mask = correction_mask & (repaired_df.values == clean_df.values)
    else:
        correction_mask = None
        tp_mask = None

    type_metrics = defaultdict(lambda: {'tp': 0, 'tpfp': 0, 'tpfn': 0})

    for i in range(len(dirty_df)):
        etype = row_to_type.get(i, 'UNKNOWN')
        row_errors = int(error_mask[i].sum())
        if row_errors:
            type_metrics[etype]['tpfn'] += row_errors
        if has_repairs:
            row_corrections = int(correction_mask[i].sum())
            row_tp = int(tp_mask[i].sum())
            if row_corrections:
                type_metrics[etype]['tpfp'] += row_corrections
                type_metrics[etype]['tp'] += row_tp

    return dict(type_metrics)


def compute_metrics(tp, tpfp, tpfn):
    precision = tp / tpfp if tpfp > 0 else -1
    recall = tp / tpfn if tpfn > 0 else -1
    f1 = (2 * precision * recall) / (precision + recall) if (precision + recall) > 0 else -1
    return precision, recall, f1


RESULTS_TO_DATASETS_NAME_MAP = {
    'flatted_partitioned_base': 'flattened_partitioned_base',
}


def find_tables(dataset_root, results_root, human_repair_num):
    """
    Yield (subdir_name, dataset_dir, repaired_path_or_None) for EVERY dataset
    table that exists, regardless of whether corrections exist.

    ZeroDCcorrection layout:
        dataset:  <dataset_root>/<subdir>/<table>/  (dirty.csv, clean.csv, lineage.csv)
        result:   <results_root>/<subdir>/<table>/human_repair_<N>/corrections.csv
    """
    for results_subdir in sorted(os.listdir(results_root)):
        subdir_results = os.path.join(results_root, results_subdir)
        if not os.path.isdir(subdir_results):
            continue

        dataset_subdir = RESULTS_TO_DATASETS_NAME_MAP.get(results_subdir, results_subdir)
        subdir_datasets = os.path.join(dataset_root, dataset_subdir)
        if not os.path.isdir(subdir_datasets):
            continue

        for table in sorted(os.listdir(subdir_datasets)):
            dataset_dir = os.path.join(subdir_datasets, table)
            if not os.path.isdir(dataset_dir):
                continue
            if (not os.path.exists(os.path.join(dataset_dir, 'dirty.csv')) or
                not os.path.exists(os.path.join(dataset_dir, 'clean.csv'))):
                continue

            hr_dir = os.path.join(subdir_results, table,
                                  f'human_repair_{human_repair_num}')
            repaired_path = os.path.join(hr_dir, 'corrections.csv')
            if not os.path.exists(repaired_path):
                repaired_path = None

            yield results_subdir, dataset_dir, repaired_path


def main():
    parser = argparse.ArgumentParser(
        description='Evaluate ZeroDCcorrection results grouped by error type (FD, NO, Typo).'
    )
    parser.add_argument(
        '--dataset_root',
        default=str(Path(__file__).resolve().parents[3] / 'datasets' / 'unionable_tables' / 'union_datasets_used_in_exp'),
        help='Root directory containing datasets (Final_Datasets)'
    )
    parser.add_argument(
        '--results_root',
        default=str(Path(__file__).resolve().parents[3] / 'results' / 'zerodccorrection'),
        help='Root directory containing ZeroDCcorrection results'
    )
    parser.add_argument(
        '--human_repair_num',
        type=int,
        default=10,
        help='Which human_repair_N subdirectory to evaluate'
    )
    parser.add_argument(
        '--output_dir',
        default=str(Path(__file__).resolve().parent),
        help='Directory to save output files'
    )
    args = parser.parse_args()

    if not os.path.isdir(args.dataset_root):
        print(f"Error: Dataset root '{args.dataset_root}' not found.")
        sys.exit(1)
    if not os.path.isdir(args.results_root):
        print(f"Error: Results root '{args.results_root}' not found.")
        sys.exit(1)

    os.makedirs(args.output_dir, exist_ok=True)

    # Group by subdir (scenario)
    subdir_tables = defaultdict(list)
    for subdir, dataset_dir, repaired_path in find_tables(
        args.dataset_root, args.results_root, args.human_repair_num
    ):
        subdir_tables[subdir].append((dataset_dir, repaired_path))

    all_overall_results = []
    lake_type_totals = defaultdict(lambda: {'tp': 0, 'tpfp': 0, 'tpfn': 0})

    for subdir in sorted(subdir_tables.keys()):
        tables = subdir_tables[subdir]
        print(f"\n{'='*60}")
        print(f"Processing: {subdir}")
        print(f"{'='*60}")

        subdir_type_totals = defaultdict(lambda: {'tp': 0, 'tpfp': 0, 'tpfn': 0})
        table_count = 0

        for dataset_dir, repaired_path in tables:
            try:
                type_metrics = evaluate_table_by_type(dataset_dir, repaired_path)
                if not type_metrics:
                    continue

                table_count += 1
                for error_type, counts in type_metrics.items():
                    subdir_type_totals[error_type]['tp'] += counts['tp']
                    subdir_type_totals[error_type]['tpfp'] += counts['tpfp']
                    subdir_type_totals[error_type]['tpfn'] += counts['tpfn']

            except Exception as e:
                print(f"  Error processing {dataset_dir}: {e}")

        print(f"  Processed {table_count} tables")

        aggregate_rows = []
        total_tp = 0
        total_tpfp = 0
        total_tpfn = 0

        for error_type in sorted(subdir_type_totals.keys()):
            counts = subdir_type_totals[error_type]
            tp, tpfp, tpfn = counts['tp'], counts['tpfp'], counts['tpfn']
            precision, recall, f1 = compute_metrics(tp, tpfp, tpfn)

            total_tp += tp
            total_tpfp += tpfp
            total_tpfn += tpfn

            lake_type_totals[error_type]['tp']   += tp
            lake_type_totals[error_type]['tpfp'] += tpfp
            lake_type_totals[error_type]['tpfn'] += tpfn

            print(f"  {error_type}: P={precision:.4f}, R={recall:.4f}, F1={f1:.4f} "
                  f"(TP={tp}, TP+FP={tpfp}, TP+FN={tpfn})")

            aggregate_rows.append({
                'error_type': error_type,
                'tp': tp, 'tpfp': tpfp, 'tpfn': tpfn,
                'precision': precision, 'recall': recall, 'f1': f1
            })

        overall_precision, overall_recall, overall_f1 = compute_metrics(
            total_tp, total_tpfp, total_tpfn
        )
        print(f"  OVERALL: P={overall_precision:.4f}, R={overall_recall:.4f}, "
              f"F1={overall_f1:.4f}")

        aggregate_rows.append({
            'error_type': 'OVERALL',
            'tp': total_tp, 'tpfp': total_tpfp, 'tpfn': total_tpfn,
            'precision': overall_precision, 'recall': overall_recall,
            'f1': overall_f1
        })

        output_csv = os.path.join(
            args.output_dir,
            f'zerodccorrection_by_type_{subdir}_hr{args.human_repair_num}.csv'
        )
        with open(output_csv, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=[
                'error_type', 'tp', 'tpfp', 'tpfn', 'precision', 'recall', 'f1'
            ])
            writer.writeheader()
            writer.writerows(aggregate_rows)
        print(f"  Saved: {output_csv}")

        all_overall_results.append({
            'dataset': subdir,
            'tables': table_count,
            'tp': total_tp, 'tpfp': total_tpfp, 'tpfn': total_tpfn,
            'precision': overall_precision, 'recall': overall_recall,
            'f1': overall_f1
        })

    # Overall summary
    summary_csv = os.path.join(
        args.output_dir,
        f'zerodccorrection_by_type_summary_hr{args.human_repair_num}.csv'
    )
    acc_tp   = sum(r['tp']   for r in all_overall_results)
    acc_tpfp = sum(r['tpfp'] for r in all_overall_results)
    acc_tpfn = sum(r['tpfn'] for r in all_overall_results)
    acc_p, acc_r, acc_f1 = compute_metrics(acc_tp, acc_tpfp, acc_tpfn)
    all_overall_results.append({
        'dataset': 'ACCUMULATIVE',
        'tables': sum(r['tables'] for r in all_overall_results),
        'tp': acc_tp, 'tpfp': acc_tpfp, 'tpfn': acc_tpfn,
        'precision': acc_p, 'recall': acc_r, 'f1': acc_f1
    })
    with open(summary_csv, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=[
            'dataset', 'tables', 'tp', 'tpfp', 'tpfn',
            'precision', 'recall', 'f1'
        ])
        writer.writeheader()
        writer.writerows(all_overall_results)
    print(f"\n\nOverall summary saved to: {summary_csv}")

    # Accumulative by error type across ALL datasets
    print(f"\n=== ACCUMULATIVE SCORES BY ERROR TYPE (all datasets, "
          f"human_repair={args.human_repair_num}) ===")
    lake_type_rows = []
    lake_total_tp = lake_total_tpfp = lake_total_tpfn = 0
    for error_type in sorted(lake_type_totals.keys()):
        counts = lake_type_totals[error_type]
        tp, tpfp, tpfn = counts['tp'], counts['tpfp'], counts['tpfn']
        precision, recall, f1 = compute_metrics(tp, tpfp, tpfn)
        print(f"  {error_type}: P={precision:.4f}, R={recall:.4f}, F1={f1:.4f} "
              f"(TP={tp}, TP+FP={tpfp}, TP+FN={tpfn})")
        lake_type_rows.append({
            'error_type': error_type,
            'tp': tp, 'tpfp': tpfp, 'tpfn': tpfn,
            'precision': precision, 'recall': recall, 'f1': f1
        })
        lake_total_tp   += tp
        lake_total_tpfp += tpfp
        lake_total_tpfn += tpfn

    overall_p, overall_r, overall_f1 = compute_metrics(
        lake_total_tp, lake_total_tpfp, lake_total_tpfn
    )
    print(f"  OVERALL: P={overall_p:.4f}, R={overall_r:.4f}, F1={overall_f1:.4f} "
          f"(TP={lake_total_tp}, TP+FP={lake_total_tpfp}, TP+FN={lake_total_tpfn})")
    lake_type_rows.append({
        'error_type': 'OVERALL',
        'tp': lake_total_tp, 'tpfp': lake_total_tpfp, 'tpfn': lake_total_tpfn,
        'precision': overall_p, 'recall': overall_r, 'f1': overall_f1
    })

    lake_type_csv = os.path.join(
        args.output_dir,
        f'zerodccorrection_by_type_lake_accumulative_hr{args.human_repair_num}.csv'
    )
    with open(lake_type_csv, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=[
            'error_type', 'tp', 'tpfp', 'tpfn', 'precision', 'recall', 'f1'
        ])
        writer.writeheader()
        writer.writerows(lake_type_rows)
    print(f"Accumulative by-type scores saved to: {lake_type_csv}")


if __name__ == '__main__':
    main()
