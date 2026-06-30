# Dataset Creation Pipeline

Extract structured postal addresses from [Web Data Commons (WDC)](https://webdatacommons.org/)
N-Quads, validate against OpenStreetMap (Nominatim), and pack into CSV datasets.

> **Warning — this pipeline is expensive.** Expect several days of wall-clock time,
> ~1.5 TB of NVMe storage, 64 GB RAM (for Nominatim import), and ~400 GB of raw
> WDC downloads. If you only want to reproduce the analysis or experiments, use
> the pre-built datasets instead (see the root README).

---

## Prerequisites

### Python 3.13+

This package uses PEP 695 generic class syntax (`class Record[T]`) which requires
**Python 3.13 or newer**. Python 3.12 and earlier will fail at import time.

```bash
python3 --version   # must print 3.13.x or higher
```

Install Python 3.13 from https://python.org/downloads if needed.

### uv

[uv](https://docs.astral.sh/uv/) is a fast Python package manager that manages the
virtual environment for this package. Install it once:

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh
# Windows (PowerShell)
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Then, from the `dataset_creation/` directory, create the environment and install
all dependencies:

```bash
cd dataset_creation
uv sync
```

This creates `.venv/` and installs everything listed in `pyproject.toml`.
To run any pipeline command, prefix with `uv run`:

```bash
uv run python -m postalcrawl.wdc.download_postal_subsets --help
```

Or activate the environment for the session:

```bash
source .venv/bin/activate   # Linux/macOS
.venv\Scripts\activate      # Windows
```

### libpostal (optional but recommended)

libpostal improves address parsing during extraction. Install the system library
before installing the Python binding:

1. Follow https://github.com/openvenues/libpostal#installation
2. Then: `uv run pip install postal`

The pipeline runs without libpostal; it falls back to regex-based parsing.

### Docker (for Nominatim)

The validation step (§3 below) requires a local Nominatim instance running in
Docker. Install Docker Desktop from https://docs.docker.com/get-docker/.

---

## Pipeline overview

```
WDC N-Quads
  → [1] download        
  → [2] extract         
  → [3] validate        
  → [4] pack            
  → [5] merge           
  → [6] post-pack      
```

All steps are idempotent — re-running skips files that already exist.

---

## Step 1 — Download WDC subsets

Downloads 22 Schema.org class-specific subsets plus the microformat subset.
Total size: ~400 GB compressed N-Quads.

```bash
uv run python -m postalcrawl.wdc.download_postal_subsets --out-dir ./data/wdc
```

**Expected output:** `./data/wdc/` with one `.nq.gz` file per WDC subset.

If downloads are interrupted, re-run the command — already-complete files are
skipped. For individual retries: `scripts/wget_missing_wdc.sh`.

---

## Step 2 — Extract addresses

Parse N-Quads and emit structured JSON records. Run schema.org and microformat
extractions separately because they use different parsers.

```bash
# Schema.org PostalAddress (all 22 subsets)
uv run python -m postalcrawl.wdc.extract_main \
    --input-dir ./data/wdc \
    --out-dir ./data/extracted_wdc \
    --jobs 8

# vCard microformat subset
uv run python -m postalcrawl.wdc.extract_main \
    --input-dir ./data/wdc \
    --out-dir ./data/extracted_mfr \
    --format vcard \
    --jobs 8
```

`--jobs 8` parallelises across WDC files; set to your CPU core count.

**Expected output:** `./data/extracted_wdc/` and `./data/extracted_mfr/` — one
`.json.gz` per input file. Files with parse errors produce a sibling `.json.error`
log; check these if a subset looks empty.

---

## Step 3 — Validate via Nominatim (geocode → ground truth)

This step geocodes every address against a local OpenStreetMap Nominatim instance
to produce the clean ground-truth values.

### 3a. Start Nominatim

The first-time import of the full OSM planet takes **2–3 days** and requires:
- 64 GB RAM during import
- ~1.5 TB NVMe SSD (database + flat-node file)
- The `osm-nominatim/docker-compose.yml` is pre-configured for a full planet import

```bash
cd osm-nominatim

# Create the bind-mount directories first
mkdir -p mount/pbf/planet mount/data/db mount/data/flatnode

# (Optional but faster) Download the planet file manually beforehand:
# wget -P mount/pbf/planet https://ftp.fau.de/osm-planet/pbf/planet-latest.osm.pbf
# Then in docker-compose.yml, switch PBF_URL to PBF_PATH: /pbf/planet-latest.osm.pbf

docker compose up -d

# Watch the import progress (takes ~2–3 days)
docker logs -f nominatim-planet
```

Nominatim is ready when `docker logs` shows `nominatim is ready to accept connections`.
The API will be available at `http://localhost:9020`.

### 3b. Run validation

```bash
cd ..   # back to dataset_creation/

uv run python -m postalcrawl.validate.main \
    --input-dir ./data/extracted_wdc \
    --output-dir ./data/validated_wdc

# Repeat for microformat
uv run python -m postalcrawl.validate.main \
    --input-dir ./data/extracted_mfr \
    --output-dir ./data/validated_mfr
```

**Expected output:** `./data/validated_wdc/` and `./data/validated_mfr/` — each
input `.json.gz` gets a paired validation result file.

---

## Step 4 — Pack into dirty/clean CSV pairs

Converts validated records into paired `dirty.csv` / `clean.csv` files.

```bash
uv run python -m postalcrawl.pack.main \
    --validated-root ./data/validated_wdc \
    --output-dir ./data/pack_schema_org

uv run python -m postalcrawl.pack.main \
    --validated-root ./data/validated_mfr \
    --output-dir ./data/pack_microformat
```

---

## Step 5 — Merge schema.org + microformat outputs

```bash
uv run python -m postalcrawl.merge.main \
    --schema-org-dir ./data/pack_schema_org \
    --microformat-dir ./data/pack_microformat \
    --out-dir ./data/merged_pack
```

**Expected output:** six CSVs in `./data/merged_pack/`:
`merged_named_dirty.csv`, `merged_named_clean.csv`,
`merged_unnamed_dirty.csv`, `merged_unnamed_clean.csv`, and two provenance files.

---

## Step 6 — Post-pack validation (US / DE slices, Section 4.2.3)

Certifies locality names against OpenDataSoft reference lists.
Produces the `slices/us/` and `slices/de/` datasets used in Section 5.1.1.

**Download locality reference files** from OpenDataSoft and save them under
`data/locality_lists/` (see [`post_pack/README.md`](post_pack/README.md) for
the exact filenames and download links).

```bash
cd post_pack
python prepare_us_slice.py
python prepare_de_slice.py
python prepare_full_dataset.py --variant named
python prepare_full_dataset.py --variant unnamed
```

See [`post_pack/README.md`](post_pack/README.md) for full details.

---

## Step 7 — Geocoding validator comparison (Table 1, optional)

Compares Nominatim against Google, TomTom, Overture Maps, and OpenAddresses
on a stratified sample. See [`geocoding_comparison/README.md`](geocoding_comparison/README.md).

---

## Output format

Pack produces paired CSV files with these columns:

| Column | Description |
|--------|-------------|
| `id` | Stable record ID |
| `name` | Entity name (blank for unnamed datasets) |
| `house_number` | Street number |
| `road` | Street name |
| `postcode` | Postal code |
| `locality` | City / town |
| `region` | State / province |
| `country` | Country name |
| `country_code` | ISO 3166-1 alpha-2 |
| `provenance_graph_iri` | Source WDC graph IRI |

`dirty.csv` contains the raw web-extracted values; `clean.csv` contains the
Nominatim-verified ground truth.

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Download interrupted | Re-run `download_postal_subsets`; completed files are skipped. Or use `scripts/wget_missing_wdc.sh` for individual files. |
| Extract produces `.json.error` files | Parser skipped malformed N-Quad lines; the error file lists the bad lines. Re-run `extract_main` after fixing or removing the offending input. |
| Nominatim returns no results | Check `docker logs nominatim-planet` — import may still be running. Wait for "ready to accept connections". |
| `uv sync` fails with Python version error | Ensure `python3 --version` is 3.13+. Run `uv python install 3.13` to let uv manage the interpreter. |

---

## Sample data

Small N-Quad samples for testing extraction without downloading the full WDC are in
`postalcrawl/wdc/sample/`.
