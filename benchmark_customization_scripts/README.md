# Slice customization

`customize_slice.py` builds a dirty/clean pair from an existing slice.

- Columns passed to `--drop-columns` are removed from both files. `country_code` is the usual case: it is an identifier, not an address error.
- A cell is set to the clean value only when every label on it is one of the types passed to `--exclude-types`. A cell that also carries another label stays dirty.
- `--exclude-preset representational` selects `Special_Character`, `Abbreviation`, and `Formatting`.

`--domain` is `address` (default), `books`, or `movies`. It only changes which columns are treated as text. Libpostal and the place gazetteer are required for address slices, the same as the error taxonomy.

```bash
python benchmark_customization_scripts/customize_slice.py \
    --dirty data/slices/de/named/dirty.csv \
    --clean data/slices/de/named/clean.csv \
    --drop-columns country_code \
    --exclude-preset representational \
    --output-dir benchmark_customization_scripts/data/de
```

The output directory gets `dirty.csv`, `clean.csv`, and `report.json`. `report.json` counts cells of each label before the replacement. A cell with two labels is counted under both. `data/` in this folder is gitignored.
