# Experiments (Section 6)

Benchmark harness and baseline implementations for evaluating data cleaning systems
on the address datasets.

---

## Layout

```
experiments/
├── harness/              Main orchestrator (prepare → run → collect)
├── baselines/            Vendored baseline code
│   ├── datawig/          Column imputation baseline
│   ├── glocks/           PCI LLM toolkit
│   ├── holoclean/        HoloClean Python package
│   ├── horizon/          Java Horizon repairer
│   ├── raha/             Raha (detection) + Baran (correction)
│   ├── tane/             TANE FD discovery
│   └── uniclean/         UniClean address benchmark scripts
├── prompts/glocks/       Canonical Glocks LLM prompts
├── rules/fds/            Pre-generated FD files (checked in; regenerated at run time)
└── aggregate/            Post-hoc scripts for paper tables/plots
```

---

## Prerequisites

Install each prerequisite that corresponds to the baselines you intend to run.
The harness skips disabled systems (set `"enabled": false` in `config.json`).

### Python environments

Each baseline has different (and often conflicting) dependency versions.
Use a **separate virtualenv per baseline**.

```bash
# Example: create envs for Raha/Baran and DataWig
python3 -m venv baselines/raha/.venv
baselines/raha/.venv/bin/pip install -r baselines/raha/requirements.txt
baselines/raha/.venv/bin/pip install -e baselines/raha/

python3 -m venv baselines/datawig/.venv
baselines/datawig/.venv/bin/pip install datawig
```

The harness runner scripts locate baselines relative to `baselines_dir` in
`config.json` and invoke each system's own Python interpreter. If a system's
venv is not at the expected path, set it in `config.json` under
`systems.<name>.python` (if supported by that runner).

> **Tip:** The `run_all_experiments.sh` `--system <name>` flag lets you run a
> single baseline at a time during setup and testing.

### Per-baseline setup

#### DataWig

```bash
python3 -m venv baselines/datawig/.venv
baselines/datawig/.venv/bin/pip install datawig
```

No other external dependencies.

#### Raha + Baran

```bash
python3 -m venv baselines/raha/.venv
source baselines/raha/.venv/bin/activate
pip install -r baselines/raha/requirements.txt
pip install -e baselines/raha/
deactivate
```

#### TANE (used internally by `prepare_rules.py`)

```bash
python3 -m venv baselines/tane/.venv
baselines/tane/.venv/bin/pip install -r baselines/tane/requirements.txt
```

#### HoloClean (requires PostgreSQL)

1. **Install PostgreSQL 9.4+** (tested on 12–15):

   ```bash
   # Ubuntu
   sudo apt-get install postgresql postgresql-contrib
   # macOS (Homebrew)
   brew install postgresql@15
   ```

2. **Create the database and user:**

   ```bash
   psql -U postgres <<'SQL'
   CREATE DATABASE holo;
   CREATE USER holocleanuser;
   ALTER USER holocleanuser WITH PASSWORD 'abcd1234';
   GRANT ALL PRIVILEGES ON DATABASE holo TO holocleanuser;
   \c holo
   ALTER SCHEMA public OWNER TO holocleanuser;
   SQL
   ```

3. **Install the HoloClean Python package:**

   ```bash
   python3 -m venv baselines/holoclean/.venv
   source baselines/holoclean/.venv/bin/activate
   pip install -r baselines/holoclean/holoclean/requirements.txt
   deactivate
   ```

4. **Configure `config.json`:**
   Set `systems.holoclean.db_name`, `db_user`, `db_host`, `db_port`, and
   export the password:
   ```bash
   export HOLOCLEAN_DB_PWD=abcd1234
   ```

#### Horizon (requires Java JDK)

1. **Install Java JDK 11+:**
   ```bash
   # Ubuntu
   sudo apt-get install default-jdk
   # macOS (Homebrew)
   brew install openjdk@17
   ```
   Verify: `javac -version`

2. **Download the required JAR** (not shipped in the repo):
   ```bash
   curl -L -o baselines/horizon/commons-collections4-4.3.jar \
     https://repo1.maven.org/maven2/org/apache/commons/commons-collections4/4.3/commons-collections4-4.3.jar
   ```
   The harness compiles Horizon's Java sources automatically on first run.

#### Glocks (requires an LLM API key)

```bash
python3 -m venv baselines/glocks/.venv
baselines/glocks/.venv/bin/pip install -r \
    baselines/glocks/pci-llm-toolkit/error-detection-cleaning-llm/requirements.txt
```

Export your API key before running (the key name is configurable):

```bash
export GOOGLE_API_KEY=your-key-here
```

See `prompts/glocks/prompt_notes.txt` for prompt documentation and
`config.json → systems.glocks.prompt_id_map` for the per-slice prompt IDs.

#### UniClean (requires PySpark)

PySpark requires Java 8 or 11 on the PATH. Then:

```bash
python3 -m venv baselines/uniclean/.venv
baselines/uniclean/.venv/bin/pip install -r \
    baselines/uniclean/uniclean_cleaners/requirements.txt
```

The harness sets `PYSPARK_PYTHON` to this venv's interpreter automatically.

---

## Configuration

Edit `harness/config.json` before the first run. All paths are relative to
`experiments/harness/` unless they start with `..` or `/`.

**Required edits:**

| Key | Default | What to set |
|-----|---------|-------------|
| `paths.datasets_dir` | `../../data/merged_named` | Path to the `merged_named/` CSV directory from the dataset pipeline |
| `systems.holoclean.db_*` | `holo` / `holocleanuser` / `localhost:5436` | Your PostgreSQL connection details |
| `systems.glocks.api_key_env` | `GOOGLE_API_KEY` | Env var name holding your LLM API key |

**Optional tuning:**

| Key | Default | Purpose |
|-----|---------|---------|
| `paths.results_dir` | `./results` | Where per-run output CSVs are written |
| `paths.experiment_datasets_dir` | `./experiment_datasets` | Prepared effectiveness/runtime datasets |
| `experiment.n_effectiveness_runs` | `1` | How many repetitions per effectiveness experiment |
| `experiment.n_runtime_runs` | `1` | How many repetitions per runtime experiment |
| `systems.<name>.enabled` | `true` | Set to `false` to skip a system entirely |

---

## Running the harness

```bash
cd experiments/harness

# Full pipeline (prepare + compile + run all systems + collect)
bash run_all_experiments.sh

# Useful flags for iterative development:
bash run_all_experiments.sh --dry-run              # print what would run, do nothing
bash run_all_experiments.sh --skip-prepare         # reuse existing experiment_datasets/
bash run_all_experiments.sh --system glocks        # run only one system
bash run_all_experiments.sh --effectiveness-only   # skip runtime experiments
bash run_all_experiments.sh --runtime-only         # skip effectiveness experiments
```

### What the harness does

1. **`prepare_datasets.py`** — samples each slice, injects the configured error
   rates (5% / 10% / 20%), writes CSVs to `experiment_datasets/effectiveness/`
   and `experiment_datasets/runtime/`.

2. **`prepare_rules.py`** — runs TANE on each clean dataset to discover functional
   dependencies, writes `experiment_datasets/fds/`. Pre-generated FD files are
   also checked in under `rules/fds/`; pass `--skip-prepare` to reuse them
   without re-running TANE.

3. **Horizon compilation** — `javac`-compiles Java sources once, caches the
   result in `horizon_build/`.

4. **Effectiveness runs** — runs all enabled systems on the 5 slices × 3 error
   rates. Each run writes a timestamped directory under `results/<system>/`.

5. **Runtime runs** — runs all enabled systems on the full dataset at 4 sizes
   (10k / 100k / 500k / 1M rows).

6. **`collect_results.py`** — aggregates per-run `summary.csv` files into
   `manuscript_results/` CSVs ready for LaTeX.

### Running individual phases

```bash
python3 prepare_datasets.py --config config.json --out ./experiment_datasets
python3 prepare_rules.py    --config config.json \
    --datasets-dir ./experiment_datasets --out-dir ./experiment_datasets/fds

python3 run_glocks.py   --mode effectiveness --config config.json
python3 run_raha_baran.py --mode effectiveness --system both --config config.json

python3 collect_results.py --config config.json --results-dir ./results
```

---

## Experiment slices

| Slice | Source | Description |
|-------|--------|-------------|
| `full` | `data/merged_named/full_{dirty,clean}.csv` | Multi-country, 10k sample |
| `de` | `data/merged_named/slice_de_{dirty,clean}.csv` | Germany-only, 10k sample |
| `russia` | `data/merged_named/russia/full_{dirty,clean}_russia.csv` | Russia-only, 10k sample |
| `poi_Library` | `data/subsets/Library/named/{dirty,clean}.csv` | Schema.org Library POIs |
| `poi_ShoppingCenter` | `data/subsets/ShoppingCenter/named/{dirty,clean}.csv` | Schema.org ShoppingCenter POIs |

---

## Results layout

Each system run writes:

```
harness/results/<system>/<dataset>_<timestamp>/
  summary.csv          # P / R / F1, runtime (s), peak memory (MB)
  dirty.csv            # input
  clean.csv            # ground truth
  repaired.csv         # system output (where applicable)
  run_config.json      # exact parameters used
```

After `collect_results.py`:

```
manuscript_results/
  effectiveness/<slice>/<system>.csv
  runtime/error_detection/<system>.csv
  runtime/error_correction/<system>.csv
```

---

## Running UniClean separately

The harness runner is the primary path. For ad-hoc single-dataset runs:

```bash
cd experiments/baselines/uniclean/uniclean_cleaners
python3 main_full.py \
    --file_load DIRTY.csv \
    --clean_path CLEAN.csv \
    --save_path ./out \
    --table_name myrun
```

Slice-specific scripts: `main_de.py`, `main_russia.py`, `main_poi_Library.py`, etc.

---

## Aggregate scripts (post-hoc paper tables)

Scripts in `aggregate/` read results from `harness/results/` and produce averaged
metrics. Run them **after** the harness has completed at least one round.

```bash
cd experiments/aggregate

python avg_raha_results.py
python avg_baran_results.py
python avg_datawig_results.py
python avg_glocks_results.py
python avg_horizon_results.py
```

Path overrides (all optional):

| Env variable | Default | Purpose |
|--------------|---------|---------|
| `REPO_ROOT` | parent of `experiments/` | Repository root |
| `RESULTS_DIR` | `experiments/harness/results` | Harness results tree |
| `DATASETS_DIR` | `{REPO_ROOT}/data/merged_named` | Source merged CSVs |
| `ANALYSIS_ERRORS_DIR` | `{REPO_ROOT}/dataset_analysis/analysis_out_errors` | Error-type outputs from `run_analysis.py` |
