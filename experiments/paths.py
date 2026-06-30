"""Repo-relative paths for experiment scripts.

All defaults are derived from the repository layout. Override with environment
variables when data or results live elsewhere:

  REPO_ROOT              — repository root (parent of experiments/)
  DATASETS_DIR           — source merged CSVs for prepare_datasets.py
  EXPERIMENT_DATASETS_DIR — prepared harness datasets
  RESULTS_DIR            — harness per-run outputs
  ANALYSIS_ERRORS_DIR    — dataset_analysis error-type outputs
"""

import os

_EXPERIMENTS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.normpath(os.environ.get("REPO_ROOT", os.path.join(_EXPERIMENTS_DIR, "..")))

EXPERIMENTS_DIR = os.path.join(REPO_ROOT, "experiments")
HARNESS_DIR = os.path.join(EXPERIMENTS_DIR, "harness")
AGGREGATE_DIR = os.path.join(EXPERIMENTS_DIR, "aggregate")
RULES_FDS_DIR = os.path.join(EXPERIMENTS_DIR, "rules", "fds")
DATA_DIR = os.path.join(REPO_ROOT, "data")

EXPERIMENT_DATASETS_DIR = os.environ.get(
    "EXPERIMENT_DATASETS_DIR",
    os.path.join(HARNESS_DIR, "experiment_datasets"),
)
RESULTS_DIR = os.environ.get(
    "RESULTS_DIR",
    os.path.join(HARNESS_DIR, "results"),
)
MANUSCRIPT_RESULTS_DIR = os.path.join(EXPERIMENTS_DIR, "manuscript_results")

DEFAULT_SOURCE_DATASETS_DIR = os.environ.get(
    "DATASETS_DIR",
    os.path.join(DATA_DIR, "merged_named"),
)

EXTERNAL_BASELINE_RESULTS_DIR = os.path.join(
    REPO_ROOT,
    "dataset_analysis",
    "external",
    "baselines",
    "experiments",
    "results",
)

ANALYSIS_ERRORS_DIR = os.environ.get(
    "ANALYSIS_ERRORS_DIR",
    os.path.join(REPO_ROOT, "dataset_analysis", "analysis_out_errors"),
)


def system_results_dir(system: str) -> str:
    """Harness results subdirectory for a baseline system."""
    return os.path.join(RESULTS_DIR, system)


def cell_error_types_csv(poi_slice: str, version: str) -> str:
    """Path to cell_error_types.csv for a POI slice analysis run."""
    return os.path.join(ANALYSIS_ERRORS_DIR, version, "cell_error_types.csv")
