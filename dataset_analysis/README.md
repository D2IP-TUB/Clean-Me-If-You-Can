# Dataset Analysis (Section 5)

Statistics and the **v3 error taxonomy** for the address benchmark.

---

## Prerequisites

### Python environment

Any Python 3.9+ works (3.11 recommended). Create an isolated environment:

```bash
cd dataset_analysis
python3 -m venv .venv
source .venv/bin/activate        # Linux/macOS
# .venv\Scripts\activate         # Windows
```

### Install dependencies

```bash
pip install -r requirements.txt
python -m nltk.downloader wordnet omw-1.4
```

All packages in `requirements.txt` are **required** to reproduce paper numbers:

| Package | Used for | Effect if missing |
|---------|----------|-------------------|
| `ftfy` | Parsing error detector (encoding artifacts) | Parsing counts silently drop to near zero |
| `pycountry` | Abbreviation detector (ISO country codes) | Country-code abbreviations undetected |
| `lingua-language-detector` | Language error detector | Language errors classified as Misc |
| `rapidfuzz` | Typo + Word_Variant / Word_Substitution detection | Required; will ImportError |
| `geopandas` | Geographic distribution plot | Required for Figure 2 |

The `postal` package (libpostal Python binding) further improves Abbreviation
detection but requires a manual system-level install of libpostal
(https://github.com/openvenues/pypostal) and is **truly optional**.

### Data

Datasets must be placed under `../data/` relative to this directory (i.e., `data/`
in the repo root). See the root README for how to obtain them.

```
data/
  full_named/dirty.csv
  full_named/clean.csv
  full_unnamed/dirty.csv
  full_unnamed/clean.csv
  slices/us/named/dirty.csv
  slices/us/named/clean.csv
  slices/de/named/dirty.csv
  slices/de/named/clean.csv
  subsets/<POI>/named/dirty.csv   # one dir per POI type
  subsets/<POI>/named/clean.csv
```

---

## Error taxonomy (13 types)

Applied in strict priority order — each cell gets the **first** matching type:

| Priority | Type | Definition |
|----------|------|------------|
| 1 | Clean | dirty == clean |
| 2 | Missing | dirty is blank, clean is not |
| 3 | Parsing | encoding artifact (ftfy / html entity / URL decoding restores equality) |
| 4 | Capitalization | equal after case-fold |
| 5 | Special_Character | equal after Unicode punct/symbol stripping |
| 6 | Name_Reformat | same tokens, different order |
| 7 | Language | different language detected by lingua |
| 8 | Abbreviation | abbreviation ↔ expansion (libpostal / pycountry / static map) |
| 9 | Token_Subset | one value is a subset of the other's tokens |
| 10 | Typo | edit distance 1 after normalization |
| 11 | Word_Variant | same root / transliteration variant |
| 12 | Word_Substitution | same slot, different word |
| 13 | Misc | none of the above |

---

## Running the analysis

All commands assume you are in `dataset_analysis/` with the virtualenv active.

### Table 4 — error-type distribution across all slices

```bash
python run_analysis.py
```

Processes all datasets found under `../data/` in chunks of 50,000 rows.
Runtime: ~2–4 h for the full named + unnamed datasets on a laptop.

Outputs to `output/`:
- `error_type_results_all.csv` — per-dataset counts and percentages
- `error_type_results_progress.csv` — intermediate results (updated after each dataset)
- `error_type_table.tex` — copy of the published LaTeX table

Also updates the checked-in Table 4 artifacts:
- [`error_type_table.csv`](error_type_table.csv)

### Single dataset with heatmaps (Figures 3–5)

```bash
python run_single_dataset.py \
    ../data/full_named/dirty.csv \
    ../data/full_named/clean.csv \
    output/full_named
```

Or call the classifier directly with more control:

```bash
python error_taxonomy/analyze_error_types.py \
    --values ../data/full_named/dirty.csv \
    --targets ../data/full_named/clean.csv \
    --output_dir output/full_named
```

Produces in `output/full_named/`:
- `cell_error_types.csv` — per-cell error type labels
- `error_matrix_heatmap.pdf` — row × column error heatmap
- `per_column_error_stack.png` — stacked bar chart per column

### Geographic distribution (Figure 2)

```bash
python statistics/plot_geo_distribution.py \
    ../data/full_named/clean.csv \
    --output output/geo_distribution.png
```

Requires `geopandas`

### Cardinalities (Table 2)

```bash
python statistics/cardinalities.py \
    --targets ../data/full_named/clean.csv \
    --values ../data/full_named/dirty.csv \
    --output_dir output/cardinalities
```

### Quick scan (no output directory needed)

```bash
python statistics/shallow_analyze.py ../data/full_named/dirty.csv
```

Prints null rates, duplicate counts, and value-count summaries to stdout.

---

## Layout

| Path | Purpose |
|------|---------|
| `error_taxonomy/analyze_error_types.py` | v3 classifier — canonical implementation |
| `error_type_table.csv` | Published Table 4 (CSV) |
| `run_analysis.py` | Batch runner → regenerates Table 4 files |
| `run_single_dataset.py` | One dataset → heatmaps (wrapper around classifier CLI) |
| `statistics/plot_geo_distribution.py` | Geographic distribution figure |
| `statistics/cardinalities.py` | Attribute cardinality statistics |
| `statistics/shallow_analyze.py` | Quick null/dup/value-count scan |
| `slices/country/` | US / DE / RU country slice builders |

POI slices are drawn from WDC Schema.org subsets under `../data/subsets/<POI>/`,
not from name-token matching.
