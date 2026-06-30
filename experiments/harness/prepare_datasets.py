"""
prepare_datasets.py — generate all experiment datasets from raw source files.

Reads paths and parameters from config.json. Safe to re-run: skips existing outputs.

Effectiveness datasets:
  - Full dataset and DE slice, sampled to `sample_size` rows, at each configured error_rate
    (achieved by proportionally replacing erroneous cells with clean values)
  - POI slices: used as-is (no subsampling, no error rate modification)

Runtime datasets:
  - Random samples of the full dataset at each configured sample_size

Output layout under experiment_datasets/:
  effectiveness/
    full/
      sample_full_0.05/dirty.csv  clean.csv
      sample_full_0.10/...
      sample_full_0.20/...
      sample_full_native/...      (native error rate, no modification)
    de/
      sample_de_0.05/...
      ...
    poi_Library/dirty.csv  clean.csv
    poi_ShoppingCenter/dirty.csv  clean.csv
  runtime/
    full_10000/dirty.csv  clean.csv
    full_100000/...
    ...
  fds/
    de_full/clean.csv      (full DE slice, data cols only, no sampling — for FD discovery)
    full_full/clean.csv    (full multi-country dataset, data cols only, no sampling — for FD discovery)
"""

import argparse
import json
import os
import random
import sys

import pandas as pd

EXPERIMENTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, EXPERIMENTS_DIR)
from evaluate import normalize


def load_config(config_path: str) -> dict:
    with open(config_path) as f:
        return json.load(f)


def read_csv(path: str) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str, keep_default_na=False, low_memory=False)


def write_pair(dirty_df: pd.DataFrame, clean_df: pd.DataFrame, out_dir: str):
    os.makedirs(out_dir, exist_ok=True)
    dirty_out = os.path.join(out_dir, "dirty.csv")
    clean_out = os.path.join(out_dir, "clean.csv")
    if os.path.exists(dirty_out) and os.path.exists(clean_out):
        print(f"  [skip] {out_dir} already exists")
        return
    dirty_df.to_csv(dirty_out, index=False)
    clean_df.to_csv(clean_out, index=False)
    print(f"  [ok]   {out_dir}  ({len(dirty_df)} rows)")


def preprocess_pair(
    dirty_df: pd.DataFrame,
    clean_df: pd.DataFrame,
    id_col: str,
    keep_cols: list,
    deduplicate: bool = True,
) -> tuple:
    """
    Preprocessing applied to every dirty/clean pair before any sampling or analysis:
      1. Keep only the configured columns (drops everything else, e.g. provenance_graph_iri).
      2. Remove duplicate rows from the dirty file, ignoring the id column (skipped if deduplicate=False).
      3. Align the clean file to the same surviving rows.
    """
    # 1. Select only the expected columns (in order, ignoring any extras)
    present = [c for c in keep_cols if c in dirty_df.columns]
    dirty_df = dirty_df[present]
    clean_df = clean_df[[c for c in keep_cols if c in clean_df.columns]]

    if not deduplicate:
        return dirty_df.reset_index(drop=True), clean_df.reset_index(drop=True)

    # 2. Deduplicate dirty on all non-id columns
    non_id_cols = [c for c in dirty_df.columns if c != id_col]
    dedup_mask = ~dirty_df.duplicated(subset=non_id_cols, keep="first")
    dirty_out = dirty_df[dedup_mask].reset_index(drop=True)

    # 3. Align clean to surviving rows
    clean_out = clean_df[dedup_mask].reset_index(drop=True)

    n_removed = len(dirty_df) - len(dirty_out)
    if n_removed > 0:
        print(f"    [preprocess] removed {n_removed} duplicate rows from dirty ({len(dirty_out)} remain)")

    return dirty_out, clean_out


def current_error_rate(dirty_df: pd.DataFrame, clean_df: pd.DataFrame, data_cols: list) -> float:
    """Cell-level error rate over data columns only (uses normalize() consistent with evaluate.py)."""
    n_cells = len(dirty_df) * len(data_cols)
    if n_cells == 0:
        return 0.0
    errors = 0
    for col in data_cols:
        if col in dirty_df.columns and col in clean_df.columns:
            d_norm = dirty_df[col].map(normalize)
            c_norm = clean_df[col].map(normalize)
            errors += (d_norm != c_norm).sum()
    return errors / n_cells


def reduce_error_rate(
    dirty_df: pd.DataFrame,
    clean_df: pd.DataFrame,
    target_rate: float,
    data_cols: list,
    rng: random.Random,
) -> pd.DataFrame:
    """
    Reduce error rate to target_rate by replacing some dirty cells with their clean values.
    Randomly selects erroneous cells and replaces them with the ground truth until the
    target rate is reached. Never introduces new errors.
    If the current error rate is already <= target, returns dirty_df unchanged.
    Works on data_cols only; the id column is never modified.
    """
    native_rate = current_error_rate(dirty_df, clean_df, data_cols)
    if native_rate <= target_rate:
        print(f"    native error rate {native_rate:.3f} <= target {target_rate}, returning as-is")
        return dirty_df.copy()

    # Collect all erroneous (row, col) pairs
    erroneous = []
    for col in data_cols:
        if col not in dirty_df.columns or col not in clean_df.columns:
            continue
        d_norm = dirty_df[col].map(normalize)
        c_norm = clean_df[col].map(normalize)
        mask = d_norm != c_norm
        for i in dirty_df.index[mask]:
            erroneous.append((i, col))

    n_total_cells = len(dirty_df) * len(data_cols)
    n_target_errors = int(target_rate * n_total_cells)
    n_current_errors = len(erroneous)
    n_to_fix = n_current_errors - n_target_errors

    if n_to_fix <= 0:
        return dirty_df.copy()

    rng.shuffle(erroneous)
    cells_to_fix = erroneous[:n_to_fix]

    new_dirty = dirty_df.copy()
    for (i, col) in cells_to_fix:
        new_dirty.at[i, col] = clean_df.at[i, col]

    return new_dirty


def prepare_effectiveness(cfg: dict, datasets_dir: str, out_base: str, rng: random.Random):
    print("\n=== Effectiveness datasets ===")
    eff_cfg = cfg["effectiveness"]
    data_cols = cfg["dataset"]["data_columns"]
    id_col = cfg["dataset"]["id_column"]  # "_id"
    keep_cols = [id_col] + data_cols
    error_rates = eff_cfg["error_rates"]

    slices = [
        (eff_cfg["full_dataset"], "full"),
        (eff_cfg["de_slice"], "de"),
        (eff_cfg.get("russia_slice"), "russia"),
    ]

    for slice_cfg, slice_key in slices:
        if not slice_cfg:
            continue
        dirty_src = read_csv(os.path.join(datasets_dir, slice_cfg["dirty"]))
        clean_src = read_csv(os.path.join(datasets_dir, slice_cfg["clean"]))
        dirty_src, clean_src = preprocess_pair(dirty_src, clean_src, id_col, keep_cols)
        sample_size = slice_cfg["sample_size"]
        name = slice_cfg["name"]

        print(f"\n--- {name} slice ({len(dirty_src)} rows, sampling {sample_size}) ---")

        # Sample once, reuse same rows for all error rates
        if len(dirty_src) > sample_size:
            idx = rng.sample(range(len(dirty_src)), sample_size)
            idx.sort()
            dirty_sampled = dirty_src.iloc[idx].reset_index(drop=True)
            clean_sampled = clean_src.iloc[idx].reset_index(drop=True)
        else:
            dirty_sampled = dirty_src.reset_index(drop=True)
            clean_sampled = clean_src.reset_index(drop=True)

        # Native error rate — named with actual rate so it parses as float in runner_utils
        native_rate = current_error_rate(dirty_sampled, clean_sampled, data_cols)
        print(f"  native error rate: {native_rate:.4f}")
        write_pair(
            dirty_sampled, clean_sampled,
            os.path.join(out_base, "effectiveness", name, f"sample_{name}_{native_rate:.2f}"),
        )

        # Adjusted error rate datasets (reduce only — replace dirty cells with clean values)
        for rate in error_rates:
            adjusted_dirty = reduce_error_rate(dirty_sampled, clean_sampled, rate, data_cols, rng)
            achieved = current_error_rate(adjusted_dirty, clean_sampled, data_cols)
            print(f"  target {rate:.2f} -> achieved {achieved:.4f}")
            write_pair(
                adjusted_dirty, clean_sampled,
                os.path.join(out_base, "effectiveness", name, f"sample_{name}_{rate:.2f}"),
            )

    # POI slices — no id column needed (same schema as de/full)
    print("\n--- POI slices ---")
    for poi in eff_cfg["poi_slices"]:
        dirty_src = read_csv(os.path.join(datasets_dir, poi["dirty"]))
        clean_src = read_csv(os.path.join(datasets_dir, poi["clean"]))
        dirty_src, clean_src = preprocess_pair(dirty_src, clean_src, id_col, data_cols)
        write_pair(
            dirty_src, clean_src,
            os.path.join(out_base, "effectiveness", f"poi_{poi['name']}"),
        )


def prepare_fds_source(cfg: dict, datasets_dir: str, out_base: str):
    """Write full clean datasets (data cols only, no sampling) for FD discovery."""
    print("\n=== FD-discovery source ===")
    data_cols = cfg["dataset"]["data_columns"]
    id_col = cfg["dataset"]["id_column"]

    sources = [
        (cfg["effectiveness"]["de_slice"], "de_full"),
        (cfg["effectiveness"]["full_dataset"], "full_full"),
        (cfg["effectiveness"].get("russia_slice"), "russia_full"),
    ]

    for slice_cfg, out_name in sources:
        if not slice_cfg:
            continue
        dirty_src = read_csv(os.path.join(datasets_dir, slice_cfg["dirty"]))
        clean_src = read_csv(os.path.join(datasets_dir, slice_cfg["clean"]))
        _, clean_src = preprocess_pair(dirty_src, clean_src, id_col, data_cols)

        out_dir = os.path.join(out_base, "fds", out_name)
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, "clean.csv")
        if os.path.exists(out_path):
            print(f"  [skip] {out_path} already exists")
            continue
        clean_src.to_csv(out_path, index=False)
        print(f"  [ok]   {out_path}  ({len(clean_src)} rows)")


def prepare_runtime(cfg: dict, datasets_dir: str, out_base: str, rng: random.Random):
    print("\n=== Runtime datasets ===")
    rt_cfg = cfg["runtime"]
    dirty_src = read_csv(os.path.join(datasets_dir, rt_cfg["source_dirty"]))
    clean_src = read_csv(os.path.join(datasets_dir, rt_cfg["source_clean"]))
    id_col = cfg["dataset"]["id_column"]
    keep_cols = [id_col] + cfg["dataset"]["data_columns"]
    dirty_src, clean_src = preprocess_pair(dirty_src, clean_src, id_col, keep_cols, deduplicate=False)
    name = rt_cfg["name"]
    print(f"Source: {len(dirty_src)} rows")

    for size in rt_cfg["sample_sizes"]:
        if size > len(dirty_src):
            print(f"  [warn] requested {size} > available {len(dirty_src)}, using full dataset")
            idx = list(range(len(dirty_src)))
        else:
            idx = sorted(rng.sample(range(len(dirty_src)), size))

        d = dirty_src.iloc[idx].reset_index(drop=True)
        c = clean_src.iloc[idx].reset_index(drop=True)
        write_pair(d, c, os.path.join(out_base, "runtime", f"{name}_{size}"))

    # Full dataset symlink/copy for completeness
    full_out = os.path.join(out_base, "runtime", f"{name}_full")
    write_pair(dirty_src.reset_index(drop=True), clean_src.reset_index(drop=True), full_out)


def main():
    parser = argparse.ArgumentParser(description="Prepare all experiment datasets.")
    parser.add_argument(
        "--config", default=os.path.join(EXPERIMENTS_DIR, "config.json"),
        help="Path to config.json"
    )
    parser.add_argument(
        "--out", default=None,
        help="Output root directory (default: experiment_datasets_dir from config.json)"
    )
    parser.add_argument("--seed", type=int, default=None, help="Override random seed (default: system entropy)")
    args = parser.parse_args()

    cfg = load_config(args.config)
    # No fixed seed by default — use system entropy for reproducibility-free runs
    rng = random.Random(args.seed) if args.seed is not None else random.Random()

    datasets_dir = os.path.normpath(
        os.path.join(EXPERIMENTS_DIR, cfg["paths"]["datasets_dir"])
    )
    out_base = args.out if args.out is not None else os.path.normpath(
        os.path.join(EXPERIMENTS_DIR, cfg["paths"]["experiment_datasets_dir"])
    )

    print(f"Config:      {args.config}")
    print(f"Datasets:    {datasets_dir}")
    print(f"Output root: {out_base}")
    print(f"Seed:        {'system entropy' if args.seed is None else args.seed}")

    prepare_effectiveness(cfg, datasets_dir, out_base, rng)
    prepare_runtime(cfg, datasets_dir, out_base, rng)
    prepare_fds_source(cfg, datasets_dir, out_base)

    print("\nDone.")


if __name__ == "__main__":
    main()
