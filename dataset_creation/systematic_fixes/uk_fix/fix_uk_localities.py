"""Rewrite UK clean locality values from OS Open Names."""

from __future__ import annotations

import argparse
import csv
import logging
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

import pandas as pd

DEFAULT_UK_DIR = Path(__file__).resolve().parent
DEFAULT_DERIVED = DEFAULT_UK_DIR / "os_open_names" / "derived"
DEFAULT_NI_PLACENAMES = (
    DEFAULT_UK_DIR / "os_open_names" / "Data" / "osni_open_data_-_gazetteer_-_place_names.csv"
)

logger = logging.getLogger("fix_uk_localities")

# One council name is the town in the scraped locality. The other two unmatched
# NI rows are left out of the repaired files rather than rewritten.
MANUAL_LOCALITY_BY_ID = {
    "2992b2d3-3186-472e-a7f2-8223ddded687": "Bangor",
}
EXCLUDED_ROW_IDS = {
    "9e6a3b2d-d5bc-4b23-aed7-5720e4cbfed3",  # Causeway Coast and Glens District
    "c4e27a09-5865-477c-b08b-3aa4722427b0",  # Oritor
}

LONDONISH = {
    "london",
    "londres",
    "londra",
    "lontoo",
    "londen",
    "londyn",
    "londýn",
    "λονδίνο",
    "לונדון",
    "لندن",
    "ロンドン",
    "倫敦",
    "런던",
}

CITY_SUFFIX_KEEP = {"welwyn garden city"}

LOCALITY_SPELLING = {
    "lytham st anne's": "Lytham St Anne's",
    "lytham st annes": "Lytham St Anne's",
    "newark on trent": "Newark-on-Trent",
    "newark-on-trent": "Newark-on-Trent",
    "st ives": "St Ives",
    "st neots": "St Neots",
    "wells-next-the-sea": "Wells-next-the-Sea",
}


# District labels, not the town on the row. Elmbridge, Runnymede, Sandwell
# and Waverley also name a suburb or village, so a settlement hit must not
# keep the district. Hart's only rows are the Hampshire district.
DISTRICT_NOT_A_SETTLEMENT = frozenset(
    {
        "adur",
        "east suffolk",
        "elmbridge",
        "hart",
        "mid sussex",
        "runnymede",
        "sandwell",
        "vale of white horse",
        "waverley",
        "west lancashire",
    }
)


def read_csv_as_strings(path: Path, usecols: Iterable[str] | None = None) -> pd.DataFrame:
    return pd.read_csv(
        path,
        dtype=str,
        keep_default_na=False,
        na_filter=False,
        usecols=list(usecols) if usecols is not None else None,
    )


def norm_name(value: str) -> str:
    value = re.sub(r"\s+", " ", value).strip().casefold()
    return value.replace(".", "")


def norm_postcode(value: str) -> str:
    return re.sub(r"\s+", "", value).strip().upper()


def bilingual_parts(value: str) -> list[str]:
    """Split Open Names bilingual forms like 'Cardigan / Aberteifi'."""
    if not value:
        return []
    parts = [p.strip() for p in value.split(" / ")]
    return [p for p in parts if p]


def bilingual_first(value: str) -> str:
    parts = bilingual_parts(value)
    return parts[0] if parts else value.strip()


def strip_alias(value: str) -> str | None:
    """Return stripped form if value looks like City of X / X City / X CP, else None."""
    raw = re.sub(r"\s+", " ", value).strip()
    if not raw:
        return None
    n = norm_name(raw)
    if n in CITY_SUFFIX_KEEP:
        return None
    out = raw
    changed = False
    m = re.match(r"(?i)^City of\s+(.+)$", out)
    if m:
        out = m.group(1).strip()
        changed = True
    if re.search(r"(?i)\s+City$", out) and norm_name(out) not in CITY_SUFFIX_KEEP:
        out = re.sub(r"(?i)\s+City$", "", out).strip()
        changed = True
    if re.search(r"(?i)\s+CP$", out):
        out = re.sub(r"(?i)\s+CP$", "", out).strip()
        changed = True
    return out if changed and out else None


@dataclass(frozen=True)
class SettlementHit:
    name1: str
    districts: frozenset[str]
    counties: frozenset[str]


@dataclass
class Gazetteer:
    settlements: dict[str, SettlementHit]
    admin_names: dict[str, str]  # norm -> display name
    london_boroughs: dict[str, str]  # norm -> display
    postcodes: dict[str, dict[str, str]]
    postcode_sectors: dict[str, str] = field(default_factory=dict)

    def is_london_admin(self, locality: str) -> bool:
        n = norm_name(locality)
        if n in {"greater london", "city of westminster", "city of london"}:
            return True
        if n == norm_name("City and County of the City of London"):
            return True
        return n in self.london_boroughs

    def is_admin(self, locality: str) -> bool:
        return norm_name(locality) in self.admin_names

    def settlement(self, locality: str) -> SettlementHit | None:
        direct = self.settlements.get(norm_name(locality))
        if direct is not None:
            return direct
        parts = [p.strip() for p in re.split(r"\s*/\s*", locality) if p.strip()]
        if len(parts) < 2:
            return None
        hits: list[SettlementHit] = []
        seen: set[str] = set()
        for part in parts:
            hit = self.settlements.get(norm_name(part))
            if hit is not None and hit.name1 not in seen:
                seen.add(hit.name1)
                hits.append(hit)
        if len(hits) == 1:
            return hits[0]
        return None

    def lookup_postcode(self, postcode: str) -> dict[str, str] | None:
        key = norm_postcode(postcode)
        if not key:
            return None
        return self.postcodes.get(key)

    def sector_place(self, postcode: str) -> str:
        key = norm_postcode(postcode)
        if len(key) <= 2:
            return ""
        return self.postcode_sectors.get(key[:-2], "")


def display_place(raw: str) -> str:
    """Title-case an all-caps OSNI name.

    Both sides of an apostrophe are capitalized, so Helen's stays Helen's and
    O'Neill does not become O'neill. Mc/Mac stay one word: Macosquin is not
    Mac + Osquin.
    """
    text = raw.strip().strip('"')

    def repl(match: re.Match[str]) -> str:
        word = match.group(0)
        if "'" in word:
            left, right = word.split("'", 1)
            right_out = "s" if right.casefold() == "s" else right.capitalize()
            return f"{left.capitalize()}'{right_out}"
        return word.capitalize()

    return re.sub(r"[A-Za-z]+(?:'[A-Za-z]+)?", repl, text)


def load_ni_placenames(path: Path, buckets: dict[str, dict]) -> int:
    """Add OSNI towns that are not already in the GB settlement index.

    Existing names are left alone so a GB homonym (Newcastle) keeps its county.
    """
    frame = read_csv_as_strings(path)
    added = 0
    for raw in frame["PLACENAME"]:
        name = display_place(raw)
        key = norm_name(name)
        if not key or key in buckets:
            continue
        buckets[key] = {
            "name1": name,
            "districts": set(),
            "counties": {"Northern Ireland"},
        }
        added += 1
    return added


def load_gazetteer(derived_dir: Path, ni_placenames: Path | None = None) -> Gazetteer:
    settlements_df = read_csv_as_strings(derived_dir / "settlements.csv")
    admin_df = read_csv_as_strings(derived_dir / "admin_units.csv")
    pc_df = read_csv_as_strings(
        derived_dir / "postcode_to_place.csv",
        usecols=[
            "postcode",
            "populated_place",
            "populated_place_type",
            "district_borough",
            "county_unitary",
            "region",
            "country",
        ],
    )

    buckets: dict[str, dict] = {}
    london_boroughs: dict[str, str] = {}

    def add_name(key: str, name1: str, district: str, county: str) -> None:
        if not key:
            return
        b = buckets.setdefault(
            key,
            {"name1": name1, "districts": set(), "counties": set()},
        )
        if not b["name1"] and name1:
            b["name1"] = name1
        if district:
            b["districts"].add(district)
        if county:
            b["counties"].add(county)

    main_keys: set[str] = set()
    for row in settlements_df.itertuples(index=False):
        name1 = (row.name1 or "").strip()
        district = (row.district_borough or "").strip()
        county = (row.county_unitary or "").strip()
        if county == "Greater London" and district:
            london_boroughs[norm_name(district)] = district
        key = norm_name(name1)
        add_name(key, name1, district, county)
        if key:
            main_keys.add(key)
    for row in settlements_df.itertuples(index=False):
        name1 = (row.name1 or "").strip()
        name2 = (row.name2 or "").strip()
        district = (row.district_borough or "").strip()
        county = (row.county_unitary or "").strip()
        key = norm_name(name2)
        if key and key not in main_keys:
            add_name(key, name1 or name2, district, county)

    ni_path = (
        DEFAULT_NI_PLACENAMES
        if ni_placenames is None
        else ni_placenames
    )
    if ni_path.is_file():
        added = load_ni_placenames(ni_path, buckets)
        logger.info("OSNI place names: added %d settlements from %s", added, ni_path)
    else:
        logger.warning("OSNI place names not found: %s", ni_path)

    london_boroughs[norm_name("City of Westminster")] = "City of Westminster"
    london_boroughs[norm_name("City of London")] = "City of London"
    london_boroughs[norm_name("City and County of the City of London")] = (
        "City and County of the City of London"
    )

    settlements = {
        key: SettlementHit(
            name1=val["name1"],
            districts=frozenset(val["districts"]),
            counties=frozenset(val["counties"]),
        )
        for key, val in buckets.items()
        if val["name1"]
    }

    admin_names = {
        norm_name(row.name): row.name
        for row in admin_df.itertuples(index=False)
        if (row.name or "").strip()
    }
    admin_names.setdefault(norm_name("Greater London"), "Greater London")

    postcodes = {
        row.postcode: {
            "populated_place": row.populated_place,
            "populated_place_type": row.populated_place_type,
            "district_borough": row.district_borough,
            "county_unitary": row.county_unitary,
            "region": row.region,
            "country": row.country,
        }
        for row in pc_df.itertuples(index=False)
        if row.postcode
    }
    sector_counts: dict[str, Counter[str]] = {}
    for code, row in postcodes.items():
        place = bilingual_first(row["populated_place"])
        if not place or len(code) <= 2:
            continue
        sector_counts.setdefault(code[:-2], Counter())[place] += 1
    postcode_sectors = {}
    for sector, counts in sector_counts.items():
        total = sum(counts.values())
        place, count = counts.most_common(1)[0]
        if total >= 10 and count / total >= 0.8:
            postcode_sectors[sector] = place

    logger.info(
        "gazetteer: %d settlements, %d admin units, %d london boroughs, %d postcodes",
        len(settlements),
        len(admin_names),
        len(london_boroughs),
        len(postcodes),
    )
    return Gazetteer(
        settlements=settlements,
        admin_names=admin_names,
        london_boroughs=london_boroughs,
        postcodes=postcodes,
        postcode_sectors=postcode_sectors,
    )


def classify(gaz: Gazetteer, locality: str) -> str:
    if gaz.is_london_admin(locality):
        return "london_admin"
    if norm_name(locality) in DISTRICT_NOT_A_SETTLEMENT:
        return "other_admin"
    if strip_alias(locality) is not None:
        return "alias"
    if gaz.is_admin(locality) and gaz.settlement(locality) is None:
        return "other_admin"
    if gaz.settlement(locality) is not None:
        return "settlement"
    return "unmatched"


def canonical_settlement_name(gaz: Gazetteer, locality: str) -> str | None:
    hit = gaz.settlement(locality)
    return hit.name1 if hit else None


def settlement_in_admin(gaz: Gazetteer, settlement_name: str, admin_name: str) -> bool:
    hit = gaz.settlement(settlement_name)
    if hit is None:
        return False
    admin = admin_name.strip()
    return admin in hit.districts or admin in hit.counties


def locality_candidates(value: str) -> list[str]:
    """Pieces of a scraped locality, including text split on a comma or newline."""
    found: list[str] = []
    for part in re.split(r"[\n,]", value):
        part = re.sub(r"\s+", " ", part).strip(" .")
        if part and part not in found:
            found.append(part)
    return found


def settlement_named_in_text(gaz: Gazetteer, admin_name: str, text: str) -> str | None:
    """Longest settlement of this district written as a whole word in text."""
    text_n = norm_name(text)
    if not text_n:
        return None
    admin_n = norm_name(admin_name)
    best_key = ""
    best_name = ""
    for key, hit in gaz.settlements.items():
        if len(key) < 4 or key == admin_n:
            continue
        parents = {norm_name(item) for item in hit.districts | hit.counties}
        if admin_n not in parents:
            continue
        if re.search(rf"(?<!\w){re.escape(key)}(?!\w)", text_n) and len(key) > len(best_key):
            best_key = key
            best_name = hit.name1
    return best_name or None


def propose(
    gaz: Gazetteer,
    clean_locality: str,
    dirty_locality: str,
    clean_postcode: str,
    clean_class: str,
    clean_name: str = "",
    dirty_name: str = "",
) -> tuple[str | None, str]:
    """Return (proposed_locality or None, rule)."""
    if clean_class == "london_admin":
        return "London", "london_collapse"

    if clean_class == "alias":
        stripped = strip_alias(clean_locality)
        if stripped:
            canon = canonical_settlement_name(gaz, stripped)
            if canon:
                return canon, "alias"

    if clean_class in {"other_admin", "alias"}:
        candidates = locality_candidates(dirty_locality)
        for cand in list(candidates):
            stripped_dirty = strip_alias(cand)
            if stripped_dirty and stripped_dirty not in candidates:
                candidates.append(stripped_dirty)
        for cand in candidates:
            if norm_name(cand) == norm_name(clean_locality):
                continue
            canon = canonical_settlement_name(gaz, cand)
            if canon and norm_name(canon) == norm_name(clean_locality):
                continue
            if canon and settlement_in_admin(gaz, canon, clean_locality):
                return canon, "dirty"
            if clean_class == "alias":
                stripped_clean = strip_alias(clean_locality)
                if (
                    stripped_clean
                    and canon
                    and norm_name(canon) == norm_name(stripped_clean)
                ):
                    return canon, "dirty"

        pc = gaz.lookup_postcode(clean_postcode)
        if pc and pc["populated_place"]:
            place = bilingual_first(pc["populated_place"])
            canon = canonical_settlement_name(gaz, place) or place
            if not (
                clean_class == "other_admin" and norm_name(canon) == norm_name(clean_locality)
            ):
                return canon, "postcode"
        if clean_class == "other_admin":
            sector_place = gaz.sector_place(clean_postcode)
            if sector_place and norm_name(sector_place) != norm_name(clean_locality):
                canon = canonical_settlement_name(gaz, sector_place) or sector_place
                return canon, "postcode"
            for text in (clean_name, dirty_name):
                mentioned = settlement_named_in_text(gaz, clean_locality, text)
                if mentioned:
                    return mentioned, "dirty"
        if clean_class == "alias":
            stripped = strip_alias(clean_locality)
            if stripped:
                return stripped, "alias"
        return None, "unresolved"

    if clean_class == "settlement":
        return clean_locality, "keep"

    if norm_name(clean_locality) == "highcliffe-on-sea":
        canon = canonical_settlement_name(gaz, "Christchurch")
        if canon:
            return canon, "manual"

    return None, "unresolved"


def _names_match(a: str, b: str) -> bool:
    if not a or not b:
        return False
    na, nb = norm_name(a), norm_name(b)
    if na == nb:
        return True
    a_parts = {norm_name(p) for p in bilingual_parts(a)} or {na}
    b_parts = {norm_name(p) for p in bilingual_parts(b)} or {nb}
    return bool(a_parts & b_parts)


def pc_ok(gaz: Gazetteer, place: str, pc_row: dict[str, str] | None, *, required: bool) -> str:
    """Return 'ok', 'abstain', or 'fail'."""
    if pc_row is None:
        return "fail" if required else "abstain"

    if _names_match(place, pc_row.get("populated_place", "")):
        return "ok"

    if norm_name(place) == "london":
        if pc_row.get("county_unitary") == "Greater London":
            return "ok"
        district = pc_row.get("district_borough", "")
        if district and norm_name(district) in gaz.london_boroughs:
            return "ok"
        return "fail"

    hit = gaz.settlement(place)
    if hit:
        district = pc_row.get("district_borough", "")
        county = pc_row.get("county_unitary", "")
        if district and district in hit.districts:
            return "ok"
        if county and county in hit.counties:
            return "ok"

    pp = bilingual_first(pc_row.get("populated_place", ""))
    pp_hit = gaz.settlement(pp) if pp else None
    if hit and pp_hit:
        if hit.districts & pp_hit.districts or hit.counties & pp_hit.counties:
            return "ok"

    return "fail"


def dirty_loc_ok(gaz: Gazetteer, place: str, dirty_locality: str) -> str:
    """Return 'ok' or 'abstain'. Abstain covers empty, unknown, and contradicting names."""
    dirty = re.sub(r"\s+", " ", dirty_locality).strip()
    if not dirty:
        return "abstain"

    if _names_match(place, dirty):
        return "ok"

    stripped = strip_alias(dirty)
    if stripped and _names_match(place, stripped):
        return "ok"

    dn = norm_name(dirty)

    if norm_name(place) == "london":
        if dn in LONDONISH or dn == "greater london" or "london" in dn:
            return "ok"
        if gaz.is_london_admin(dirty):
            return "ok"
        dirty_hit = gaz.settlement(dirty) or (gaz.settlement(stripped) if stripped else None)
        if dirty_hit and "Greater London" in dirty_hit.counties:
            return "ok"
        return "abstain"

    hit = gaz.settlement(place)
    if hit:
        parents = {norm_name(x) for x in hit.districts | hit.counties}
        if dn in parents:
            return "ok"
    return "abstain"


def verify(
    gaz: Gazetteer,
    proposed: str,
    dirty_locality: str,
    clean_postcode: str,
    dirty_postcode: str,
    *,
    require_clean_pc: bool,
) -> tuple[bool, str, str, str, str, str, str]:
    """Return accepted, conflict, clean place, dirty place, clean status, dirty postcode status, dirty locality status.

    The two dirty statuses are only 'ok' or 'abstain'. Abstain means the dirty
    value was missing or named a different place; it never rejects the row.
    """
    clean_row = gaz.lookup_postcode(clean_postcode)
    dirty_row = gaz.lookup_postcode(dirty_postcode)

    clean_status = pc_ok(gaz, proposed, clean_row, required=require_clean_pc)
    dirty_pc_status = pc_ok(gaz, proposed, dirty_row, required=False)
    if dirty_pc_status == "fail":
        dirty_pc_status = "abstain"
    dirty_loc_status = dirty_loc_ok(gaz, proposed, dirty_locality)

    clean_pc_place = bilingual_first((clean_row or {}).get("populated_place", ""))
    dirty_pc_place = bilingual_first((dirty_row or {}).get("populated_place", ""))

    if clean_status == "fail":
        conflict = "pc_unknown" if clean_row is None else "clean_pc_mismatch"
        return False, conflict, clean_pc_place, dirty_pc_place, clean_status, dirty_pc_status, dirty_loc_status
    return True, "", clean_pc_place, dirty_pc_place, clean_status, dirty_pc_status, dirty_loc_status


def apply_spelling(result: dict[str, str]) -> dict[str, str]:
    """Rewrite a locality to the single Open Names spelling of its pair."""
    spelling = LOCALITY_SPELLING.get(norm_name(result["new_locality"]))
    if not spelling or spelling == result["new_locality"]:
        return result
    result = dict(result)
    result["new_locality"] = spelling
    result["proposed"] = spelling
    result["accepted"] = "true"
    result["rule"] = "alias"
    result["conflict"] = ""
    return result


def fix_row(
    gaz: Gazetteer,
    *,
    clean_locality: str,
    dirty_locality: str,
    clean_postcode: str,
    dirty_postcode: str,
    clean_name: str = "",
    dirty_name: str = "",
) -> dict[str, str]:
    clean_class = classify(gaz, clean_locality)
    proposed, rule = propose(
        gaz,
        clean_locality,
        dirty_locality,
        clean_postcode,
        clean_class,
        clean_name,
        dirty_name,
    )

    if rule == "keep":
        return apply_spelling({
            "old_locality": clean_locality,
            "new_locality": clean_locality,
            "proposed": clean_locality,
            "accepted": "true",
            "rule": "keep",
            "conflict": "",
            "clean_class": clean_class,
            "clean_pc_place": bilingual_first(
                (gaz.lookup_postcode(clean_postcode) or {}).get("populated_place", "")
            ),
            "dirty_pc_place": bilingual_first(
                (gaz.lookup_postcode(dirty_postcode) or {}).get("populated_place", "")
            ),
            "clean_pc_ok": "abstain",
            "dirty_pc_ok": "abstain",
            "dirty_loc_ok": "abstain",
        })

    if proposed is None or rule == "unresolved":
        return apply_spelling({
            "old_locality": clean_locality,
            "new_locality": clean_locality,
            "proposed": proposed or "",
            "accepted": "false",
            "rule": "unresolved",
            "conflict": "no_proposal",
            "clean_class": clean_class,
            "clean_pc_place": bilingual_first(
                (gaz.lookup_postcode(clean_postcode) or {}).get("populated_place", "")
            ),
            "dirty_pc_place": bilingual_first(
                (gaz.lookup_postcode(dirty_postcode) or {}).get("populated_place", "")
            ),
            "clean_pc_ok": "abstain",
            "dirty_pc_ok": "abstain",
            "dirty_loc_ok": "abstain",
        })

    (
        accepted,
        conflict,
        clean_pc_place,
        dirty_pc_place,
        clean_status,
        dirty_pc_status,
        dirty_loc_status,
    ) = verify(
        gaz,
        proposed,
        dirty_locality,
        clean_postcode,
        dirty_postcode,
        require_clean_pc=rule != "london_collapse"
        and not (rule == "alias" and _names_match(dirty_locality, proposed or "")),
    )

    if (
        not accepted
        and conflict == "clean_pc_mismatch"
        and clean_pc_place
        and _names_match(clean_pc_place, dirty_pc_place)
    ):
        accepted = True
        conflict = ""
        rule = "postcode"
        proposed = clean_pc_place
        clean_status = "ok"
        dirty_pc_status = "ok"
    if (
        not accepted
        and norm_name(clean_locality) == "city of nottingham"
        and norm_name(proposed or "") == "nottingham"
    ):
        accepted = True
        conflict = ""
        rule = "alias"
        proposed = "Nottingham"
    if (
        not accepted
        and norm_name(clean_locality) == "city of edinburgh"
        and norm_name(proposed or "") == "edinburgh"
        and not clean_pc_place
    ):
        dirty_hit = gaz.settlement(re.sub(r"\s+", " ", dirty_locality).strip())
        clean_row = gaz.lookup_postcode(clean_postcode) or {}
        county = clean_row.get("county_unitary", "")
        district = clean_row.get("district_borough", "")
        in_postcode_area = bool(
            dirty_hit
            and norm_name(dirty_hit.name1) != "edinburgh"
            and (
                (county and county in dirty_hit.counties)
                or (district and district in dirty_hit.districts)
            )
        )
        accepted = True
        conflict = ""
        if in_postcode_area and dirty_hit is not None:
            rule = "dirty"
            proposed = dirty_hit.name1
        else:
            rule = "alias"
            proposed = "Edinburgh"
    if (
        not accepted
        and clean_class == "other_admin"
        and proposed
        and not clean_pc_place
    ):
        accepted = True
        conflict = ""
    new_locality = proposed if accepted else clean_locality
    return apply_spelling({
        "old_locality": clean_locality,
        "new_locality": new_locality,
        "proposed": proposed,
        "accepted": "true" if accepted else "false",
        "rule": rule,
        "conflict": conflict,
        "clean_class": clean_class,
        "clean_pc_place": clean_pc_place,
        "dirty_pc_place": dirty_pc_place,
        "clean_pc_ok": clean_status,
        "dirty_pc_ok": dirty_pc_status,
        "dirty_loc_ok": dirty_loc_status,
    })


def _logical_csv_rows(lines: list[str]):
    """Yield start line, end line, and parsed fields for each CSV record.

    Line slices are the original text, including quoted line breaks.
    """
    cursor = {"i": 0}

    class _Lines:
        def __iter__(self):
            return self

        def __next__(self):
            i = cursor["i"]
            if i >= len(lines):
                raise StopIteration
            cursor["i"] = i + 1
            return lines[i]

    reader = csv.reader(_Lines())
    start = cursor["i"]
    for row in reader:
        end = cursor["i"]
        yield start, end, row
        start = end


def _write_kept_lines(path: Path, lines: list[str], spans: list[tuple[int, int]]) -> None:
    path.write_text("".join("".join(lines[start:end]) for start, end in spans), encoding="utf-8")


def drop_csv_ids(path: Path, drop_ids: set[str], *, id_column: str = "id") -> int:
    """Delete records whose id is in drop_ids. Every other record is copied unchanged."""
    if not drop_ids or not path.is_file():
        return 0
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    parsed = list(_logical_csv_rows(lines))
    if not parsed:
        return 0
    _, header_end, header = parsed[0]
    id_at = header.index(id_column)
    spans = [(0, header_end)]
    removed = 0
    for start, end, row in parsed[1:]:
        if row and row[id_at] in drop_ids:
            removed += 1
            continue
        spans.append((start, end))
    if removed:
        _write_kept_lines(path, lines, spans)
    return removed


def drop_cell_label_addresses(path: Path, drop_ids: set[str]) -> int:
    """Delete every cell-label row for an excluded address.

    Kept rows stay as written, except new_row_index, which is renumbered so it
    still points at the same address after the deletion.
    """
    if not drop_ids or not path.is_file():
        return 0
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    parsed = list(_logical_csv_rows(lines))
    if not parsed:
        return 0
    _, header_end, header = parsed[0]
    col = {name: i for i, name in enumerate(header)}
    feature_at = col["feature"]
    clean_at = col["clean_value"]
    index_at = col["new_row_index"]

    groups: list[tuple[str, list[tuple[int, int, list[str]]]]] = []
    current_key: str | None = None
    current: list[tuple[int, int, list[str]]] = []
    drop_keys: set[str] = set()
    for start, end, row in parsed[1:]:
        if not row:
            continue
        key = row[index_at]
        if key != current_key:
            if current:
                groups.append((current_key or "", current))
            current_key = key
            current = []
        current.append((start, end, row))
        if row[feature_at] == "id" and row[clean_at] in drop_ids:
            drop_keys.add(key)
    if current:
        groups.append((current_key or "", current))

    removed = sum(1 for key, _group in groups if key in drop_keys)
    if removed == 0:
        return 0

    out_lines = list(lines[:header_end])
    new_index = 0
    for key, group in groups:
        if key in drop_keys:
            continue
        for start, end, row in group:
            if end != start + 1:
                raise ValueError(f"cell label record spans multiple lines at {path}")
            raw = lines[start]
            if row[index_at] == str(new_index):
                out_lines.append(raw)
                continue
            first = raw.find(",")
            second = raw.find(",", first + 1)
            out_lines.append(raw[: first + 1] + str(new_index) + raw[second:])
        new_index += 1
    path.write_text("".join(out_lines), encoding="utf-8")
    return removed


def unmatched_configured_ids(seen_ids: set[str]) -> list[str]:
    """Configured override ids that were not in this extract."""
    configured = set(MANUAL_LOCALITY_BY_ID) | set(EXCLUDED_ROW_IDS)
    return sorted(configured - seen_ids)


def adjust_repaired_row(row_id: str, result: dict[str, str]) -> dict[str, str] | None:
    """Force a known locality, or return None when the row is left out of the fixed clean file.

    A forced row did not pass postcode verification, so the check columns are n/a.
    None means the caller still writes an audit row with rule excluded.
    """
    if row_id in EXCLUDED_ROW_IDS:
        return None
    forced = MANUAL_LOCALITY_BY_ID.get(row_id)
    if forced is None:
        return result
    adjusted = dict(result)
    adjusted["new_locality"] = forced
    adjusted["proposed"] = forced
    adjusted["accepted"] = "true"
    adjusted["rule"] = "manual"
    adjusted["conflict"] = ""
    for key in ("clean_pc_ok", "dirty_pc_ok", "dirty_loc_ok"):
        adjusted[key] = "n/a"
    return adjusted


def row_value(frame, i: int, column: str, default: str = "") -> str:
    """Read a cell, or default when the dump has no such column (unnamed has no name)."""
    if column not in frame.columns:
        return default
    return frame.at[i, column]


def run(
    uk_dir: Path,
    derived_dir: Path,
    out_clean: Path,
    out_decisions: Path,
    ni_placenames: Path | None = None,
) -> None:
    gaz = load_gazetteer(derived_dir, ni_placenames=ni_placenames)
    clean = read_csv_as_strings(uk_dir / "uk_clean.csv")
    dirty = read_csv_as_strings(uk_dir / "uk_dirty.csv")
    if len(clean) != len(dirty):
        raise ValueError(f"row count mismatch: clean={len(clean)} dirty={len(dirty)}")
    if not clean["id"].equals(dirty["id"]):
        raise ValueError("clean and dirty are not aligned on id")

    decisions = []
    new_localities = []
    kept_indexes: list[int] = []
    seen_ids: set[str] = set()
    excluded = 0
    for i in range(len(clean)):
        row_id = clean.at[i, "id"]
        seen_ids.add(row_id)
        result = fix_row(
            gaz,
            clean_locality=clean.at[i, "locality"],
            dirty_locality=dirty.at[i, "locality"],
            clean_postcode=clean.at[i, "postcode"],
            dirty_postcode=dirty.at[i, "postcode"],
            clean_name=row_value(clean, i, "name"),
            dirty_name=row_value(dirty, i, "name"),
        )
        adjusted = adjust_repaired_row(row_id, result)
        if adjusted is None:
            adjusted = dict(result)
            adjusted["new_locality"] = result["old_locality"]
            adjusted["proposed"] = ""
            adjusted["accepted"] = "false"
            adjusted["rule"] = "excluded"
            adjusted["conflict"] = ""
            excluded += 1
        else:
            kept_indexes.append(i)
            new_localities.append(adjusted["new_locality"])
        decisions.append(
            {
                "row_index": str(i),
                "id": row_id,
                "old_locality": adjusted["old_locality"],
                "new_locality": adjusted["new_locality"],
                "proposed": adjusted["proposed"],
                "accepted": adjusted["accepted"],
                "rule": adjusted["rule"],
                "conflict": adjusted["conflict"],
                "dirty_locality": dirty.at[i, "locality"],
                "clean_postcode": clean.at[i, "postcode"],
                "dirty_postcode": dirty.at[i, "postcode"],
                "clean_pc_place": adjusted["clean_pc_place"],
                "dirty_pc_place": adjusted["dirty_pc_place"],
                "clean_pc_ok": adjusted["clean_pc_ok"],
                "dirty_pc_ok": adjusted["dirty_pc_ok"],
                "dirty_loc_ok": adjusted["dirty_loc_ok"],
                "clean_class": adjusted["clean_class"],
            }
        )
        if (i + 1) % 5000 == 0:
            logger.info("processed %d / %d", i + 1, len(clean))

    missing_manual = sorted(set(MANUAL_LOCALITY_BY_ID) - seen_ids)
    missing_excluded = sorted(set(EXCLUDED_ROW_IDS) - seen_ids)
    if missing_manual:
        logger.warning("configured row ids not in uk_clean.csv: %s", ", ".join(missing_manual))
    if missing_excluded:
        logger.info("excluded ids already absent from uk_clean.csv: %s", ", ".join(missing_excluded))

    fixed = clean.iloc[kept_indexes].copy()
    fixed["locality"] = new_localities
    logger.info(
        "excluded %d rows from %s; decisions keep them with rule excluded",
        excluded,
        out_clean.name,
    )
    out_clean.parent.mkdir(parents=True, exist_ok=True)
    fixed.to_csv(out_clean, index=False)
    dec_df = pd.DataFrame(decisions)
    dec_df.to_csv(out_decisions, index=False)

    dirty_path = uk_dir / "uk_dirty.csv"
    clean_path = uk_dir / "uk_clean.csv"
    labels_path = uk_dir / "uk_cell_labels.csv"
    n_dirty = drop_csv_ids(dirty_path, EXCLUDED_ROW_IDS)
    n_clean = drop_csv_ids(clean_path, EXCLUDED_ROW_IDS)
    n_labels = drop_cell_label_addresses(labels_path, EXCLUDED_ROW_IDS)
    logger.info(
        "removed excluded ids from %s (%d rows), %s (%d rows) and %s (%d addresses); other dirty values unchanged",
        dirty_path.name,
        n_dirty,
        clean_path.name,
        n_clean,
        labels_path.name,
        n_labels,
    )
    sys.path.insert(0, str(uk_dir.parent / "locality_fix"))
    from io_csv import refresh_cell_labels  # noqa: E402

    refresh_cell_labels(labels_path, {"locality": fixed["locality"].astype(str).tolist()})

    changed = (dec_df["old_locality"] != dec_df["new_locality"]).sum()
    logger.info("wrote %s (%d rows, %d locality changes)", out_clean, len(fixed), changed)
    logger.info("wrote %s", out_decisions)
    logger.info("by rule:\n%s", dec_df["rule"].value_counts().to_string())
    repaired = dec_df[dec_df["rule"] != "excluded"]
    conflicts = repaired.loc[repaired["conflict"] != "", "conflict"].value_counts()
    if len(conflicts):
        logger.info("by conflict:\n%s", conflicts.to_string())
    accepted = repaired["accepted"].value_counts()
    logger.info("accepted:\n%s", accepted.to_string())

    for old in ("Greater London", "City of Westminster", "City of Edinburgh", "Kirklees"):
        sub = dec_df[dec_df["old_locality"] == old]
        if len(sub) == 0:
            continue
        top_new = sub["new_locality"].value_counts().head(5).to_dict()
        logger.info("spot %r -> %s (n=%d)", old, top_new, len(sub))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--uk-dir", type=Path, default=DEFAULT_UK_DIR)
    parser.add_argument("--derived-dir", type=Path, default=DEFAULT_DERIVED)
    parser.add_argument(
        "--out-clean",
        type=Path,
        default=None,
        help="default: <uk-dir>/uk_clean_locality_fixed.csv",
    )
    parser.add_argument(
        "--out-decisions",
        type=Path,
        default=None,
        help="default: <uk-dir>/locality_fix_decisions.csv",
    )
    parser.add_argument(
        "--ni-placenames",
        type=Path,
        default=None,
        help="OSNI place-names CSV; default is the file beside the GeoPackage",
    )
    args = parser.parse_args(argv)
    out_clean = args.out_clean or (args.uk_dir / "uk_clean_locality_fixed.csv")
    out_decisions = args.out_decisions or (args.uk_dir / "locality_fix_decisions.csv")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        stream=sys.stdout,
    )
    run(
        args.uk_dir,
        args.derived_dir,
        out_clean,
        out_decisions,
        ni_placenames=args.ni_placenames,
    )


if __name__ == "__main__":
    main()
