"""Count cells whose only dirty/clean difference is capitalization.

A cell counts when the harness normalizer still sees a difference, but the two
values are equal under case folding. Any other change (characters added, removed,
or replaced) is not counted, even if the case also differs.

Run from this directory:
  python3 count_capitalization_errors.py
"""

import os
import sys

HARNESS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HARNESS_DIR)
from evaluate import normalize
from prepare_datasets import read_csv

EFFECTIVENESS_DIR = os.path.join(
    HARNESS_DIR, "experiment_datasets_other_domains", "effectiveness"
)


def count_pair(dirty, clean):
    case_only = 0
    errors = 0
    by_column = {}
    for col in dirty.columns:
        d_norm = dirty[col].map(normalize)
        c_norm = clean[col].map(normalize)
        differs = d_norm != c_norm
        only_case = differs & (d_norm.str.lower() == c_norm.str.lower())
        n_case = int(only_case.sum())
        n_err = int(differs.sum())
        case_only += n_case
        errors += n_err
        by_column[col] = (n_case, n_err)
    return case_only, errors, by_column


def main() -> None:
    if not os.path.isdir(EFFECTIVENESS_DIR):
        raise SystemExit(f"missing {EFFECTIVENESS_DIR}")

    for domain in sorted(os.listdir(EFFECTIVENESS_DIR)):
        domain_dir = os.path.join(EFFECTIVENESS_DIR, domain)
        if not os.path.isdir(domain_dir):
            continue
        print(f"\n{domain}")
        for folder in sorted(os.listdir(domain_dir)):
            pair_dir = os.path.join(domain_dir, folder)
            dirty_path = os.path.join(pair_dir, "dirty.csv")
            clean_path = os.path.join(pair_dir, "clean.csv")
            if not (os.path.isfile(dirty_path) and os.path.isfile(clean_path)):
                continue
            dirty = read_csv(dirty_path)
            clean = read_csv(clean_path)
            if list(dirty.columns) != list(clean.columns) or len(dirty) != len(clean):
                print(f"  {folder}: shape mismatch, skipped")
                continue
            case_only, errors, by_column = count_pair(dirty, clean)
            share = (case_only / errors) if errors else 0.0
            print(f"  {folder}: {case_only} capitalization-only / {errors} errors ({share:.1%})")
            for col, (n_case, n_err) in by_column.items():
                print(f"    {col}: {n_case} / {n_err}")


if __name__ == "__main__":
    main()
