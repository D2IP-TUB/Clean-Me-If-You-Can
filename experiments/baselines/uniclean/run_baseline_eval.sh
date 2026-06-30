#!/usr/bin/env bash
# Re-evaluate every baseline system's cleaned CSV against the same dirty/clean ground truth
# and write per-(system, dataset) metrics under baseline_cleaning_systems_results/.
#
# Usage:
#   chmod +x run_baseline_eval.sh
#   ./run_baseline_eval.sh                       # all 5 systems × 4 datasets
#   ./run_baseline_eval.sh baran holoclean       # subset of systems
#   DATASETS="1_hospital 4_rayyan" ./run_baseline_eval.sh   # subset of datasets
#
# The script iterates baseline_cleaned_data/original_cleaned_data/<system>/<dataset>_cleaned_by_<system>.csv,
# pairs it with datasets_and_rules/original_datasets/<dataset>/{dirty,clean}_index.csv, and feeds
# all three to evaluate_result.py.
#
# 5_tax and 6_soccer are skipped by default because each baseline ran on a different
# subset size (e.g. baran on 10k rows, holoclean on 200k) so the dirty/clean ground truth
# files don't always line up. Add them via the DATASETS env override if you have the
# matching subset prepared in datasets_and_rules/original_datasets/.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

BASELINE_DIR="baseline_cleaned_data/original_cleaned_data"
DATA_DIR="datasets_and_rules/original_datasets"
OUTPUT_DIR="baseline_cleaning_systems_results/original_datasets"

ALL_SYSTEMS=("baran" "bigdansing" "holistic" "holoclean" "horizon")
DEFAULT_DATASETS=("1_hospital" "2_flights" "3_beers" "4_rayyan")

# CLI: positional args = systems
if [ "$#" -gt 0 ]; then
    SYSTEMS=("$@")
else
    SYSTEMS=("${ALL_SYSTEMS[@]}")
fi

# Env override: DATASETS="1_hospital 4_rayyan" ./run_baseline_eval.sh
if [ -n "${DATASETS:-}" ]; then
    # shellcheck disable=SC2206
    DS_LIST=($DATASETS)
else
    DS_LIST=("${DEFAULT_DATASETS[@]}")
fi

mse_attrs_for() {
    case "$1" in
        1_hospital) echo "Score" ;;
        3_beers)    echo "abv ibu" ;;
        5_tax)      echo "rate" ;;
        *)          echo "" ;;
    esac
}

# Some baseline systems emit cleaned CSVs with column-name typos that don't match the
# ground-truth clean_index.csv (e.g. 'jounral_abbreviation' instead of 'journal_abbreviation'
# in baran/bigdansing rayyan output). We rename the cleaned CSV's columns to match the
# clean.csv schema in a tmp file before evaluation; the original file on disk is not touched.
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

sanitize_cleaned() {
    # args: <cleaned_csv> <clean_csv> ; prints the path to a tmp copy of the cleaned CSV
    # (always copied — evaluate_result.py rewrites cleaned_path in-place via
    # format_empty_data, so we never want it to touch the file shipped in the repo).
    local cleaned="$1" clean="$2"
    python3 - "$cleaned" "$clean" "$TMP_DIR" <<'PY'
import sys, os, shutil, pandas as pd
cleaned_path, clean_path, tmp_dir = sys.argv[1:4]
cl_cols = pd.read_csv(clean_path, nrows=0).columns.tolist()
cd_cols = pd.read_csv(cleaned_path, nrows=0).columns.tolist()

out = os.path.join(tmp_dir, os.path.basename(cleaned_path))

# Case 0: columns already aligned — just copy verbatim so the original is never touched.
if cl_cols == cd_cols:
    shutil.copyfile(cleaned_path, out)
    print(out)
    sys.exit(0)

df = pd.read_csv(cleaned_path, dtype=str, keep_default_na=False)

# Case 1: same number of columns, same order, just typos (e.g. journal vs jounral)
if len(cl_cols) == len(cd_cols):
    rename_map = {old: new for old, new in zip(cd_cols, cl_cols) if old != new}
    if rename_map:
        df.rename(columns=rename_map, inplace=True)
        df.to_csv(out, index=False)
        print(out)
        sys.exit(0)

# Case 2: cleaned is missing the 'index' column entirely (e.g. bigdansing 3_beers).
# Restore it by row order (1-based) and reorder columns to match clean.csv.
if 'index' in cl_cols and 'index' not in df.columns:
    other_cl = [c for c in cl_cols if c != 'index']
    other_cd = [c for c in df.columns]
    if sorted(other_cl) == sorted(other_cd):
        df['index'] = range(1, len(df) + 1)
        df = df[cl_cols]
        df.to_csv(out, index=False)
        print(out)
        sys.exit(0)

# Fallback: column sets just don't match — copy as-is and let evaluate_result.py error out
shutil.copyfile(cleaned_path, out)
print(out)
PY
}

ok=0
fail=0
skip=0

for system in "${SYSTEMS[@]}"; do
    for ds in "${DS_LIST[@]}"; do
        cleaned_csv="$BASELINE_DIR/$system/${ds}_cleaned_by_${system}.csv"
        dirty_path="$DATA_DIR/$ds/dirty_index.csv"
        clean_path="$DATA_DIR/$ds/clean_index.csv"

        if [ ! -f "$cleaned_csv" ]; then
            echo "[skip] $system / $ds — missing cleaned: $cleaned_csv"
            skip=$((skip + 1))
            continue
        fi
        if [ ! -f "$dirty_path" ] || [ ! -f "$clean_path" ]; then
            echo "[skip] $system / $ds — missing dirty/clean ground truth"
            skip=$((skip + 1))
            continue
        fi

        out_dir="$OUTPUT_DIR/$system/${ds}_ori"
        mkdir -p "$out_dir"
        log_path="$out_dir/output.log"

        mse_attr="$(mse_attrs_for "$ds")"
        cleaned_for_eval="$(sanitize_cleaned "$cleaned_csv" "$clean_path")"
        echo "[run ] $system / $ds → $log_path"

        if [ -n "$mse_attr" ]; then
            python3 evaluate_result.py \
                --dirty_path "$dirty_path" \
                --clean_path "$clean_path" \
                --cleaned_path "$cleaned_for_eval" \
                --output_path "$OUTPUT_DIR/$system" \
                --task_name "${ds}_ori" \
                --index_attribute "index" \
                --mse_attributes $mse_attr \
                --elapsed_time "0.0" > "$log_path" 2>&1 \
                && { echo "       OK"; ok=$((ok + 1)); } \
                || { echo "       FAIL — see $log_path"; fail=$((fail + 1)); }
        else
            python3 evaluate_result.py \
                --dirty_path "$dirty_path" \
                --clean_path "$clean_path" \
                --cleaned_path "$cleaned_for_eval" \
                --output_path "$OUTPUT_DIR/$system" \
                --task_name "${ds}_ori" \
                --index_attribute "index" \
                --elapsed_time "0.0" > "$log_path" 2>&1 \
                && { echo "       OK"; ok=$((ok + 1)); } \
                || { echo "       FAIL — see $log_path"; fail=$((fail + 1)); }
        fi
    done
done

echo
echo "==== summary ===="
echo "OK:    $ok"
echo "FAIL:  $fail"
echo "SKIP:  $skip"
echo "Per-baseline results live under $OUTPUT_DIR/<system>/<dataset>_ori/output.log"
[ "$fail" -eq 0 ]
