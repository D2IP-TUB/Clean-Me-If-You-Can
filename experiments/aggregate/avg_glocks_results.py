"""
Reads the three iteration results for each dataset under the glocks results
directory and prints the averaged scores per dataset.
"""

import json
import os
import sys
from collections import defaultdict

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from paths import REPO_ROOT, system_results_dir  # noqa: E402

RESULTS_DIR_GLOCKS = system_results_dir("glocks")
RESULTS_DIR_RERUN = os.path.join(RESULTS_DIR_GLOCKS, "glocks")

# (slice, error_rate) groups to exclude entirely
EXCLUDE_GROUPS = {
    # ("de", 0.49),
}

SCORE_COLS = [
    "det_precision",
    "det_recall",
    "det_f1",
    "cor_precision",
    "cor_recall",
    "cor_f1",
    "runtime_seconds",
    "peak_memory_mb",
]

RENAME_COLS = {
    "cor_precision": "corr_precision",
    "cor_recall": "corr_recall",
    "cor_f1": "corr_f1",
}


def _require_results_dir(path: str) -> None:
    if not os.path.isdir(path):
        print(
            f"ERROR: results directory not found: {path}\n"
            "Run the experiment harness first (experiments/harness/run_all_experiments.sh),\n"
            "or set RESULTS_DIR env var to point at an existing results tree.\n"
            "See experiments/README.md for environment variable overrides.",
            file=sys.stderr,
        )
        sys.exit(1)


def main():
    _require_results_dir(RESULTS_DIR_GLOCKS)
    # Group run dirs by (slice, error_rate) using run_config.json.
    # Scan RESULTS_DIR_GLOCKS first, then overlay with RESULTS_DIR_RERUN (higher priority).
    runs: dict[tuple, list[tuple[str, str]]] = defaultdict(list)

    for search_dir in [RESULTS_DIR_GLOCKS, RESULTS_DIR_RERUN]:
        if not os.path.isdir(search_dir):
            continue
        for entry in sorted(os.listdir(search_dir)):
            full_path = os.path.join(search_dir, entry)
            if not os.path.isdir(full_path):
                continue
            cfg_path = os.path.join(full_path, "run_config.json")
            csv_path = os.path.join(full_path, "summary.csv")
            if not os.path.isfile(cfg_path) or not os.path.isfile(csv_path):
                continue
            with open(cfg_path) as f:
                cfg = json.load(f)
            key = (cfg["slice"], cfg["error_rate"])
            if key in EXCLUDE_GROUPS:
                continue
            runs[key].append((entry, csv_path, search_dir))

    # For each group, if any runs come from RESULTS_DIR_RERUN, discard RESULTS_DIR_GLOCKS runs.
    for key in runs:
        rerun_entries = [(e, p, d) for e, p, d in runs[key] if d == RESULTS_DIR_RERUN]
        if rerun_entries:
            runs[key] = rerun_entries

    # Keep only the 3 most recent per group
    for key in runs:
        if len(runs[key]) > 3:
            runs[key] = sorted(runs[key], key=lambda x: x[0])[-3:]

    records = []
    for (slice_name, error_rate), entries in sorted(
        runs.items(), key=lambda x: (x[0][0], str(x[0][1]))
    ):
        csv_files = [csv_path for _, csv_path, _d in entries]
        dfs = [pd.read_csv(f) for f in csv_files]
        combined = pd.concat(dfs, ignore_index=True)
        avg = combined[SCORE_COLS].mean()

        if str(error_rate) == "native":
            label = slice_name
        else:
            label = f"{slice_name}_{float(error_rate):.2f}"

        row = {
            "dataset": label,
            "slice": slice_name,
            "error_rate": error_rate,
            "n_iterations": len(csv_files),
        }
        row.update(avg.rename(RENAME_COLS).to_dict())
        records.append(row)
        display_cols = [RENAME_COLS.get(c, c) for c in SCORE_COLS]
        print(f"\n=== {label} ({len(csv_files)} iteration(s)) ===")
        for col in display_cols:
            print(f"  {col:20s}: {row[col]:.6f}")

    print("\n\n--- Summary Table ---")
    summary_df = pd.DataFrame(records)
    print(summary_df.to_string(index=False, float_format=lambda x: f"{x:.6f}"))

    out_path = os.path.join(REPO_ROOT, "glocks_avg_results.csv")
    summary_df.to_csv(out_path, index=False)
    print(f"\nSaved to {out_path}")


if __name__ == "__main__":
    main()
