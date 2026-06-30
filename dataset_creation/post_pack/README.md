# Post-Pack Validation (Section 4.2.3)

Scripts from `pre_process_manual/slices/` — the **final** locality certification
pipeline. These operate on merged pack CSVs directly (no Nominatim response
pickles, no `slices_luca/` scripts).

## Download locality lists

Place semicolon-separated CSV exports under `data/locality_lists/`:

| File | OpenDataSoft dataset | Required columns |
|------|---------------------|------------------|
| `localities_us.csv` | [US Places](https://public.opendatasoft.com/explore/dataset/georef-united-states-of-america-place/) | `Official Name Place`, `Official Name State` |
| `localities_us_subdivisions.csv` | [US County Subdivisions](https://public.opendatasoft.com/explore/dataset/georef-united-states-of-america-county-subdivision/) | `cousub_name`, `ste_name` |
| `localities_de.csv` | [DE Municipalities](https://public.opendatasoft.com/explore/dataset/georef-germany-gemeinde/) | `Gemeinde name (short)`, `Land name` |

On each dataset page: **Export → CSV → Whole dataset**.

## Pipeline

Inputs: merged pack CSVs from `postalcrawl.merge` (`merged_named_*`, `merged_unnamed_*`).

```
merged pack CSVs
  → prepare_us_slice.py / prepare_de_slice.py   (locality certification + slice export)
  → prepare_full_dataset.py                     (full named/unnamed, minus skipped IDs)
  → prepare_subset_datasets.py                  (per-POI subsets, optional)
```

### 1. Country slices (US + DE)

```bash
cd dataset_creation/post_pack
python prepare_us_slice.py
python prepare_de_slice.py
```

Writes `slice_{us,de}_{clean,dirty}.csv`, `skipped_{us,de}.csv`, `duplicates_{us,de}.csv`.

### 2. Full datasets

```bash
python prepare_full_dataset.py --variant named
python prepare_full_dataset.py --variant unnamed
```

Removes records skipped in either country slice and deduplicates dirty rows.

### 3. Per-subset datasets (optional)

```bash
python prepare_subset_datasets.py \
    --pack-dir ../data/pack_schema_org \
    --output-dir ../data/subsets_processed
```

Use `--flat` when the pack dir has `named/` and `unnamed/` at the root (microformat pack).

## Utility

`scripts/prepare_datasets.py` — strip embedded newlines and add `_id` column to raw CSVs:

```bash
python scripts/prepare_datasets.py input.csv output.csv
```

## Configuration

Edit `config.py` to point `BASE` and file paths at your workspace.
