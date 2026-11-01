"""Build UK gazetteer tables from the OS Open Names GeoPackage."""

from __future__ import annotations

import argparse
import csv
import logging
import re
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

UK_DIR = Path(__file__).resolve().parent
DEFAULT_GPKG = UK_DIR / "os_open_names" / "Data" / "opname_gb.gpkg"
DEFAULT_OUT = UK_DIR / "os_open_names" / "derived"
DEFAULT_CLEAN = UK_DIR / "uk_clean.csv"

SETTLEMENT_TYPES = ("City", "Town", "Village", "Hamlet", "Suburban Area")
OTHER_SETTLEMENT_TYPE = "Other Settlement"

SETTLEMENT_FIELDS = [
    "name1",
    "name1_lang",
    "name2",
    "name2_lang",
    "local_type",
    "postcode_district",
    "district_borough",
    "district_borough_type",
    "county_unitary",
    "county_unitary_type",
    "region",
    "country",
    "same_as_dbpedia",
    "same_as_geonames",
    "id",
]
OTHER_FIELDS = [field for field in SETTLEMENT_FIELDS if not field.startswith("same_as_")]
POSTCODE_FIELDS = [
    "postcode",
    "populated_place",
    "populated_place_type",
    "district_borough",
    "county_unitary",
    "region",
    "country",
]
ADMIN_FIELDS = [
    "name",
    "role",
    "district_types",
    "county_types",
    "countries",
    "n_settlement_children",
    "also_settlement_name",
    "example_children",
]
INDEX_FIELDS = [
    "name_norm",
    "forms",
    "local_types",
    "n_forms",
    "districts",
    "counties",
    "countries",
    "ambiguous",
]

logger = logging.getLogger("derive_os_open_names")


def norm_name(value: str) -> str:
    value = re.sub(r"\s+", " ", value).strip().casefold()
    return value.replace(".", "")


def norm_postcode(value: str) -> str:
    return re.sub(r"\s+", "", value).strip().upper()


def cell(value: object) -> str:
    if value is None:
        return ""
    return str(value)


def write_csv(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fields,
            lineterminator="\r\n",
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(rows)
    logger.info("wrote %s (%d rows)", path, len(rows))


def fetch_places(connection: sqlite3.Connection, local_types: tuple[str, ...]) -> list[dict[str, str]]:
    marks = ",".join("?" for _ in local_types)
    columns = ", ".join(SETTLEMENT_FIELDS)
    query = f"""
        SELECT {columns}
        FROM named_place
        WHERE local_type IN ({marks})
        ORDER BY id
    """
    cursor = connection.execute(query, local_types)
    return [{field: cell(value) for field, value in zip(SETTLEMENT_FIELDS, row)} for row in cursor]


def fetch_postcodes(connection: sqlite3.Connection) -> list[dict[str, str]]:
    cursor = connection.execute(
        """
        SELECT name1, populated_place, populated_place_type,
               district_borough, county_unitary, region, country
        FROM named_place
        WHERE local_type = 'Postcode'
        """
    )
    rows = []
    for name1, place, place_type, district, county, region, country in cursor:
        rows.append(
            {
                "postcode": norm_postcode(cell(name1)),
                "populated_place": cell(place),
                "populated_place_type": cell(place_type),
                "district_borough": cell(district),
                "county_unitary": cell(county),
                "region": cell(region),
                "country": cell(country),
            }
        )
    rows.sort(key=lambda row: row["postcode"])
    return rows


def settlement_name_keys(settlements: list[dict[str, str]]) -> set[str]:
    keys = set()
    for row in settlements:
        for field in ("name1", "name2"):
            if row[field]:
                keys.add(norm_name(row[field]))
    return keys


def build_admin(settlements: list[dict[str, str]]) -> list[dict[str, str]]:
    """One row per district or county named on a settlement feature."""
    name_keys = settlement_name_keys(settlements)
    buckets: dict[tuple[str, str], dict] = {}

    def add(role: str, name: str, type_uri: str, country: str, child: str) -> None:
        if not name:
            return
        bucket = buckets.setdefault(
            (role, name),
            {
                "types": set(),
                "countries": set(),
                "children": set(),
            },
        )
        if type_uri:
            bucket["types"].add(type_uri)
        if country:
            bucket["countries"].add(country)
        if child:
            bucket["children"].add(child)

    for row in settlements:
        add(
            "district_borough",
            row["district_borough"],
            row["district_borough_type"],
            row["country"],
            row["name1"],
        )
        add(
            "county_unitary",
            row["county_unitary"],
            row["county_unitary_type"],
            row["country"],
            row["name1"],
        )

    rows = []
    for (role, name), bucket in buckets.items():
        children = sorted(bucket["children"], key=str.casefold)
        type_list = " | ".join(sorted(bucket["types"]))
        rows.append(
            {
                "name": name,
                "role": role,
                "district_types": type_list if role == "district_borough" else "",
                "county_types": type_list if role == "county_unitary" else "",
                "countries": "|".join(sorted(bucket["countries"])),
                "n_settlement_children": str(len(bucket["children"])),
                "also_settlement_name": "yes" if norm_name(name) in name_keys else "no",
                "example_children": "; ".join(children[:8]),
            }
        )
    rows.sort(key=lambda row: (row["name"].casefold(), row["role"]))
    return rows


def build_name_index(settlements: list[dict[str, str]]) -> list[dict[str, str]]:
    buckets: dict[str, dict] = {}
    for row in settlements:
        for field in ("name1", "name2"):
            form = row[field]
            if not form:
                continue
            key = norm_name(form)
            bucket = buckets.setdefault(
                key,
                {
                    "forms": set(),
                    "types": set(),
                    "districts": set(),
                    "counties": set(),
                    "countries": set(),
                },
            )
            bucket["forms"].add(form)
            if row["local_type"]:
                bucket["types"].add(row["local_type"])
            if row["district_borough"]:
                bucket["districts"].add(row["district_borough"])
            if row["county_unitary"]:
                bucket["counties"].add(row["county_unitary"])
            if row["country"]:
                bucket["countries"].add(row["country"])

    rows = []
    for key, bucket in buckets.items():
        forms = sorted(bucket["forms"], key=lambda form: (form.casefold(), form.swapcase()))
        districts = bucket["districts"]
        counties = bucket["counties"]
        rows.append(
            {
                "name_norm": key,
                "forms": " | ".join(forms),
                "local_types": "|".join(sorted(bucket["types"])),
                "n_forms": str(len(forms)),
                "districts": " | ".join(sorted(districts)),
                "counties": " | ".join(sorted(counties)),
                "countries": "|".join(sorted(bucket["countries"])),
                "ambiguous": "yes" if len(districts) > 1 or len(counties) > 1 else "no",
            }
        )
    rows.sort(key=lambda row: row["name_norm"])
    return rows


def locality_counts(clean_path: Path) -> list[tuple[str, int]]:
    """Return (locality, count), most frequent first. Ties break on the name."""
    counts: dict[str, int] = defaultdict(int)
    with clean_path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            counts[row.get("locality", "")] += 1
    return sorted(counts.items(), key=lambda item: (-item[1], item[0].casefold()))


def write_clean_locality_lists(
    clean_path: Path,
    settlements: list[dict[str, str]],
    admin: list[dict[str, str]],
    out_dir: Path,
) -> None:
    settlement_keys = settlement_name_keys(settlements)
    admin_keys = {norm_name(row["name"]) for row in admin if row["name"]}
    admin_only = []
    unmatched = []
    for locality, count in locality_counts(clean_path):
        key = norm_name(locality)
        record = {"locality": locality, "count": str(count)}
        if key in admin_keys and key not in settlement_keys:
            admin_only.append(record)
        elif key not in settlement_keys and key not in admin_keys:
            bare = re.sub(r"(?i)\s+CP$", "", locality).strip()
            if bare != locality and norm_name(bare) in settlement_keys:
                continue
            unmatched.append(record)
    write_csv(out_dir / "uk_clean_localities_admin_only.csv", ["locality", "count"], admin_only)
    write_csv(out_dir / "uk_clean_localities_unmatched.csv", ["locality", "count"], unmatched)


def derive(gpkg: Path, out_dir: Path, clean_path: Path | None) -> None:
    logger.info("reading %s", gpkg)
    connection = sqlite3.connect(f"file:{gpkg}?mode=ro", uri=True)
    try:
        settlements = fetch_places(connection, SETTLEMENT_TYPES)
        other = fetch_places(connection, (OTHER_SETTLEMENT_TYPE,))
        postcodes = fetch_postcodes(connection)
    finally:
        connection.close()

    admin = build_admin(settlements)
    index = build_name_index(settlements)
    write_csv(out_dir / "settlements.csv", SETTLEMENT_FIELDS, settlements)
    write_csv(out_dir / "other_settlement.csv", OTHER_FIELDS, other)
    write_csv(out_dir / "settlement_name_index.csv", INDEX_FIELDS, index)
    write_csv(out_dir / "admin_units.csv", ADMIN_FIELDS, admin)
    write_csv(out_dir / "postcode_to_place.csv", POSTCODE_FIELDS, postcodes)
    if clean_path is not None and clean_path.is_file():
        write_clean_locality_lists(clean_path, settlements, admin, out_dir)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gpkg", type=Path, default=DEFAULT_GPKG)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--clean",
        type=Path,
        default=DEFAULT_CLEAN,
        help="uk_clean.csv used for the admin-only and unmatched locality lists",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout)
    derive(args.gpkg, args.out_dir, args.clean)


if __name__ == "__main__":
    main()
