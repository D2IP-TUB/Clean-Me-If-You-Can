"""Join US address rows to a local NAD SQLite index."""


from __future__ import annotations

import argparse
import csv
import io
import itertools
import re
import sqlite3
import sys
import zipfile
from collections import defaultdict
from pathlib import Path

from classify_postcode import CATEGORIES, alnum, classify_postcode
from paths import RESULTS, SAMPLES

_PUNCT = re.compile(r"[^A-Z0-9]+")
_ZIP = re.compile(r"(?<![.\d])(\d{5})")
_ZIP_SHORT = re.compile(r"^0*(\d{3,4})(?:\.0+)?$")

STREET_TYPES = {
    "ST": "STREET",
    "STR": "STREET",
    "STREET": "STREET",
    "AVE": "AVENUE",
    "AV": "AVENUE",
    "AVENUE": "AVENUE",
    "BLVD": "BOULEVARD",
    "BOULEVARD": "BOULEVARD",
    "RD": "ROAD",
    "ROAD": "ROAD",
    "DR": "DRIVE",
    "DRIVE": "DRIVE",
    "LN": "LANE",
    "LANE": "LANE",
    "CT": "COURT",
    "COURT": "COURT",
    "CIR": "CIRCLE",
    "CIRCLE": "CIRCLE",
    "PL": "PLACE",
    "PLACE": "PLACE",
    "TER": "TERRACE",
    "TERRACE": "TERRACE",
    "HWY": "HIGHWAY",
    "HIGHWAY": "HIGHWAY",
    "PKWY": "PARKWAY",
    "PARKWAY": "PARKWAY",
    "TRL": "TRAIL",
    "TRAIL": "TRAIL",
    "WAY": "WAY",
}

DIRECTIONALS = {
    "NORTH": "N",
    "SOUTH": "S",
    "EAST": "E",
    "WEST": "W",
    "NORTHEAST": "NE",
    "NORTHWEST": "NW",
    "SOUTHEAST": "SE",
    "SOUTHWEST": "SW",
    "N": "N",
    "S": "S",
    "E": "E",
    "W": "W",
    "NE": "NE",
    "NW": "NW",
    "SE": "SE",
    "SW": "SW",
}

STATES = {
    "ALABAMA": "AL", "ALASKA": "AK", "ARIZONA": "AZ", "ARKANSAS": "AR",
    "CALIFORNIA": "CA", "COLORADO": "CO", "CONNECTICUT": "CT", "DELAWARE": "DE",
    "FLORIDA": "FL", "GEORGIA": "GA", "HAWAII": "HI", "IDAHO": "ID",
    "ILLINOIS": "IL", "INDIANA": "IN", "IOWA": "IA", "KANSAS": "KS",
    "KENTUCKY": "KY", "LOUISIANA": "LA", "MAINE": "ME", "MARYLAND": "MD",
    "MASSACHUSETTS": "MA", "MICHIGAN": "MI", "MINNESOTA": "MN", "MISSISSIPPI": "MS",
    "MISSOURI": "MO", "MONTANA": "MT", "NEBRASKA": "NE", "NEVADA": "NV",
    "NEW HAMPSHIRE": "NH", "NEW JERSEY": "NJ", "NEW MEXICO": "NM", "NEW YORK": "NY",
    "NORTH CAROLINA": "NC", "NORTH DAKOTA": "ND", "OHIO": "OH", "OKLAHOMA": "OK",
    "OREGON": "OR", "PENNSYLVANIA": "PA", "RHODE ISLAND": "RI", "SOUTH CAROLINA": "SC",
    "SOUTH DAKOTA": "SD", "TENNESSEE": "TN", "TEXAS": "TX", "UTAH": "UT",
    "VERMONT": "VT", "VIRGINIA": "VA", "WASHINGTON": "WA", "WEST VIRGINIA": "WV",
    "WISCONSIN": "WI", "WYOMING": "WY", "DISTRICT OF COLUMBIA": "DC",
}

PROVINCES = {
    "ALBERTA": "AB", "BRITISH COLUMBIA": "BC", "MANITOBA": "MB",
    "NEW BRUNSWICK": "NB", "NEWFOUNDLAND": "NL", "NEWFOUNDLAND AND LABRADOR": "NL",
    "NORTHWEST TERRITORIES": "NT", "NOVA SCOTIA": "NS", "NUNAVUT": "NU",
    "ONTARIO": "ON", "PRINCE EDWARD ISLAND": "PE", "QUEBEC": "QC", "QUÉBEC": "QC",
    "SASKATCHEWAN": "SK", "YUKON": "YT",
}

_CA_PC = re.compile(
    r"^[ABCEGHJ-NPRSTVXY]\d[ABCEGHJ-NPRSTV-Z](\d[ABCEGHJ-NPRSTV-Z]\d)?$"
)


def zip5(pc: str) -> str:
    if not pc:
        return ""
    s = str(pc).strip()
    m = _ZIP.search(s)
    if m:
        return m.group(1)
    m = _ZIP_SHORT.fullmatch(s)
    return m.group(1).zfill(5) if m else ""


def index_postcode(pc: str) -> str:
    z = zip5(pc)
    if z:
        return z
    a = alnum(pc)
    return a if _CA_PC.match(a) else ""


def state_abbr(value: str) -> str:
    v = (value or "").strip()
    if len(v) == 2 and v.isalpha():
        return v.upper()
    u = v.upper()
    return STATES.get(u) or PROVINCES.get(u, "")


def norm_number(house: str) -> str:
    digits = re.sub(r"\D", "", house or "")
    return digits.lstrip("0") or digits


_TYPE_CANON = set(STREET_TYPES.values())
_PREFIX_TYPES = {"CALLE", "AVENIDA"}
_DIR_CANON = set(DIRECTIONALS.values())
_ORDINAL = re.compile(r"^([0-9]+)(ST|ND|RD|TH)$")


def _expand_street_tokens(road: str) -> list[str]:
    s = _PUNCT.sub(" ", (road or "").upper()).strip()
    toks: list[str] = []
    for tok in s.split():
        if tok in DIRECTIONALS:
            t = DIRECTIONALS[tok]
        elif tok in STREET_TYPES:
            t = STREET_TYPES[tok]
        else:
            t = tok
        m = _ORDINAL.match(t)
        toks.append(m.group(1) if m else t)
    return toks


def norm_street(road: str) -> str:
    """Full normalized street: expand types/dirs and ordinals; keep type and dir."""
    return " ".join(_expand_street_tokens(road))


def street_core(road: str) -> str:
    """Join-key street: expand, then drop trailing dir and type; keep a dir
    in front only when the remainder is purely numeric (W 95th / 95th St W).
    Spec: docs/street_core.md
    """
    toks = _expand_street_tokens(road)
    post_dir = toks.pop() if len(toks) > 1 and toks[-1] in _DIR_CANON else ""
    if len(toks) > 1 and toks[-1] in _TYPE_CANON:
        toks.pop()
    if len(toks) > 1 and toks[0] in _PREFIX_TYPES:
        toks.pop(0)
    pre_dir = toks.pop(0) if len(toks) > 1 and toks[0] in _DIR_CANON else ""
    if toks and all(t.isdigit() for t in toks) and (pre_dir or post_dir):
        toks.insert(0, pre_dir or post_dir)
    return " ".join(toks)


def make_key(state: str, number: str, street: str) -> str:
    return f"{state}|{number}|{street}"


INDEX_FORMAT = "full_core_v1"


def index_key(kind: str, state: str, number: str, street: str) -> str:
    return f"{kind}|{state}|{number}|{street}"


_PLACE_PREFIX = re.compile(
    r"^(CITY|TOWN|VILLAGE|BOROUGH|TOWNSHIP|MUNICIPALITY)\s+OF\s+"
)
_PLACE_SUFFIX = re.compile(
    r"\s+(TOWN|VILLAGE|BOROUGH|TOWNSHIP|MUNICIPALITY)$"
)
_LEADING_THE = re.compile(r"^THE\s+")
_NYC = {
    "NEW YORK",
    "NEW YORK CITY",
    "NYC",
    "MANHATTAN",
    "BROOKLYN",
    "QUEENS",
    "BRONX",
    "STATEN ISLAND",
}


def norm_city(value: str) -> str:
    s = _PUNCT.sub(" ", (value or "").upper()).strip()
    s = _LEADING_THE.sub("", s).strip()
    s = _PLACE_PREFIX.sub("", s).strip()
    s = _PLACE_SUFFIX.sub("", s).strip()
    s = re.sub(r"\bSAINT\b", "ST", s)
    return " ".join(s.split())


def cities_match(query_city: str, index_city: str) -> bool:
    a, b = norm_city(query_city), norm_city(index_city)
    if not a or not b:
        return False
    if a == b:
        return True
    if a in _NYC and b in _NYC:
        return True
    return False


def decide(dirty_zip: str, clean_zip: str, hit_zips: set[str]) -> str:
    d, c = index_postcode(dirty_zip), index_postcode(clean_zip)
    hits = {index_postcode(z) for z in hit_zips if index_postcode(z)}
    if not hits:
        return "no_match"
    if d and d == c:
        return "confirm" if d in hits else "other"
    if hits == {d}:
        return "keep_dirty"
    if hits == {c}:
        return "keep_clean"
    if d in hits and c in hits:
        return "has_both"
    if d in hits:
        return "keep_dirty"
    if c in hits:
        return "keep_clean"
    return "other"


def _paired_csv_rows(dirty_fh, clean_fh):
    """Yield aligned dirty/clean dicts. Unequal lengths → SystemExit, not ValueError."""
    di = csv.DictReader(dirty_fh)
    ci = csv.DictReader(clean_fh)
    sentinel = object()
    while True:
        d = next(di, sentinel)
        c = next(ci, sentinel)
        if d is sentinel and c is sentinel:
            return
        if d is sentinel or c is sentinel:
            raise SystemExit("dirty/clean row count mismatch")
        yield d, c


def load_query_rows(
    dirty_csv: Path,
    clean_csv: Path,
    categories: list[str] | None = None,
) -> list[dict]:
    wanted = set(categories) if categories else set(CATEGORIES)
    rows = []
    with dirty_csv.open(newline="", encoding="utf-8", errors="replace") as fd, \
         clean_csv.open(newline="", encoding="utf-8", errors="replace") as fc:
        for d, c in _paired_csv_rows(fd, fc):
            if d["id"] != c["id"]:
                raise SystemExit(f"id mismatch: {d['id']} vs {c['id']}")
            cc = (c.get("country_code") or d.get("country_code") or "").lower()
            if cc != "us":
                continue
            cat = classify_postcode(d.get("postcode", ""), c.get("postcode", ""), "us")
            if cat not in wanted:
                continue
            house = c.get("house_number") or d.get("house_number") or ""
            road = c.get("road") or d.get("road") or ""
            if not house.strip() or not road.strip():
                continue
            st = state_abbr(c.get("region") or "") or state_abbr(d.get("region") or "")
            rows.append({
                "id": d["id"],
                "name": c.get("name") or d.get("name") or "",
                "house_number": house,
                "road": road,
                "locality": c.get("locality") or d.get("locality") or "",
                "state": st,
                "category": cat,
                "dirty_zip": d.get("postcode", ""),
                "clean_zip": c.get("postcode", ""),
                "dirty_house": d.get("house_number") or "",
                "dirty_road": d.get("road") or "",
                "dirty_locality": d.get("locality") or "",
                "url": d.get("provenance_graph_iri") or c.get("provenance_graph_iri") or "",
            })
    return rows


def _row_get(row: dict, *names: str) -> str:
    lower = {k.lower(): v for k, v in row.items()}
    for n in names:
        if n.lower() in lower and lower[n.lower()] is not None:
            return str(lower[n.lower()])
    return ""


def _nad_street(row: dict) -> str:
    full = _row_get(row, "StNam_Full", "St_Nam_Full", "StNameFull")
    if full.strip():
        return full
    parts = [
        _row_get(row, "St_PreDir", "StPreDir", "PreDir", "StNamPreDir"),
        _row_get(row, "St_Name", "StNam", "StreetName", "StName"),
        _row_get(row, "St_PosTyp", "StTyp", "St_PosType", "StreetType", "StPosTyp"),
        _row_get(row, "St_PosDir", "StPosDir", "PostDir", "StNamPosDir"),
    ]
    return " ".join(p for p in parts if p.strip())


def nad_record(row: dict) -> tuple[str, str, str] | None:
    number = norm_number(
        _row_get(row, "Add_Number", "AddNum", "AddNo", "AddNo_Full", "AddNum_Full", "NUMBER")
    )
    raw_street = _nad_street(row) or _row_get(row, "STREET", "street")
    street = norm_street(raw_street) or street_core(raw_street)
    st = state_abbr(_row_get(row, "State", "STATE", "StAbbr", "State_Name"))
    if not number or not street or not st:
        return None
    z = zip5(_row_get(row, "Zip_Code", "ZipCode", "ZIP", "Zip", "POSTCODE"))
    if not z:
        return None
    city = norm_city(
        _row_get(
            row,
            "Inc_Muni",
            "IncMuni",
            "Post_City",
            "PostCity",
            "PostComm",
            "Uninc_Comm",
            "UnincComm",
            "CITY",
            "city",
        )
    )
    return make_key(st, number, street), city, z


def nad_index_rows(row: dict) -> list[tuple[str, str, str]]:
    rec = nad_record(row)
    if rec is None:
        return []
    key, _, z = rec
    cities: list[str] = []
    for field in (
        "Inc_Muni",
        "IncMuni",
        "Post_City",
        "PostCity",
        "PostComm",
        "Post_Comm",
        "Uninc_Comm",
        "UnincComm",
        "CITY",
        "city",
    ):
        c = norm_city(_row_get(row, field))
        if c and c not in cities:
            cities.append(c)
    if not cities:
        cities = [rec[1]]
    raw_street = _nad_street(row) or _row_get(row, "STREET", "street")
    st, number, _rest = rec[0].split("|", 2)
    keys: list[str] = []
    full = norm_street(raw_street)
    core = street_core(raw_street)
    if full:
        keys.append(index_key("F", st, number, full))
    if core:
        k = index_key("C", st, number, core)
        if k not in keys:
            keys.append(k)
    return [(k, c, z) for k in keys for c in cities]


def _is_nad_table(name: str) -> bool:
    n = name.replace("\\", "/").lower()
    if n.startswith("__macosx") or "/." in n:
        return False
    return n.endswith((".csv", ".txt", ".tsv"))


def _iter_nad_files(nad_path: Path):
    if nad_path.is_file() and zipfile.is_zipfile(nad_path):
        with zipfile.ZipFile(nad_path) as zf:
            for name in zf.namelist():
                if not _is_nad_table(name):
                    continue
                with zf.open(name) as fh:
                    yield name, io.TextIOWrapper(fh, encoding="utf-8", errors="replace")
    elif nad_path.is_dir():
        for fp in sorted(nad_path.rglob("*")):
            if fp.is_file() and _is_nad_table(str(fp)):
                with fp.open(encoding="utf-8", errors="replace") as fh:
                    yield str(fp), fh
    elif nad_path.is_file() and _is_nad_table(nad_path.name):
        with nad_path.open(encoding="utf-8", errors="replace") as fh:
            yield str(nad_path), fh
    else:
        raise SystemExit(f"Not a NAD zip, table, or directory: {nad_path}")


def _iter_nad_rows(name: str, fh):
    first = fh.readline()
    if not first or not first.strip():
        return
    n_pipe, n_comma, n_tab = first.count("|"), first.count(","), first.count("\t")
    delim = ","
    if n_pipe > n_comma and n_pipe > n_tab:
        delim = "|"
    elif n_tab > n_comma and n_tab > n_pipe:
        delim = "\t"
    yield from csv.DictReader(itertools.chain([first], fh), delimiter=delim)


def _prepare_queries(queries: list[dict]) -> dict[str, list[int]]:
    wanted: dict[str, list[int]] = defaultdict(list)
    for i, q in enumerate(queries):
        house = norm_number(q["house_number"])
        q["_key_typed"] = index_key("F", q["state"], house, norm_street(q["road"]))
        q["_key"] = index_key("C", q["state"], house, street_core(q["road"]))
        clean = norm_city(q.get("locality") or "")
        dirty = norm_city(q.get("dirty_locality") or "")
        q["_clean_cities"] = [clean] if clean else []
        q["_dirty_cities"] = [dirty] if dirty and dirty != clean else []
        cities = list(q["_clean_cities"])
        for c in q["_dirty_cities"]:
            if c not in cities:
                cities.append(c)
        q["_city"] = cities[0] if cities else ""
        q["_cities"] = cities
        wanted[q["_key_typed"]].append(i)
    return wanted


def _city_hit_kind(q: dict, index_city: str) -> str | None:
    clean = q.get("_clean_cities") or []
    dirty = q.get("_dirty_cities") or []
    if not clean and not dirty:
        return "nocity"
    if not index_city:
        return None
    if clean and any(cities_match(c, index_city) for c in clean):
        return "clean"
    if dirty and any(cities_match(c, index_city) for c in dirty):
        return "dirty"
    return None


def _hits_to_results(
    queries: list[dict],
    hits: list[set[str]],
    methods: list[str],
    matched_keys: list[str],
) -> list[dict]:
    out = []
    for q, hit_zips, method, matched in zip(queries, hits, methods, matched_keys):
        rec = {k: v for k, v in q.items() if not k.startswith("_")}
        rec["join_key"] = (matched or q.get("_key_typed") or q["_key"]) + f"|{q.get('_city') or ''}"
        rec["nad_zips"] = "|".join(sorted(hit_zips))
        rec["n_nad_zips"] = str(len(hit_zips))
        rec["match_method"] = method if hit_zips else ""
        dec = decide(q["dirty_zip"], q["clean_zip"], hit_zips)
        if dec in {"keep_clean", "keep_dirty"} and rec["match_method"] != "exact":
            dec = "other"
        rec["decision"] = dec
        out.append(rec)
    return out


_INDEX_SCHEMA = """
CREATE TABLE IF NOT EXISTS nad (
  key TEXT NOT NULL,
  city TEXT NOT NULL,
  zip TEXT NOT NULL,
  PRIMARY KEY (key, city, zip)
) WITHOUT ROWID
"""
_META_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
  k TEXT PRIMARY KEY,
  v TEXT NOT NULL
)
"""
_INDEX_BATCH = 10_000


def _hits_table(conn: sqlite3.Connection) -> str:
    names = {
        r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    if "meta" not in names:
        raise SystemExit(
            "index is missing meta.key_format; rebuild with nad_join.py --build-index"
        )
    row = conn.execute("SELECT v FROM meta WHERE k = 'key_format'").fetchone()
    got = row[0] if row else None
    if got != INDEX_FORMAT:
        raise SystemExit(
            f"index key_format {got!r} != {INDEX_FORMAT}; rebuild with nad_join.py --build-index"
        )
    done = conn.execute("SELECT v FROM meta WHERE k = 'complete'").fetchone()
    if not done or done[0] != "1":
        raise SystemExit(
            "index meta.complete is not 1 (partial build); rebuild with nad_join.py --build-index"
        )
    if "nad" not in names:
        raise SystemExit("index has no nad table")
    return "nad"


def _sqlite_sidecars(path: Path) -> list[Path]:
    return [Path(str(path) + "-wal"), Path(str(path) + "-shm")]


def _unlink_sqlite(path: Path) -> None:
    path.unlink(missing_ok=True)
    for extra in _sqlite_sidecars(path):
        extra.unlink(missing_ok=True)


def _install_built_index(tmp_path: Path, index_path: Path) -> None:
    for extra in _sqlite_sidecars(index_path):
        extra.unlink(missing_ok=True)
    tmp_path.replace(index_path)
    for extra in _sqlite_sidecars(tmp_path):
        extra.unlink(missing_ok=True)


def build_nad_index(nad_path: Path | list[Path], index_path: Path) -> None:
    paths = [nad_path] if isinstance(nad_path, Path) else list(nad_path)
    index_path = Path(index_path)
    index_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = index_path.with_name(index_path.name + ".building")
    _unlink_sqlite(tmp_path)
    conn: sqlite3.Connection | None = sqlite3.connect(tmp_path)
    renamed = False
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute(_INDEX_SCHEMA)
        conn.execute(_META_SCHEMA)
        batch: list[tuple[str, str, str]] = []
        n_files = 0
        n_rows = 0

        def flush() -> None:
            if not batch:
                return
            conn.executemany(
                "INSERT OR IGNORE INTO nad(key, city, zip) VALUES (?, ?, ?)", batch
            )
            conn.commit()
            batch.clear()

        for path in paths:
            print(f"NAD source {path}", flush=True)
            for name, fh in _iter_nad_files(path):
                n_files += 1
                print(f"  indexing {name}", flush=True)
                for row in _iter_nad_rows(name, fh):
                    n_rows += 1
                    for rec in nad_index_rows(row):
                        batch.append(rec)
                    if len(batch) >= _INDEX_BATCH:
                        flush()
                        print(f"    {n_rows:,} NAD rows so far", flush=True)
                print(f"    {n_rows:,} NAD rows so far", flush=True)
        flush()
        n_keys = conn.execute("SELECT COUNT(*) FROM nad").fetchone()[0]
        conn.execute(
            "INSERT OR REPLACE INTO meta(k, v) VALUES ('key_format', ?)", (INDEX_FORMAT,)
        )
        conn.execute("INSERT OR REPLACE INTO meta(k, v) VALUES ('complete', '1')")
        conn.commit()
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        conn.execute("PRAGMA journal_mode=DELETE")
        conn.close()
        conn = None
        _install_built_index(tmp_path, index_path)
        renamed = True
    finally:
        if conn is not None:
            conn.close()
        if not renamed:
            _unlink_sqlite(tmp_path)
    print(
        f"wrote {index_path} ({n_keys:,} unique key/city/zip from {n_files} files, {n_rows:,} rows)",
        flush=True,
    )


def join_from_index(
    queries: list[dict],
    index_path: Path,
    *,
    unique_zip_fallback: bool = False,
    dirty_retry: bool = False,
) -> list[dict]:
    _prepare_queries(queries)
    if dirty_retry:
        for q in queries:
            dh, dr = (q.get("dirty_house") or "").strip(), (q.get("dirty_road") or "").strip()
            if dh and dr:
                q["_dirty_typed"] = index_key("F", q["state"], norm_number(dh), norm_street(dr))
                q["_dirty_key"] = index_key("C", q["state"], norm_number(dh), street_core(dr))
            else:
                q["_dirty_typed"] = ""
                q["_dirty_key"] = ""
    hits: list[set[str]] = [set() for _ in queries]
    methods: list[str] = [""] * len(queries)
    matched_keys: list[str] = [""] * len(queries)
    conn = sqlite3.connect(f"file:{Path(index_path).as_posix()}?mode=ro", uri=True)
    try:
        table = _hits_table(conn)
        conn.execute("CREATE TEMP TABLE q (idx INTEGER, key TEXT)")

        def lookup(key_attr: str) -> dict[int, list[tuple[str, str]]]:
            conn.execute("DELETE FROM q")
            conn.executemany(
                "INSERT INTO q(idx, key) VALUES (?, ?)",
                [(i, q[key_attr]) for i, q in enumerate(queries) if q.get(key_attr)],
            )
            by_idx: dict[int, list[tuple[str, str]]] = defaultdict(list)
            cur = conn.execute(
                f"SELECT q.idx, t.city, t.zip FROM q JOIN {table} t ON t.key = q.key"
            )
            for idx, index_city, z in cur:
                by_idx[idx].append((index_city, z))
            return by_idx

        def absorb_city(
            by_idx: dict[int, list[tuple[str, str]]],
            method: str,
            key_attr: str,
        ) -> None:
            for i, rows in by_idx.items():
                if hits[i]:
                    continue
                classified: list[tuple[str, str]] = []
                for index_city, z in rows:
                    kind = _city_hit_kind(queries[i], index_city)
                    if kind:
                        classified.append((kind, z))
                if not classified:
                    continue
                kinds = {kind for kind, _ in classified}
                if "clean" in kinds:
                    use, methods[i] = "clean", method
                elif "nocity" in kinds:
                    use, methods[i] = "nocity", f"{method}_nocity"
                elif method in {"exact", "core"}:
                    use, methods[i] = "dirty", f"{method}_dirtycity"
                else:
                    use, methods[i] = "dirty", method
                for kind, z in classified:
                    if kind == use:
                        hits[i].add(z)
                matched_keys[i] = queries[i].get(key_attr) or ""

        def absorb_unique(
            by_idx: dict[int, list[tuple[str, str]]],
            method: str,
            key_attr: str,
        ) -> None:
            if not unique_zip_fallback:
                return
            for i, rows in by_idx.items():
                if hits[i]:
                    continue
                zips = {index_postcode(z) for _, z in rows if index_postcode(z)}
                if len(zips) == 1:
                    hits[i] = zips
                    methods[i] = method
                    matched_keys[i] = queries[i].get(key_attr) or ""

        full_rows = lookup("_key_typed")
        core_rows = lookup("_key")
        absorb_city(full_rows, "exact", "_key_typed")
        absorb_city(core_rows, "core", "_key")
        # Clean unique-ZIP (possibly another town) is intentionally before
        # city-checked dirty retries: dirty lookups are circular.
        absorb_unique(full_rows, "unique_zip_full", "_key_typed")
        absorb_unique(core_rows, "unique_zip_core", "_key")
        if dirty_retry:
            dirty_full = lookup("_dirty_typed")
            dirty_core = lookup("_dirty_key")
            absorb_city(dirty_full, "dirty_full", "_dirty_typed")
            absorb_city(dirty_core, "dirty_core", "_dirty_key")
            absorb_unique(dirty_full, "dirty_unique_zip_full", "_dirty_typed")
            absorb_unique(dirty_core, "dirty_unique_zip_core", "_dirty_key")
        return _hits_to_results(queries, hits, methods, matched_keys)
    finally:
        conn.close()


def main():
    p = argparse.ArgumentParser(description="Join US named-address rows to local NAD")
    p.add_argument("--dirty", default=str(SAMPLES / "dirty.csv"))
    p.add_argument("--clean", default=str(SAMPLES / "clean.csv"))
    p.add_argument(
        "--nad",
        action="append",
        help="NAD comma-delimited zip, .txt/.csv, or unpacked directory (repeatable)",
    )
    p.add_argument(
        "--build-index",
        metavar="SQLITE",
        help="Write NAD rows into this SQLite file and exit",
    )
    p.add_argument(
        "--index",
        metavar="SQLITE",
        help="Join against an existing NAD SQLite index",
    )
    p.add_argument(
        "--categories",
        default=",".join(CATEGORIES),
        help="Comma-separated A–F labels (default: all)",
    )
    p.add_argument("--out", default=str(RESULTS / "sample_nad_join_us.csv"))
    p.add_argument(
        "--fights-only",
        action="store_true",
        help="Keep only dirty ZIP5 <> clean ZIP5 (blank vs a ZIP counts)",
    )
    p.add_argument(
        "--unique-zip-fallback",
        action="store_true",
        help="If city misses, keep the hit when that street+house has one ZIP",
    )
    p.add_argument(
        "--dirty-retry",
        action="store_true",
        help="On no_match, retry with dirty house/street",
    )
    args = p.parse_args()

    if args.build_index:
        if not args.nad:
            raise SystemExit("--build-index requires --nad")
        build_nad_index([Path(p) for p in args.nad], Path(args.build_index))
        return
    if not args.index:
        raise SystemExit("provide --index or --build-index --nad")

    cats = [x.strip() for x in args.categories.split(",") if x.strip()]
    bad = [x for x in cats if x not in CATEGORIES]
    if bad:
        raise SystemExit(f"Unknown categories {bad}; choose from {list(CATEGORIES)}")

    queries = load_query_rows(Path(args.dirty), Path(args.clean), categories=cats)
    if args.fights_only:
        queries = [
            q for q in queries
            if zip5(q.get("dirty_zip") or "") != zip5(q.get("clean_zip") or "")
        ]
    print(f"US rows with street in {cats}: {len(queries)}", flush=True)
    results = join_from_index(
        queries,
        Path(args.index),
        unique_zip_fallback=args.unique_zip_fallback,
        dirty_retry=args.dirty_retry,
    )

    out_path = Path(args.out)
    fields = [
        "id", "name", "house_number", "road", "locality", "state", "category",
        "dirty_zip", "clean_zip", "nad_zips", "n_nad_zips", "match_method",
        "decision", "join_key", "url",
    ]
    with out_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(results)

    from collections import Counter
    print(f"wrote {out_path}")
    print("by decision:")
    for k, n in Counter(r["decision"] for r in results).most_common():
        print(f"  {k:12} {n}")
    print("by category x decision:")
    for k, n in Counter((r["category"], r["decision"]) for r in results).most_common():
        print(f"  {k[0]:16} {k[1]:12} {n}")


if __name__ == "__main__":
    main()
