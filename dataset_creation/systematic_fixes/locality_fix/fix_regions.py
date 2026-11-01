"""Rewrite too-coarse clean region values from the derived gazetteer."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from countries import CONFIGS  # noqa: E402
from io_csv import (  # noqa: E402
    in_native_script,
    norm_name,
    norm_postcode,
    read_csv_as_strings,
    refresh_cell_labels,
)

ROOT = Path(__file__).resolve().parents[1]
logger = logging.getLogger("fix_regions")


def load_postcodes(derived: Path) -> dict[str, dict[str, str]]:
    pc = read_csv_as_strings(derived / "postcode_to_place.csv")
    out = {}
    for row in pc.itertuples(index=False):
        key = norm_postcode(row.postcode)
        if not key:
            continue
        out[key] = {
            "region": row.region or "",
            "county_unitary": row.county_unitary or "",
            "district_borough": row.district_borough or "",
            "populated_place": row.populated_place or "",
        }
    return out


def gaz_region(cfg, pc_row: dict[str, str] | None) -> str:
    if not pc_row:
        return ""
    for field in ("region", "county_unitary"):
        raw = (pc_row.get(field) or "").strip()
        if not raw:
            continue
        if cfg.region_canonical:
            mapped = cfg.region_canonical.get(norm_name(raw))
            if mapped:
                return mapped
            if norm_name(raw) in cfg.valid_regions:
                return raw
        else:
            return raw
    return ""


def load_fr_commune_index(folder: Path) -> dict[str, tuple[str, str | None]]:
    """Map a current INSEE commune code to (région, postcode).

    The postcode is set only when Hexasmal lists exactly one code for that commune.
    """
    cog_path = folder / "gazetteer" / "raw" / "cog" / "v_commune_2026.csv"
    reg_path = folder / "gazetteer" / "raw" / "cog" / "v_region_2026.csv"
    hx_path = folder / "gazetteer" / "raw" / "laposte_hexasmal.csv"
    if not cog_path.is_file() or not reg_path.is_file() or not hx_path.is_file():
        return {}
    cog = pd.read_csv(cog_path, dtype=str, keep_default_na=False)
    regs = pd.read_csv(reg_path, dtype=str, keep_default_na=False)
    reg_name = {row.REG: row.LIBELLE for row in regs.itertuples(index=False)}
    laposte = pd.read_csv(hx_path, dtype=str, keep_default_na=False, sep=";", encoding="latin-1")
    laposte.columns = [column.lstrip("#") for column in laposte.columns]
    code_col = next(column for column in laposte.columns if "insee" in column.lower())
    pc_col = next(column for column in laposte.columns if "postal" in column.lower())
    postcodes_for: dict[str, set[str]] = {}
    for code, postcode in zip(laposte[code_col], laposte[pc_col]):
        code = (code or "").strip()
        postcode = (postcode or "").strip().replace(" ", "")
        if code and postcode:
            postcodes_for.setdefault(code, set()).add(postcode)
    index: dict[str, tuple[str, str | None]] = {}
    for row in cog.itertuples(index=False):
        if row.TYPECOM != "COM":
            continue
        region = reg_name.get(row.REG, "")
        if not region:
            continue
        codes = postcodes_for.get(row.COM, set())
        unique = next(iter(codes)) if len(codes) == 1 else None
        index[row.COM] = (region, unique)
    return index


def decide(
    cfg,
    region: str,
    postcode: str,
    pcs: dict[str, dict[str, str]],
    insee: dict[str, tuple[str, str | None]] | None = None,
    dirty_postcode: str = "",
    locality: str = "",
    localities: dict[str, str] | None = None,
) -> tuple[str, str, str, str]:
    """Return new_region, new_postcode, rule, conflict."""
    n = norm_name(region)
    if n in cfg.region_alias:
        return cfg.region_alias[n], postcode, "alias", ""
    dirty_key = norm_postcode(dirty_postcode)
    dirty_region = ""
    if dirty_key and dirty_key != norm_postcode(postcode):
        dirty_region = gaz_region(cfg, pcs.get(dirty_key))
    if (
        cfg.code == "es"
        and norm_postcode(postcode) not in pcs
        and dirty_region
        and (n not in cfg.valid_regions or norm_name(dirty_region) == n)
    ):
        new_region = region if n in cfg.valid_regions else dirty_region
        return new_region, dirty_key, "dirty", ""
    if n in cfg.valid_regions:
        commune = (insee or {}).get(norm_postcode(postcode))
        if (
            commune
            and norm_postcode(postcode) not in pcs
            and dirty_region
            and norm_name(commune[0]) != n
            and norm_name(dirty_region) == n
        ):
            return region, dirty_key, "dirty", ""
        return region, postcode, "keep", ""
    needs_pc = n in cfg.coarse_regions or (cfg.valid_regions and n not in cfg.valid_regions)
    if not needs_pc:
        return region, postcode, "keep", ""
    row = pcs.get(norm_postcode(postcode))
    proposed = gaz_region(cfg, row)
    if proposed:
        return proposed, postcode, "postcode", ""
    commune = (insee or {}).get(norm_postcode(postcode))
    if commune is not None and n in cfg.coarse_regions:
        region_name, unique_postcode = commune
        if unique_postcode:
            return region_name, unique_postcode, "insee", ""
        if dirty_region:
            return dirty_region, dirty_key, "dirty", ""
        locality_region = (localities or {}).get(norm_name(locality))
        if locality_region and norm_name(locality_region) != norm_name(region_name):
            mapped = cfg.region_alias.get(norm_name(locality_region), locality_region)
            mapped = cfg.region_canonical.get(norm_name(mapped), mapped)
            return mapped, postcode, "locality", ""
        return region_name, postcode, "insee", ""
    if n in cfg.coarse_regions and dirty_region:
        return dirty_region, dirty_key, "dirty", ""
    if n in cfg.coarse_regions:
        locality_region = (localities or {}).get(norm_name(locality))
        if locality_region:
            mapped = cfg.region_alias.get(norm_name(locality_region), locality_region)
            mapped = cfg.region_canonical.get(norm_name(mapped), mapped)
            return mapped, postcode, "locality", ""
    if row is None:
        return region, postcode, "unresolved", "pc_unknown"
    return region, postcode, "unresolved", "no_proposal"


def load_locality_regions(derived: Path) -> dict[str, str]:
    """Map a settlement name to its région when that name has only one région."""
    path = derived / "settlements.csv"
    if not path.is_file():
        return {}
    frame = read_csv_as_strings(path)
    found: dict[str, set[str]] = {}
    for row in frame.itertuples(index=False):
        region = (row.county_unitary or "").strip()
        if not region:
            continue
        for raw in (row.name1, getattr(row, "name2", "")):
            name = norm_name(raw or "")
            if name:
                found.setdefault(name, set()).add(region)
    return {name: next(iter(regions)) for name, regions in found.items() if len(regions) == 1}


def run(country: str, root: Path) -> None:
    cfg = CONFIGS[country]
    folder = root / f"{cfg.prefix}_fix"
    loc_fixed = folder / f"{cfg.prefix}_clean_locality_fixed.csv"
    src = loc_fixed if loc_fixed.exists() else folder / f"{cfg.prefix}_clean.csv"
    clean = read_csv_as_strings(src)
    pcs = load_postcodes(folder / "gazetteer" / "derived")
    insee = load_fr_commune_index(folder) if country == "fr" else {}
    localities = (
        load_locality_regions(folder / "gazetteer" / "derived") if country == "fr" else {}
    )
    dirty_by_id: dict[str, str] = {}
    if country in {"fr", "es"}:
        dirty = read_csv_as_strings(folder / f"{cfg.prefix}_dirty.csv")
        dirty_by_id = dict(zip(dirty["id"], dirty["postcode"]))

    decisions = []
    new_regions = []
    new_postcodes = []
    for i in range(len(clean)):
        old = clean.at[i, "region"]
        old_postcode = clean.at[i, "postcode"]
        row_id = clean.at[i, "id"]
        new, new_postcode, rule, conflict = decide(
            cfg,
            old,
            old_postcode,
            pcs,
            insee,
            dirty_by_id.get(row_id, ""),
            clean.at[i, "locality"],
            localities,
        )
        if not in_native_script(new, cfg.code):
            new, rule, conflict = old, "unresolved", "foreign_script"
        new_regions.append(new)
        new_postcodes.append(new_postcode)
        pc_row = pcs.get(norm_postcode(old_postcode))
        decisions.append(
            {
                "row_index": str(i),
                "id": row_id,
                "old_region": old,
                "new_region": new,
                "rule": rule,
                "conflict": conflict,
                "postcode": old_postcode,
                "new_postcode": new_postcode,
                "gaz_region": (pc_row or {}).get("region", ""),
                "gaz_county": (pc_row or {}).get("county_unitary", ""),
            }
        )

    out = clean.copy()
    out["region"] = new_regions
    out["postcode"] = new_postcodes
    out_path = folder / f"{cfg.prefix}_clean_fixed.csv"
    dec_path = folder / "region_fix_decisions.csv"
    out.to_csv(out_path, index=False)
    dec = pd.DataFrame(decisions)
    dec.to_csv(dec_path, index=False)
    changed = int((dec.old_region != dec.new_region).sum())
    postcode_changed = int((dec.postcode != dec.new_postcode).sum())
    logger.info(
        "wrote %s (%d rows, %d region changes, %d postcode changes)",
        out_path,
        len(out),
        changed,
        postcode_changed,
    )
    logger.info("by rule:\n%s", dec.rule.value_counts().to_string())
    conflicts = dec.loc[dec.conflict != "", "conflict"].value_counts()
    if len(conflicts):
        logger.info("by conflict:\n%s", conflicts.to_string())
    ch = dec[dec.old_region != dec.new_region]
    if len(ch):
        logger.info(
            "top rewrites:\n%s",
            ch.groupby(["old_region", "new_region"]).size().sort_values(ascending=False).head(12).to_string(),
        )
    label_fields = {"region": new_regions, "locality": list(out["locality"])}
    if postcode_changed:
        label_fields["postcode"] = new_postcodes
    refresh_cell_labels(folder / f"{cfg.prefix}_cell_labels.csv", label_fields)


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--country", required=True, choices=["fr", "es", "au"])
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        stream=sys.stdout,
    )
    run(args.country, args.root)


if __name__ == "__main__":
    main()
