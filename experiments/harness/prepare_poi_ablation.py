"""
prepare_poi_ablation.py — two POI variants for the dedup ablation.

Does not touch the current experiment slices (poi_Library / poi_ShoppingCenter,
which were dirty-deduplicated). Writes four new effectiveness slices:

  poi_Library_orig            all source rows, column-select only
  poi_Library_gt              one row per unique ground-truth (clean) address
  poi_ShoppingCenter_orig
  poi_ShoppingCenter_gt

Ground-truth identity = the 8 data columns after evaluate.normalize()
(html unescape, collapse whitespace, .lower()). keep=first, dirty aligned.

Usage:
    python prepare_poi_ablation.py
    python prepare_poi_ablation.py --dry-run
    python prepare_poi_ablation.py --force
"""

from __future__ import annotations

import argparse
import os
import sys

import pandas as pd

EXPERIMENTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, EXPERIMENTS_DIR)

from evaluate import normalize
from prepare_datasets import current_error_rate, load_config, preprocess_pair, read_csv


VARIANTS = ("orig", "gt")
FILTER = "poi_Library_orig,poi_Library_gt,poi_ShoppingCenter_orig,poi_ShoppingCenter_gt"


def _keep_cols(cfg: dict) -> tuple[str, list[str], list[str]]:
    id_col = cfg["dataset"].get("id_column") or ""
    data_cols = list(cfg["dataset"]["data_columns"])
    keep = ([id_col] if id_col else []) + data_cols
    return id_col, data_cols, keep


def _source_paths(cfg: dict, poi_name: str) -> tuple[str, str]:
    datasets_dir = cfg["paths"]["datasets_dir"]
    if not os.path.isabs(datasets_dir):
        datasets_dir = os.path.normpath(os.path.join(EXPERIMENTS_DIR, datasets_dir))
    for spec in cfg["effectiveness"]["poi_slices"]:
        if spec["name"] == poi_name:
            dirty = spec["dirty"] if os.path.isabs(spec["dirty"]) else os.path.normpath(
                os.path.join(datasets_dir, spec["dirty"])
            )
            clean = spec["clean"] if os.path.isabs(spec["clean"]) else os.path.normpath(
                os.path.join(datasets_dir, spec["clean"])
            )
            return dirty, clean
    raise KeyError(f"POI {poi_name!r} not in config.effectiveness.poi_slices")


def _dedup_on_clean(
    dirty: pd.DataFrame,
    clean: pd.DataFrame,
    data_cols: list[str],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    keys = pd.DataFrame({c: clean[c].map(normalize) for c in data_cols})
    mask = ~keys.duplicated(keep="first")
    return dirty.loc[mask].reset_index(drop=True), clean.loc[mask].reset_index(drop=True)


def _write_pair(dirty: pd.DataFrame, clean: pd.DataFrame, out_dir: str, force: bool) -> None:
    os.makedirs(out_dir, exist_ok=True)
    dirty_out = os.path.join(out_dir, "dirty.csv")
    clean_out = os.path.join(out_dir, "clean.csv")
    if not force and os.path.exists(dirty_out) and os.path.exists(clean_out):
        print(f"  [skip] {out_dir} already exists ({len(pd.read_csv(dirty_out))} rows)")
        return
    dirty.to_csv(dirty_out, index=False)
    clean.to_csv(clean_out, index=False)
    print(f"  [ok]   {out_dir}  ({len(dirty)} rows)")


def build_variants(
    dirty_src: pd.DataFrame,
    clean_src: pd.DataFrame,
    id_col: str,
    data_cols: list[str],
    keep: list[str],
) -> dict[str, tuple[pd.DataFrame, pd.DataFrame]]:
    orig_d, orig_c = preprocess_pair(dirty_src, clean_src, id_col, keep, deduplicate=False)
    gt_d, gt_c = _dedup_on_clean(orig_d, orig_c, data_cols)
    # Current experiment slices: unique dirty rows (shown for comparison, not written).
    non_id = [c for c in orig_d.columns if c != id_col]
    dirty_mask = ~orig_d.duplicated(subset=non_id, keep="first")
    return {
        "orig": (orig_d, orig_c),
        "gt": (gt_d, gt_c),
        "dirty_dedup_current": (
            orig_d.loc[dirty_mask].reset_index(drop=True),
            orig_c.loc[dirty_mask].reset_index(drop=True),
        ),
    }


def main() -> None:
    p = argparse.ArgumentParser(description="Prepare original vs GT-dedup POI ablation slices.")
    p.add_argument("--config", default=os.path.join(EXPERIMENTS_DIR, "config.json"))
    p.add_argument(
        "--out",
        default=os.path.join(EXPERIMENTS_DIR, "experiment_datasets"),
        help="experiment_datasets root (writes under effectiveness/)",
    )
    p.add_argument("--dry-run", action="store_true", help="Print counts only, do not write")
    p.add_argument("--force", action="store_true", help="Overwrite existing ablation slices")
    args = p.parse_args()

    cfg = load_config(args.config)
    id_col, data_cols, keep = _keep_cols(cfg)
    eff_dir = os.path.join(args.out, "effectiveness")

    print("POI ablation variants")
    print("  orig = all source records (column-select only, no dedup)")
    print("  gt   = unique ground-truth entities (dedup on normalized clean columns)")
    print("  dirty_dedup_current = existing experiment slices (NOT rewritten here)")
    print()
    print(f"{'slice':<28} {'n':>6} {'err_rate':>10} {'gt_dups_dropped':>16}")

    for poi in ("Library", "ShoppingCenter"):
        dirty_path, clean_path = _source_paths(cfg, poi)
        dirty_src = read_csv(dirty_path)
        clean_src = read_csv(clean_path)
        variants = build_variants(dirty_src, clean_src, id_col, data_cols, keep)
        n_orig = len(variants["orig"][0])

        for key, (d, c) in variants.items():
            rate = current_error_rate(d, c, data_cols)
            dropped = n_orig - len(d) if key != "orig" else 0
            label = f"poi_{poi}_{key}" if key != "dirty_dedup_current" else f"poi_{poi} (current)"
            print(f"{label:<28} {len(d):>6} {rate:>10.4f} {dropped:>16}")
            if key in VARIANTS and not args.dry_run:
                _write_pair(d, c, os.path.join(eff_dir, f"poi_{poi}_{key}"), force=args.force)

    print()
    print("Runner filter (does not match current poi_Library / poi_ShoppingCenter):")
    print(f"  --filter-datasets {FILTER}")


if __name__ == "__main__":
    main()
