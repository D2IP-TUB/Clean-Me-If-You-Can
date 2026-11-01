# Dataset Analysis (Section 5)

Statistics and the multi-label error taxonomy for the address benchmark.

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
./install_libpostal.sh
```

All packages in `requirements.txt` are **required** to reproduce the taxonomy:

| Package | Used for | Effect if missing |
|---------|----------|-------------------|
| `ftfy` | Encoding repair inside `Special_Character` | Encoding differences go unlabelled |
| `pycountry` | Abbreviation detector (ISO country codes) | Country-code abbreviations undetected |
| `lingua-language-detector` | Language error detector | `Language` does not fire |
| `rapidfuzz` | Typo (Damerau-Levenshtein) | ImportError |
| `jellyfish` | Phonetic check inside `Formatting` | ImportError |
| `geopandas` | Geographic distribution plot | Required for Figure 2 |

`postal` (libpostal) is required for the Abbreviation layer. `install_libpostal.sh`
builds it without root and copies the per-language dictionaries to
`error_taxonomy/libpostal_dictionaries/`. The classifier raises `LibpostalMissing`
if either the binding or the dictionaries are absent.

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
  slices/us/unnamed/dirty.csv
  slices/us/unnamed/clean.csv
  slices/de/named/dirty.csv
  slices/de/named/clean.csv
  slices/de/unnamed/dirty.csv
  slices/de/unnamed/clean.csv
  slices/ru/named/dirty.csv
  slices/ru/named/clean.csv
  slices/ru/unnamed/dirty.csv
  slices/ru/unnamed/clean.csv
  subsets/<POI>/named/dirty.csv   # one dir per POI type
  subsets/<POI>/named/clean.csv
  subsets/<POI>/unnamed/dirty.csv
  subsets/<POI>/unnamed/clean.csv
  books/dirty.csv
  books/clean.csv
  movies/dirty.csv          # shipped in other_domains_movies.zip
  movies/clean.csv          # built locally; IMDb ground truth
```

---

## Error taxonomy

`classify()` in `error_taxonomy/analyze_error_types.py` returns the set of
labels that fire. Cells are whitespace- and Unicode-normalised, then
lower-cased. A case-only difference is `Clean`.

These labels are exclusive. The first match is the only label.

| Order | Type | Definition |
|-------|------|------------|
| 1 | Clean | dirty == clean after normalisation and lower-casing |
| 2 | Missing | dirty is blank |
| 3 | Special_Character | equal after punctuation/symbol strip, the German fold, or encoding repair |
| 4 | Abbreviation | token expansion makes the two strings equal |
| 5 | Language | lingua (or the script) disagrees, and the strings do not share a word |

If abbreviation expansion changes the pair but the strings still differ, the
cell keeps `Abbreviation` and the rules below run on the expanded pair.
`Special_Character` and a same-token reorder stop that layer. The others can
combine.

| Type | Definition |
|------|------------|
| Special_Character | same test as above, after abbreviation substitution |
| Formatting | same tokens in another order, or one token that is the same name, number, or street type in another form |
| Token_Subset | one value's tokens are a strict subset of the other's |
| Typo | Damerau-Levenshtein distance ≤ 2 |
| Semantic | one token differs and the lexical resources do not relate them |
| Unresolved_Type | nothing fired |

A cell keeps every label that fires. Clean, Missing, and Error partition the
cells. The type columns can sum to more than Error.

---

## Running the analysis

All commands assume you are in `dataset_analysis/` with the virtualenv active.

### All slices

```bash
python run_analysis.py
```

Classifies every dataset under `../data/` and writes:

- `output/multilabel/<label>/summary.json` — label counts, cardinality, co-occurrence
- `output/multilabel/<label>/examples.csv` — a few pairs per label combination
- `output/error_type_results_all.csv`, `output/error_type_table.tex`, and `output/error_type_table.csv` — multi-label percentages. The checked-in `error_type_table.csv` is not overwritten

`--from-summaries` rebuilds the table files from `summary.json` without classifying again.

`run_analysis.py` classifies the full sets, the US, DE, and RU slices, and every `../data/subsets/<POI>/named/` pair that is present. Books and movies are a separate command.

### Books and movies

```bash
python run_other_domains_multilabel.py
python run_other_domains_multilabel.py --only books
```

Those two corpora are the only non-address domains. Output goes to `output/multilabel/books/` and `output/multilabel/movies/`.

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

Produces label sets, prevalence, cardinality, and a co-occurrence matrix.

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
| `error_taxonomy/analyze_error_types.py` | Multi-label classifier |
| `error_taxonomy/analyze_error_types_multilabel.py` | Multiprocessing driver |
| `error_taxonomy/tests/test_hierarchy.py` | Layer-order regression tests |
| `error_type_table.csv` | Checked-in multi-label percentages for the full sets, country slices, POI subsets, books, and movies. `run_analysis.py` writes a fresh multi-label table under `output/` and leaves this file in place |
| `run_analysis.py` | Address datasets, plus any POI subset under `../data/subsets/` |
| `run_other_domains_multilabel.py` | Books and movies |
| `run_single_dataset.py` | One dataset, wrapper around the classifier CLI |
| `build_gazetteer.py` | Place-name gazetteer for locality, region, and country |
| `install_libpostal.sh` | Build libpostal and install its dictionaries |
| `statistics/plot_geo_distribution.py` | Geographic distribution figure |
| `statistics/cardinalities.py` | Attribute cardinality statistics |
| `statistics/shallow_analyze.py` | Quick null/dup/value-count scan |
| `slices/country/` | US / DE / RU country slice builders |

POI slices are drawn from WDC Schema.org subsets under `../data/subsets/<POI>/`,
not from name-token matching.
