"""
prepare_rules.py — discover FDs per dataset using TANE and generate system-specific rule files.

For each dataset (effectiveness + runtime), runs TANE on the clean sample to discover FDs,
then translates them into:
  1. fds_{dataset_name}_indexed.txt      — column-index format for Java Horizon
  2. fds_{dataset_name}_holoclean.txt   — denial-constraint format for HoloClean
  3. uniclean_rules_{dataset_name}.py   — AttrRelation list for UniClean

Filtering for UniClean:
  - Keep all FDs (including cyclic and LHS size > 2)

TANE is used as a library from ../baselines/tane/tane.py.
It requires a headerless CSV (TANE reads raw comma-separated lines).

Usage:
    python prepare_rules.py [--config config.json] [--datasets-dir ./experiment_datasets]
                            [--out-dir .] [--list] [--dataset NAME]
    python prepare_rules.py --list   # print FDs for all datasets, no files written
"""

import argparse
import csv
import json
import os
import sys
import tempfile
from collections import defaultdict

EXPERIMENTS_DIR = os.path.dirname(os.path.abspath(__file__))
TANE_DIR = os.path.normpath(os.path.join(EXPERIMENTS_DIR, "../baselines/tane"))
sys.path.insert(0, TANE_DIR)


# ---------------------------------------------------------------------------
# TANE integration
# ---------------------------------------------------------------------------

def run_tane(clean_csv_path: str, data_cols: list) -> list:
    """
    Run TANE on the data columns of clean_csv_path.
    Returns list of (lhs: list[str], rhs: str) using column names.

    TANE reads a headerless CSV where each value is a token.
    We write a temp file with only data_cols (no id), using all rows.
    """
    import pandas as pd
    from tane import TANE, read_db

    df = pd.read_csv(clean_csv_path, dtype=str, keep_default_na=False, low_memory=False)

    # Keep only configured data columns that exist
    cols = [c for c in data_cols if c in df.columns]
    if not cols:
        print(f"  [warn] No data columns found in {clean_csv_path}")
        return []

    df = df[cols]

    # Write headerless temp CSV for TANE
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False)
    for _, row in df.iterrows():
        tmp.write(",".join(str(v).replace(",", " ") for v in row.values) + "\n")
    tmp.close()

    try:
        T = read_db(tmp.name)
        tane = TANE(T)
        tane.run()
        rules = tane.rules  # list of (LHS_tuple_of_col_idx, rhs_col_idx)
    finally:
        os.unlink(tmp.name)

    # Translate col indices → col names
    named_rules = []
    for lhs_indices, rhs_idx in rules:
        lhs = [cols[i] for i in lhs_indices]
        rhs = cols[rhs_idx]
        named_rules.append((lhs, rhs))

    return named_rules


# ---------------------------------------------------------------------------
# Cycle detection (SCC via Kosaraju)
# ---------------------------------------------------------------------------

def find_cyclic_indices(fds: list) -> tuple:
    """
    Build a directed graph on attributes; find SCCs.
    Returns (set of cyclic FD indices, set of cyclic attribute names).
    """
    attrs = set()
    for lhs, rhs in fds:
        attrs.update(lhs)
        attrs.add(rhs)
    attr_list = sorted(attrs)
    idx = {a: i for i, a in enumerate(attr_list)}
    n = len(attr_list)

    graph = defaultdict(set)
    rgraph = defaultdict(set)
    for lhs, rhs in fds:
        # Only single-LHS FDs can create true repair-loop cycles (e.g. A→B and B→A).
        # Multi-column FDs would require coincidental multi-attribute agreement and
        # should not be considered cyclic for the purposes of UniClean filtering.
        if len(lhs) != 1:
            continue
        r = idx[rhs]
        l = idx[lhs[0]]
        graph[l].add(r)
        rgraph[r].add(l)

    visited = [False] * n
    order = []

    def dfs1(v):
        stack = [(v, iter(graph[v]))]
        visited[v] = True
        while stack:
            node, children = stack[-1]
            try:
                child = next(children)
                if not visited[child]:
                    visited[child] = True
                    stack.append((child, iter(graph[child])))
            except StopIteration:
                order.append(node)
                stack.pop()

    for v in range(n):
        if not visited[v]:
            dfs1(v)

    comp = [-1] * n
    scc_id = 0

    def dfs2(v, cid):
        stack = [v]
        comp[v] = cid
        while stack:
            node = stack.pop()
            for child in rgraph[node]:
                if comp[child] == -1:
                    comp[child] = cid
                    stack.append(child)

    for v in reversed(order):
        if comp[v] == -1:
            dfs2(v, scc_id)
            scc_id += 1

    scc_sizes = defaultdict(int)
    for c in comp:
        scc_sizes[c] += 1
    cyclic_attrs = {attr_list[i] for i in range(n) if scc_sizes[comp[i]] > 1}

    cyclic_indices = set()
    for i, (lhs, rhs) in enumerate(fds):
        if rhs in cyclic_attrs or any(a in cyclic_attrs for a in lhs):
            cyclic_indices.add(i)

    return cyclic_indices, cyclic_attrs


# ---------------------------------------------------------------------------
# Horizon — indexed format
# ---------------------------------------------------------------------------

def make_horizon_fds(fds: list, column_order: list) -> list:
    """Translate named FDs to column-index format for Java Horizon."""
    col_idx = {col: i for i, col in enumerate(column_order)}
    lines = []
    for lhs, rhs in fds:
        if rhs not in col_idx:
            continue
        lhs_valid = [a for a in lhs if a in col_idx]
        if not lhs_valid:
            continue
        lhs_str = ", ".join(str(col_idx[a]) for a in lhs_valid)
        rhs_str = str(col_idx[rhs])
        lines.append(f"{lhs_str} -> {rhs_str}")
    return lines


# ---------------------------------------------------------------------------
# HoloClean — denial-constraint format
# ---------------------------------------------------------------------------

def make_holoclean_fds(fds: list) -> list:
    """
    Translate named FDs to HoloClean denial-constraint format.
    Each FD  lhs1, lhs2 -> rhs  becomes:
        t1&t2&EQ(t1.lhs1,t2.lhs1)&EQ(t1.lhs2,t2.lhs2)&IQ(t1.rhs,t2.rhs)
    """
    lines = []
    for lhs, rhs in fds:
        eq_parts = "&".join(f"EQ(t1.{a},t2.{a})" for a in lhs)
        lines.append(f"t1&t2&{eq_parts}&IQ(t1.{rhs},t2.{rhs})")
    return lines


# ---------------------------------------------------------------------------
# UniClean — Python AttrRelation list
# ---------------------------------------------------------------------------

def make_uniclean_rules(fds: list, cyclic_indices: set) -> list:
    # Keep all FDs, including cyclic and LHS size > 2.
    # cyclic_indices is retained for logging only.
    _ = cyclic_indices
    return list(fds)


def write_uniclean_rules_py(rules: list, out_path: str, dataset_name: str):
    lines = [
        f"# Auto-generated by prepare_rules.py for dataset: {dataset_name}",
        "# All TANE FDs kept (cyclic and any LHS size).",
        "# Loaded by UniClean main scripts or imported after uniclean_cleaners is on sys.path.",
        "from SampleScrubber.cleaner.multiple import AttrRelation",
        "",
        "def get_cleaners():",
        "    return [",
    ]
    for i, (lhs, rhs) in enumerate(rules):
        lines.append(f"        AttrRelation({repr(lhs)}, {repr([rhs])}, 'r{i+1}'),")
    lines.append("    ]")
    lines.append("")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


# ---------------------------------------------------------------------------
# Per-dataset processing
# ---------------------------------------------------------------------------

def process_dataset(name: str, clean_csv: str, cfg: dict, out_dir: str, list_only: bool):
    """Run TANE on clean_csv, write Horizon FD file + UniClean rules for this dataset."""
    data_cols = cfg["dataset"]["data_columns"]

    print(f"\n--- {name} ({clean_csv}) ---")
    fds = run_tane(clean_csv, data_cols)
    print(f"  TANE found {len(fds)} FDs:")
    for lhs, rhs in fds:
        print(f"    {', '.join(lhs)} -> {rhs}")

    cyclic_indices, cyclic_attrs = find_cyclic_indices(fds)
    print(f"  Cyclic attrs: {cyclic_attrs}")

    uniclean_rules = make_uniclean_rules(fds, cyclic_indices)
    print(f"  UniClean rules ({len(uniclean_rules)}, all FDs kept):")
    for lhs, rhs in uniclean_rules:
        print(f"    {', '.join(lhs)} -> {rhs}")

    # Index columns in the CSV's own order. The config list is a union across
    # domains, so using it would point Horizon at the wrong attributes.
    import pandas as pd
    file_cols = list(pd.read_csv(clean_csv, nrows=0).columns)
    horizon_cols = [c for c in file_cols if c in data_cols]
    horizon_lines = make_horizon_fds(fds, horizon_cols)
    print(f"  Horizon indexed FDs ({len(horizon_lines)}):")
    for line in horizon_lines:
        print(f"    {line}")

    if list_only:
        return

    horizon_out = os.path.join(out_dir, f"fds_{name}_indexed.txt")
    with open(horizon_out, "w", encoding="utf-8") as f:
        f.write("\n".join(horizon_lines) + "\n")
    print(f"  Written: {horizon_out}")

    holoclean_lines = make_holoclean_fds(fds)
    holoclean_out = os.path.join(out_dir, f"fds_{name}_holoclean.txt")
    with open(holoclean_out, "w", encoding="utf-8") as f:
        f.write("\n".join(holoclean_lines) + "\n")
    print(f"  Written: {holoclean_out}")

    uniclean_out = os.path.join(out_dir, f"uniclean_rules_{name}.py")
    write_uniclean_rules_py(uniclean_rules, uniclean_out, name)
    print(f"  Written: {uniclean_out}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Discover FDs with TANE and generate rule files.")
    parser.add_argument("--config", default=os.path.join(EXPERIMENTS_DIR, "config.json"))
    parser.add_argument("--datasets-dir", default=os.path.join(EXPERIMENTS_DIR, "experiment_datasets"),
                        help="Root of prepared experiment datasets")
    parser.add_argument("--out-dir", default=EXPERIMENTS_DIR,
                        help="Where to write output rule files")
    parser.add_argument("--list", action="store_true", help="Print FDs only, do not write files")
    parser.add_argument("--dataset", default=None,
                        help="Process only this dataset name (e.g. sample_full_0.05)")
    parser.add_argument("--source-clean", default=None,
                        help="Override clean CSV path for the dataset given by --dataset")
    parser.add_argument("--filter-datasets", default=None,
                        help="Comma-separated substrings; only datasets whose name contains at least one are processed")
    parser.add_argument("--only-fds-sources", action="store_true",
                        help="Mine FDs only from <datasets-dir>/fds/<name>/clean.csv (the full clean tables)")
    args = parser.parse_args()

    with open(args.config) as f:
        cfg = json.load(f)
    out_dir = args.out_dir
    os.makedirs(out_dir, exist_ok=True)
    datasets_dir = args.datasets_dir

    # Collect one clean CSV per unique dataset (one per slice, not per error rate)
    datasets_to_process = []

    eff_dir = os.path.join(datasets_dir, "effectiveness")
    if os.path.isdir(eff_dir) and not args.only_fds_sources:
        for slice_name in sorted(os.listdir(eff_dir)):
            slice_dir = os.path.join(eff_dir, slice_name)
            if not os.path.isdir(slice_dir):
                continue
            # POI slices: clean.csv directly inside
            clean = os.path.join(slice_dir, "clean.csv")
            if os.path.exists(clean):
                datasets_to_process.append((slice_name, clean))
                continue
            # Per-error-rate subdirs: process each subset separately
            for sub in sorted(os.listdir(slice_dir)):
                clean = os.path.join(slice_dir, sub, "clean.csv")
                if os.path.exists(clean):
                    datasets_to_process.append((f"{slice_name}_{sub}", clean))

    # All runtime datasets
    rt_dir = os.path.join(datasets_dir, "runtime")
    if os.path.isdir(rt_dir) and not args.only_fds_sources:
        for rt_name in sorted(os.listdir(rt_dir)):
            clean = os.path.join(rt_dir, rt_name, "clean.csv")
            if os.path.exists(clean):
                datasets_to_process.append((rt_name, clean))

    # FD-source datasets (full slices, no sampling — for stable FD discovery)
    fds_src_dir = os.path.join(datasets_dir, "fds")
    if os.path.isdir(fds_src_dir):
        for fds_name in sorted(os.listdir(fds_src_dir)):
            clean = os.path.join(fds_src_dir, fds_name, "clean.csv")
            if os.path.exists(clean):
                datasets_to_process.append((fds_name, clean))

    if not datasets_to_process:
        print("No datasets found — run prepare_datasets.py first.")
        sys.exit(1)

    if args.dataset:
        datasets_to_process = [(n, p) for n, p in datasets_to_process if n == args.dataset]
        if not datasets_to_process and not args.source_clean:
            print(f"Dataset '{args.dataset}' not found.")
            sys.exit(1)
        if args.source_clean:
            # Use the provided clean CSV regardless of auto-discovery
            datasets_to_process = [(args.dataset, args.source_clean)]

    if args.filter_datasets:
        filters = [f.strip() for f in args.filter_datasets.split(",") if f.strip()]
        datasets_to_process = [(n, p) for n, p in datasets_to_process
                               if any(f in n for f in filters)]
        if not datasets_to_process:
            print(f"No datasets matched filter '{args.filter_datasets}'.")
            sys.exit(1)

    for name, clean_csv in datasets_to_process:
        process_dataset(name, clean_csv, cfg, out_dir, args.list)

    print("\nDone.")


if __name__ == "__main__":
    main()
