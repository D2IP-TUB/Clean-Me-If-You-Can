"""Check prepared other-domain pairs against the error rate in the folder name.

For each effectiveness/<domain>/sample_<domain>_<rate>/ pair, dirty and clean are
compared cell by cell with the same normalizer used to build the files. A folder
named with two decimals (0.05, 0.10, 0.20) is a target rate: the error count must
equal int(target * n_cells), which is what reduce_error_rate leaves behind. A
folder named with four decimals is the native rate of the sample and must match
the measured rate rounded to four decimals.

Also checks that every rate of a domain shares one clean table, and that a lower
rate only repairs cells that were already wrong at the native rate.
"""

import os
import sys

import pandas as pd

HARNESS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HARNESS_DIR)
from evaluate import normalize
from prepare_datasets import read_csv

EFFECTIVENESS_DIR = os.path.join(
    HARNESS_DIR, "experiment_datasets_other_domains", "effectiveness"
)
TARGET_RATES = (0.05, 0.1, 0.2)
TARGET_LABELS = {f"{rate:.2f}": rate for rate in TARGET_RATES}


def rate_label(folder_name: str) -> str:
    return folder_name.rsplit("_", 1)[-1]


def error_cells(dirty: pd.DataFrame, clean: pd.DataFrame) -> set:
    cells = set()
    for col in dirty.columns:
        d_norm = dirty[col].map(normalize)
        c_norm = clean[col].map(normalize)
        for i in dirty.index[d_norm != c_norm]:
            cells.add((i, col))
    return cells


def main() -> None:
    if not os.path.isdir(EFFECTIVENESS_DIR):
        raise SystemExit(f"missing {EFFECTIVENESS_DIR}")

    failures = []
    checked = 0
    for domain in sorted(os.listdir(EFFECTIVENESS_DIR)):
        domain_dir = os.path.join(EFFECTIVENESS_DIR, domain)
        if not os.path.isdir(domain_dir):
            continue

        pairs = []
        for folder in sorted(os.listdir(domain_dir)):
            pair_dir = os.path.join(domain_dir, folder)
            dirty_path = os.path.join(pair_dir, "dirty.csv")
            clean_path = os.path.join(pair_dir, "clean.csv")
            if os.path.isfile(dirty_path) and os.path.isfile(clean_path):
                pairs.append((folder, read_csv(dirty_path), read_csv(clean_path)))

        native = [(folder, dirty, clean) for folder, dirty, clean in pairs
                  if rate_label(folder) not in TARGET_LABELS]
        if len(native) != 1:
            failures.append(f"{domain}: expected one native pair, found {len(native)}")
            native_errors = None
            native_clean = None
        else:
            _, native_dirty, native_clean = native[0]
            native_errors = error_cells(native_dirty, native_clean)

        for folder, dirty, clean in pairs:
            label = rate_label(folder)
            name = f"{domain}/{folder}"
            if list(dirty.columns) != list(clean.columns) or len(dirty) != len(clean):
                failures.append(
                    f"{name}: shape mismatch dirty {dirty.shape} clean {clean.shape}"
                )
                continue

            cells = error_cells(dirty, clean)
            n_cells = len(dirty) * len(dirty.columns)
            measured = len(cells) / n_cells if n_cells else 0.0

            if label in TARGET_LABELS:
                expected_errors = int(TARGET_LABELS[label] * n_cells)
                ok = len(cells) == expected_errors
                detail = (
                    f"errors {len(cells)} vs int({label} * {n_cells}) = {expected_errors}"
                    f"  (measured {measured:.4f})"
                )
            else:
                ok = f"{measured:.4f}" == label
                detail = f"measured {measured:.4f} vs folder {label}  ({len(cells)}/{n_cells} cells)"

            status = "ok" if ok else "FAIL"
            print(f"  [{status}] {name}: {detail}")
            if not ok:
                failures.append(f"{name}: {detail}")
            checked += 1

            if native_clean is not None and not clean.equals(native_clean):
                failures.append(f"{name}: clean table differs from the native sample")
            if (
                native_errors is not None
                and label in TARGET_LABELS
                and not cells <= native_errors
            ):
                extra = len(cells - native_errors)
                failures.append(f"{name}: {extra} errors are not present in the native sample")

    print(f"\n{checked} pairs checked, {len(failures)} failure(s)")
    if failures:
        for failure in failures:
            print(f"  {failure}")
        sys.exit(1)


if __name__ == "__main__":
    main()
