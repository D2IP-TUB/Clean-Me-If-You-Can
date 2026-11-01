"""Build common derived gazetteer CSVs from downloaded official files."""

from __future__ import annotations

import argparse
import csv
import json
import logging
import re
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from io_csv import norm_name, read_csv_as_strings, title_locality  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
logger = logging.getLogger("derive_gazetteers")

SETTLEMENT_FIELDS = [
    "name1",
    "name2",
    "local_type",
    "district_borough",
    "county_unitary",
    "country",
    "id",
]
ADMIN_FIELDS = [
    "name",
    "role",
    "n_settlement_children",
    "also_settlement_name",
    "example_children",
]
PC_FIELDS = [
    "postcode",
    "populated_place",
    "populated_place_type",
    "district_borough",
    "county_unitary",
    "region",
    "country",
]


def write_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") or "" for k in fieldnames})
    logger.info("wrote %s (%d rows)", path, len(rows))


def finish_admin(settlements: list[dict], extra_admin: list[tuple[str, str]]) -> list[dict]:
    children = defaultdict(list)
    sett_names = {norm_name(r["name1"]) for r in settlements if r.get("name1")}
    sett_names |= {norm_name(r["name2"]) for r in settlements if r.get("name2")}
    roles = {}
    for name, role in extra_admin:
        if not name:
            continue
        roles.setdefault(name, set()).add(role)
    for r in settlements:
        for col, role in (("district_borough", "district_borough"), ("county_unitary", "county_unitary")):
            parent = (r.get(col) or "").strip()
            if parent:
                roles.setdefault(parent, set()).add(role)
                children[parent].append(r["name1"])
    rows = []
    for name, role_set in sorted(roles.items(), key=lambda x: x[0].casefold()):
        kids = sorted(set(children.get(name, [])), key=str.casefold)
        rows.append(
            {
                "name": name,
                "role": "|".join(sorted(role_set)),
                "n_settlement_children": str(len(kids)),
                "also_settlement_name": "yes" if norm_name(name) in sett_names else "no",
                "example_children": "; ".join(kids[:8]),
            }
        )
    return rows


def derive_fr(base: Path) -> None:
    cog = base / "gazetteer" / "raw" / "cog"
    files = {p.name.lower(): p for p in cog.rglob("*.csv")}

    def find(*needles: str, exclude: tuple[str, ...] = ()) -> Path:
        hits = []
        for name, path in files.items():
            if all(n in name for n in needles) and not any(x in name for x in exclude):
                hits.append(path)
        if not hits:
            raise FileNotFoundError(f"COG file matching {needles} excl={exclude} in {cog}: {list(files)}")
        hits.sort(key=lambda p: len(p.name))
        return hits[0]

    communes = pd.read_csv(
        find("commune", exclude=("comer", "depuis", "outremer", "mvt")),
        dtype=str,
        keep_default_na=False,
    )
    deps = pd.read_csv(find("departement"), dtype=str, keep_default_na=False)
    regs = pd.read_csv(find("region", exclude=("arrondissement",)), dtype=str, keep_default_na=False)
    logger.info("COG communes=%d columns=%s", len(communes), list(communes.columns))

    dep_name = {r.DEP: r.LIBELLE for r in deps.itertuples(index=False)}
    reg_name = {r.REG: r.LIBELLE for r in regs.itertuples(index=False)}

    parent_lib = {}
    for r in communes.itertuples(index=False):
        parent_lib[r.COM] = r.LIBELLE

    settlements = []
    for r in communes.itertuples(index=False):
        typ = getattr(r, "TYPECOM", "COM")
        name = r.LIBELLE
        parent_code = getattr(r, "COMPARENT", "") or ""
        if typ == "ARM" and parent_code in parent_lib:
            continue
        settlements.append(
            {
                "name1": name,
                "name2": (getattr(r, "NCCENR", "") or "").strip() if getattr(r, "NCCENR", "") != name else "",
                "local_type": "commune" if typ == "COM" else typ,
                "district_borough": dep_name.get(r.DEP, ""),
                "county_unitary": reg_name.get(r.REG, ""),
                "country": "France",
                "id": r.COM,
            }
        )

    extra_admin = [(n, "departement") for n in dep_name.values()]
    extra_admin += [(n, "region") for n in reg_name.values()]
    extra_admin += [
        ("Métropole du Grand Paris", "metro"),
        ("Grand Paris", "metro"),
    ]

    laposte = pd.read_csv(
        base / "gazetteer" / "raw" / "laposte_hexasmal.csv",
        dtype=str,
        keep_default_na=False,
        sep=";",
        encoding="latin-1",
    )
    laposte.columns = [c.lstrip("#") for c in laposte.columns]
    insee_to_name = {r["id"]: r["name1"] for r in settlements}
    for r in communes.itertuples(index=False):
        insee_to_name.setdefault(r.COM, r.LIBELLE)

    code_col = next(c for c in laposte.columns if "insee" in c.lower())
    pc_col = next(c for c in laposte.columns if "postal" in c.lower())
    comm_by_code = {}
    for row in communes.itertuples(index=False):
        previous = comm_by_code.get(row.COM)
        if previous is None or (
            getattr(previous, "TYPECOM", "") != "COM" and getattr(row, "TYPECOM", "") == "COM"
        ):
            comm_by_code[row.COM] = row
    postcodes = []
    for code, pc in zip(laposte[code_col], laposte[pc_col]):
        code = (code or "").strip()
        pc = (pc or "").strip().replace(" ", "")
        if not pc:
            continue
        comm = comm_by_code.get(code)
        name = insee_to_name.get(code, "")
        dep = dep_name.get(getattr(comm, "DEP", ""), "") if comm is not None else ""
        reg = reg_name.get(getattr(comm, "REG", ""), "") if comm is not None else ""
        postcodes.append(
            {
                "postcode": pc,
                "populated_place": name,
                "populated_place_type": "commune",
                "district_borough": dep,
                "county_unitary": reg,
                "region": reg,
                "country": "France",
            }
        )

    out = base / "gazetteer" / "derived"
    write_csv(out / "settlements.csv", SETTLEMENT_FIELDS, settlements)
    write_csv(out / "admin_units.csv", ADMIN_FIELDS, finish_admin(settlements, extra_admin))
    write_csv(out / "postcode_to_place.csv", PC_FIELDS, postcodes)


def _first_col(df: pd.DataFrame, *needles: str) -> str:
    cols = list(df.columns)
    lower = [str(c).casefold() for c in cols]
    for n in needles:
        for i, name in enumerate(lower):
            if n in name:
                return cols[i]
    raise KeyError(f"no column matching {needles} in {cols}")


INE_CCAA = {
    "01": "Andalucía",
    "02": "Aragón",
    "03": "Asturias, Principado de",
    "04": "Balears, Illes",
    "05": "Canarias",
    "06": "Cantabria",
    "07": "Castilla y León",
    "08": "Castilla-La Mancha",
    "09": "Cataluña",
    "10": "Comunitat Valenciana",
    "11": "Extremadura",
    "12": "Galicia",
    "13": "Madrid, Comunidad de",
    "14": "Murcia, Región de",
    "15": "Navarra, Comunidad Foral de",
    "16": "País Vasco",
    "17": "Rioja, La",
    "18": "Ceuta",
    "19": "Melilla",
}

INE_PROVINCIAS = {
    "01": "Araba/Álava",
    "02": "Albacete",
    "03": "Alicante/Alacant",
    "04": "Almería",
    "05": "Ávila",
    "06": "Badajoz",
    "07": "Balears, Illes",
    "08": "Barcelona",
    "09": "Burgos",
    "10": "Cáceres",
    "11": "Cádiz",
    "12": "Castellón/Castelló",
    "13": "Ciudad Real",
    "14": "Córdoba",
    "15": "Coruña, A",
    "16": "Cuenca",
    "17": "Girona",
    "18": "Granada",
    "19": "Guadalajara",
    "20": "Gipuzkoa",
    "21": "Huelva",
    "22": "Huesca",
    "23": "Jaén",
    "24": "León",
    "25": "Lleida",
    "26": "Rioja, La",
    "27": "Lugo",
    "28": "Madrid",
    "29": "Málaga",
    "30": "Murcia",
    "31": "Navarra",
    "32": "Ourense",
    "33": "Asturias",
    "34": "Palencia",
    "35": "Palmas, Las",
    "36": "Pontevedra",
    "37": "Salamanca",
    "38": "Santa Cruz de Tenerife",
    "39": "Cantabria",
    "40": "Segovia",
    "41": "Sevilla",
    "42": "Soria",
    "43": "Tarragona",
    "44": "Teruel",
    "45": "Toledo",
    "46": "Valencia/València",
    "47": "Valladolid",
    "48": "Bizkaia",
    "49": "Zamora",
    "50": "Zaragoza",
    "51": "Ceuta",
    "52": "Melilla",
}


def derive_es(base: Path) -> None:
    xlsx = base / "gazetteer" / "raw" / "ine_diccionario.xlsx"
    raw = pd.read_excel(xlsx, header=None, dtype=str).fillna("")
    raw.columns = [str(c).strip() for c in raw.iloc[1].tolist()]
    muni = raw.iloc[2:].copy()
    logger.info("INE municipios columns=%s rows=%d", list(muni.columns), len(muni))

    settlements = []
    extra_admin = [(n, "provincia") for n in INE_PROVINCIAS.values()]
    extra_admin += [(n, "ccaa") for n in INE_CCAA.values()]
    extra_admin += [
        ("Comunidad de Madrid", "ccaa"),
        ("Provincia de Madrid", "provincia"),
        ("Comunidad Autónoma de Madrid", "ccaa"),
        ("Cataluña", "ccaa"),
        ("Catalunya", "ccaa"),
        ("País Vasco", "ccaa"),
        ("Euskadi", "ccaa"),
    ]
    for rec in muni.to_dict(orient="records"):
        name = str(rec.get("NOMBRE", "")).strip()
        if not name:
            continue
        cpro = str(rec.get("CPRO", "")).zfill(2)
        cmun = str(rec.get("CMUN", "")).zfill(3)
        ccaa = str(rec.get("CODAUTO", "")).zfill(2)
        district = INE_PROVINCIAS.get(cpro, "")
        county = INE_CCAA.get(ccaa, "")
        parts = [p.strip() for p in re.split(r"\s*/\s*", name) if p.strip()]
        names = [name] + [p for p in parts if p != name]
        m = re.match(r"^(.+),\s+(El|La|Los|Las|A|O|As|Os|L['’])\s*$", name, flags=re.I)
        if m:
            article = m.group(2).replace("’", "'")
            names.append(f"{article} {m.group(1)}".replace("' ", "'"))
        for i, nm in enumerate(names):
            settlements.append(
                {
                    "name1": nm if i == 0 else names[0],
                    "name2": nm if i else (names[1] if len(names) > 1 else ""),
                    "local_type": "municipio",
                    "district_borough": district,
                    "county_unitary": county,
                    "country": "Spain",
                    "id": cpro + cmun + (f":{i}" if i else ""),
                }
            )

    gn = base / "gazetteer" / "raw" / "geonames"
    txt = next(gn.glob("*.txt"), None)
    postcodes = []
    if txt:
        gn_df = pd.read_csv(
            txt,
            sep="\t",
            header=None,
            dtype=str,
            keep_default_na=False,
            names=[
                "country",
                "postcode",
                "place",
                "admin1",
                "admin1code",
                "admin2",
                "admin2code",
                "admin3",
                "admin3code",
                "lat",
                "lon",
                "accuracy",
            ],
        )
        for r in gn_df.itertuples(index=False):
            postcodes.append(
                {
                    "postcode": (r.postcode or "").replace(" ", ""),
                    "populated_place": r.place,
                    "populated_place_type": "geonames",
                    "district_borough": r.admin2,
                    "county_unitary": r.admin1,
                    "region": r.admin1,
                    "country": "Spain",
                }
            )

    out = base / "gazetteer" / "derived"
    write_csv(out / "settlements.csv", SETTLEMENT_FIELDS, settlements)
    write_csv(out / "admin_units.csv", ADMIN_FIELDS, finish_admin(settlements, extra_admin))
    write_csv(out / "postcode_to_place.csv", PC_FIELDS, postcodes)


def _au_names(name: str) -> tuple[str, str]:
    pretty = title_locality(name)
    short = re.sub(r"\s+City$", "", pretty, flags=re.I).strip()
    if short and short.casefold() != pretty.casefold():
        return pretty, short
    return pretty, ""


def _read_psv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, sep="|", dtype=str, keep_default_na=False)
    return pd.read_csv(path, sep="|", dtype=str, keep_default_na=False)


def derive_au(base: Path) -> None:
    raw = base / "gazetteer" / "raw"
    gnaf = raw / "gnaf"
    loc_files = [
        p
        for p in gnaf.rglob("*.psv")
        if p.name.upper().endswith("_LOCALITY_PSV.PSV")
        and "ALIAS" not in p.name.upper()
        and "POINT" not in p.name.upper()
        and "STREET" not in p.name.upper()
    ]
    alias_files = [p for p in gnaf.rglob("*.psv") if "LOCALITY_ALIAS" in p.name.upper()]
    state_files = [
        p
        for p in gnaf.rglob("*.psv")
        if p.name.upper().endswith("_STATE_PSV.PSV") or "AUTHORITY_CODE_STATE" in p.name.upper()
    ]
    if not loc_files:
        raise FileNotFoundError(f"no G-NAF LOCALITY psv files under {gnaf}")
    loc = pd.concat([_read_psv(p) for p in loc_files], ignore_index=True)
    alias = (
        pd.concat([_read_psv(p) for p in alias_files], ignore_index=True)
        if alias_files
        else pd.DataFrame()
    )
    state = (
        pd.concat([_read_psv(p) for p in state_files], ignore_index=True)
        if state_files
        else pd.DataFrame()
    )
    logger.info("G-NAF locality files=%d rows=%d columns=%s", len(loc_files), len(loc), list(loc.columns))

    def col(df, *cands):
        lower = {c.casefold(): c for c in df.columns}
        for c in cands:
            if c.casefold() in lower:
                return lower[c.casefold()]
        raise KeyError(list(df.columns))

    loc_name = col(loc, "locality_name", "LOCALITY_NAME")
    loc_pid = col(loc, "locality_pid", "LOCALITY_PID")
    loc_pc = col(loc, "primary_postcode", "PRIMARY_POSTCODE")
    loc_class = col(loc, "locality_class_code", "LOCALITY_CLASS_CODE")
    loc_state = col(loc, "state_pid", "STATE_PID")
    if len(state):
        st_pid = col(state, "state_pid", "STATE_PID", "code")
        try:
            st_name = col(state, "state_name", "STATE_NAME", "name")
        except KeyError:
            st_name = col(state, "name")
        state_map = {r[st_pid]: r[st_name] for _, r in state.iterrows()}
    else:
        state_map = {}

    aliases = defaultdict(list)
    if len(alias):
        alias_pid = col(alias, "locality_pid", "LOCALITY_PID")
        alias_name = col(alias, "name", "NAME", "locality_name")
        for _, r in alias.iterrows():
            aliases[r[alias_pid]].append(r[alias_name])

    settlements = []
    postcodes = []
    for _, r in loc.iterrows():
        name = str(r[loc_name] or "").strip()
        if not name or name in {"nan", "None"}:
            continue
        pid = str(r[loc_pid])
        state_name = state_map.get(str(r[loc_state]), "") or state_map.get(r[loc_state], "")
        al = aliases.get(pid, []) or aliases.get(r[loc_pid], [])
        pretty, city_short = _au_names(name)
        alias_pretty = title_locality(str(al[0])) if al else ""
        settlements.append(
            {
                "name1": city_short or pretty,
                "name2": pretty if city_short else alias_pretty,
                "local_type": str(r[loc_class] or "locality"),
                "district_borough": "",
                "county_unitary": str(state_name),
                "country": "Australia",
                "id": pid,
            }
        )
        if city_short and alias_pretty and alias_pretty != pretty:
            settlements.append(
                {
                    "name1": city_short,
                    "name2": alias_pretty,
                    "local_type": str(r[loc_class] or "locality"),
                    "district_borough": "",
                    "county_unitary": str(state_name),
                    "country": "Australia",
                    "id": pid + ":alias",
                }
            )
        pc = str(r[loc_pc] or "").strip()
        if pc and pc not in {"None", "nan"}:
            postcodes.append(
                {
                    "postcode": pc,
                    "populated_place": city_short or pretty,
                    "populated_place_type": "locality",
                    "district_borough": "",
                    "county_unitary": state_name,
                    "region": state_name,
                    "country": "Australia",
                }
            )

    extra_admin = [(n, "state") for n in state_map.values()]
    extra_admin += [
        ("Greater Sydney", "metro"),
        ("Greater Melbourne", "metro"),
        ("Greater Brisbane", "metro"),
        ("Greater Perth", "metro"),
        ("Greater Adelaide", "metro"),
        ("Australian Capital Territory", "territory"),
    ]
    lga_path = raw / "abs_lga.json"
    if lga_path.exists():
        payload = json.loads(lga_path.read_text())
        for feat in payload.get("features", []):
            attrs = feat.get("attributes") or feat.get("properties") or {}
            name = ""
            for k, v in attrs.items():
                if v and "lga_name" in k.casefold():
                    name = str(v)
                    break
            if name:
                extra_admin.append((name, "lga"))
                stripped = re.sub(r"\s*\([A-Z]\)\s*$", "", name).strip()
                if stripped != name:
                    extra_admin.append((stripped, "lga"))

    out = base / "gazetteer" / "derived"
    write_csv(out / "settlements.csv", SETTLEMENT_FIELDS, settlements)
    write_csv(out / "admin_units.csv", ADMIN_FIELDS, finish_admin(settlements, extra_admin))
    write_csv(out / "postcode_to_place.csv", PC_FIELDS, postcodes)
    derive_au_address_postcodes(base)


def derive_au_address_postcodes(base: Path) -> None:
    """Replace the thin locality postcode table with ADDRESS_DETAIL pairs.

    G-NAF locality rows leave PRIMARY_POSTCODE empty. The address table in the
    same zip has LOCALITY_PID and POSTCODE. One postcode often covers several
    localities, so every pair is kept.
    """
    import zipfile

    derived = base / "gazetteer" / "derived"
    settlements = read_csv_as_strings(derived / "settlements.csv")
    by_pid: dict[str, tuple[str, str]] = {}
    for row in settlements.itertuples(index=False):
        pid = (row.id or "").strip()
        if not pid or pid.endswith(":alias"):
            continue
        state = _AU_STATE.get((row.county_unitary or "").casefold(), row.county_unitary or "")
        by_pid[pid] = (row.name1, state)
    zip_path = base / "gazetteer" / "raw" / "gnaf_source.zip"
    if not zip_path.is_file():
        logger.warning("G-NAF zip missing at %s; keeping PRIMARY_POSTCODE rows", zip_path)
        return
    pairs: dict[tuple[str, str], int] = {}
    with zipfile.ZipFile(zip_path) as archive:
        members = [name for name in archive.namelist() if name.upper().endswith("_ADDRESS_DETAIL_PSV.PSV")]
        for member in members:
            label = member.rsplit("/", 1)[-1]
            logger.info("reading %s", label)
            with archive.open(member) as handle:
                header = handle.readline().decode("utf-8").rstrip("\n").split("|")
                index = {name: i for i, name in enumerate(header)}
                postcode_at = index["POSTCODE"]
                locality_at = index["LOCALITY_PID"]
                retired_at = index["DATE_RETIRED"]
                seen = 0
                for raw in handle:
                    seen += 1
                    if seen % 2_000_000 == 0:
                        logger.info("%s %d addresses", label, seen)
                    parts = raw.decode("utf-8", "replace").rstrip("\n").split("|")
                    if retired_at < len(parts) and parts[retired_at]:
                        continue
                    postcode = parts[postcode_at].strip() if postcode_at < len(parts) else ""
                    locality = parts[locality_at].strip() if locality_at < len(parts) else ""
                    if len(postcode) == 4 and postcode.isdigit() and locality in by_pid:
                        pairs[(postcode, locality)] = pairs.get((postcode, locality), 0) + 1
            logger.info("%s done, %d addresses", label, seen)
    postcodes = []
    for (postcode, locality) , count in pairs.items():
        place, state = by_pid[locality]
        postcodes.append(
            {
                "postcode": postcode,
                "populated_place": place,
                "populated_place_type": "locality",
                "district_borough": "",
                "county_unitary": state,
                "region": state,
                "country": "Australia",
                "address_count": str(count),
            }
        )
    postcodes.sort(key=lambda row: (row["postcode"], int(row["address_count"]), row["populated_place"]))
    write_csv(derived / "postcode_to_place.csv", PC_FIELDS + ["address_count"], postcodes)
    logger.info(
        "address postcodes: %d locality pairs, %d postcodes",
        len(postcodes),
        len({row["postcode"] for row in postcodes}),
    )


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--countries", default="fr,es,au")
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        stream=sys.stdout,
    )
    wanted = {c.strip().lower() for c in args.countries.split(",") if c.strip()}
    if "fr" in wanted:
        derive_fr(args.root / "fr_fix")
    if "es" in wanted:
        derive_es(args.root / "es_fix")
    if "au" in wanted:
        derive_au(args.root / "au_fix")


if __name__ == "__main__":
    main()
