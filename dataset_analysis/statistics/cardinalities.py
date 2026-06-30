#!/usr/bin/env python3
"""
Address Dataset Analysis: Clean (targets) vs Dirty (values)

Features:
- Wrong cells per feature (counts + %) with stacked bar plot
- Cardinality, per-column uniqueness for both datasets
- Value distributions (Top-K + "others") side-by-side
- Smart combinational uniqueness over address-meaningful column combos
- Outputs printed to console and saved as CSV/PNG in a timestamped folder

Author: (you)
"""

import argparse
import os
import sys
import json
from datetime import datetime
from typing import List, Tuple, Dict, Optional

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# ----------------------------- Utilities -----------------------------

def make_outdir(base: str = "analysis/analysis_out") -> str:
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    outdir = os.path.join(base, f"run_{ts}")
    os.makedirs(outdir, exist_ok=True)
    return outdir


def read_csv_safely(path: str, chunksize: Optional[int] = None) -> pd.DataFrame:
    """
    Read CSV with a memory-friendly fallback. Tries Arrow backend if available.
    """
    read_kwargs = dict(
        low_memory=True
    )
    # Try pyarrow backend (pandas >=2.0) for memory/perf if available
    try:
        df = pd.read_csv(path, dtype_backend="pyarrow", **read_kwargs)
        return df
    except Exception:
        pass
    # Fallback to default pandas
    df = pd.read_csv(path, **read_kwargs)

    if "_id" in df.columns:
        df = df.drop(columns="_id", errors="ignore")

    return df


def safe_equal_series(a: pd.Series, b: pd.Series) -> pd.Series:
    """
    Element-wise equality treating NaN==NaN as True.
    """
    a_na = a.isna()
    b_na = b.isna()
    both_na = a_na & b_na
    eq_vals = (a == b)
    eq_vals = eq_vals.fillna(False)
    return both_na | eq_vals


def to_csv(df: pd.DataFrame, path: str):
    df.to_csv(path, index=False)


def print_header(title: str):
    bar = "=" * len(title)
    print(f"\n{title}\n{bar}")


# ------------------------ Wrong Cells per Feature ------------------------

def compare_wrong_cells_per_feature(clean: pd.DataFrame, dirty: pd.DataFrame) -> pd.DataFrame:
    """
    Return DataFrame with columns: feature, total, correct, wrong, wrong_pct
    """
    assert list(clean.columns) == list(dirty.columns), "Columns must match."
    cols = list(clean.columns)
    # Align index if needed (assuming same order)
    if not clean.index.equals(dirty.index):
        clean = clean.reset_index(drop=True)
        dirty = dirty.reset_index(drop=True)

    stats = []
    n_rows = len(clean)
    for c in cols:
        eq_mask = safe_equal_series(clean[c], dirty[c])
        correct = int(eq_mask.sum())
        wrong = int(n_rows - correct)
        stats.append({
            "feature": c,
            "total": n_rows,
            "correct": correct,
            "wrong": wrong,
            "wrong_pct": (wrong / n_rows) * 100.0 if n_rows else 0.0
        })
    return pd.DataFrame(stats).sort_values("wrong", ascending=False)


def plot_stacked_correct_wrong(df_stats: pd.DataFrame, out_png: str):
    """
    Stacked bar: correct vs wrong per feature (sorted by wrong desc).
    """
    df = df_stats.copy()
    df = df.sort_values("wrong", ascending=False)
    features = df["feature"].tolist()
    correct = df["correct"].to_numpy()
    wrong = df["wrong"].to_numpy()

    fig, ax = plt.subplots(figsize=(max(8, len(features)*0.6), 6))
    ax.bar(features, correct, label="Correct")
    ax.bar(features, wrong, bottom=correct, label="Wrong")
    ax.set_ylabel("Count")
    ax.set_title("Correct vs Wrong Cells per Feature")
    ax.set_xticklabels(features, rotation=45, ha="right")
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_png, dpi=200)
    plt.close(fig)


# ------------------- Cardinality & Uniqueness (per column) -------------------

def cardinality_and_uniqueness(df: pd.DataFrame, dataset_name: str) -> pd.DataFrame:
    """
    Returns per-column cardinality, unique_ratio, null_ratio.
    """
    rows = len(df)
    records = []
    for c in df.columns:
        nunique = int(df[c].nunique(dropna=True))
        nulls = int(df[c].isna().sum())
        records.append({
            "dataset": dataset_name,
            "feature": c,
            "rows": rows,
            "cardinality_non_null": nunique,
            "unique_ratio_non_null": (nunique / (rows - nulls)) * 100.0 if rows - nulls > 0 else 0.0,
            "nulls": nulls,
            "null_ratio": (nulls / rows) * 100.0 if rows > 0 else 0.0
        })
    return pd.DataFrame(records).sort_values(["feature", "dataset"])


# ------------------- Value Distributions (Top-K + others) -------------------

def topk_distribution(series: pd.Series, k: int) -> pd.DataFrame:
    """
    Compute Top-K value counts + others as a single row with columns [value, count, pct].
    """
    s = series.copy()
    total = len(s)
    vc = s.value_counts(dropna=False)
    # Represent NaN consistently
    labels = vc.index.to_list()
    labels = ["<NA>" if (isinstance(x, float) and np.isnan(x)) else str(x) for x in labels]
    vc.index = labels

    top = vc.head(k)
    top_df = top.reset_index()
    top_df.columns = ["value", "count"]
    top_df["pct"] = top_df["count"] / total * 100.0 if total else 0.0

    others_count = int(vc.iloc[k:].sum()) if len(vc) > k else 0
    if others_count > 0:
        others_row = pd.DataFrame([{"value": "__OTHERS__", "count": others_count,
                                    "pct": (others_count / total * 100.0) if total else 0.0}])
        top_df = pd.concat([top_df, others_row], ignore_index=True)

    return top_df


def save_topk_distributions(df: pd.DataFrame, dataset_name: str, k: int, outdir: str) -> Dict[str, str]:
    """
    For each column, save a CSV of top-k + others, and a bar plot PNG.
    Returns mapping: feature -> csv_path (for reference).
    """
    paths = {}
    for c in df.columns:
        dist_df = topk_distribution(df[c], k)
        csv_path = os.path.join(outdir, f"value_dist_top{k}_{dataset_name}_{c}.csv")
        to_csv(dist_df, csv_path)
        paths[c] = csv_path

        # Plot horizontal bar for readability
        fig, ax = plt.subplots(figsize=(8, max(4, min(20, len(dist_df)*0.4))))
        ax.barh(dist_df["value"], dist_df["count"])
        ax.set_xlabel("Count")
        ax.set_title(f"Top-{k} Value Distribution (+others): {dataset_name}.{c}")
        plt.tight_layout()
        png_path = os.path.join(outdir, f"value_dist_top{k}_{dataset_name}_{c}.png")
        fig.savefig(png_path, dpi=200)
        plt.close(fig)

    return paths


# ------------------- Combinational Uniqueness (smart combos) -------------------

ADDRESS_HINTS = {
    "house_number": ["house", "house_number", "hnr", "number", "housenumber", "street_number"],
    "road": ["road", "street", "strasse", "str", "rd", "st"],
    "postcode": ["postcode", "postal", "zip", "plz"],
    "locality": ["locality", "city", "town", "place", "village", "district"],
    "name": ["name", "poi", "organization", "org", "shop"]
}

def find_first_matching_column(cols: List[str], keywords: List[str]) -> Optional[str]:
    lcols = [c.lower() for c in cols]
    for kw in keywords:
        for i, lc in enumerate(lcols):
            # full or partial contains match
            if kw == lc or kw in lc:
                return cols[i]
    return None


def select_address_combos(cols: List[str]) -> List[Tuple[str, ...]]:
    """
    Select meaningful combos if the corresponding columns exist.
    Combos:
      (house_number, road, postcode)
      (road, postcode)
      (locality, postcode)
      (name, postcode)
      (name, road, postcode)
    """
    candidates = {}
    for key, kws in ADDRESS_HINTS.items():
        candidates[key] = find_first_matching_column(cols, kws)

    combos = []
    def has(*keys):
        return all(candidates[k] is not None for k in keys)

    if has("house_number", "road", "postcode"):
        combos.append((
            candidates["house_number"], candidates["road"], candidates["postcode"]
        ))
    if has("road", "postcode"):
        combos.append((candidates["road"], candidates["postcode"]))
    if has("locality", "postcode"):
        combos.append((candidates["locality"], candidates["postcode"]))
    if has("name", "postcode"):
        combos.append((candidates["name"], candidates["postcode"]))
    if has("name", "road", "postcode"):
        combos.append((
            candidates["name"], candidates["road"], candidates["postcode"]
        ))
    if has("name", "road", "locality", "house_number"):
        combos.append((
            candidates["name"], candidates["road"], candidates["locality"], candidates["house_number"]
        ))

    # Deduplicate and keep order
    seen = set()
    ordered = []
    for t in combos:
        if t not in seen:
            ordered.append(t)
            seen.add(t)
    return ordered


def combinational_uniqueness(df: pd.DataFrame, combos: List[Tuple[str, ...]], dataset_name: str) -> pd.DataFrame:
    """
    For each combination, compute unique pairs/tuples & ratio (non-null tuple uniqueness).
    """
    rows = len(df)
    out = []
    for combo in combos:
        # Treat a tuple as null if any of its values is null
        non_null_mask = np.ones(rows, dtype=bool)
        for c in combo:
            non_null_mask &= ~df[c].isna().to_numpy()

        subset = df.loc[non_null_mask, list(combo)]
        nunique = int(subset.drop_duplicates().shape[0])
        denom = int(non_null_mask.sum())
        out.append({
            "dataset": dataset_name,
            "columns": " + ".join(combo),
            "rows": rows,
            "non_null_rows": denom,
            "unique_combinations": nunique,
            "unique_ratio_non_null": (nunique / denom) * 100.0 if denom > 0 else 0.0
        })
    return pd.DataFrame(out)


# ----------------------------- Main Pipeline -----------------------------

def main(args):
    outdir = make_outdir(args.output_dir)
    config_path = os.path.join(outdir, "run_config.json")
    with open(config_path, "w") as f:
        json.dump(vars(args), f, indent=2)
    print_header("Output Directory")
    print(outdir)

    print_header("Loading Data")
    print(f"Clean (targets): {args.targets}")
    print(f"Dirty (values):  {args.values}")
    clean = read_csv_safely(args.targets)
    dirty = read_csv_safely(args.values)

    # Basic sanity
    if clean.shape != dirty.shape:
        print(f"ERROR: Shape mismatch clean={clean.shape} dirty={dirty.shape}", file=sys.stderr)
        sys.exit(1)
    if list(clean.columns) != list(dirty.columns):
        print("WARNING: Column names differ in order/labels. Aligning by position.", file=sys.stderr)
        # Force same columns by position with synthetic names
        ncols = min(clean.shape[1], dirty.shape[1])
        cols = [f"col_{i}" for i in range(ncols)]
        clean = clean.iloc[:, :ncols]; clean.columns = cols
        dirty = dirty.iloc[:, :ncols]; dirty.columns = cols

    # ---------------- Wrong cells per feature ----------------
    print_header("Wrong Cells per Feature (counts + %)")
    wrong_stats = compare_wrong_cells_per_feature(clean, dirty)
    print(wrong_stats)
    wrong_csv = os.path.join(outdir, "wrong_cells_per_feature.csv")
    to_csv(wrong_stats, wrong_csv)

    stacked_png = os.path.join(outdir, "correct_vs_wrong_stacked.png")
    plot_stacked_correct_wrong(wrong_stats, stacked_png)

    total_wrong = int(wrong_stats["wrong"].sum())
    total_cells = int(len(clean) * len(clean.columns))
    total_wrong_pct = (total_wrong / total_cells) * 100.0 if total_cells else 0.0
    print(f"\nTotal wrong cells: {total_wrong} / {total_cells} "
          f"({total_wrong_pct:.3f}%)")
    with open(os.path.join(outdir, "wrong_cells_summary.txt"), "w") as f:
        f.write(f"Total wrong cells: {total_wrong} / {total_cells} ({total_wrong_pct:.6f}%)\n")

    # ---------------- Cardinality & Uniqueness (per column) ----------------
    print_header("Cardinality & Per-Column Uniqueness")
    card_clean = cardinality_and_uniqueness(clean, "clean")
    card_dirty = cardinality_and_uniqueness(dirty, "dirty")
    card_all = pd.concat([card_clean, card_dirty], ignore_index=True)
    print(card_all)
    to_csv(card_all, os.path.join(outdir, "cardinality_uniqueness_per_column.csv"))

    # ---------------- Value distributions (Top-K + others) ----------------
    print_header(f"Value Distributions (Top-{args.top_k} + others)")
    dist_dir = os.path.join(outdir, f"value_distributions_top{args.top_k}")
    os.makedirs(dist_dir, exist_ok=True)

    paths_clean = save_topk_distributions(clean, "clean", args.top_k, dist_dir)
    paths_dirty = save_topk_distributions(dirty, "dirty", args.top_k, dist_dir)

    # Mapping index JSON for convenience
    with open(os.path.join(dist_dir, "index.json"), "w") as f:
        json.dump({
            "clean": paths_clean,
            "dirty": paths_dirty
        }, f, indent=2)

    # ---------------- Combinational Uniqueness (smart) ----------------
    print_header("Combinational Uniqueness (smart address combos)")
    combos = select_address_combos(list(clean.columns))
    if len(combos) == 0:
        print("No meaningful address combos detected from column names; skipping.")
        with open(os.path.join(outdir, "combos_detected.json"), "w") as f:
            json.dump({"combos": []}, f, indent=2)
    else:
        print("Detected combos:")
        for t in combos:
            print("  - " + " + ".join(t))
        with open(os.path.join(outdir, "combos_detected.json"), "w") as f:
            json.dump({"combos": [list(t) for t in combos]}, f, indent=2)

        cu_clean = combinational_uniqueness(clean, combos, "clean")
        cu_dirty = combinational_uniqueness(dirty, combos, "dirty")
        cu_all = pd.concat([cu_clean, cu_dirty], ignore_index=True)
        print(cu_all)
        to_csv(cu_all, os.path.join(outdir, "combinational_uniqueness.csv"))

        # Simple bar plots for each combo comparing clean vs dirty unique_ratio
        for combo in combos:
            key = " + ".join(combo)
            sub = cu_all[cu_all["columns"] == key].copy()
            fig, ax = plt.subplots(figsize=(6, 4))
            ax.bar(sub["dataset"], sub["unique_ratio_non_null"])
            ax.set_ylabel("Unique Ratio on Non-Null Tuples (%)")
            ax.set_title(f"Combinational Uniqueness: {key}")
            plt.tight_layout()
            fig.savefig(os.path.join(outdir, f"combo_unique_ratio_{'_'.join(combo)}.png"), dpi=200)
            plt.close(fig)

    print_header("Done")
    print(f"All outputs saved under: {outdir}")


# ----------------------------- Entrypoint -----------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Analyze clean vs dirty address datasets.")
    parser.add_argument("--targets", type=str, required=True,
                        help="Path to clean CSV (targets).")
    parser.add_argument("--values", type=str, required=True,
                        help="Path to dirty CSV (values).")
    parser.add_argument("--top_k", type=int, default=20,
                        help="Top-K values to report in distributions.")
    parser.add_argument("--output_dir", type=str, default="output/cardinalities",
                        help="Base output directory (a timestamped subfolder will be created).")
    args = parser.parse_args()
    main(args)
