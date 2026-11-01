# Clean Me If You Can

A large collection of real-world postal addresses with ground truth for data cleaning benchmarking. The same repository includes a books corpus from the Web Data Commons crawl with Open Library ground truth, and the movie dirty tables from that crawl.

**Paper:** *Clean Me If You Can: A Large Collection of Real-World Addresses for Data Cleaning Benchmarking* 

**Authors:** Fatemeh Ahmadi, Tobias Bernhard, Mohamed Abdelmaksoud, Luca Zecchini, Tilmann Rabl, Ziawasch Abedjan

---

## Repository layout

| Directory | Purpose |
|-----------|---------|
| [`dataset_creation/`](dataset_creation/) | WDC extraction → OSM Nominatim validation → pack pipeline (Section 4) |
| [`dataset_analysis/`](dataset_analysis/) | Statistics, error taxonomy, slice generation (Section 5) |
| [`benchmark_customization_scripts/`](benchmark_customization_scripts/) | Drop columns or restore selected error types to ground truth (Section 5.2.2) |
| [`experiments/`](experiments/) | Baseline systems + experiment harness (Section 6) |
| `data/` | Address datasets — **gitignored**; see [Get the data](#get-the-data) below |
| `other_domains_books.zip` | Books corpus, unpacked into `other_domains_data/books/` |
| `other_domains_books_samples.zip` | Book experiment samples, unpacked into `other_domains_data/effectiveness_other_domains/books/` |
| `other_domains_movies.zip` | Movie crawl dirty table, unpacked into `other_domains_data/movies/dirty.csv` |

---

## Datasets

Each dataset ships as a paired `dirty.csv` / `clean.csv` with columns:
`id`, `name`, `house_number`, `road`, `postcode`, `locality`, `region`, `country`, `country_code`, `provenance_graph_iri`.

| Dataset | Rows | Description |
|---------|------|-------------|
| `full_named` | 4,335,421 | All records with an entity name |
| `full_unnamed` | 9,312,725 | All records without an entity name |
| `slices/us/named` | 2,267,134 | US-only slice, with an entity name |
| `slices/us/unnamed` | 4,447,612 | US-only slice, without an entity name |
| `slices/de/named` | 374,503 | Germany-only slice, with an entity name |
| `slices/de/unnamed` | 1,072,166 | Germany-only slice, without an entity name |
| `slices/ru/named` | 194,229 | Russia-only slice, with an entity name |
| `slices/ru/unnamed` | 340,697 | Russia-only slice, without an entity name |
| `subsets/<POI>/named` | see below | 22 Schema.org POI types, with an entity name |
| `subsets/<POI>/unnamed` | see below | 22 Schema.org POI types, without an entity name |

POI subset sizes (rows):

| POI | Named | Unnamed |
|-----|------:|--------:|
| AdministrativeArea | 10,657 | 25,520 |
| City | 63,615 | 90,582 |
| CollegeOrUniversity | 55,429 | 82,900 |
| Country | 224,170 | 303,712 |
| EducationalOrganization | 38,629 | 78,158 |
| Event | 1,830,143 | 2,107,300 |
| GeoCoordinates | 1,784,594 | 2,541,065 |
| GovernmentOrganization | 10,323 | 13,723 |
| Hospital | 20,720 | 34,623 |
| Hotel | 413,303 | 418,177 |
| JobPosting | 10,440 | 338,008 |
| LandmarksOrHistoricalBuildings | 1,804 | 1,489 |
| Library | 5,370 | 5,129 |
| LocalBusiness | 860,576 | 1,387,885 |
| Museum | 5,507 | 6,087 |
| Park | 1,055 | 941 |
| Place | 2,243,749 | 3,965,102 |
| School | 6,559 | 7,813 |
| ShoppingCenter | 3,478 | 8,234 |
| SkiResort | 1,350 | 1,566 |
| SportsEvent | 130,076 | 137,855 |
| SportsTeam | 87,617 | 99,798 |

### Books and movies

Error rates use these content columns. `id`, `provenance_graph_iri`, and the catalogue keys are the same on the dirty and clean side, so they are not part of those cell counts.

| Dataset | Rows | Content columns |
|---------|-----:|-----------------|
| books | 649,664 | `title`, `author`, `isbn`, `date_published`, `publisher`, `number_of_pages` |
| movies | 88,100 | `title`, `director`, `actor`, `date_published`, `duration`, `genre` |

Book files also carry `openlibrary_key`, `work_key`, and `match`. The published movie dirty file carries `id`, the six content columns, and `provenance_graph_iri`. Book experiment samples, at the native error rate and at 5%, 10%, and 20%, ship in `other_domains_books_samples.zip`. The clean movie table and the movie experiment samples are IMDb data. IMDb's non-commercial terms prohibit publishing them. Download the IMDb files and run the scripts in [`dataset_creation/other_domains/README.md`](dataset_creation/other_domains/README.md) to build those tables locally.

Rebuild steps: [`dataset_creation/other_domains/README.md`](dataset_creation/other_domains/README.md).

> **License note:** Address ground truth derived from OpenStreetMap is licensed under
> [ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/).
> Book ground truth comes from the Open Library dump, dedicated to the public domain under [CC0 1.0](https://openlibrary.org/help/faq/using).
> Movie ground truth comes from the [IMDb non-commercial datasets](https://developer.imdb.com/non-commercial-datasets/). Those terms allow a personal, non-commercial local copy. They prohibit republishing the data or turning it into another movie database, so this repository cannot include the clean movie table or the movie experiment samples. It ships only the crawl dirty table. Anyone can download the IMDb datasets and run [`dataset_creation/other_domains/README.md`](dataset_creation/other_domains/README.md) (`python -m movies.download_imdb`, then index, validate, pack, and merge) to rebuild the clean table on their own machine.
> Source code in this repository is MIT-licensed.

---

## Error types

`Clean`, `Missing`, `Special_Character`, `Abbreviation`, `Language`, `Formatting`, `Token_Subset`, `Typo`, `Semantic`, `Unresolved_Type`.

Definitions: [`dataset_analysis/README.md`](dataset_analysis/README.md).
Measured multi-label percentages for the full sets, the country slices, all 22 POI subsets (named and unnamed), and the books and movies corpora are in [`dataset_analysis/error_type_table.csv`](dataset_analysis/error_type_table.csv) and [`dataset_analysis/error_type_table.tex`](dataset_analysis/error_type_table.tex). Clean, Missing, and Error partition the cells. A cell can carry more than one error label, so the type columns can sum to more than Error.

Full sets, country slices, books, and movies (percent of cells):

| Dataset | Variant | Clean | Missing | Error | Special char. | Language | Abbreviation | Token subset | Typo | Formatting | Semantic |
|---------|---------|------:|--------:|------:|--------------:|---------:|-------------:|-------------:|-----:|-----------:|---------:|
| full_named | named | 54.189 | 23.658 | 22.153 | 0.947 | 1.32 | 13.453 | 4.452 | 0.361 | 0.26 | 1.9 |
| full_unnamed | unnamed | 49.853 | 28.564 | 21.583 | 1.14 | 1.291 | 14.116 | 2.663 | 0.313 | 0.184 | 2.601 |
| US | named | 54.259 | 20.108 | 25.633 | 0.561 | 0.258 | 19.944 | 4.093 | 0.098 | 0.22 | 1.037 |
| DE | named | 54.795 | 30.006 | 15.2 | 2.129 | 2.679 | 5.285 | 4.116 | 0.288 | 0.203 | 0.967 |
| RU | named | 57.627 | 36.965 | 5.409 | 0.419 | 0.15 | 2.122 | 1.699 | 0.142 | 0.477 | 0.885 |
| US | unnamed | 49.445 | 25.252 | 25.303 | 0.623 | 0.185 | 21.206 | 2.267 | 0.06 | 0.142 | 1.348 |
| DE | unnamed | 57.034 | 30.142 | 12.824 | 2.287 | 2.812 | 6.507 | 1.086 | 0.173 | 0.003 | 1.009 |
| RU | unnamed | 43.481 | 45.119 | 11.4 | 0.458 | 0.19 | 5.027 | 2.835 | 0.283 | 1.314 | 2.585 |
| books |  | 24.487 | 26.163 | 49.349 | 2.006 | 2.778 | 1.08 | 19.273 | 0.953 | 14.692 | 9.467 |
| movies |  | 19.065 | 33.213 | 47.722 | 0.47 | 9.607 | 0.198 | 18.86 | 0.306 | 4.897 | 13.453 |

`python dataset_analysis/run_analysis.py` writes a multi-label address table under `dataset_analysis/output/` and does not change the checked-in table. Books and movies are classified by `python dataset_analysis/run_other_domains_multilabel.py`.

---

## Get the data

The address datasets are hosted on Zenodo:

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
  subsets/<POI>/named/dirty.csv     # one directory per POI type
  subsets/<POI>/named/clean.csv
  subsets/<POI>/unnamed/dirty.csv
  subsets/<POI>/unnamed/clean.csv
```

Books ship in this repository as `other_domains_books.zip` (97 MB). The book experiment samples ship as `other_domains_books_samples.zip` (4 MB). The movie crawl dirty table ships as `other_domains_movies.zip`: `movies/dirty.csv`. The IMDb clean table and movie experiment samples cannot be published. Download the [IMDb non-commercial datasets](https://developer.imdb.com/non-commercial-datasets/) and run the scripts in [dataset_creation/other_domains/README.md](dataset_creation/other_domains/README.md) to build `movies/clean.csv` locally, then place it beside the dirty file.

```bash
unzip other_domains_books.zip
unzip other_domains_books_samples.zip
mkdir -p data other_domains_data/movies
ln -sfn ../other_domains_data/books data/books
ln -sfn ../other_domains_data/movies data/movies
```

The symlinks are what `dataset_analysis/run_other_domains_multilabel.py` reads. The unpacked CSVs are gitignored.

To **rebuild the address datasets from scratch** (from raw WDC N-Quads),
see [dataset_creation/README.md](dataset_creation/README.md). That takes days
and requires a full OSM planet (~1.5 TB). Books and movies are rebuilt with
[dataset_creation/other_domains/README.md](dataset_creation/other_domains/README.md).

---

## Quick start

### 1. Dataset analysis (error taxonomy + statistics)

```bash
# From repo root
cd dataset_analysis
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m nltk.downloader wordnet omw-1.4

# Address error-type table (needs the Zenodo datasets under ../data/)
python run_analysis.py

# Books and movies (after the symlinks above)
python run_other_domains_multilabel.py

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

Books and movies use [`experiments/harness/config_other_domains.json`](experiments/harness/config_other_domains.json), which reads `other_domains_data/{books,movies}/{dirty,clean}.csv`. The book 10k samples are in `other_domains_books_samples.zip`. Movie runs need `movies/clean.csv`, which you build by downloading IMDb and running the scripts in [`dataset_creation/other_domains/README.md`](dataset_creation/other_domains/README.md). Those IMDb-derived tables stay on your machine.

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
