"""Join Canadian address rows to a local NAR SQLite index."""


from __future__ import annotations

import argparse
import csv
import importlib.util
import io
import itertools
import re
import sqlite3
import sys
import unicodedata
import zipfile
from collections import defaultdict
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_PARENT = _HERE.parent


def _load_mod(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_cpaths = _load_mod("canada_paths", _HERE / "paths.py")
RESULTS = _cpaths.RESULTS
SLICES = _cpaths.SLICES
nar_zip = _cpaths.nar_zip

# classify_postcode imports `paths` (the parent module). Don't let canada/paths.py win.
_saved_paths = sys.modules.get("paths")
sys.path.insert(0, str(_PARENT))
sys.modules.pop("paths", None)
from classify_postcode import CATEGORIES, alnum, classify_postcode  # noqa: E402
if sys.path and sys.path[0] == str(_PARENT):
    del sys.path[0]
if _saved_paths is not None:
    sys.modules["paths"] = _saved_paths
else:
    sys.modules.pop("paths", None)

_PUNCT = re.compile(r"[^A-Z0-9]+")
_CA_PC = re.compile(
    r"^[ABCEGHJ-NPRSTVXY]\d[ABCEGHJ-NPRSTV-Z](\d[ABCEGHJ-NPRSTV-Z]\d)?$"
)
_ORDINAL = re.compile(r"^([0-9]+)(ST|ND|RD|TH)$")
_FR_ORDINAL = re.compile(r"^([0-9]+)(E|ER|ERE|EME|IEME)$")

STREET_TYPES = {
    "ST": "STREET",
    "STR": "STREET",
    "STREET": "STREET",
    "AVE": "AVENUE",
    "AV": "AVENUE",
    "AVENUE": "AVENUE",
    "BLVD": "BOULEVARD",
    "BOUL": "BOULEVARD",
    "BOULEVARD": "BOULEVARD",
    "RD": "ROAD",
    "ROAD": "ROAD",
    "DR": "DRIVE",
    "DRIVE": "DRIVE",
    "LN": "LANE",
    "LANE": "LANE",
    "CT": "COURT",
    "CRT": "COURT",
    "COURT": "COURT",
    "CIR": "CIRCLE",
    "CIRCLE": "CIRCLE",
    "CERCLE": "CERCLE",
    "PL": "PLACE",
    "PLACE": "PLACE",
    "TER": "TERRACE",
    "TERR": "TERRACE",
    "TERRACE": "TERRACE",
    "TSSE": "TERRASSE",
    "TERRASSE": "TERRASSE",
    "HWY": "HIGHWAY",
    "HIGHWAY": "HIGHWAY",
    "PKWY": "PARKWAY",
    "PKY": "PARKWAY",
    "PARKWAY": "PARKWAY",
    "TRL": "TRAIL",
    "TRAIL": "TRAIL",
    "WAY": "WAY",
    "RUE": "RUE",
    "CH": "CHEMIN",
    "CHEMIN": "CHEMIN",
    "ROUTE": "ROUTE",
    "RTE": "ROUTE",
    "RANG": "RANG",
    "MONTEE": "MONTEE",
    "CROIS": "CROISSANT",
    "CROISSANT": "CROISSANT",
    "CRES": "CRESCENT",
    "CRESCENT": "CRESCENT",
    "CAR": "CARRE",
    "CARRE": "CARRE",
    "COTE": "COTE",
    "IMP": "IMPASSE",
    "IMPASSE": "IMPASSE",
    "PROM": "PROMENADE",
    "PROMENADE": "PROMENADE",
    "ALLEE": "ALLEE",
    "MALL": "MALL",
    "GDNS": "GARDENS",
    "GARDENS": "GARDENS",
    "CONC": "CONCESSION",
    "CONCESSION": "CONCESSION",
    "AUT": "AUTOROUTE",
    "AUTOROUTE": "AUTOROUTE",
    "QUAI": "QUAI",
    "CLOSE": "CLOSE",
    "GATE": "GATE",
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
    "NORD": "N",
    "SUD": "S",
    "EST": "E",
    "OUEST": "W",
    "OUE": "W",
    "N": "N",
    "S": "S",
    "E": "E",
    "W": "W",
    "O": "W",
    "NE": "NE",
    "NW": "NW",
    "SE": "SE",
    "SW": "SW",
    "NO": "NW",
    "SO": "SW",
}

_COMPASS_PAIRS = {
    ("NORD", "EST"): "NE",
    ("NORD", "OUEST"): "NW",
    ("SUD", "EST"): "SE",
    ("SUD", "OUEST"): "SW",
    ("NORTH", "EAST"): "NE",
    ("NORTH", "WEST"): "NW",
    ("SOUTH", "EAST"): "SE",
    ("SOUTH", "WEST"): "SW",
}

PROVINCES = {
    "ALBERTA": "AB", "BRITISH COLUMBIA": "BC", "MANITOBA": "MB",
    "NEW BRUNSWICK": "NB", "NEWFOUNDLAND": "NL", "NEWFOUNDLAND AND LABRADOR": "NL",
    "NORTHWEST TERRITORIES": "NT", "NOVA SCOTIA": "NS", "NUNAVUT": "NU",
    "ONTARIO": "ON", "PRINCE EDWARD ISLAND": "PE", "QUEBEC": "QC",
    "SASKATCHEWAN": "SK", "YUKON": "YT",
}

PROV_CODE = {
    "10": "NL", "11": "PE", "12": "NS", "13": "NB", "24": "QC",
    "35": "ON", "46": "MB", "47": "SK", "48": "AB", "59": "BC",
    "60": "YT", "61": "NT", "62": "NU",
}

_TYPE_CANON = set(STREET_TYPES.values())
_PREFIX_TYPES = _TYPE_CANON | {"CALLE", "AVENIDA"}
_DIR_CANON = set(DIRECTIONALS.values())


def fold_ascii(value: str) -> str:
    s = unicodedata.normalize("NFKD", value or "")
    return "".join(c for c in s if not unicodedata.combining(c))


def postal_code(pc: str) -> str:
    a = alnum(pc)
    return a if _CA_PC.match(a) else ""


def index_postcode(pc: str) -> str:
    return postal_code(pc)


def province_abbr(value: str) -> str:
    v = fold_ascii(value or "").strip()
    if len(v) == 2 and v.isalpha():
        return v.upper()
    u = v.upper()
    left = u.split("/")[0].strip()
    if left in PROVINCES:
        return PROVINCES[left]
    if u in PROVINCES:
        return PROVINCES[u]
    for name, ab in PROVINCES.items():
        if name in u:
            return ab
    return ""


def norm_number(house: str) -> str:
    digits = re.sub(r"\D", "", house or "")
    return digits.lstrip("0") or digits


def _raw_tokens(road: str) -> list[str]:
    s = _PUNCT.sub(" ", fold_ascii(road or "").upper()).strip()
    raw = s.split()
    toks: list[str] = []
    i = 0
    while i < len(raw):
        pair = _COMPASS_PAIRS.get((raw[i], raw[i + 1])) if i + 1 < len(raw) else None
        if pair:
            toks.append(pair)
            i += 2
            continue
        toks.append(raw[i])
        i += 1
    return toks


def _expand_street_tokens(road: str) -> list[str]:
    raw = _raw_tokens(road)
    toks: list[str] = []
    last = len(raw) - 1
    for i, tok in enumerate(raw):
        if tok in {"SAINT", "STTE"}:
            toks.append("ST")
            continue
        if tok == "SAINTE":
            toks.append("STE")
            continue
        # Leading ST is Saint (St-Joseph). Any later ST is STREET (Dundas St W).
        # Trailing ST is STREET via STREET_TYPES (Eddy St).
        if tok == "ST" and i == 0 and i < last:
            toks.append("ST")
            continue
        if tok in DIRECTIONALS:
            t = DIRECTIONALS[tok]
        elif tok in STREET_TYPES:
            t = STREET_TYPES[tok]
        else:
            t = tok
        m = _ORDINAL.match(t) or _FR_ORDINAL.match(t)
        toks.append(m.group(1) if m else t)
    if len(toks) > 1 and toks[0] in _PREFIX_TYPES:
        typ = toks.pop(0)
        insert_at = len(toks)
        if toks and toks[-1] in _DIR_CANON:
            insert_at = len(toks) - 1
        toks.insert(insert_at, typ)
    return toks


def norm_street(road: str) -> str:
    """Full normalized street: expand, move a leading type to suffix, keep type/dir."""
    return " ".join(_expand_street_tokens(road))


def street_core(road: str) -> str:
    """Join-key street: expand, drop type and dirs unless the name is only digits."""
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
    r"^(CITY|TOWN|VILLE|VILLAGE|BOROUGH|TOWNSHIP|MUNICIPALITY|MUNICIPALITE|"
    r"CITE|PAROISSE|REGION)\s+(DE|OF|D)\s+"
)
_PLACE_SUFFIX = re.compile(
    r"\s+(TOWN|VILLAGE|BOROUGH|TOWNSHIP|MUNICIPALITY|CITY|VILLE)$"
)
_LEADING_THE = re.compile(r"^THE\s+")


def norm_city(value: str) -> str:
    s = _PUNCT.sub(" ", fold_ascii(value or "").upper()).strip()
    s = _LEADING_THE.sub("", s).strip()
    s = _PLACE_PREFIX.sub("", s).strip()
    s = _PLACE_SUFFIX.sub("", s).strip()
    s = re.sub(r"\bSAINTE\b", "STE", s)
    s = re.sub(r"\bSAINT\b", "ST", s)
    return " ".join(s.split())


def cities_match(query_city: str, index_city: str) -> bool:
    a, b = norm_city(query_city), norm_city(index_city)
    if not a or not b:
        return False
    return a == b


def decide(dirty_zip: str, clean_zip: str, hit_zips: set[str]) -> str:
    d, c = index_postcode(dirty_zip), index_postcode(clean_zip)
    hits = {index_postcode(z) for z in hit_zips if index_postcode(z)}
    if not hits:
        return "no_match"
    if d and d == c:
        if d in hits:
            return "confirm"
        if len(d) == 3 and any(len(h) == 6 and h.startswith(d) for h in hits):
            return "confirm"
        return "other"
    d_hit, c_hit = d in hits, c in hits
    if d_hit and c_hit:
        return "has_both"
    if d_hit:
        return "keep_dirty"
    if c_hit:
        return "keep_clean"
    return "other"


def _paired_csv_rows(dirty_fh, clean_fh):
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
            if cc != "ca":
                continue
            cat = classify_postcode(d.get("postcode", ""), c.get("postcode", ""), "ca")
            if cat not in wanted:
                continue
            house = c.get("house_number") or d.get("house_number") or ""
            road = c.get("road") or d.get("road") or ""
            if not house.strip() or not road.strip():
                continue
            st = province_abbr(c.get("region") or "") or province_abbr(d.get("region") or "")
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
            return str(lower[n.lower()]).strip()
    return ""


def _compose_street(name: str, typ: str, direction: str) -> str:
    return " ".join(p for p in (name, typ, direction) if p.strip())


def _nar_street(row: dict) -> str:
    return _compose_street(
        _row_get(row, "OFFICIAL_STREET_NAME"),
        _row_get(row, "OFFICIAL_STREET_TYPE"),
        _row_get(row, "OFFICIAL_STREET_DIR"),
    )


def _mail_street(row: dict) -> str:
    return _compose_street(
        _row_get(row, "MAIL_STREET_NAME"),
        _row_get(row, "MAIL_STREET_TYPE"),
        _row_get(row, "MAIL_STREET_DIR"),
    )


def _nar_province(row: dict) -> str:
    return (
        province_abbr(_row_get(row, "MAIL_PROV_ABVN"))
        or PROV_CODE.get(_row_get(row, "PROV_CODE"), "")
    )


def nar_record(row: dict) -> tuple[str, str, str] | None:
    number = norm_number(
        _row_get(row, "CIVIC_NO") + _row_get(row, "CIVIC_NO_SUFFIX")
    )
    raw_street = _nar_street(row) or _mail_street(row)
    street = norm_street(raw_street) or street_core(raw_street)
    st = _nar_province(row)
    if not number or not street or not st:
        return None
    z = postal_code(_row_get(row, "MAIL_POSTAL_CODE"))
    if not z:
        return None
    city = norm_city(
        _row_get(row, "MAIL_MUN_NAME")
        or _row_get(row, "CSD_ENG_NAME")
        or _row_get(row, "CSD_FRE_NAME")
    )
    return make_key(st, number, street), city, z


def _index_keys(state: str, number: str, raw_street: str) -> list[str]:
    keys: list[str] = []
    full = norm_street(raw_street)
    core = street_core(raw_street)
    if full:
        keys.append(index_key("F", state, number, full))
    if core:
        k = index_key("C", state, number, core)
        if k not in keys:
            keys.append(k)
    return keys


def nar_index_rows(row: dict) -> list[tuple[str, str, str]]:
    rec = nar_record(row)
    if rec is None:
        return []
    key, _, z = rec
    st, number, _rest = rec[0].split("|", 2)
    cities: list[str] = []
    for field in ("CSD_ENG_NAME", "CSD_FRE_NAME", "MAIL_MUN_NAME"):
        c = norm_city(_row_get(row, field))
        if c and c not in cities:
            cities.append(c)
    if not cities:
        cities = [rec[1]] if rec[1] else []
    if not cities:
        return []
    keys: list[str] = []
    for raw in (_nar_street(row), _mail_street(row)):
        if not raw.strip():
            continue
        for k in _index_keys(st, number, raw):
            if k not in keys:
                keys.append(k)
    if not keys:
        keys = [index_key("F", st, number, key.split("|", 2)[2])]
    return [(k, c, z) for k in keys for c in cities]


def _is_nar_table(name: str) -> bool:
    n = name.replace("\\", "/").lower()
    if n.startswith("__macosx") or "/." in n:
        return False
    if "location" in n:
        return False
    if not n.endswith((".csv", ".txt", ".tsv")):
        return False
    base = n.rsplit("/", 1)[-1]
    return base.startswith("address") or "/addresses/" in f"/{n}"


def _iter_nar_files(nar_path: Path):
    if nar_path.is_file() and zipfile.is_zipfile(nar_path):
        with zipfile.ZipFile(nar_path) as zf:
            for name in zf.namelist():
                if not _is_nar_table(name):
                    continue
                with zf.open(name) as fh:
                    yield name, io.TextIOWrapper(fh, encoding="utf-8-sig", errors="replace")
    elif nar_path.is_dir():
        for fp in sorted(nar_path.rglob("*")):
            if fp.is_file() and _is_nar_table(str(fp)):
                with fp.open(encoding="utf-8-sig", errors="replace") as fh:
                    yield str(fp), fh
    elif nar_path.is_file() and _is_nar_table(nar_path.name):
        with nar_path.open(encoding="utf-8-sig", errors="replace") as fh:
            yield str(nar_path), fh
    else:
        raise SystemExit(f"Not a NAR zip, Addresses CSV, or directory: {nar_path}")


def _iter_nar_rows(name: str, fh):
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
    for q, hit_pcs, method, matched in zip(queries, hits, methods, matched_keys):
        rec = {k: v for k, v in q.items() if not k.startswith("_")}
        rec["join_key"] = (matched or q.get("_key_typed") or q["_key"]) + f"|{q.get('_city') or ''}"
        rec["nar_pcs"] = "|".join(sorted(hit_pcs))
        rec["n_nar_pcs"] = str(len(hit_pcs))
        rec["match_method"] = method if hit_pcs else ""
        dec = decide(q["dirty_zip"], q["clean_zip"], hit_pcs)
        if dec in {"keep_clean", "keep_dirty"} and rec["match_method"] != "exact":
            dec = "other"
        rec["decision"] = dec
        out.append(rec)
    return out


_INDEX_SCHEMA = """
CREATE TABLE IF NOT EXISTS nar (
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
            "index is missing meta.key_format; rebuild with nar_join.py --build-index"
        )
    row = conn.execute("SELECT v FROM meta WHERE k = 'key_format'").fetchone()
    got = row[0] if row else None
    if got != INDEX_FORMAT:
        raise SystemExit(
            f"index key_format {got!r} != {INDEX_FORMAT}; rebuild with nar_join.py --build-index"
        )
    done = conn.execute("SELECT v FROM meta WHERE k = 'complete'").fetchone()
    if not done or done[0] != "1":
        raise SystemExit(
            "index meta.complete is not 1 (partial build); rebuild with nar_join.py --build-index"
        )
    if "nar" not in names:
        raise SystemExit("index has no nar table")
    return "nar"


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


def build_nar_index(nar_path: Path | list[Path], index_path: Path) -> None:
    paths = [nar_path] if isinstance(nar_path, Path) else list(nar_path)
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
                "INSERT OR IGNORE INTO nar(key, city, zip) VALUES (?, ?, ?)", batch
            )
            conn.commit()
            batch.clear()

        for path in paths:
            print(f"NAR source {path}", flush=True)
            for name, fh in _iter_nar_files(path):
                n_files += 1
                print(f"  indexing {name}", flush=True)
                for row in _iter_nar_rows(name, fh):
                    n_rows += 1
                    for rec in nar_index_rows(row):
                        batch.append(rec)
                    if len(batch) >= _INDEX_BATCH:
                        flush()
                        print(f"    {n_rows:,} NAR rows so far", flush=True)
                print(f"    {n_rows:,} NAR rows so far", flush=True)
        flush()
        n_keys = conn.execute("SELECT COUNT(*) FROM nar").fetchone()[0]
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
                q["_dirty_typed"] = index_key(
                    "F", q["state"], norm_number(dh), norm_street(dr)
                )
                q["_dirty_key"] = index_key(
                    "C", q["state"], norm_number(dh), street_core(dr)
                )
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
                pcs = {index_postcode(z) for _, z in rows if index_postcode(z)}
                if len(pcs) == 1:
                    hits[i] = pcs
                    methods[i] = method
                    matched_keys[i] = queries[i].get(key_attr) or ""

        full_rows = lookup("_key_typed")
        core_rows = lookup("_key")
        absorb_city(full_rows, "exact", "_key_typed")
        absorb_city(core_rows, "core", "_key")
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
    p = argparse.ArgumentParser(description="Join CA named-address rows to local NAR")
    p.add_argument("--dirty", default=str(SLICES / "slice_ca_dirty.csv"))
    p.add_argument("--clean", default=str(SLICES / "slice_ca_clean.csv"))
    p.add_argument(
        "--nar",
        action="append",
        help="NAR zip, Addresses CSV, or unpacked directory (repeatable)",
    )
    p.add_argument(
        "--build-index",
        metavar="SQLITE",
        help="Write NAR rows into this SQLite file and exit",
    )
    p.add_argument("--index", metavar="SQLITE", help="Join against an existing NAR SQLite index")
    p.add_argument(
        "--categories",
        default=",".join(CATEGORIES),
        help="Comma-separated A–F labels (default: all)",
    )
    p.add_argument("--out", default=str(RESULTS / "sample_nar_join_ca.csv"))
    p.add_argument(
        "--fights-only",
        action="store_true",
        help="Keep only dirty PC <> clean PC (blank vs a code counts)",
    )
    p.add_argument(
        "--unique-zip-fallback",
        action="store_true",
        help="If city misses, keep the hit when that street+house has one postal code",
    )
    p.add_argument(
        "--dirty-retry",
        action="store_true",
        help="On no_match, retry with dirty house/street",
    )
    args = p.parse_args()

    if args.build_index:
        sources = [Path(p) for p in args.nar] if args.nar else [nar_zip()]
        build_nar_index(sources, Path(args.build_index))
        return
    if not args.index:
        raise SystemExit("provide --index or --build-index --nar")

    cats = [x.strip() for x in args.categories.split(",") if x.strip()]
    bad = [x for x in cats if x not in CATEGORIES]
    if bad:
        raise SystemExit(f"Unknown categories {bad}; choose from {list(CATEGORIES)}")

    queries = load_query_rows(Path(args.dirty), Path(args.clean), categories=cats)
    if args.fights_only:
        queries = [
            q for q in queries
            if postal_code(q.get("dirty_zip") or "") != postal_code(q.get("clean_zip") or "")
        ]
    print(f"CA rows with street in {cats}: {len(queries)}", flush=True)
    results = join_from_index(
        queries,
        Path(args.index),
        unique_zip_fallback=args.unique_zip_fallback,
        dirty_retry=args.dirty_retry,
    )

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "id", "name", "house_number", "road", "locality", "state", "category",
        "dirty_zip", "clean_zip", "nar_pcs", "n_nar_pcs", "match_method",
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
