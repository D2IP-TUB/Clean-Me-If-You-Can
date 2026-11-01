"""
Nominatim error-detection / correction baseline.

Query dirty rows with structured Nominatim search (same fields as OsmValidator),
map the hit with pack/extraction rules (pick_best_osm_field), then:
  - detect a cell when Nominatim returns a value different from dirty
  - propose that value as a correction whenever it is present
  - abstain when Nominatim returns no hit or the field is missing (FN if oracle error)
"""

from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Iterable, List, Mapping, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from evaluate import normalize


ADDRESS_COLUMNS = [
    "name",
    "house_number",
    "road",
    "postcode",
    "locality",
    "region",
    "country",
    "country_code",
]

_LOCALITY_PREFERRED = ["city", "town"]
_LOCALITY_FALLBACK = ["village", "borough", "neighborhood", "hamlet", "municipality"]
_REGION_PREFERRED = ["region", "state"]
_REGION_FALLBACK = ["province", "county", "state_district"]

Cell = Tuple[int, int]


def _levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(cur[j - 1] + 1, prev[j] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def pick_best_osm_field(
    query_val: Optional[str],
    address: dict,
    preferred_keys: list,
    fallback_keys: list,
) -> Optional[str]:
    """Same selection rule as postalcrawl.pack.main.pick_best_osm_field."""

    def best_of(candidates: list) -> Optional[str]:
        if not candidates:
            return None
        if query_val is None or len(candidates) == 1:
            return candidates[0]
        q = query_val.lower()
        return min(candidates, key=lambda v: _levenshtein(q, v.lower()))

    preferred = [address[k] for k in preferred_keys if address.get(k)]
    if preferred:
        return best_of(preferred)
    fallback = [address[k] for k in fallback_keys if address.get(k)]
    return best_of(fallback)


def _nonempty(value) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def build_query_params(row: Mapping) -> dict:
    """Structured search params matching OsmValidator.query_validator."""
    house = _nonempty(row.get("house_number"))
    road = _nonempty(row.get("road"))
    street = " ".join(p for p in (house, road) if p) or None
    params = {
        "amenity": _nonempty(row.get("name")),
        "street": street,
        "city": _nonempty(row.get("locality")),
        "state": _nonempty(row.get("region")),
        "country": _nonempty(row.get("country")),
        "postalcode": _nonempty(row.get("postcode")),
    }
    return {k: v for k, v in params.items() if v}


def map_feature_to_row(
    feature: Optional[dict],
    dirty_locality: Optional[str] = None,
    dirty_region: Optional[str] = None,
) -> Dict[str, Optional[str]]:
    """Map a GeoJSON feature to the experiment schema using pack extraction rules."""
    mapped = {col: None for col in ADDRESS_COLUMNS}
    if not feature:
        return mapped

    props = feature.get("properties") or {}
    address = props.get("address") or {}
    geocoding = props.get("geocoding") or {}
    namedetails = props.get("namedetails") or geocoding.get("namedetails") or {}

    mapped["name"] = _nonempty(namedetails.get("name") or props.get("name") or geocoding.get("name"))
    mapped["house_number"] = _nonempty(address.get("house_number") or geocoding.get("housenumber"))
    mapped["road"] = _nonempty(address.get("road") or geocoding.get("street"))
    mapped["postcode"] = _nonempty(address.get("postcode") or geocoding.get("postcode"))
    mapped["locality"] = _nonempty(
        pick_best_osm_field(dirty_locality, address, _LOCALITY_PREFERRED, _LOCALITY_FALLBACK)
        or geocoding.get("city")
    )
    mapped["region"] = _nonempty(
        pick_best_osm_field(dirty_region, address, _REGION_PREFERRED, _REGION_FALLBACK)
        or geocoding.get("state")
    )
    mapped["country"] = _nonempty(address.get("country") or geocoding.get("country"))
    mapped["country_code"] = _nonempty(address.get("country_code") or geocoding.get("country_code"))
    return mapped


def cells_from_mapped_row(
    row_idx: int,
    dirty_row: Mapping,
    mapped: Mapping,
    col_names: List[str],
) -> Tuple[Dict[Cell, str], Dict[Cell, str]]:
    """Return (detected_cells, corrected_cells) for one row.

    Missing Nominatim values abstain (not detected, not corrected).
    A present value is always a correction; it is a detection iff it differs
    from the dirty cell after evaluate.normalize.
    """
    detected: Dict[Cell, str] = {}
    corrected: Dict[Cell, str] = {}
    for j, col in enumerate(col_names):
        nom_val = _nonempty(mapped.get(col))
        if nom_val is None:
            continue
        corrected[(row_idx, j)] = nom_val
        if normalize(nom_val) != normalize(dirty_row.get(col, "")):
            detected[(row_idx, j)] = nom_val
    return detected, corrected


def query_nominatim(
    params: dict,
    nominatim_url: str,
    timeout: float = 60.0,
    retries: int = 3,
) -> Optional[dict]:
    if not params:
        return None
    query = {
        "format": "geojson",
        "limit": "1",
        "addressdetails": "1",
        "namedetails": "1",
        "extratags": "1",
        **params,
    }
    url = nominatim_url.rstrip("/") + "/search?" + urlencode(query)
    delay = 0.2
    for attempt in range(max(1, retries)):
        req = Request(url, headers={"User-Agent": "address-paper-nominatim-baseline/1.0"})
        try:
            with urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            features = data.get("features") or []
            return features[0] if features else None
        except (HTTPError, URLError, TimeoutError, ValueError, OSError):
            if attempt + 1 < retries:
                time.sleep(delay)
                delay = min(delay * 2, 2.0)
            continue
    return None


def _fill_features(
    rows: List[Mapping],
    features: List[Optional[dict]],
    indices: List[int],
    nominatim_url: str,
    max_workers: int,
    timeout: float,
    progress_every: int,
    log,
    label: str,
) -> None:
    if not indices:
        return

    def _one(i: int):
        return i, query_nominatim(build_query_params(rows[i]), nominatim_url, timeout=timeout)

    done = 0
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futs = [pool.submit(_one, i) for i in indices]
        for fut in as_completed(futs):
            i, feature = fut.result()
            features[i] = feature
            done += 1
            if progress_every and done % progress_every == 0:
                n_hit = sum(1 for f in features if f is not None)
                log(f"  {label} {done}/{len(indices)}  hits={n_hit}/{len(features)}")


def query_rows(
    rows: Iterable[Mapping],
    nominatim_url: str,
    max_workers: int = 16,
    timeout: float = 60.0,
    progress_every: int = 200,
    log=print,
    existing: Optional[List[Optional[dict]]] = None,
) -> List[Optional[dict]]:
    """Query Nominatim for each row; return a feature (or None) per row index.

    If *existing* is provided (e.g. a cache), already-hit rows are kept and
    only None slots are queried, then retried once at lower concurrency.
    """
    rows = list(rows)
    features: List[Optional[dict]] = list(existing) if existing is not None else [None] * len(rows)
    if existing is not None and len(features) != len(rows):
        features = [None] * len(rows)
    if not rows:
        return features

    todo = [i for i, feat in enumerate(features) if feat is None]
    _fill_features(
        rows, features, todo,
        nominatim_url, max_workers, timeout, progress_every, log, "Nominatim",
    )
    missing = [i for i, feat in enumerate(features) if feat is None]
    if missing:
        retry_workers = max(1, min(8, max_workers))
        log(f"  Retrying {len(missing)} misses with {retry_workers} workers")
        _fill_features(
            rows, features, missing,
            nominatim_url, retry_workers, timeout, progress_every, log, "Nominatim retry",
        )
    return features


def detect_and_correct(
    dirty_rows: List[Mapping],
    features: List[Optional[dict]],
    col_names: List[str],
) -> Tuple[Dict[Cell, str], Dict[Cell, str]]:
    detected: Dict[Cell, str] = {}
    corrected: Dict[Cell, str] = {}
    for i, (row, feature) in enumerate(zip(dirty_rows, features)):
        mapped = map_feature_to_row(
            feature,
            dirty_locality=_nonempty(row.get("locality")),
            dirty_region=_nonempty(row.get("region")),
        )
        det, cor = cells_from_mapped_row(i, row, mapped, col_names)
        detected.update(det)
        corrected.update(cor)
    return detected, corrected
