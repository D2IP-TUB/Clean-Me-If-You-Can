# Geocoding Validator Comparison

Scripts and documentation for comparing address validators used to choose
Nominatim/OSM as the ground-truth source (Section 4.2).

## Validators

| Validator | Script | API key |
|-----------|--------|---------|
| **Nominatim/OSM** (chosen) | `nominatim_validate.py` | None |
| Google Address Validation | `main.py` | `GOOGLE_MAPS_API_KEY` |

TomTom, Overture Maps, and OpenAddresses were also evaluated when selecting the
ground-truth source (paper Section 4.2);

## Quick start

### 1. Create stratified sample (~1,068 records, 120+ countries)

```bash
python create_true_stratified_sample.py \
    --input-csv ../data/full_named/clean.csv \
    --output-csv samples/stratified_sample.csv
```

### 2. Run Nominatim validation (free, no API key)

```bash
python nominatim_validate.py --csv samples/stratified_sample.csv --limit 10
python nominatim_validate.py --csv samples/stratified_sample.csv
```

### 3. Run Google validation (optional, requires API key)

```bash
export GOOGLE_MAPS_API_KEY='your-key'
python main.py --csv samples/stratified_sample.csv --limit 10
```

## Analysis scripts

- `compare_clean_dirty.py` — similarity between clean and dirty variants
- `analyze_similarity.py` / `analyze_similarity_by_country.py` — field-level scores
- `analyze_by_country.py` — per-country breakdown
