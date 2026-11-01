# Books and movies from Web Data Commons

Scripts that turn Schema.org markup in the Web Data Commons crawl into paired dirty/clean tables for books and movies.

Crawl text is kept as extracted. Ground truth comes from Open Library (ISBN) and the IMDb non-commercial dataset (IMDb `tt` id). A record is dropped when the identifier is missing or the catalogue has no hit. Packed rows are then mapped to a shared schema and deduplicated.

The dumps themselves are absent from this repository. The commands below download them. IMDb's non-commercial terms allow a personal local copy and prohibit republishing the data or building another movie database from it, so the clean movie table and the movie experiment samples cannot be published. Download the IMDb files with `python -m movies.download_imdb` and run the index, validate, pack, and merge steps below to build them locally. The books corpus is distributed as `other_domains_books.zip`. The book experiment samples are distributed as `other_domains_books_samples.zip`. The movie crawl dirty table is distributed as `other_domains_movies.zip`.

## Setup

Python 3.13 or newer.

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

Downloaded files and built tables go under `data/`, which is gitignored.

## External data

### Web Data Commons, December 2024

Schema.org class-specific N-Quads. Release page:

https://webdatacommons.org/structureddata/2024-12/stats/schema_org_subsets.html

Files:

https://data.dws.informatik.uni-mannheim.de/structureddata/2024-12/quads/classspecific/

- Books: https://data.dws.informatik.uni-mannheim.de/structureddata/2024-12/quads/classspecific/Book/
- Movies: https://data.dws.informatik.uni-mannheim.de/structureddata/2024-12/quads/classspecific/Movie/

Overview of the crawl: https://webdatacommons.org/structureddata/

### Open Library dump, 31 August 2026

Dump documentation: https://openlibrary.org/developers/dumps

The scripts download the combined dump `ol_dump_2026-08-31.txt.gz`:

https://archive.org/download/ol_dump_2026-08-31/ol_dump_2026-08-31.txt.gz

Archive.org item: https://archive.org/details/ol_dump_2026-08-31

### IMDb non-commercial dataset

License and file list: https://developer.imdb.com/non-commercial-datasets/

The files are served from https://datasets.imdbws.com/ and refreshed daily. Use is limited to personal and non-commercial use under IMDb's terms. The downloader fetches:

- https://datasets.imdbws.com/title.basics.tsv.gz
- https://datasets.imdbws.com/title.crew.tsv.gz
- https://datasets.imdbws.com/title.principals.tsv.gz
- https://datasets.imdbws.com/name.basics.tsv.gz

## Pipeline

Run the commands from this directory, with the virtualenv activated (or prefix them with `.venv/bin/`).

### 1. Download the crawl

```bash
python -m shared.download --subset Book --subset Movie --full
```

Shards land in `data/wdc/Book/` and `data/wdc/Movie/`. Add `--sample` to fetch the small `{Subset}_sample.txt` files instead.

### 2. Extract dirty records

```bash
python -m shared.extract_main --input-dir data/wdc --out-dir data/extracted --domain book --parts-only
python -m shared.extract_main --input-dir data/wdc --out-dir data/extracted --subset Movie --parts-only
```

A book page is kept when it has a title or an ISBN. A movie page is kept when it has a title. Nested author, publisher, director, and actor nodes are reduced to their names. Output is `data/extracted/Book/` and `data/extracted/Movie/`.

### 3. Download and index the catalogues

```bash
python -m books.download_dump
python -m books.index_dump
python -m movies.download_imdb
python -m movies.index_imdb
```

This writes `data/openlibrary/ol_dump_2026-08-31.txt.gz`, `data/openlibrary/openlibrary.sqlite`, the IMDb TSVs under `data/imdb/`, and `data/imdb/imdb_index.sqlite`.

### 4. Match identifiers

```bash
python -m books.validate \
  --input-dir data/extracted/Book \
  --output-dir data/validated/Book \
  --parts-only \
  --dump-index data/openlibrary/openlibrary.sqlite

python -m movies.validate \
  --input-dir data/extracted/Movie \
  --output-dir data/validated/Movie \
  --imdb-index data/imdb/imdb_index.sqlite
```

Books are joined on a normalized ISBN-10 or ISBN-13 (`isbn` or `gtin13`). Movies are joined on an IMDb `tt` id found in `sameAs` or `identifier`.

### 5. Align the schema and deduplicate

```bash
python -m books.pack --validated-root data/validated/Book --output-dir data/pack/Book
python -m books.merge --pack-dir data/pack --out-dir data/merged/books

python -m movies.pack --validated-root data/validated/Movie --output-dir data/pack/Movie
python -m movies.merge --pack-dir data/pack --out-dir data/merged/movies
```

Pack writes one flat table per domain. Rows with an empty clean cell are dropped, then rows that are identical on every field are collapsed. Comparison ignores capitalization. Merge then keeps one row per dirty tuple and writes the dropped ids to `duplicates.csv`.

Book columns: `title`, `author`, `isbn`, `date_published`, `publisher`, `number_of_pages`.

Movie columns: `title`, `director`, `actor`, `date_published`, `duration`, `genre`. IMDb stores the date as a year.

Packed files, under `data/pack/Book/` and `data/pack/Movie/`:

- `values_experiment.csv`, `targets_experiment.csv` — dirty and clean columns
- `values.csv`, `targets.csv` — same columns plus catalogue ids
- `provenance.csv` — page URL, WDC graph, source file, and match id
- `dataset_full.csv` — all of the above

Merged files, under `data/merged/books/` and `data/merged/movies/`:

- `merged_values_experiment.csv`
- `merged_targets_experiment.csv`
- `merged_provenance.csv`
- `duplicates.csv`

## Tests

```bash
python -m pytest
```
