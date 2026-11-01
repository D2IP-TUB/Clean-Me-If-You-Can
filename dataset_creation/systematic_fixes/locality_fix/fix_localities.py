"""Rewrite clean locality values for France, Spain, and Australia."""

from __future__ import annotations

import argparse
import logging
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from countries import CONFIGS, CountryConfig  # noqa: E402
from io_csv import (  # noqa: E402
    bilingual_first,
    bilingual_parts,
    in_native_script,
    invert_article_name,
    loose_name,
    names_match,
    norm_name,
    norm_postcode,
    read_csv_as_strings,
    refresh_cell_labels,
    richer_spelling,
    title_locality,
)

ROOT = Path(__file__).resolve().parents[1]
logger = logging.getLogger("fix_localities")


def strip_alias(value: str, keep: set[str]) -> str | None:
    raw = re.sub(r"\s+", " ", value).strip()
    if not raw:
        return None
    n = norm_name(raw)
    if n in keep:
        return None
    out = raw
    changed = False
    patterns = [
        (r"(?i)^City of\s+(.+)$", 1),
        (r"(?i)^Shire of\s+(.+)$", 1),
        (r"(?i)^Region of\s+(.+)$", 1),
        (r"(?i)^Regional Council of\s+(.+)$", 1),
        (r"(?i)^Municipality of\s+(.+)$", 1),
        (r"(?i)^Provincia de\s+(.+)$", 1),
        (r"(?i)^Province of\s+(.+)$", 1),
        (r"(?i)^Departamento de\s+(.+)$", 1),
        (r"(?i)^Département de\s+(.+)$", 1),
        (r"(?i)^Communauté de\s+(.+)$", 1),
        (r"(?i)^Comunidad(?: Autónoma)? de\s+(.+)$", 1),
        (r"(?i)^Métropole (?:de |du |des )?(.+)$", 1),
        (r"(?i)^Greater\s+(.+)$", 1),
    ]
    for pat, grp in patterns:
        m = re.match(pat, out)
        if m:
            out = m.group(grp).strip()
            changed = True
            break
    if re.search(r"(?i)\s+City$", out) and norm_name(out) not in keep:
        out = re.sub(r"(?i)\s+City$", "", out).strip()
        changed = True
    if re.search(r"(?i)\s+CP$", out):
        out = re.sub(r"(?i)\s+CP$", "", out).strip()
        changed = True
    if re.search(r"\s*\([A-Z]{1,3}\)\s*$", out):
        out = re.sub(r"\s*\([A-Z]{1,3}\)\s*$", "", out).strip()
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
    admin_names: dict[str, str]
    postcodes: dict[str, dict]
    capital_collapse: dict[str, str]
    loose: dict[str, SettlementHit] = field(default_factory=dict)
    locality_names: dict[str, dict[str, str]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.loose:
            return
        grouped: dict[str, dict[str, SettlementHit]] = {}
        for key, hit in self.settlements.items():
            grouped.setdefault(loose_name(key), {})[hit.name1] = hit
        self.loose = {
            key: next(iter(hits.values()))
            for key, hits in grouped.items()
            if len(hits) == 1
        }

    def lookup_variants(self, locality: str) -> list[str]:
        raw = re.sub(r"\s+", " ", locality or "").strip()
        if not raw:
            return []
        cands = [raw, *bilingual_parts(raw)]
        extra = []
        for cand in cands:
            inv = invert_article_name(cand)
            if inv:
                extra.append(inv)
        out = []
        seen = set()
        for cand in cands + extra:
            key = norm_name(cand)
            if key and key not in seen:
                seen.add(key)
                out.append(cand)
        return out

    def is_capital_admin(self, locality: str) -> bool:
        return any(norm_name(c) in self.capital_collapse for c in self.lookup_variants(locality))

    def is_admin(self, locality: str) -> bool:
        return any(norm_name(c) in self.admin_names for c in self.lookup_variants(locality))

    def settlement_exact(self, locality: str) -> SettlementHit | None:
        for cand in self.lookup_variants(locality):
            hit = self.settlements.get(norm_name(cand))
            if hit is not None:
                return hit
        return None

    def settlement(self, locality: str) -> SettlementHit | None:
        hit = self.settlement_exact(locality)
        if hit is not None:
            return hit
        for cand in self.lookup_variants(locality):
            hit = self.loose.get(loose_name(cand))
            if hit is not None:
                return hit
        return None

    def lookup_postcode(self, postcode: str) -> dict | None:
        key = norm_postcode(postcode)
        if not key:
            return None
        return self.postcodes.get(key)


def load_gazetteer(derived_dir: Path, cfg: CountryConfig) -> Gazetteer:
    settlements_df = read_csv_as_strings(derived_dir / "settlements.csv")
    admin_df = read_csv_as_strings(derived_dir / "admin_units.csv")
    pc_df = read_csv_as_strings(derived_dir / "postcode_to_place.csv")

    buckets: dict[str, dict] = {}

    def add_name(key: str, name1: str, district: str, county: str) -> None:
        if not key:
            return
        b = buckets.setdefault(key, {"name1": name1, "districts": set(), "counties": set()})
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

    locality_names: dict[str, dict[str, str]] = {}
    for row in settlements_df.itertuples(index=False):
        name1 = (row.name1 or "").strip()
        county = norm_name(row.county_unitary or "")
        if name1 and county:
            locality_names.setdefault(norm_name(name1), {}).setdefault(county, name1)

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
    grouped: dict[str, list] = {}
    for row in pc_df.itertuples(index=False):
        if not row.postcode:
            continue
        grouped.setdefault(norm_postcode(row.postcode), []).append(row)
    postcodes = {}
    for key, rows in grouped.items():
        place_names = []
        seen_places = set()
        for row in rows:
            name = (row.populated_place or "").strip()
            key_name = norm_name(name)
            if not key_name or key_name in seen_places:
                continue
            seen_places.add(key_name)
            place_names.append(name)
        payload = {
            "populated_place": place_names[0] if len(place_names) == 1 else "",
            "place_names": place_names,
            "populated_place_type": rows[0].populated_place_type,
            "district_borough": rows[0].district_borough,
            "county_unitary": rows[0].county_unitary,
            "region": rows[0].region,
            "country": rows[0].country,
            "ambiguous": len(place_names) > 1,
        }
        postcodes[key] = payload
    logger.info(
        "gazetteer: %d settlements, %d admin, %d postcodes",
        len(settlements),
        len(admin_names),
        len(postcodes),
    )
    return Gazetteer(
        settlements=settlements,
        admin_names=admin_names,
        postcodes=postcodes,
        capital_collapse=cfg.capital_collapse,
        locality_names=locality_names,
    )


def classify(gaz: Gazetteer, cfg: CountryConfig, locality: str) -> str:
    if gaz.is_capital_admin(locality):
        return "capital_admin"
    if strip_alias(locality, cfg.city_suffix_keep) is not None:
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


def _resembles(place: str, name: str, size: int = 4) -> bool:
    """The two names start alike once accents, hyphens and case are folded."""
    a, b = loose_name(place), loose_name(name)
    if len(a) < size or len(b) < size:
        return False
    return a[:size] == b[:size]


def propose_all(gaz, cfg, clean_locality, dirty_locality, clean_postcode, clean_class):
    """Every proposal for this row, best first, as (locality, rule) pairs.

    The caller tries them in order and keeps the first one the clean postcode
    accepts. An empty list means unresolved.
    """
    out: list[tuple[str, str]] = []

    def add(value, rule):
        if value and all(norm_name(value) != norm_name(v) or rule != r for v, r in out):
            out.append((value, rule))

    if clean_class == "capital_admin":
        for cand in gaz.lookup_variants(clean_locality):
            target = gaz.capital_collapse.get(norm_name(cand))
            if target:
                add(target, "capital_collapse")
                break
        return out

    stripped_clean = strip_alias(clean_locality, cfg.city_suffix_keep) if clean_class == "alias" else None

    if clean_class in {"other_admin", "alias"}:
        dirty = re.sub(r"\s+", " ", dirty_locality).strip()
        if dirty:
            candidates = [dirty]
            stripped_dirty = strip_alias(dirty, cfg.city_suffix_keep)
            if stripped_dirty:
                candidates.append(stripped_dirty)
            for cand in candidates:
                canon = canonical_settlement_name(gaz, cand)
                if not canon:
                    continue
                if (
                    settlement_in_admin(gaz, canon, clean_locality)
                    or gaz.settlement(cand) is not None
                    or (stripped_clean and names_match(canon, stripped_clean))
                ):
                    add(richer_spelling(canon, cand, stripped_clean or ""), "dirty")
        if stripped_clean:
            if gaz.is_capital_admin(stripped_clean):
                add(gaz.capital_collapse[norm_name(stripped_clean)], "capital_collapse")
            canon = canonical_settlement_name(gaz, stripped_clean)
            if canon:
                add(richer_spelling(canon, stripped_clean), "alias")
        pc = gaz.lookup_postcode(clean_postcode)
        if pc and not pc.get("ambiguous") and pc.get("populated_place"):
            place = bilingual_first(pc["populated_place"])
            canon = canonical_settlement_name(gaz, place) or title_locality(place)
            if not out or _resembles(canon, stripped_clean or clean_locality):
                add(richer_spelling(canon, stripped_clean or "", dirty), "postcode")
        return out

    if clean_class == "settlement":
        if gaz.settlement_exact(clean_locality) is not None:
            return [(clean_locality, "keep")]
        canon = canonical_settlement_name(gaz, clean_locality)
        if canon and norm_name(canon) != norm_name(clean_locality):
            canon = richer_spelling(canon, clean_locality)
            if norm_name(canon) != norm_name(clean_locality):
                return [(canon, "alias")]
        return [(clean_locality, "keep")]

    if clean_class == "unmatched":
        dirty = re.sub(r"\s+", " ", dirty_locality).strip()
        canon = canonical_settlement_name(gaz, dirty) if dirty else None
        source = dirty
        if not canon and dirty:
            stripped = strip_alias(dirty, cfg.city_suffix_keep)
            if stripped:
                canon = canonical_settlement_name(gaz, stripped)
                source = stripped
        if canon:
            add(richer_spelling(canon, source, clean_locality), "dirty")
    return out


def propose(gaz, cfg, clean_locality, dirty_locality, clean_postcode, clean_class):
    """The best proposal only. Kept for callers and tests that want one."""
    found = propose_all(gaz, cfg, clean_locality, dirty_locality, clean_postcode, clean_class)
    return found[0] if found else (None, "unresolved")


def _names_match(a: str, b: str) -> bool:
    return names_match(a, b)


def pc_ok(gaz, cfg, place: str, pc_row, *, required: bool) -> str:
    if pc_row is None:
        return "fail" if required else "abstain"
    place_names = list(pc_row.get("place_names") or [])
    if not place_names and pc_row.get("populated_place"):
        place_names = [pc_row["populated_place"]]
    if any(_names_match(place, candidate) for candidate in place_names):
        return "ok"
    if pc_row.get("ambiguous"):
        return "fail"
    if _names_match(place, pc_row.get("populated_place", "")):
        return "ok"
    if any(norm_name(place) == norm_name(v) for v in cfg.capital_collapse.values()):
        for field in ("county_unitary", "district_borough", "region", "populated_place"):
            val = pc_row.get(field, "")
            if val and norm_name(val) in gaz.capital_collapse:
                if norm_name(gaz.capital_collapse[norm_name(val)]) == norm_name(place):
                    return "ok"
            if _names_match(place, val):
                return "ok"
    if place_names:
        return "fail"
    hit = gaz.settlement(place)
    district = pc_row.get("district_borough", "")
    if hit and district and district in hit.districts:
        return "ok"
    return "fail"


def dirty_loc_ok(gaz, cfg, place: str, dirty_locality: str) -> str:
    dirty = re.sub(r"\s+", " ", dirty_locality).strip()
    if not dirty:
        return "abstain"
    if _names_match(place, dirty):
        return "ok"
    stripped = strip_alias(dirty, cfg.city_suffix_keep)
    if stripped and _names_match(place, stripped):
        return "ok"
    dn = norm_name(dirty)
    aliases = set()
    for city, extra in cfg.city_aliases.items():
        if norm_name(place) == city:
            aliases = extra
            break
    if dn in aliases or norm_name(place) in dn:
        return "ok"
    if gaz.is_capital_admin(dirty) and norm_name(gaz.capital_collapse[dn]) == norm_name(place):
        return "ok"
    dirty_hit = gaz.settlement(dirty) or (gaz.settlement(stripped) if stripped else None)
    dirty_is_admin = gaz.is_admin(dirty)
    if any(norm_name(place) == norm_name(v) for v in cfg.capital_collapse.values()):
        if dirty_hit and (
            place in dirty_hit.districts
            or place in dirty_hit.counties
            or _names_match(place, dirty_hit.name1)
        ):
            return "ok"
        return "abstain"
    hit = gaz.settlement(place)
    if hit:
        parents = {norm_name(x) for x in hit.districts | hit.counties}
        if dn in parents:
            return "ok"
        if dirty_hit is not None:
            return "abstain"
        if not dirty_is_admin:
            return "abstain"
    if dirty_hit is None and not dirty_is_admin:
        return "abstain"
    return "abstain"


def verify(gaz, cfg, proposed, dirty_locality, clean_postcode, dirty_postcode, rule: str):
    """Accept or reject on the clean postcode only.

    A scraped postcode or locality may confirm the proposal. A miss, a typo,
    or another place abstains and cannot reject the row.
    """
    clean_row = gaz.lookup_postcode(clean_postcode)
    dirty_row = gaz.lookup_postcode(dirty_postcode)
    require_pc = rule == "postcode"
    clean_status = pc_ok(gaz, cfg, proposed, clean_row, required=require_pc)
    dirty_pc_status = pc_ok(gaz, cfg, proposed, dirty_row, required=False)
    if dirty_pc_status == "fail":
        dirty_pc_status = "abstain"
    dirty_loc_status = dirty_loc_ok(gaz, cfg, proposed, dirty_locality)
    if dirty_loc_status == "fail":
        dirty_loc_status = "abstain"
    clean_pc_place = bilingual_first((clean_row or {}).get("populated_place", ""))
    dirty_pc_place = bilingual_first((dirty_row or {}).get("populated_place", ""))
    if clean_status == "fail":
        conflict = "pc_unknown" if clean_row is None else "clean_pc_mismatch"
        return False, conflict, clean_pc_place, dirty_pc_place, clean_status, dirty_pc_status, dirty_loc_status
    return True, "", clean_pc_place, dirty_pc_place, clean_status, dirty_pc_status, dirty_loc_status


def is_lga_label(locality: str) -> bool:
    """Council, shire, regional, or city/town-of name. Not a suburb."""
    name = f" {norm_name(locality)} "
    return any(
        marker in name
        for marker in (" council ", " shire ", " regional ", " city of ", " town of ")
    )


def single_postcode_place(gaz, postcode: str) -> str:
    row = gaz.lookup_postcode(postcode)
    if not row or row.get("ambiguous"):
        return ""
    return bilingual_first(row.get("populated_place") or "")


_AU_STATE_WORDS = frozenset({
    "qld", "nsw", "vic", "wa", "sa", "tas", "nt", "act",
    "queensland", "new south wales", "victoria", "western australia",
    "south australia", "tasmania", "northern territory", "australia",
})


def dirty_locality_pieces(dirty_locality: str) -> list[str]:
    """Locality tokens inside a scraped cell, without state or postcode."""
    raw = str(dirty_locality or "")
    pieces: list[str] = []
    for part in re.split(r"[\n,;/|]+", raw):
        part = re.sub(r"\s+", " ", part).strip(" .-\t")
        if not part or part == "-":
            continue
        part = re.sub(r"\b\d{4}\b", " ", part)
        part = re.sub(r"\s+", " ", part).strip(" .,-")
        tokens = part.split()
        while len(tokens) >= 2 and norm_name(" ".join(tokens[-2:])) in _AU_STATE_WORDS:
            tokens = tokens[:-2]
        while tokens and norm_name(tokens[-1]) in _AU_STATE_WORDS:
            tokens.pop()
        if not tokens:
            continue
        pieces.append(" ".join(tokens))
        if norm_name(tokens[0]) == "mt" and len(tokens) > 1:
            pieces.append("Mount " + " ".join(tokens[1:]))
    seen: set[str] = set()
    out: list[str] = []
    for piece in pieces:
        key = norm_name(piece)
        if key and key not in seen:
            seen.add(key)
            out.append(piece)
    return out


def dirty_place_on_postcode(gaz, cfg, postcode: str, dirty_locality: str) -> str:
    """Return the postcode's own suburb when the scrape names that suburb."""
    row = gaz.lookup_postcode(postcode)
    if not row:
        return ""
    names = list(row.get("place_names") or [])
    if not names and row.get("populated_place"):
        names = [bilingual_first(row["populated_place"])]
    candidates = dirty_locality_pieces(dirty_locality)
    dirty = re.sub(r"\s+", " ", dirty_locality or "").strip()
    stripped = strip_alias(dirty, cfg.city_suffix_keep) if dirty else None
    if stripped:
        candidates.append(stripped)
    for cand in candidates:
        if is_lga_label(cand):
            continue
        key = norm_name(cand)
        for name in names:
            if name and norm_name(name) == key:
                return bilingual_first(name) or name
    return ""


def apply_unique_lga_postcode(result, gaz, cfg, clean_locality, clean_postcode, dirty_locality):
    """Replace an Australian council name from its postcode's suburbs.

    One suburb on the postcode replaces the council. Several suburbs replace
    it only when the scraped locality is one of those suburbs.
    """
    if cfg.code != "au" or result["accepted"] == "true" or not is_lga_label(clean_locality):
        return result
    place = single_postcode_place(gaz, clean_postcode)
    rule = "postcode"
    if not place or norm_name(place) == norm_name(clean_locality):
        place = dirty_place_on_postcode(gaz, cfg, clean_postcode, dirty_locality)
        rule = "dirty"
    if not place or norm_name(place) == norm_name(clean_locality):
        return result
    row = gaz.lookup_postcode(clean_postcode)
    if pc_ok(gaz, cfg, place, row, required=True) != "ok":
        return result
    place = title_locality(place)
    result = dict(result)
    result["new_locality"] = place
    result["proposed"] = place
    result["accepted"] = "true"
    result["rule"] = rule
    result["conflict"] = ""
    result["clean_pc_place"] = place
    result["clean_pc_ok"] = "ok"
    return result


def fix_row(gaz, cfg, *, clean_locality, dirty_locality, clean_postcode, dirty_postcode):
    """Try each proposal in order. The first one the clean postcode accepts wins."""
    clean_class = classify(gaz, cfg, clean_locality)
    proposals = propose_all(gaz, cfg, clean_locality, dirty_locality, clean_postcode, clean_class)
    lookup = lambda pc: bilingual_first((gaz.lookup_postcode(pc) or {}).get("populated_place", ""))
    finish = lambda result: apply_unique_lga_postcode(
        result, gaz, cfg, clean_locality, clean_postcode, dirty_locality
    )

    if not proposals or proposals[0][1] == "keep":
        keep = bool(proposals)
        return finish({
            "old_locality": clean_locality,
            "new_locality": clean_locality,
            "proposed": proposals[0][0] if keep else clean_locality,
            "accepted": "true" if keep else "false",
            "rule": "keep" if keep else "unresolved",
            "conflict": "" if keep else "no_proposal",
            "clean_class": clean_class,
            "clean_pc_place": lookup(clean_postcode),
            "dirty_pc_place": lookup(dirty_postcode),
            "clean_pc_ok": "abstain",
            "dirty_pc_ok": "abstain",
            "dirty_loc_ok": "abstain",
        })

    first = None
    for proposed, rule in proposals:
        if not in_native_script(proposed, cfg.code):
            accepted, conflict = False, "foreign_script"
            cplace = dplace = ""
            cs = ds = dls = "abstain"
        else:
            accepted, conflict, cplace, dplace, cs, ds, dls = verify(
                gaz, cfg, proposed, dirty_locality, clean_postcode, dirty_postcode, rule
            )
        result = {
            "old_locality": clean_locality,
            "new_locality": proposed if accepted else clean_locality,
            "proposed": proposed,
            "accepted": "true" if accepted else "false",
            "rule": rule,
            "conflict": conflict,
            "clean_class": clean_class,
            "clean_pc_place": cplace,
            "dirty_pc_place": dplace,
            "clean_pc_ok": cs,
            "dirty_pc_ok": ds,
            "dirty_loc_ok": dls,
        }
        if accepted:
            return finish(result)
        if first is None:
            first = result
    return finish(first)


def run(country: str, root: Path) -> None:
    cfg = CONFIGS[country]
    uk_dir = root / f"{cfg.prefix}_fix"
    derived = uk_dir / "gazetteer" / "derived"
    gaz = load_gazetteer(derived, cfg)
    clean = read_csv_as_strings(uk_dir / f"{cfg.prefix}_clean.csv")
    dirty = read_csv_as_strings(uk_dir / f"{cfg.prefix}_dirty.csv")
    if len(clean) != len(dirty) or not clean["id"].equals(dirty["id"]):
        raise ValueError("clean/dirty not aligned")

    decisions = []
    new_localities = []
    for i in range(len(clean)):
        result = fix_row(
            gaz,
            cfg,
            clean_locality=clean.at[i, "locality"],
            dirty_locality=dirty.at[i, "locality"],
            clean_postcode=clean.at[i, "postcode"],
            dirty_postcode=dirty.at[i, "postcode"],
        )
        new_localities.append(result["new_locality"])
        decisions.append(
            {
                "row_index": str(i),
                "id": clean.at[i, "id"],
                **{k: result[k] for k in result},
                "dirty_locality": dirty.at[i, "locality"],
                "clean_postcode": clean.at[i, "postcode"],
                "dirty_postcode": dirty.at[i, "postcode"],
            }
        )
        if (i + 1) % 5000 == 0:
            logger.info("processed %d / %d", i + 1, len(clean))

    fixed = clean.copy()
    fixed["locality"] = new_localities
    out_clean = uk_dir / f"{cfg.prefix}_clean_locality_fixed.csv"
    out_dec = uk_dir / "locality_fix_decisions.csv"
    fixed.to_csv(out_clean, index=False)
    dec_df = pd.DataFrame(decisions)
    dec_df.to_csv(out_dec, index=False)
    changed = (dec_df["old_locality"] != dec_df["new_locality"]).sum()
    logger.info("wrote %s (%d rows, %d changes)", out_clean, len(fixed), int(changed))
    logger.info("by rule:\n%s", dec_df["rule"].value_counts().to_string())
    conflicts = dec_df.loc[dec_df["conflict"] != "", "conflict"].value_counts()
    if len(conflicts):
        logger.info("by conflict:\n%s", conflicts.to_string())
    refresh_cell_labels(
        uk_dir / f"{cfg.prefix}_cell_labels.csv",
        {"locality": new_localities},
    )


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
