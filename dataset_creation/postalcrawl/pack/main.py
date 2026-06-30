import argparse
import json
import logging
import re
import uuid
from pathlib import Path
from typing import Iterable, Iterator

log = logging.getLogger(__name__)

import polars as pl
from postal.parser import parse_address as postal_parse_address
from postalcrawl.utils import project_root, read_from_jsongz
from postalcrawl.validate.refine import ensure_string
from rapidfuzz import fuzz, utils
from rapidfuzz.distance import Levenshtein
from unidecode import unidecode
from tqdm import tqdm

DEFAULT_VALIDATED_ROOT = project_root() / "data" / "validated"
DEFAULT_DATASET_DIR = project_root() / "data" / "dataset"

# Core address columns (from query)
ADDRESS_COLUMNS = [
    "name",
    "street",
    "house_number",
    "city",
    "postalcode",
    "state",
    "country",
    "countrycode",
]

# Parent entity fields (extracted from WDC data)
PARENT_ENTITY_COLUMNS = [
    "telephone",
    "email",
    "url",
    "sameAs",
    "openingHours",
    "latitude",
    "longitude",
]

# Crawl metadata / provenance columns
PROVENANCE_COLUMNS = [
    "subset",
    "crawl_url",
    "crawl_source",
    "provenance_graph_iri",
    "provenance_wdc_release",
    "provenance_subset",
    "provenance_source_file",
    "provenance_format",
]

# OSM geospatial and metadata columns
OSM_COLUMNS = [
    "osm_latitude",
    "osm_longitude",
    "osm_id",
    "osm_type",
    "osm_key",
    "osm_value",
    "osm_importance",
    "osm_place_rank",
    "osm_neighbourhood",
    "osm_borough",
    "osm_suburb",
    "osm_county",
    "osm_district",
    "osm_state_district",
    "osm_iso3166",
    "osm_extratags",
    "osm_namedetails",
]

# Quality/validation columns (deprecated - use OSM importance instead)
VALIDATION_COLUMNS = []

COLUMNS = ADDRESS_COLUMNS + PARENT_ENTITY_COLUMNS + PROVENANCE_COLUMNS + OSM_COLUMNS + VALIDATION_COLUMNS
TARGET_COLUMNS = [f"target_{col}" for col in ADDRESS_COLUMNS] + ["target_label"]


# OSM address fields that map to schema concepts (Figure 1)
# Preferred fields are semantically closest; fallbacks used only when none of
# the preferred fields are present. Levenshtein distance from the query value
# is the tie-breaking criterion when multiple candidates are available.
_LOCALITY_PREFERRED = ["city", "town"]
_LOCALITY_FALLBACK  = ["village", "borough", "neighborhood", "hamlet", "municipality"]
_REGION_PREFERRED   = ["region", "state"]
_REGION_FALLBACK    = ["province", "county", "state_district"]


def _extract_str(val) -> str | None:
    """Return a plain string from a value that may be a JSON-LD object like
    {"@value": "...", "@language": "en-US"} or a plain string/None."""
    if val is None:
        return None
    if isinstance(val, dict):
        return val.get("@value")
    return str(val) if val != "" else None


def pick_best_osm_field(
    query_val: str | None,
    address: dict,
    preferred_keys: list[str],
    fallback_keys: list[str],
) -> str | None:
    """Return the best OSM address field value following the Figure 1 schema.

    Preferred keys are tried first. If multiple candidates exist at the same
    tier, the one with the smallest Levenshtein distance from *query_val* wins.
    Falls back to *fallback_keys* if no preferred key is present.
    """
    def best_of(candidates: list[str]) -> str | None:
        if not candidates:
            return None
        if query_val is None or len(candidates) == 1:
            return candidates[0]
        q = query_val.lower()
        return min(candidates, key=lambda v: Levenshtein.distance(q, v.lower()))

    preferred = [address[k] for k in preferred_keys if address.get(k)]
    if preferred:
        return best_of(preferred)

    fallback = [address[k] for k in fallback_keys if address.get(k)]
    if fallback:
        used_keys = [k for k in fallback_keys if address.get(k)]
        log.debug(
            "Fallback used for query=%r: preferred_keys=%s absent, "
            "using fallback_keys=%s -> %r",
            query_val, preferred_keys, used_keys, fallback[0],
        )
    return best_of(fallback)


def generate_address_rows(records: Iterable[dict]) -> Iterator[dict]:
    """Extract address data from validated records.
    
    Yields rows with all ADDRESS_COLUMNS, PARENT_ENTITY_COLUMNS, PROVENANCE_COLUMNS,
    and their target_* equivalents, ensuring consistent schema.
    """
    skipped = 0
    for record in records:
        if record.get("osm") is None:
            skipped += 1
            log.debug("Skipping record with no OSM result: %s", record.get("address_query", {}))
            continue
        
        crawl_data = record.get("crawl", {})
        crawl_metadata = crawl_data.get("crawl_metadata", {})
        data = crawl_data.get("data", {})
        
        query_data = record["address_query"]
        target_data = record["osm"]["properties"]["geocoding"]
        # Raw address object — used as fallback for fields not stored in geocoding (e.g. province)
        raw_address = record["osm"]["properties"].get("address") or {}
        assert target_data is not None
        assert query_data is not None
        
        # Start with a template to ensure all columns exist
        row = {}
        
        # Core address fields from query
        row["name"] = _extract_str(query_data.get("name"))
        row["street"] = _extract_str(query_data.get("street"))
        row["city"] = _extract_str(query_data.get("city"))
        row["state"] = _extract_str(query_data.get("state"))
        row["country"] = _extract_str(query_data.get("country"))
        row["postalcode"] = _extract_str(query_data.get("postalcode"))
        
        # Target fields from OSM
        row["target_name"] = target_data.get("name")
        row["target_street"] = target_data.get("street")
        row["target_house_number"] = target_data.get("housenumber")
        row["target_city"] = pick_best_osm_field(
            _extract_str(query_data.get("city")),
            raw_address,
            _LOCALITY_PREFERRED,
            _LOCALITY_FALLBACK,
        )
        row["target_state"] = pick_best_osm_field(
            _extract_str(query_data.get("state")),
            raw_address,
            _REGION_PREFERRED,
            _REGION_FALLBACK,
        )
        row["target_country"] = target_data.get("country")
        row["target_postalcode"] = target_data.get("postcode")
        row["target_countrycode"] = target_data.get("country_code")
        row["target_label"] = target_data.get("label")
        
        # Parent entity fields (telephone, email, url, etc.)
        for field in PARENT_ENTITY_COLUMNS:
            value = data.get(field)
            # Handle list fields (e.g., openingHours may be a list)
            if isinstance(value, list):
                value = ", ".join(str(v) for v in value if v)
            row[field] = value
        
        # Crawl metadata / provenance
        row["crawl_url"] = crawl_metadata.get("url")
        row["crawl_source"] = crawl_metadata.get("source")
        
        # Flatten provenance dict
        provenance = crawl_metadata.get("provenance", {})
        row["provenance_graph_iri"] = provenance.get("graph_iri")
        row["provenance_wdc_release"] = provenance.get("wdc_release")
        row["provenance_subset"] = provenance.get("subset")
        row["provenance_source_file"] = provenance.get("source_file")
        row["provenance_format"] = provenance.get("format")
        
        # OSM geospatial and metadata
        osm = record.get("osm", {})
        geometry = osm.get("geometry", {})
        coords = geometry.get("coordinates", [])
        osm_lat = None
        osm_lon = None
        if len(coords) == 2:
            osm_lon = coords[0]  # OSM uses [lon, lat]
            osm_lat = coords[1]
            row["osm_longitude"] = osm_lon
            row["osm_latitude"] = osm_lat
        else:
            row["osm_longitude"] = None
            row["osm_latitude"] = None
        
        row["osm_id"] = target_data.get("osm_id")
        row["osm_type"] = target_data.get("osm_type")
        row["osm_key"] = target_data.get("osm_key")
        row["osm_value"] = target_data.get("osm_value")
        row["osm_importance"] = target_data.get("importance")
        row["osm_place_rank"] = target_data.get("place_rank")
        row["osm_neighbourhood"] = target_data.get("neighbourhood")
        row["osm_borough"] = target_data.get("borough")
        row["osm_suburb"] = target_data.get("suburb")
        row["osm_county"] = target_data.get("county")
        row["osm_district"] = target_data.get("district")
        row["osm_state_district"] = target_data.get("state_district")
        # iso3166, extratags, namedetails are dicts; serialize to JSON strings
        iso3166 = target_data.get("iso3166")
        row["osm_iso3166"] = json.dumps(iso3166, ensure_ascii=False) if iso3166 else None
        extratags = target_data.get("extratags")
        row["osm_extratags"] = json.dumps(extratags, ensure_ascii=False) if extratags else None
        namedetails = target_data.get("namedetails")
        row["osm_namedetails"] = json.dumps(namedetails, ensure_ascii=False) if namedetails else None
        
        # Ensure all values are strings or None (consistent types)
        row = {k: ensure_string(v) for k, v in row.items()}
        yield row

    if skipped:
        log.info("generate_address_rows: skipped %d record(s) with no OSM result", skipped)


def generate_section_rows(section_dir: Path) -> Iterator[dict]:
    """Generate rows from all .json.gz files in a directory."""
    if not section_dir.is_dir():
        raise ValueError(f"Not a directory: {section_dir}")
    section_files = list(section_dir.glob("*.json.gz"))
    for file_path in tqdm(section_files, desc=f"Processing {section_dir.name}"):
        file_records = read_from_jsongz(file_path)
        yield from generate_address_rows(file_records)


def split_street_number_field(records: Iterable[dict]) -> Iterator[dict]:
    def split_street_number(street: str) -> tuple[str | None, str | None]:
        parsed: list[tuple[str, str]] = postal_parse_address(street)
        d = {field: value for value, field in parsed}
        road = d.get("road")
        road = road.title() if road else None
        house_number = d.get("house_number")
        house_number = house_number.title() if house_number else None
        return road, house_number

    for record in records:
        if record.get("street") is None:
            record["street"] = None
            record["house_number"] = None
        else:
            street, house = split_street_number(record["street"])
            record["street"] = street
            record["house_number"] = house
        yield record


def add_country_code(records: Iterable[dict]) -> Iterator[dict]:
    for record in records:
        country = record.get("country")
        if country and re.match(r"^[A-Za-z]{2}$", country):
            record["countrycode"] = country.lower()
        else:
            record["countrycode"] = None
        yield record


def create_section_datasets(validated_root: Path):
    """Create parquet files from validated data.
    
    Handles both:
    - Nested structure: validated_root/SectionA/*.json.gz, validated_root/SectionB/*.json.gz
    - Flat structure: validated_root/*.json.gz (creates single addresses.parquet)
    """
    validated_root = Path(validated_root)
    
    # Check if this is a flat structure (JSON files directly in root)
    json_files_in_root = list(validated_root.glob("*.json.gz"))
    if json_files_in_root:
        # Flat structure: process all files as one section
        outfile = validated_root / "addresses.parquet"
        print(f"Processing flat directory: {validated_root}")
        print(f"  Found {len(json_files_in_root)} JSON files")
        
        row_gen = generate_section_rows(validated_root)
        row_gen = split_street_number_field(row_gen)
        row_gen = add_country_code(row_gen)
        row_gen = (
            row
            for row in row_gen
            if any(row[c] is not None for c in ["street", "city", "postalcode"])
        )
        rows = list(row_gen)
        if not rows:
            print(f"  No valid rows found")
            log.warning("No valid rows found in flat directory: %s", validated_root)
            return
        
        df = pl.DataFrame(rows, infer_schema_length=len(rows))
        before_dedup = len(df)
        df = df.unique()
        dupes = before_dedup - len(df)
        
        # Select all available columns
        available_cols = [c for c in COLUMNS + TARGET_COLUMNS if c in df.columns]
        df = df.select(available_cols)

        df.write_parquet(outfile, compression="brotli")
        print(f"  ✓ Created {outfile} ({len(df)} rows)")
        log.info("Flat dir %s: %d rows written (%d dupes dropped)", validated_root.name, len(df), dupes)
    else:
        # Nested structure: process each subdirectory
        subdirs = [d for d in validated_root.iterdir() if d.is_dir()]
        if not subdirs:
            print(f"Warning: No subdirectories or JSON files found in {validated_root}")
            log.warning("No subdirectories or JSON files found in %s", validated_root)
            return
        
        print(f"Processing nested directories: {validated_root}")
        for section_dir in subdirs:
            outfile = section_dir / "addresses.parquet"
            print(f"  Processing {section_dir.name}...")
            
            row_gen = generate_section_rows(section_dir)
            row_gen = split_street_number_field(row_gen)
            row_gen = add_country_code(row_gen)
            row_gen = (
                row
                for row in row_gen
                if any(row[c] is not None for c in ["street", "city", "postalcode"])
            )
            rows = list(row_gen)
            if not rows:
                print(f"    No valid rows found")
                log.warning("No valid rows found in section: %s", section_dir.name)
                continue
            
            df = pl.DataFrame(rows, infer_schema_length=len(rows))
            before_dedup = len(df)
            df = df.unique()
            dupes = before_dedup - len(df)
            
            # Select all available columns
            available_cols = [c for c in COLUMNS + TARGET_COLUMNS if c in df.columns]
            df = df.select(available_cols)

            df.write_parquet(outfile, compression="brotli")
            print(f"    ✓ Created {outfile} ({len(df)} rows)")
            log.info("Section %s: %d rows written (%d dupes dropped)", section_dir.name, len(df), dupes)


def _sanitize_line_terminators(df: pl.DataFrame) -> pl.DataFrame:
    """Replace Unicode line/paragraph separators (U+2028, U+2029) in all
    string columns with a space so CSV files don't contain unusual line endings."""
    str_cols = [c for c, dtype in zip(df.columns, df.dtypes) if dtype == pl.Utf8 or dtype == pl.String]
    if not str_cols:
        return df
    return df.with_columns(
        pl.col(c).str.replace_all(r"[\u2028\u2029]", " ") for c in str_cols
    )


def create_csvs(parquet_file: Path, dataset_dir: Path):
    """Export validated addresses to CSV files.

    Creates:
    - values.csv: Query address fields (aligned schema: name, road, house_number, postcode, locality, region, country, country_code) + crawl lat/lon
    - targets.csv: OSM-validated address fields (same aligned schema) + OSM lat/lon
    - provenance.csv: id + crawl metadata (source, provenance) + sameAs
    - dataset_full.csv: All columns joined (query + target + provenance)
    """
    df = pl.read_parquet(parquet_file)
    df = _sanitize_line_terminators(df)
    dataset_dir.mkdir(parents=True, exist_ok=True)

    # Aligned schema rename maps (internal name -> published name)
    QUERY_RENAME = {
        "street":      "road",
        "postalcode":  "postcode",
        "city":        "locality",
        "state":       "region",
        "countrycode": "country_code",
    }
    TARGET_RENAME = {
        "target_name":         "name",
        "target_street":       "road",
        "target_house_number": "house_number",
        "target_postalcode":   "postcode",
        "target_city":         "locality",
        "target_state":        "region",
        "target_country":      "country",
        "target_countrycode":  "country_code",
        "osm_latitude":        "latitude",
        "osm_longitude":       "longitude",
    }

    # --- values.csv: query address fields (aligned schema) + crawl lat/lon ---
    query_addr_cols = ["name", "street", "house_number", "postalcode", "city", "state", "country", "countrycode"]
    values_cols = ["id"] + [c for c in query_addr_cols + ["latitude", "longitude"] if c in df.columns]
    values_df = df.select(values_cols).rename({k: v for k, v in QUERY_RENAME.items() if k in df.columns})
    values_df.write_csv(dataset_dir / "values.csv")
    # experiment version: core address fields only (no lat/lon)
    experiment_addr_cols = ["name", "road", "house_number", "postcode", "locality", "region", "country", "country_code"]
    values_df.select(["id"] + [c for c in experiment_addr_cols if c in values_df.columns]).write_csv(dataset_dir / "values_experiment.csv")

    # --- targets.csv: OSM address fields (aligned schema) + OSM lat/lon ---
    target_addr_cols = [
        "target_name", "target_street", "target_house_number", "target_postalcode",
        "target_city", "target_state", "target_country", "target_countrycode",
    ]
    targets_cols = ["id"] + [c for c in target_addr_cols + ["osm_latitude", "osm_longitude"] if c in df.columns]
    targets_df = df.select(targets_cols).rename({k: v for k, v in TARGET_RENAME.items() if k in df.columns})
    targets_df.write_csv(dataset_dir / "targets.csv")
    # experiment version: core address fields only (no lat/lon)
    targets_df.select(["id"] + [c for c in experiment_addr_cols if c in targets_df.columns]).write_csv(dataset_dir / "targets_experiment.csv")

    # --- provenance.csv: id + crawl metadata + selected parent entity fields ---
    parent_extra_cols = [c for c in PARENT_ENTITY_COLUMNS if c not in ("latitude", "longitude", "telephone", "email", "url", "openingHours")]
    prov_cols = ["id"] + [c for c in parent_extra_cols + PROVENANCE_COLUMNS if c in df.columns]
    df.select(prov_cols).write_csv(dataset_dir / "provenance.csv")

    # --- dataset_full.csv: everything joined (values + targets + provenance) ---
    seen = set()
    all_cols = []
    for c in ["id"] + COLUMNS + TARGET_COLUMNS:
        if c not in seen and c in df.columns:
            seen.add(c)
            all_cols.append(c)
    df.select(all_cols).write_csv(dataset_dir / "dataset_full.csv")


def _configure_logging(log_file: Path | None = None) -> None:
    """Set up INFO-level logging to stderr (and optionally a file).
    DEBUG messages (individual fallbacks) go to the file only.
    """
    fmt = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"
    datefmt = "%H:%M:%S"

    # Console: INFO and above
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    console.setFormatter(logging.Formatter(fmt, datefmt))

    handlers: list[logging.Handler] = [console]

    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setLevel(logging.DEBUG)   # DEBUG = individual fallbacks
        fh.setFormatter(logging.Formatter(fmt, datefmt))
        handlers.append(fh)

    logging.basicConfig(level=logging.DEBUG, handlers=handlers, force=True)


def main(validated_root: Path = None, dataset_dir: Path = None, log_file: Path | None = None, name_sim_threshold: int = 100, subset: str | None = None):
    if validated_root is None:
        validated_root = DEFAULT_VALIDATED_ROOT
    if dataset_dir is None:
        dataset_dir = DEFAULT_DATASET_DIR
    
    validated_root = Path(validated_root)
    dataset_dir = Path(dataset_dir)

    _configure_logging(log_file)
    log.info("Processing validated data from: %s", validated_root)
    log.info("Output dataset to: %s", dataset_dir)
    
    print(f"Processing validated data from: {validated_root}")
    print(f"Output dataset to: {dataset_dir}")
    
    # Create output directory
    dataset_dir.mkdir(parents=True, exist_ok=True)
    
    create_section_datasets(validated_root)

    # Find all addresses.parquet files (handles both flat and nested structures)
    section_datasets = list(validated_root.glob("**/addresses.parquet"))
    if not section_datasets:
        print(f"No section datasets (addresses.parquet) found in {validated_root}")
        log.warning("No section datasets (addresses.parquet) found in %s", validated_root)
        return
    
    print(f"Found {len(section_datasets)} section dataset(s)")
    log.info("Found %d section dataset(s)", len(section_datasets))
    df = pl.scan_parquet(section_datasets)

    df = df.unique()
    # Drop records missing any target attribute except target_name
    target_cols_no_name = [c for c in TARGET_COLUMNS if c != "target_name"]
    df = df.drop_nulls(subset=target_cols_no_name)
    # Filter out coarse-grained matches (place_rank < 30 means street-level or above, not a specific building/house number)
    df = df.filter(pl.col("osm_place_rank").cast(pl.Int32) == 30)
    df = df.collect()
    df = df.with_columns(pl.lit(subset if subset is not None else validated_root.name).alias("subset"))

    # --- Dataset with name (dsname) ---
    # Step 1: exclude records where target_name is null
    df_has_target_name = df.filter(pl.col("target_name").is_not_null())
    df_excluded_null_name = df.filter(pl.col("target_name").is_null())
    n_excluded_null = len(df_excluded_null_name)
    print(f"  Step 1 – null target_name: {len(df_has_target_name)} kept, {n_excluded_null} excluded")
    log.info("Step 1 – null target_name: %d kept, %d excluded", len(df_has_target_name), n_excluded_null)

    df_excluded_null_name = df_excluded_null_name.with_columns(pl.Series("id", [str(uuid.uuid4()) for _ in range(len(df_excluded_null_name))]))
    excluded_null_parquet = dataset_dir / "dataset_named_excluded_null.parquet"
    df_excluded_null_name.write_parquet(excluded_null_parquet, compression="brotli")
    # create_csvs(excluded_null_parquet, dataset_dir / "named_excluded_null")
    print(f"✓ Null-name excluded dataset: {n_excluded_null} rows -> {excluded_null_parquet}")
    log.info("Null-name excluded dataset: %d rows", n_excluded_null)

    # Step 2: exclude records where query name is null
    df_has_both_names = df_has_target_name.filter(pl.col("name").is_not_null())
    df_excluded_null_query_name = df_has_target_name.filter(pl.col("name").is_null())
    n_excluded_null_query = len(df_excluded_null_query_name)
    print(f"  Step 2 – null query name: {len(df_has_both_names)} kept, {n_excluded_null_query} excluded")
    log.info("Step 2 – null query name: %d kept, %d excluded", len(df_has_both_names), n_excluded_null_query)

    df_excluded_null_query_name = df_excluded_null_query_name.with_columns(pl.Series("id", [str(uuid.uuid4()) for _ in range(len(df_excluded_null_query_name))]))
    excluded_null_query_parquet = dataset_dir / "dataset_named_excluded_null_query.parquet"
    df_excluded_null_query_name.write_parquet(excluded_null_query_parquet, compression="brotli")
    print(f"✓ Null-query-name excluded dataset: {n_excluded_null_query} rows -> {excluded_null_query_parquet}")
    log.info("Null-query-name excluded dataset: %d rows", n_excluded_null_query)

    # Step 3: exclude records where name similarity < threshold (token set ratio)
    # Both names are unidecoded before comparison (only for scoring, originals are stored).
    df_has_both_names = df_has_both_names.with_columns(
        pl.struct(["name", "target_name"]).map_elements(
            lambda r: int(fuzz.token_set_ratio(
                unidecode(r["name"]).lower(),
                unidecode(r["target_name"]).lower(),
                processor=utils.default_process,
            )),
            return_dtype=pl.Int32,
        ).alias("name_sim_score")
    )
    df_named = df_has_both_names.filter(pl.col("name_sim_score") >= name_sim_threshold).drop("name_sim_score")
    df_excluded_low_sim = df_has_both_names.filter(pl.col("name_sim_score") < name_sim_threshold)
    n_excluded_sim = len(df_excluded_low_sim)
    print(f"  Step 3 – name similarity filter: {len(df_named)} kept, {n_excluded_sim} excluded (token_set_ratio < {name_sim_threshold})")
    log.info("Step 3 – name similarity filter: %d kept, %d excluded (token_set_ratio < %d)", len(df_named), n_excluded_sim, name_sim_threshold)

    df_named = df_named.with_columns(pl.Series("id", [str(uuid.uuid4()) for _ in range(len(df_named))]))
    named_parquet = dataset_dir / "dataset_named.parquet"
    df_named.write_parquet(named_parquet, compression="brotli")
    create_csvs(named_parquet, dataset_dir / "named")
    print(f"✓ Named dataset: {len(df_named)} rows -> {named_parquet}")
    log.info("Named dataset: %d rows", len(df_named))

    # excluded low-sim: keep name_sim_score column so comparisons are self-explanatory
    df_excluded_low_sim = df_excluded_low_sim.with_columns(pl.Series("id", [str(uuid.uuid4()) for _ in range(len(df_excluded_low_sim))]))
    excluded_sim_parquet = dataset_dir / "dataset_named_excluded_low_sim.parquet"
    df_excluded_low_sim.write_parquet(excluded_sim_parquet, compression="brotli")
    # Write a focused comparison CSV: id, name, target_name, score + all address fields
    comparison_cols = ["id", "name", "target_name", "name_sim_score",
                       "street", "target_street", "city", "target_city",
                       "postalcode", "target_postalcode", "country", "target_country"]
    comp_cols_present = [c for c in comparison_cols if c in df_excluded_low_sim.columns]
    df_excluded_low_sim.select(comp_cols_present).write_csv(
        dataset_dir / "named_excluded_low_sim_comparison.csv"
    )
    create_csvs(excluded_sim_parquet, dataset_dir / "named_excluded_low_sim")
    print(f"✓ Low-similarity excluded dataset: {n_excluded_sim} rows -> {excluded_sim_parquet}")
    log.info("Low-similarity excluded dataset: %d rows", n_excluded_sim)

    print(f"  Total excluded from named dataset: {n_excluded_null + n_excluded_null_query + n_excluded_sim} ({n_excluded_null} null target_name + {n_excluded_null_query} null query name + {n_excluded_sim} low similarity)")
    log.info("Total excluded from named dataset: %d (%d null target_name + %d null query name + %d low similarity)", n_excluded_null + n_excluded_null_query + n_excluded_sim, n_excluded_null, n_excluded_null_query, n_excluded_sim)

    # --- Dataset without name (dsnoname) ---
    # Includes all records (with or without target_name); drop name columns from both sides
    drop_name_cols = [c for c in ["name", "target_name"] if c in df.columns]
    df_unnamed = df.drop(drop_name_cols)
    df_unnamed = df_unnamed.with_columns(pl.Series("id", [str(uuid.uuid4()) for _ in range(len(df_unnamed))]))
    unnamed_parquet = dataset_dir / "dataset_unnamed.parquet"
    df_unnamed.write_parquet(unnamed_parquet, compression="brotli")
    create_csvs(unnamed_parquet, dataset_dir / "unnamed")
    print(f"✓ Unnamed dataset: {len(df_unnamed)} rows -> {unnamed_parquet}")
    log.info("Unnamed dataset: %d rows", len(df_unnamed))

    print(f"✓ Datasets created successfully at {dataset_dir}")
    log.info("Done.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Pack validated address data into Parquet/CSV datasets.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Use default paths
  python -m postalcrawl.pack.main
  
  # Process custom validated directory
  python -m postalcrawl.pack.main --validated-root /pegasus/address-paper/validated_wdc_sport_sample --output-dir ./output/sport_sample
  
  # Process WDC validated data
  python -m postalcrawl.pack.main --validated-root ./data/validated_wdc --output-dir ./data/dataset_wdc
        """
    )
    parser.add_argument(
        "--validated-root",
        type=Path,
        default=None,
        help=f"Path to validated data directory (default: {DEFAULT_VALIDATED_ROOT})",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help=f"Output directory for dataset files (default: {DEFAULT_DATASET_DIR})",
    )
    
    parser.add_argument(
        "--name-sim-threshold",
        type=int,
        default=100,
        help="Minimum token_set_ratio score (0-100) for name matching in the named dataset (default: 100)",
    )
    parser.add_argument(
        "--subset",
        type=str,
        default=None,
        help="Subset label written to the 'subset' column (default: validated_root directory name)",
    )
    parser.add_argument(
        "--log-file",
        type=Path,
        default=None,
        help="Optional path to write a detailed log file (DEBUG level, includes individual fallbacks)",
    )

    args = parser.parse_args()
    main(validated_root=args.validated_root, dataset_dir=args.output_dir, log_file=args.log_file, name_sim_threshold=args.name_sim_threshold, subset=args.subset)
