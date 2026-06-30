# UnicleanResult: A Benchmark Repository for Data Cleaning Performance

# Overview
**UnicleanResult** is a repository dedicated to showcasing the performance of Uniclean, a state-of-the-art data cleaning system. While we cannot open source the system code due to commercial confidentiality, this repository provides comprehensive performance metrics and detailed cleaning results, establishing a benchmark for data cleaning. This enables researchers to evaluate and compare the performance of their own cleaning systems on various real-world datasets. The benchmark allows for direct comparisons between Uniclean’s performance, other baseline cleaning systems, and new approaches, offering a standardized framework for assessing data cleaning effectiveness across diverse datasets.

The repository includes:
- **Real-world native datasets** used by Uniclean for testing.
- **Cleaned datasets** that have been processed by Uniclean.
- **Cleaning logs** generated during the Uniclean cleaning process.
- **Baseline performance logs** for comparison with Uniclean’s results.
- An **evaluation script** (`evaluate_result.py`) that calculates various performance metrics, providing an objective assessment of the cleaning effectiveness.

# Important Note on Missing Value Representation

**All CSV files in this repository (clean / dirty / cleaned) use the literal string `empty` to denote missing cells.** It is a placeholder, **not** a meaningful value. When evaluating Uniclean's outputs against your own pipeline, you **must** normalize this token before comparison, otherwise metrics will be misleading.

Recommended pre-processing for any consumer of these files:
```python
import pandas as pd
df = pd.read_csv(path, keep_default_na=False)
# Treat 'empty' (and other common placeholders) as true missing
df.replace({'empty': '', 'nan': '', 'NULL': '', 'NaN': '', 'None': ''}, inplace=True)
```

Notes:
- The rayyan dataset additionally uses `-1` in `article_jvolumn` / `article_jissue` as a disguised-missing placeholder (kept for backward compatibility with the original release).
- The index column is `index` (integer, 1-based) and aligns row-by-row across `clean_index.csv` / `dirty_index.csv` / `<dataset>_cleaned_by_uniclean.csv`.

# Dataset Information

The following table summarizes the datasets used in this repository, including their error types and dimensions:

| Dataset  | Error Type     | Shape        | Link                                                                             |
|----------|----------------|--------------|----------------------------------------------------------------------------------|
| Hospital | T, VAD         | 1,000 × 20   | [datasets_and_rules/original_datasets/1_hospital](datasets_and_rules/original_datasets/1_hospital) |
| Flights  | MV, FI, VAD    | 2,376 × 7    | [datasets_and_rules/original_datasets/2_flights](datasets_and_rules/original_datasets/2_flights)   |
| Beers    | MV, FI, VAD    | 2,410 × 11   | [datasets_and_rules/original_datasets/3_beers](datasets_and_rules/original_datasets/3_beers)       |
| Rayyan   | MV, T, FI, VAD | 1,000 × 11   | [datasets_and_rules/original_datasets/4_rayyan](datasets_and_rules/original_datasets/4_rayyan)     |
| Tax      | T, FI, VAD     | 200,000 × 15 | [datasets_and_rules/original_datasets/5_tax](datasets_and_rules/original_datasets/5_tax)           |
| Soccer   | T, VAD         | 200,000 × 15 | [datasets_and_rules/original_datasets/6_soccer](datasets_and_rules/original_datasets/6_soccer)     |

**Error Type Abbreviations:**
- **T**: Typographical errors
- **MV**: Missing values
- **FI**: Format inconsistencies
- **VAD**: Violated attribute dependencies


# Setup

## Prerequisites

- **Python ≥ 3.8** (tested on 3.8 / 3.10)
- **Java JDK 8 or 11** (required by PySpark; verify with `java -version`)
- ~4 GB free RAM (PySpark drivers default to 8 GB heap; lower in main scripts if needed)

## Install dependencies

```bash
# (recommended) create a clean env first
python3 -m venv .venv && source .venv/bin/activate
# then install
pip install -r uniclean_cleaners/requirements.txt
```

The pinned dependencies live in [`uniclean_cleaners/requirements.txt`](uniclean_cleaners/requirements.txt) (key entries: `pyspark~=3.1.1`, `pandas~=1.5.3`, `numpy~=1.24.3`, `scikit-learn~=1.3.0`, `networkx~=3.1`).

## Smoke test

After install, the fastest way to confirm everything works is to re-evaluate the prebuilt cleaned files (Stage 2 only — no PySpark cleaning needed):

```bash
chmod +x run.sh
./run.sh
```

If you see `Completed processing for dataset: ...` for all four datasets and `Uniclean_results/original_error_results/<X>/output.log` is populated, the environment is good.

# Reproducing Uniclean Results

The pipeline is split into two stages so you can run them independently:

## Stage 1 — Run the cleaning pipeline

```bash
chmod +x uniclean_cleaners/run_clean.sh
./uniclean_cleaners/run_clean.sh
```

What it does:
- Iterates over `1_hospital`, `2_flights`, `3_beers`, `4_rayyan` (defaults; `5_tax` / `6_soccer` are commented out due to ~3h+ runtime each — uncomment in the script to enable).
- Runs the corresponding `uniclean_cleaners/main_<dataset>.py` for each, reading `dirty_index.csv` / `clean_index.csv` from `datasets_and_rules/original_datasets/<dataset>/`.
- Writes the cleaned CSV to `Uniclean_cleaned_data/original_error_cleaned_data/<dataset>_cleaned_by_uniclean.csv`.
- Saves per-dataset stdout/stderr to `Uniclean_cleaner_workflow_logs/original_error_cleaner_workflow_logs/<dataset>/clean_run.log`.
- After cleaning succeeds, automatically invokes `./run.sh` to evaluate the freshly produced cleaned files.

Optional flags:
```bash
./uniclean_cleaners/run_clean.sh hospital flights   # only run a subset
FORCE=1 ./uniclean_cleaners/run_clean.sh            # rerun even if cleaned/result already exists
PYTHON=python3.10 ./uniclean_cleaners/run_clean.sh  # pin a specific interpreter
```

## Stage 2 — Evaluate cleaning performance

```bash
chmod +x run.sh
./run.sh
```

Reads the cleaned files in `Uniclean_cleaned_data/original_error_cleaned_data/` (either freshly produced by Stage 1, or the prebuilt ones shipped in this repo) and compares against the corresponding `clean_index.csv`. Per-dataset metrics are written to `Uniclean_results/original_error_results/<dataset>/output.log`.

`run.sh` is a thin wrapper around `evaluate_result.py` and can be executed standalone if you only want to re-score existing cleaned files.

## Expected baseline (Uniclean default config)

The metrics below come from running the default scripts on the four primary datasets. Use them as a sanity check after cloning:

| Dataset    | Accuracy | Recall | F1     | EDR    | R-EDR  |
|------------|---------:|-------:|-------:|-------:|-------:|
| hospital   | 0.951    | 0.831  | 0.887  | +0.788 | +0.754 |
| flights    | 0.681    | 0.630  | 0.655  | +0.519 | +0.043 |
| beers      | 0.839    | 0.835  | 0.837  | +0.832 | +0.773 |
| rayyan     | 0.938    | 0.905  | 0.922  | +0.900 | +0.883 |

If any EDR drifts more than a few hundredths, double-check that you ran on the `*_index.csv` variants (the same `index` column that's used as the join key during evaluation).

## Running on your own data

Each `main_<dataset>.py` accepts the same set of CLI flags so you can repurpose the cleaners for new datasets:

| Flag              | Default     | Meaning |
|-------------------|-------------|---------|
| `--file_load`     | (per-script) | Path to the dirty CSV |
| `--clean_path`    | (per-script) | Path to the ground-truth clean CSV |
| `--save_path`     | `TestDataset/result/` | Directory where the cleaned CSV is written |
| `--table_name`    | `<dataset>` | Subfolder name + filename prefix for the cleaned CSV |
| `--index_col`     | `index`     | Name of the index column in your dirty/clean CSV. If different (e.g. `ID`) the scripts will rename it transparently |
| `--missing_token` | `empty`     | Placeholder string used to denote missing cells in the cleaned CSV (must match how your `clean.csv` represents missingness). See the *Important Note* above |

Example: cleaning a custom hospital-like dataset whose index column is `ID` and which uses the bare empty string as the missing marker:

```bash
python3 uniclean_cleaners/main_hospitals.py \
    --file_load   path/to/dirty.csv \
    --clean_path  path/to/clean.csv \
    --save_path   ./out/ \
    --table_name  myhospital \
    --index_col   ID \
    --missing_token ""
```

# Comparing with Baseline Cleaning Systems

This repository ships **all five baseline systems' cleaned outputs and evaluation logs in-place**, so you can do head-to-head comparisons without setting up any of them yourself:

```
baseline_cleaned_data/original_cleaned_data/
├── baran/         <dataset>_cleaned_by_baran.csv
├── bigdansing/    <dataset>_cleaned_by_bigdansing.csv
├── holistic/      <dataset>_cleaned_by_holistic.csv
├── holoclean/     <dataset>_cleaned_by_holoclean.csv
└── horizon/       <dataset>_cleaned_by_horizon.csv

baseline_cleaning_systems_logs/original_datasets/    # raw stdout/stderr from each baseline run
baseline_cleaning_systems_results/original_datasets/<system>/<dataset>_ori/
                                                     # per-(system, dataset) metrics, diff CSVs, evaluation .txt
```

## Re-evaluate every baseline on your machine

```bash
chmod +x run_baseline_eval.sh
./run_baseline_eval.sh                          # all 5 systems × 4 datasets
./run_baseline_eval.sh baran holoclean          # subset of systems (positional args)
DATASETS="1_hospital 4_rayyan" ./run_baseline_eval.sh   # subset of datasets (env var)
```

The script feeds each baseline's cleaned CSV plus the matching `dirty_index.csv` / `clean_index.csv` into the same `evaluate_result.py` used for Uniclean. Per-(system, dataset) metrics land in `baseline_cleaning_systems_results/original_datasets/<system>/<dataset>_ori/output.log`. Column-name typos and missing `index` columns observed in some baseline outputs are auto-normalized; the original cleaned CSVs on disk are not modified.

`5_tax` / `6_soccer` are skipped by default because each baseline ran on a different subset size (10k / 200k / full) — pass them explicitly via `DATASETS=...` if you have prepared the matching ground-truth subset.

## EDR head-to-head (as shipped)

| Dataset    | baran  | bigdansing | holistic | holoclean | horizon | **Uniclean** |
|------------|-------:|-----------:|---------:|----------:|--------:|-------------:|
| 1_hospital | +0.417 | −0.079     | −0.039   | +0.010    | +0.057  | **+0.788**   |
| 2_flights  | +0.448 | −0.138     | −0.112   | −1.418    | +0.115  | **+0.519**   |
| 3_beers    | +0.787 | −0.040     | −0.011   | −3.829    | +0.003  | **+0.832**   |
| 4_rayyan   | −0.682 | −2.205     | −1.910   | −5.444    | −0.520  | **+0.900**   |

(Negative EDR = the baseline introduces more errors than it fixes. Numbers are reproducible with `./run_baseline_eval.sh`.)

## Running the actual baseline cleaning code

If you want to reproduce the cleaned CSVs from scratch — i.e. **run the baseline systems themselves** end-to-end on the dirty data — see the companion repository:

**[qzkinhit/MDCBaseline](https://github.com/qzkinhit/MDCBaseline)** — a unified runner for the five baseline cleaning systems (baran / bigdansing / holistic / holoclean / horizon). All baselines share a single Python environment so you can install once and run all of them; the dirty-data inputs and dataset rules are identical to the ones shipped here.

After you produce a fresh cleaned CSV with MDCBaseline, you can drop it under `baseline_cleaned_data/original_cleaned_data/<system>/` (using the same naming convention) and re-run `./run_baseline_eval.sh` to score it against this benchmark.

# Cleaners  Library Overview

## uniclean_cleaners/SampleScrubber
**Sample Cleaning Tools**
- **ModuleTest**: Unit tests for modules.
- **util**
    - `distance.py`: Computes distances between values.
    - `getNum.py`: Evaluates cleaning accuracy.
- `uniop_model.py`: Rule mining model.
- `param_builder.py`: Constructs rule parameters.
- `param_selector.py`: Selects optimal parameters.
- **cleaners**
    - `single.py`: Single-attribute operators.
    - `multiple.py`: Multi-attribute relational operators.
    - `soft.py`: Experimental or soft operators.
    - `clean_penalty.py`: Calculates cleaning costs (edit distance, semantic penalties, Jaccard penalties).


## Configuration scripts in ./uniclean_cleaners
- `main_<dataset>.py` (`main_hospitals.py`, `main_flights.py`, `main_beers.py`, `main_rayyan.py`, `main_tax.py`, `main_soccer.py`, `main_commercial.py`): per-dataset command-line entry points. Each carries its dataset-specific cleaner rule list and exposes the same CLI flags (see *Running on your own data* above).
- `run_clean.sh`: one-shot driver that runs Stage 1 cleaning + Stage 2 evaluation across all default datasets.
- `Clean.py`: core orchestration logic — cycle detection, level scheduling, per-block PySpark cleaning.
- `util.py`: shared evaluation helpers (`evaluate_cleaning_performance`, `normalize_cleaned_against_clean`, `save_cleaned_data`).
- `logsetting.py`: log file configuration shared by all `main_<dataset>.py` entries.
- `requirements.txt`: pinned Python dependencies (see *Setup* above).
- `CleanerPlantuml.svg`: flowchart visualizing the cleaning pipeline.

# Repository Structure
- `datasets_and_rules/`:real word datasets、inject error datasets and their cleaning rules:
  - `artificial_error_datasets/`:Contains datasets with artificially injected errors in eight different proportions (ranging from 0.25% to 2%) for controlled experiments and benchmarking. This folder also includes the *BART script* used for injecting these errors into the datasets.
  - `original_datasets/`: Contains real-world datasets in their native (uncleaned) form.
- `Uniclean_cleaned_data/`: Datasets that have been cleaned by Uniclean.
  - `artificial_error_cleaned_data/`:Uniclean-cleaned versions of the artificially injected error datasets.
  - `original_error_cleaned_data/`:Uniclean-cleaned  versions of the real-world datasets containing native errors.
- `Uniclean_cleaner_workflow_logs/`: Logs generated during the Uniclean cleaning process and Cleaner attributes dependencies for each dataset.
  - `artificial_error_cleaner_workflow_logs/`: Step-by-step workflow logs for datasets that had artificial errors (in different proportions).
  - `original_error_cleaner_workflow_logs/`:Step-by-step workflow logs for real-world datasets with native errors.
- `Uniclean_results/`: Contains the final outputs and performance metrics from Uniclean’s data cleaning for each dataset.
  - `artificial_error_results/`:Final outputs and metrics (e.g., accuracy, F1 score) from Uniclean’s cleaning for datasets that had artificially injected errors in different proportions.
  - `original_error_results/`:Final outputs and metrics from Uniclean’s cleaning for real-world datasets containing native errors.
- `baseline_cleaning_systems_logs/`: Logs documenting the performance of baseline systems on the same datasets, enabling a direct comparison with Uniclean’s results.
  - `artificial_error_datasets/`:Stores log files showing how baseline systems perform on datasets with artificial errors.
    - **File Naming Format**: `[dataset_name]_[cleaning_system_name]_nwcpk_[error_proportion].log`
    - Example: `1_hospitals_raha_baran_nwcpk_1.log`
  - `original_datasets/`:Stores log files showing how baseline systems perform on real-world datasets with native errors.
    - **File Naming Format**: `[dataset_name]_ori_[cleaning_system_name]_[the actual size of the dataset (if it is not in its original size)].log`
    - Example: `1_hospital_ori_baran.log`
- `baseline_cleaning_systems_results/`: Final results and performance metrics of baseline systems on the same datasets.
  - `artificial_error_datasets/`:Contains overall performance metrics (e.g., accuracy, recall, F1 score) of baseline systems on artificially injected error datasets.
    - **Folder Naming Format**: `[dataset_name]_nwcpk_[error_proportion]`
    - Example: `1_hospitals_nwcpk_1`
  - `original_datasets/`:Contains overall performance metrics of baseline systems on real-world datasets with native errors.
    - **Folder Naming Format**: `[dataset_name]_[the actual size of the dataset (if it is not in its original size)]_ori`
    - Example: `1_hospital_ori`
- `baseline_cleaned_data/`:Datasets that have been cleaned by baseline systems.
  - `artificial_error_datasets/`:Baseline-cleaned versions of artificially injected error datasets.
    - **File Naming Format**: `[dataset_name]_[error_proportion]_cleaned_by_[cleaning_system_name].csv`
    - Example: `1_hospitals_1_cleaned_by_baran.csv`
  - `original_datasets/`:Baseline-cleaned versions of real-world datasets with native errors.
    - **File Naming Format**: `[dataset_name][the actual size of the dataset (if it is not in its original size)]_cleaned_by_[cleaning_system_name].csv`
    - Example: `1_hospital_cleaned_by_baran.csv`
- `evaluate_result.py`: A script that computes performance metrics for data cleaning, such as accuracy, recall, F1 score, and error reduction rate, allowing comprehensive evaluation of data cleaning effectiveness.
- `get_holoclean_table.py` A script that transforms datasets into the Holoclean-compatible input CSV format. It transposes data and ensures compliance with Holoclean's required schema for further data cleaning tasks.
- `get_error_num.py` A script that compares dirty data with clean data to compute the number of erroneous cells and entries. It provides a detailed analysis of the extent of errors, facilitating error quantification and benchmarking.