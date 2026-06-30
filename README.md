# Clean Me If You Can

A large collection of real-world postal addresses with ground truth for data cleaning benchmarking.

**Paper:** *Clean Me If You Can: A Large Collection of Real-World Addresses for Data Cleaning Benchmarking* 

**Authors:** Fatemeh Ahmadi, Tobias Bernhard, Mohamed Abdelmaksoud, Luca Zecchini, Tilmann Rabl, Ziawasch Abedjan

---

## Repository layout

| Directory | Purpose |
|-----------|---------|
| [`dataset_creation/`](dataset_creation/) | WDC extraction → OSM Nominatim validation → pack pipeline (Section 4) |
| [`dataset_analysis/`](dataset_analysis/) | Statistics, error taxonomy, slice generation (Section 5) |
| [`experiments/`](experiments/) | Baseline systems + experiment harness (Section 6) |
| `data/` | Published datasets — **gitignored**; see [Get the data](#get-the-data) below |

---

## Datasets

Each dataset ships as a paired `dirty.csv` / `clean.csv` with columns:
`id`, `name`, `house_number`, `road`, `postcode`, `locality`, `region`, `country`, `country_code`, `provenance_graph_iri`.

| Dataset | Rows | Description |
|---------|------|-------------|
| `full_named` | ~4.3M | All records with an entity name |
| `full_unnamed` | ~9.3M | All records without an entity name |
| `slices/us/named` | ~350k | US-only slice (Section 5.1.1) |
| `slices/de/named` | ~230k | Germany-only slice (Section 5.1.1) |
| `slices/ru/named` | ~120k | Russia-only slice (Section 6 experiments) |
| `subsets/<POI>/named` | varies | 22 Schema.org POI types (Hotel, Library, …) |

> **License note:** Ground-truth data derived from OpenStreetMap is licensed under
> [ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/).
> Source code in this repository is MIT-licensed.

---

## Error type distribution (Table 4)

Percentages are over all address-field cells per slice. *Parsing* is shown as an absolute
count (and as a percentage) because it is rare overall. *Word Subst.* aggregates
lexical substitutions and word variants (same-slot related-word changes).

| Slice | Rows | Clean | Missing | Parsing (#) | Parsing (%) | Cap. | Spec. | Name | Lang. | Abbr. | Token | Typo | Word Subst. | Misc |
|-------|-----:|------:|------:|------------:|------------:|-----:|------:|-----:|------:|------:|------:|-----:|------------:|-----:|
| `full_named` | 4,338,109 | 51.1% | 23.7% | 8,830 | 0.025% | 2.1% | 0.8% | 0.6% | 6.9% | 9.3% | 2.6% | 1.2% | 0.2% | 1.5% |
| `full_unnamed` | 9,317,886 | 47.3% | 28.6% | 500 | 0.001% | 1.7% | 0.8% | 0.3% | 6.4% | 9.5% | 1.8% | 1.3% | 0.4% | 1.9% |
| `slices/us/named` | 2,267,895 | 52.9% | 20.1% | 6,940 | 0.038% | 1.0% | 0.5% | 0.1% | 7.0% | 14.9% | 2.2% | 0.7% | 0.0% | 0.5% |
| `slices/de/named` | 374,533 | 53.5% | 30.0% | 91 | 0.003% | 1.9% | 1.2% | 0.3% | 5.3% | 1.2% | 2.7% | 0.3% | 0.0% | 3.6% |
| `slices/ru/named` | 194,274 | 51.9% | 29.6% | 0 | 0.000% | 7.8% | 0.3% | 0.1% | 2.2% | 0.4% | 0.7% | 6.4% | 0.2% | 0.3% |
| AdministrativeArea | 10,657 | 45.4% | 24.0% | 15 | 0.018% | 0.6% | 1.1% | 0.2% | 10.5% | 13.8% | 2.4% | 0.8% | 0.0% | 1.4% |
| City | 63,615 | 45.9% | 21.8% | 136 | 0.027% | 1.5% | 0.9% | 1.3% | 12.9% | 10.3% | 3.2% | 0.8% | 0.1% | 1.4% |
| CollegeOrUniversity | 55,429 | 52.4% | 19.7% | 27 | 0.006% | 0.4% | 1.4% | 0.2% | 8.7% | 12.5% | 2.6% | 1.0% | 0.0% | 1.0% |
| Country | 224,170 | 46.5% | 31.6% | 732 | 0.041% | 7.5% | 0.3% | 0.2% | 3.5% | 2.0% | 0.9% | 6.9% | 0.2% | 0.4% |
| EducationalOrganization | 38,629 | 41.7% | 32.0% | 67 | 0.022% | 0.7% | 0.2% | 0.2% | 7.6% | 10.4% | 3.1% | 2.7% | 0.1% | 1.3% |
| Event | 1,830,143 | 52.4% | 25.2% | 4,020 | 0.027% | 1.5% | 0.7% | 0.3% | 6.0% | 9.2% | 2.8% | 0.8% | 0.1% | 1.0% |
| GeoCoordinates | 1,784,594 | 56.1% | 16.0% | 3,998 | 0.028% | 1.7% | 0.9% | 0.6% | 6.8% | 12.3% | 2.6% | 1.0% | 0.3% | 1.7% |
| GovernmentOrganization | 10,323 | 53.2% | 17.5% | 1 | 0.001% | 0.7% | 0.2% | 0.1% | 2.1% | 6.8% | 12.4% | 0.4% | 0.5% | 6.1% |
| Hospital | 20,720 | 48.3% | 23.1% | 11 | 0.007% | 0.6% | 1.8% | 0.4% | 6.9% | 12.0% | 3.5% | 1.9% | 0.0% | 1.4% |
| Hotel | 413,303 | 52.1% | 19.9% | 311 | 0.009% | 2.1% | 1.0% | 1.5% | 11.5% | 6.1% | 3.1% | 1.0% | 0.1% | 1.6% |
| JobPosting | 10,440 | 38.5% | 34.5% | 18 | 0.022% | 2.9% | 1.2% | 0.3% | 8.1% | 4.7% | 3.8% | 1.0% | 0.0% | 4.9% |
| LandmarksOrHistoricalBuildings | 1,804 | 39.8% | 41.3% | 9 | 0.062% | 5.6% | 0.6% | 1.1% | 2.4% | 0.9% | 2.3% | 0.3% | 0.1% | 5.6% |
| Library | 5,370 | 51.7% | 27.3% | 10 | 0.023% | 2.8% | 0.4% | 0.6% | 2.0% | 5.8% | 1.6% | 1.1% | 0.0% | 6.6% |
| LocalBusiness | 860,576 | 52.2% | 21.4% | 1,534 | 0.022% | 2.4% | 1.0% | 0.5% | 7.1% | 9.8% | 2.6% | 0.8% | 0.2% | 2.0% |
| Museum | 5,507 | 58.5% | 23.9% | 15 | 0.034% | 2.9% | 0.8% | 0.4% | 3.3% | 3.5% | 1.8% | 0.4% | 0.1% | 4.3% |
| Park | 1,055 | 40.8% | 30.0% | 1 | 0.012% | 1.2% | 0.2% | 0.6% | 13.0% | 6.0% | 7.1% | 0.6% | 0.3% | 0.3% |
| Place | 2,243,749 | 49.9% | 27.2% | 4,753 | 0.026% | 1.7% | 0.7% | 0.3% | 6.3% | 9.2% | 2.7% | 0.7% | 0.1% | 1.2% |
| School | 6,559 | 53.1% | 20.6% | 2 | 0.004% | 1.2% | 1.2% | 0.2% | 7.1% | 12.9% | 2.3% | 0.3% | 0.0% | 1.1% |
| ShoppingCenter | 3,478 | 45.8% | 22.4% | 13 | 0.047% | 3.1% | 0.2% | 7.3% | 4.2% | 7.1% | 2.5% | 6.5% | 0.2% | 0.6% |
| SkiResort | 1,350 | 28.5% | 40.9% | 0 | 0.000% | 1.8% | 0.4% | 0.3% | 16.2% | 5.0% | 4.2% | 0.2% | 0.0% | 2.5% |
| SportsEvent | 130,076 | 28.5% | 49.1% | 569 | 0.055% | 0.2% | 0.2% | 0.0% | 7.5% | 13.0% | 0.7% | 0.3% | 0.0% | 0.5% |
| SportsTeam | 87,617 | 28.6% | 45.8% | 296 | 0.042% | 0.3% | 0.2% | 0.0% | 10.6% | 13.1% | 0.8% | 0.3% | 0.0% | 0.4% |

Reproduce with `python dataset_analysis/run_analysis.py` (regenerates
[`dataset_analysis/error_type_table.csv`](dataset_analysis/error_type_table.csv) 
Taxonomy definitions: [`dataset_analysis/README.md`](dataset_analysis/README.md).

---

## Get the data

The datasets are hosted on Zenodo:

**https://zenodo.org/records/20841898**

Download and extract them into `data/` at the repo root so the layout matches the tree below.


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
  slices/ru/named/dirty.csv       
  slices/ru/named/clean.csv
  subsets/<POI>/named/dirty.csv   # one directory per POI type
  subsets/<POI>/named/clean.csv
```

If you want to **rebuild the datasets from scratch** (from raw WDC N-Quads),
see [dataset_creation/README.md](dataset_creation/README.md) — this takes days
and requires significant infrastructure (full OSM planet, ~1.5 TB).

---

## Quick start

### 1. Dataset analysis (error taxonomy + statistics)

```bash
# From repo root
cd dataset_analysis
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m nltk.downloader wordnet omw-1.4

# Run the full Table 4 analysis (needs all datasets under ../data/)
python run_analysis.py

# Or analyze a single dirty/clean pair with heatmaps
python run_single_dataset.py ../data/full_named/dirty.csv ../data/full_named/clean.csv output/full_named
```

See [`dataset_analysis/README.md`](dataset_analysis/README.md) for all analysis
scripts (geographic distribution, cardinalities, per-column heatmaps).

---

### 2. Experiments (baseline evaluation)

```bash
cd experiments/harness
# Edit config.json first — see experiments/README.md §Configuration
bash run_all_experiments.sh
```

The harness runs DataWig, HoloClean, Horizon, Glocks, Raha, Baran, and UniClean.
Each baseline has its own prerequisites; see
[`experiments/README.md`](experiments/README.md) for the full per-baseline
setup (PostgreSQL, Java JDK, API keys, PySpark).

---

### 3. Rebuild datasets from WDC (optional, takes days)

Requires Python 3.13+, Docker, and ~1.5 TB disk.

```bash
cd dataset_creation
# Install uv (https://docs.astral.sh/uv/getting-started/installation/)
curl -LsSf https://astral.sh/uv/install.sh | sh
uv sync   # creates .venv and installs all dependencies

# Then follow dataset_creation/README.md step by step
```

---

## Citation

```bibtex
@article{ahmadi2026cleanme,
  title={Clean Me If You Can: A Large Collection of Real-World Addresses for Data Cleaning Benchmarking},
  author={Ahmadi, Fatemeh and Bernhard, Tobias and Abdelmaksoud, Mohamed and Zecchini, Luca and Rabl, Tilmann and Abedjan, Ziawasch},
  journal={},
  year={2026}
}
```
