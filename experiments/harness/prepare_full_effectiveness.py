"""
prepare_full_effectiveness.py — build only the `full` (full_named) effectiveness slices.

Thin wrapper around prepare_datasets.prepare_effectiveness that:
  - reads full_dirty.csv / full_clean.csv from --datasets-dir (override of config paths.datasets_dir)
  - skips the DE / Russia / POI slices, the runtime datasets and the FD-discovery sources

Output (under --out):
  effectiveness/full/sample_full_<native>/{dirty,clean}.csv
  effectiveness/full/sample_full_0.05/...
  effectiveness/full/sample_full_0.10/...
  effectiveness/full/sample_full_0.20/...
"""

import argparse
import copy
import os
import random
import sys

HARNESS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HARNESS_DIR)

import prepare_datasets as pd_mod  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", default=os.path.join(HARNESS_DIR, "config.json"))
    ap.add_argument("--datasets-dir", required=True, help="Dir with full_dirty.csv and full_clean.csv")
    ap.add_argument("--out", default=os.path.join(HARNESS_DIR, "experiment_datasets"))
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument(
        "--slices", nargs="+", default=["full"], choices=["full", "de", "russia"],
        help="Which effectiveness slices to build (default: full). Paths come from config.json.",
    )
    ap.add_argument(
        "--fds-source", action="store_true",
        help="Also write fds/<slice>_full/clean.csv (deduped full clean table, data cols only) for TANE.",
    )
    ap.add_argument("--fds-source-only", action="store_true",
                    help="Only write the FD-discovery sources; skip the effectiveness samples.")
    args = ap.parse_args()

    cfg = copy.deepcopy(pd_mod.load_config(args.config))
    eff = cfg["effectiveness"]
    if "full" not in args.slices:
        eff["full_dataset"] = None
    if "de" not in args.slices:
        eff["de_slice"] = None
    if "russia" not in args.slices:
        eff["russia_slice"] = None
    eff["poi_slices"] = []

    rng = random.Random(args.seed) if args.seed is not None else random.Random()
    print(f"Datasets: {args.datasets_dir}\nOutput:   {args.out}\nSeed:     {args.seed}")
    datasets_dir = os.path.abspath(args.datasets_dir)
    if not args.fds_source_only:
        pd_mod.prepare_effectiveness(cfg, datasets_dir, args.out, rng)
    if args.fds_source or args.fds_source_only:
        pd_mod.prepare_fds_source(cfg, datasets_dir, args.out)
    print("\nDone.")


if __name__ == "__main__":
    main()
