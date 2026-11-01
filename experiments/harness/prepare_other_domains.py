"""Write dirty/clean pairs of at most 10k rows at the native rate and at 5/10/20%.

Source files are other_domains_data/<domain>/{dirty,clean}.csv. The pipeline
names merged_{values,targets}_experiment.csv are accepted as a fallback.
`id` is checked for row alignment and then dropped, so scoring covers only the
domain attributes. One sample is drawn per domain and reused for every error rate.
Domains smaller than the sample size are kept in full. Lower rates are produced
the same way as the address harness: erroneous cells are replaced with the clean
value until the target rate is reached. A target above the native rate is skipped,
because this step never adds errors. A case-only difference is not an error.

Also writes the full clean table of each domain for FD discovery, matching the
address harness: TANE is run on that table, and every error rate reuses the
resulting rules.

Output layout (what list_effectiveness_datasets discovers):
  experiment_datasets_other_domains/effectiveness/<domain>/sample_<domain>_<rate>/
    dirty.csv
    clean.csv
  experiment_datasets_other_domains/fds/<domain>/clean.csv
"""

import json
import os
import random
import sys

import pandas as pd

HARNESS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HARNESS_DIR)
from prepare_datasets import current_error_rate, reduce_error_rate, write_pair


def main():
    config_path = os.path.join(HARNESS_DIR, "config_other_domains.json")
    with open(config_path) as f:
        cfg = json.load(f)

    source_root = os.path.normpath(os.path.join(HARNESS_DIR, cfg["paths"]["datasets_dir"]))
    datasets_root = os.path.normpath(
        os.path.join(HARNESS_DIR, cfg["paths"]["experiment_datasets_dir"])
    )
    out_root = os.path.join(datasets_root, "effectiveness")
    fds_root = os.path.join(datasets_root, "fds")
    error_rates = cfg["effectiveness"]["error_rates"]
    sample_size = cfg["effectiveness"]["sample_size"]
    rng = random.Random(0)

    for domain, columns in cfg["dataset"]["domains"].items():
        domain_dir = os.path.join(source_root, domain)
        dirty_name, clean_name = "dirty.csv", "clean.csv"
        if not os.path.isfile(os.path.join(domain_dir, dirty_name)):
            dirty_name, clean_name = "merged_values_experiment.csv", "merged_targets_experiment.csv"
        dirty_src = pd.read_csv(
            os.path.join(domain_dir, dirty_name),
            dtype=str, keep_default_na=False, low_memory=False,
        )
        clean_src = pd.read_csv(
            os.path.join(domain_dir, clean_name),
            dtype=str, keep_default_na=False, low_memory=False,
        )
        if list(dirty_src["id"]) != list(clean_src["id"]):
            raise SystemExit(f"{domain}: id columns are not row-aligned")
        missing = [c for c in columns if c not in dirty_src.columns or c not in clean_src.columns]
        if missing:
            raise SystemExit(f"{domain}: missing columns {missing}")

        dirty_all = dirty_src[columns].reset_index(drop=True)
        clean_all = clean_src[columns].reset_index(drop=True)

        fds_dir = os.path.join(fds_root, domain)
        os.makedirs(fds_dir, exist_ok=True)
        fds_clean = os.path.join(fds_dir, "clean.csv")
        if os.path.exists(fds_clean):
            print(f"  [skip] {fds_clean} already exists")
        else:
            clean_all.to_csv(fds_clean, index=False)
            print(f"  [ok]   {fds_clean}  ({len(clean_all)} rows, FD discovery source)")

        if len(dirty_all) > sample_size:
            idx = sorted(rng.sample(range(len(dirty_all)), sample_size))
            dirty = dirty_all.iloc[idx].reset_index(drop=True)
            clean = clean_all.iloc[idx].reset_index(drop=True)
        else:
            dirty = dirty_all
            clean = clean_all
        native = current_error_rate(dirty, clean, columns)
        print(
            f"\n{domain}: sampled {len(dirty)} of {len(dirty_all)} rows, "
            f"{len(columns)} cols, native error rate {native:.4f}"
        )

        write_pair(
            dirty, clean,
            os.path.join(out_root, domain, f"sample_{domain}_{native:.4f}"),
        )
        for rate in error_rates:
            if native <= rate:
                print(f"  skip {rate:.2f}: native {native:.4f} is already at or below the target")
                continue
            adjusted = reduce_error_rate(dirty, clean, rate, columns, rng)
            achieved = current_error_rate(adjusted, clean, columns)
            print(f"  target {rate:.2f} -> achieved {achieved:.4f}")
            write_pair(
                adjusted, clean,
                os.path.join(out_root, domain, f"sample_{domain}_{rate:.2f}"),
            )


if __name__ == "__main__":
    main()
