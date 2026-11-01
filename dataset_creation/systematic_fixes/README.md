# Address fixes

Locality and region: United Kingdom, France, Spain, and Australia. Postcodes: United States (NAD) and Canada (NAR).

```bash
python3 locality_fix/run_pipeline.py --download --extract
```

Requires Python 3.11, `pandas`, `numpy`, and `openpyxl`. Input is `full_named/full_dirty.csv`, `full_clean.csv`, and `cell_labels.csv`.

Place these two files before the run:

- `uk_fix/os_open_names/Data/opname_gb.gpkg`
- `uk_fix/os_open_names/Data/osni_open_data_-_gazetteer_-_place_names.csv`

## US and Canada postcodes

From `postcode_fix/`:

```bash
python3 nad_join.py --build-index data/indexes/nad_us.sqlite --nad data/raw/NAD.zip
python3 compare_nad.py --unique-address --dirty slice_us_dirty.csv --clean slice_us_clean.csv --nad-index data/indexes/nad_us.sqlite --out unique_nad.csv
python3 fix_us_slice.py --dirty slice_us_dirty.csv --clean slice_us_clean.csv --nad unique_nad.csv --out-dirty slice_us_dirty_fixed.csv --out-clean slice_us_clean_fixed.csv
```

From `postcode_fix/canada/`:

```bash
python3 nar_join.py --build-index data/indexes/nar_ca.sqlite --nar data/raw/202606.zip
python3 compare_nar.py --unique-address --dirty slice_ca_dirty.csv --clean slice_ca_clean.csv --nar-index data/indexes/nar_ca.sqlite --out unique_nar.csv
python3 fix_ca_slice.py --dirty slice_ca_dirty.csv --clean slice_ca_clean.csv --nar unique_nar.csv --out-dirty slice_ca_dirty_fixed.csv --out-clean slice_ca_clean_fixed.csv
```

## Sources

### OS Open Names

https://osdatahub.os.uk/data/downloads/open/OpenNames

http://os.uk/opendata/licence

Contains OS data © Crown Copyright and database rights 2026.

Contains Royal Mail data © Royal Mail copyright and database right 2026.

Contains National Statistics data © Crown copyright and database right 2026.

### OSNI Open Data — Gazetteer — Place Names

https://admin.opendatani.gov.uk/dataset/osni-open-data-gazetteer-place-names

https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/

Contains public sector information licensed under the terms of the Open Government Licence v3.0.

### INSEE, Code officiel géographique au 1er janvier 2026

https://www.insee.fr/fr/information/8740222

https://www.insee.fr/fr/statistiques/fichier/8740222/cog_ensemble_2026_csv.zip

https://www.etalab.gouv.fr/licence-ouverte-open-licence

Source : Insee, Code officiel géographique au 1er janvier 2026.

### La Poste, Base officielle des codes postaux

https://data.laposte.fr/datasets/laposte-hexasmal

https://data.laposte.fr/data-fair/api/v1/datasets/laposte-hexasmal/raw

https://www.etalab.gouv.fr/licence-ouverte-open-licence

Source : La Poste, Base officielle des codes postaux.

### INE, Relación de municipios y sus códigos por provincias, 1 January 2026

https://www.ine.es/dyngs/INEbase/es/operacion.htm?c=Estadistica_C&idp=1254734710990&menu=ultiDatos

https://www.ine.es/daco/daco42/codmun/diccionario26.xlsx

https://www.ine.es/aviso_legal

Fuente: Instituto Nacional de Estadística.

### GeoNames postal codes, Spain

https://download.geonames.org/export/zip/ES.zip

https://download.geonames.org/export/zip/readme.txt

https://creativecommons.org/licenses/by/4.0/

Spain postal data: GeoNames, https://www.geonames.org/, CC BY 4.0.

### Geoscape G-NAF, August 2026

https://data.gov.au/data/dataset/geocoded-national-address-file-g-naf

https://publicdata.au/d/gnaf/v/2026-08-17/source.zip

https://data.gov.au/data/dataset/geocoded-national-address-file-g-naf/resource/09f74802-08b1-4214-a6ea-3591b2753d30

Incorporates or developed using G-NAF © Geoscape Australia licensed by the Commonwealth of Australia under the Open Geo-coded National Address File (G-NAF) End User Licence Agreement.

G-NAF must not be used to generate an address, or a compilation of addresses, for sending mail unless each address has been verified against another source.

### ABS, ASGS Edition 3, Local Government Areas 2024

https://www.abs.gov.au/statistics/standards/australian-statistical-geography-standard-asgs-edition-3/jul2021-jun2026/non-abs-structures/local-government-areas

https://geo.abs.gov.au/arcgis/rest/services/ASGS2024/LGA/FeatureServer/0/query?where=1%3D1&outFields=*&returnGeometry=false&f=json&resultRecordCount=2000

https://creativecommons.org/licenses/by/4.0/

© Commonwealth of Australia (Australian Bureau of Statistics), Australian Statistical Geography Standard (ASGS) Edition 3, Local Government Areas, CC BY 4.0.

### National Address Database

https://www.transportation.gov/mission/open/gis/national-address-database/national-address-database-nad-disclaimer

https://data.transportation.gov/dataset/National-Address-Database-NAD-Text-File/fc2s-wawr

https://data.transportation.gov/download/fc2s-wawr/application/x-zip-compressed

http://www.usa.gov/publicdomain/label/1.0/

National Address Database, U.S. Department of Transportation. Public domain. Not for use as a mailing list.

### Statistics Canada, National Address Register, June 2026

https://www150.statcan.gc.ca/n1/pub/46-26-0002/462600022026001-eng.htm

https://www150.statcan.gc.ca/n1/pub/46-26-0002/462600022022001-eng.htm

https://www150.statcan.gc.ca/n1/pub/46-26-0002/2022001/202606.zip

https://www.statcan.gc.ca/en/reference/licence

Source: Statistics Canada, National Address Register. Reproduced and distributed on an "as is" basis with the permission of Statistics Canada.

The register also contains information licensed under the Open Government Licence – Yukon: https://open.yukon.ca/data/open-government-licence-yukon
