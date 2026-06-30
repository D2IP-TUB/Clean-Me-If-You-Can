#!/usr/bin/env python3
"""
Address Validation Pipeline — Nominatim / OpenStreetMap

Uses the public Nominatim API (nominatim.openstreetmap.org) backed by the
OpenStreetMap planet dataset (~900 million POIs + addresses).

No API key required.  Rate limit: ≤1 request/second (enforced by pipeline).
Terms of use: https://operations.osmfoundation.org/policies/nominatim/

Structured search parameters:
  amenity, street, city, state, country, postalcode

Response format: geocodejson (RFC draft)

Usage
-----
    python nominatim_validate.py --csv ../datasets/stratified_sample_~1000.csv --limit 10
    python nominatim_validate.py --csv ../datasets/stratified_sample_~1000.csv
"""

import csv
import json
import time
import re
import unicodedata
import argparse
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime

try:
    import requests
except ImportError:
    print("❌  requests is required.  Run:  pip install requests")
    sys.exit(1)

try:
    from rapidfuzz import fuzz
except ImportError:
    print("❌  rapidfuzz is required.  Run:  pip install rapidfuzz")
    sys.exit(1)


# ============================================================================
# Configuration
# ============================================================================

NOMINATIM_BASE = "https://nominatim.openstreetmap.org/search"
USER_AGENT     = "address-validation-research/1.0 (academic; contact: research@tu-berlin.de)"
RATE_LIMIT_S   = 1.05   # seconds between requests (OSM ToS: max 1 req/s)
MAX_RETRIES    = 3
RETRY_BACKOFF  = 2.0    # seconds, doubled each retry

SCORE_VALID    = 85
SCORE_REVIEW   = 60


# ============================================================================
# HTTP query
# ============================================================================

_session = requests.Session()
_session.headers.update({"User-Agent": USER_AGENT})
_last_request_time = 0.0


def _rate_limited_get(params: Dict) -> Optional[Dict]:
    """GET with rate limiting and retry logic. Returns parsed JSON or None."""
    global _last_request_time
    elapsed = time.time() - _last_request_time
    if elapsed < RATE_LIMIT_S:
        time.sleep(RATE_LIMIT_S - elapsed)

    for attempt in range(MAX_RETRIES):
        try:
            _last_request_time = time.time()
            resp = _session.get(NOMINATIM_BASE, params=params, timeout=15)
            if resp.status_code == 429:
                wait = RETRY_BACKOFF * (2 ** attempt)
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.Timeout:
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_BACKOFF * (attempt + 1))
        except requests.exceptions.RequestException:
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_BACKOFF * (attempt + 1))
    return None


def query_nominatim(row: Dict) -> Tuple[Optional[Dict], str]:
    """
    Query Nominatim with structured address parameters.

    Strategy:
      Pass 1 — structured: street + city + country + postalcode (most precise)
      Pass 2 — free-text:  full address string (fallback when structured fails)

    Returns (geocoding_properties_dict, pass_label) or (None, 'no_result').
    """
    cc  = row.get("country_code", "").lower()
    hn  = row.get("house_number", "").strip()
    rd  = row.get("road", "").strip()
    pc  = row.get("postcode", "").strip()
    loc = row.get("locality", "").strip()
    reg = row.get("region", "").strip()
    ctr = row.get("country", "").strip()

    street = f"{hn} {rd}".strip() if hn else rd

    base_params = {
        "format":         "geocodejson",
        "addressdetails": 1,
        "limit":          1,
    }

    # Pass 1: fully structured
    p1 = dict(base_params)
    if street: p1["street"]     = street
    if pc:     p1["postalcode"] = pc
    if loc:    p1["city"]       = loc
    if reg:    p1["state"]      = reg
    if cc:     p1["countrycodes"] = cc   # ISO 3166-1 alpha-2 filter

    data = _rate_limited_get(p1)
    if data and data.get("features"):
        feat = data["features"][0]
        geo  = feat["properties"].get("geocoding", {})
        coords = feat.get("geometry", {}).get("coordinates", [])
        if len(coords) >= 2:
            geo["_lon"], geo["_lat"] = coords[0], coords[1]
        return geo, "structured"

    # Pass 2: free-text fallback
    parts = []
    if street: parts.append(street)
    if loc:    parts.append(loc)
    if reg:    parts.append(reg)
    if pc:     parts.append(pc)
    if ctr:    parts.append(ctr)
    q = ", ".join(parts)

    p2 = dict(base_params)
    p2["q"]            = q
    p2["countrycodes"] = cc

    data = _rate_limited_get(p2)
    if data and data.get("features"):
        feat = data["features"][0]
        geo  = feat["properties"].get("geocoding", {})
        coords = feat.get("geometry", {}).get("coordinates", [])
        if len(coords) >= 2:
            geo["_lon"], geo["_lat"] = coords[0], coords[1]
        return geo, "freetext"

    return None, "no_result"


# ============================================================================
# Text normalisation helpers
# ============================================================================

def _norm(s: str) -> str:
    if not s:
        return ""
    s = unicodedata.normalize("NFD", s.lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


_STREET_PREFIXES = re.compile(
    r"^(?:ulica|ul|aleje|al|rue|avenue|av|ave|via|calle|strasse|str|"
    r"straat|gata|gatan|vei|veien|rua|avenida|strada|"
    r"boulevard|blvd|drive|dr|road|rd|lane|ln|court|ct|place|pl|"
    r"way|weg|path|row|square|sq|park|terrace|ter)\s+",
    re.IGNORECASE,
)


def _norm_street(s: str) -> str:
    n = _norm(s)
    return _STREET_PREFIXES.sub("", n).strip()


def _strip_hn(hn: str) -> str:
    if not hn:
        return ""
    digits = re.sub(r"\D.*", "", hn.strip())
    return digits if digits else hn.lower().strip()


# ============================================================================
# Scoring
# ============================================================================

def score_result(geo: Dict, row: Dict) -> Tuple[float, List[str]]:
    """
    Score a Nominatim geocodejson result 0–100.
    Weights: house_number=35, street=40, postcode=15, city=10.
    """
    issues: List[str] = []

    # --- House number ---
    inp_hn  = _strip_hn(row.get("house_number", ""))
    cand_hn = _strip_hn(str(geo.get("housenumber") or ""))

    if not inp_hn:
        hn_score = 100
    elif inp_hn and cand_hn:
        hn_score = 100 if inp_hn == cand_hn else 0
        if hn_score == 0:
            issues.append(f"house_number_mismatch:{inp_hn}!={cand_hn}")
    else:
        hn_score = 50
        issues.append("house_number_not_in_osm")

    # --- Street ---
    inp_st  = _norm_street(row.get("road", ""))
    cand_st = _norm_street(str(geo.get("street") or ""))
    st_score = fuzz.token_sort_ratio(inp_st, cand_st) if inp_st and cand_st else 0
    if st_score < 70:
        issues.append(f"street_mismatch:{st_score:.0f}")

    # --- Postcode ---
    inp_pc  = _norm(row.get("postcode", ""))
    cand_pc = _norm(str(geo.get("postcode") or ""))
    if inp_pc and cand_pc:
        if inp_pc == cand_pc:
            pc_score = 100
        elif inp_pc[:3] == cand_pc[:3]:
            pc_score = 50
            issues.append(f"postcode_partial:{inp_pc}~{cand_pc}")
        else:
            pc_score = 0
            issues.append(f"postcode_mismatch:{inp_pc}!={cand_pc}")
    else:
        pc_score = 100

    # --- City ---
    inp_city  = _norm(row.get("locality", ""))
    cand_city = _norm(str(geo.get("city") or geo.get("locality") or geo.get("district") or ""))
    city_score = fuzz.token_sort_ratio(inp_city, cand_city) if inp_city and cand_city else 100

    total = hn_score * 0.35 + st_score * 0.40 + pc_score * 0.15 + city_score * 0.10
    return round(total, 1), issues


def _score_to_status(score: float, issues: List[str]) -> str:
    blocking_hn = "house_number_mismatch" in " ".join(issues)
    if score >= SCORE_VALID and not blocking_hn:
        return "VALID"
    elif score >= SCORE_REVIEW:
        return "REVIEW"
    return "INVALID"


# ============================================================================
# Helpers
# ============================================================================

def build_address_string(row: Dict) -> str:
    parts = []
    if row.get("house_number") and row.get("road"):
        parts.append(f"{row['house_number']} {row['road']}")
    elif row.get("road"):
        parts.append(row["road"])
    for f in ("locality", "region", "postcode", "country"):
        if row.get(f):
            parts.append(row[f])
    return ", ".join(parts)


def _format_result(geo: Dict) -> str:
    parts = []
    for f in ("housenumber", "street"):
        if geo.get(f):
            parts.append(str(geo[f]))
    city = geo.get("city") or geo.get("locality") or geo.get("district") or ""
    if city:
        parts.append(city)
    if geo.get("postcode"):
        parts.append(str(geo["postcode"]))
    return ", ".join(parts)


def _osm_type_label(geo: Dict) -> str:
    """Map OSM type/key to a granularity label."""
    t = geo.get("type", "")
    k = geo.get("osm_key", "")
    v = geo.get("osm_value", "")
    if t in ("house", "building") or (k == "building" and geo.get("housenumber")):
        return "PREMISE"
    if t in ("street", "road") or k in ("highway", "street"):
        return "ROUTE"
    if t in ("city", "village", "suburb", "neighbourhood", "postcode"):
        return "LOCALITY"
    if geo.get("housenumber"):
        return "PREMISE"
    if geo.get("street"):
        return "ROUTE"
    return "LOCALITY"


# ============================================================================
# Main Pipeline
# ============================================================================

def validate_addresses(csv_path: str, limit: Optional[int] = None, output_dir: str = "output"):
    csv_path = Path(csv_path)
    if not csv_path.exists():
        print(f"❌  File not found: {csv_path}")
        sys.exit(1)

    base_output = Path(output_dir)
    base_output.mkdir(exist_ok=True)
    timestamp  = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_folder = base_output / f"run_{timestamp}-nominatim"
    run_folder.mkdir(exist_ok=True)

    output_csv     = run_folder / "validated.csv"
    output_json    = run_folder / "api_responses.json"
    output_summary = run_folder / "summary.txt"

    print("\n" + "=" * 80)
    print("ADDRESS VALIDATION PIPELINE  [Nominatim / OpenStreetMap]")
    print("=" * 80)
    print(f"API:           {NOMINATIM_BASE}")
    print(f"Input file:    {csv_path}")
    print(f"Output folder: {run_folder}")
    print(f"Limit:         {limit if limit else 'All records'}")
    print(f"Rate limit:    {RATE_LIMIT_S}s between requests")
    print("=" * 80 + "\n")

    print("📖 Reading addresses...")
    addresses = []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for idx, row in enumerate(reader):
            if limit and idx >= limit:
                break
            addresses.append(row)
    print(f"✓ Loaded {len(addresses)} addresses\n")

    results   = []
    query_log = []
    stats     = {"VALID": 0, "REVIEW": 0, "INVALID": 0, "ERROR": 0}

    est_minutes = len(addresses) * RATE_LIMIT_S / 60
    print(f"⏱  Estimated run time: ~{est_minutes:.0f} minutes at {RATE_LIMIT_S}s/request\n")
    print("🔍 Validating addresses...\n")

    for idx, row in enumerate(addresses, 1):
        name = row.get("name", "Unknown")[:40]
        print(f"[{idx:4d}/{len(addresses)}] {name:<40}", end=" ", flush=True)

        address_str  = build_address_string(row)
        country_code = row.get("country_code", "").upper()

        result = {
            "id": row.get("_id", ""), "name": row.get("name", ""),
            "original_address": address_str, "country_code": country_code,
            "status": "ERROR", "formatted_address": "", "granularity": "",
            "osm_type": "", "osm_id": "",
            "latitude": "", "longitude": "", "complete": False, "issues": [],
        }

        geo, query_pass = query_nominatim(row)

        if geo is None:
            result["status"] = "INVALID"
            result["issues"].append("no_result_from_nominatim")
            stats["INVALID"] += 1
            print(f"❌ INVALID (no result, pass={query_pass})")
        else:
            score, issues = score_result(geo, row)
            status = _score_to_status(score, issues)

            result["status"]            = status
            result["formatted_address"] = _format_result(geo)
            result["granularity"]       = _osm_type_label(geo)
            result["osm_type"]          = geo.get("osm_type", "")
            result["osm_id"]            = str(geo.get("osm_id", ""))
            result["complete"]          = (status == "VALID")
            result["latitude"]          = geo.get("_lat", "")
            result["longitude"]         = geo.get("_lon", "")
            if score < 100:
                result["issues"].append(f"confidence:{score / 100:.2f}")
            result["issues"].extend(issues)

            # Try to get lat/lon from the feature geometry
            # (geocodejson stores it in geometry.coordinates)
            stats[status] += 1

            emoji = {"VALID": "✅", "REVIEW": "⚠️ ", "INVALID": "❌"}
            print(f"{emoji[status]} {status} (score={score:.0f}, pass={query_pass}, type={result['granularity']})")

        query_log.append({
            "record_id":   row.get("_id", ""),
            "record_name": row.get("name", ""),
            "input":       address_str,
            "country_code": country_code,
            "query_pass":  query_pass,
            "osm_type":    geo.get("osm_type", "") if geo else "",
            "osm_key":     geo.get("osm_key", "")  if geo else "",
            "osm_value":   geo.get("osm_value", "") if geo else "",
            "best_score":  score if geo else 0.0,
            "best_match":  _format_result(geo) if geo else None,
            "label":       geo.get("label", "") if geo else "",
        })

        results.append(result)

    # ── Save outputs ──────────────────────────────────────────────────────────

    print(f"\n💾 Saving query log  → {output_json}")
    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(query_log, f, indent=2, ensure_ascii=False)

    print(f"💾 Saving CSV results → {output_csv}")
    fieldnames = ["id", "name", "original_address", "country_code", "status",
                  "formatted_address", "granularity", "osm_type", "osm_id",
                  "latitude", "longitude", "complete", "issues"]
    with open(output_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in results:
            r["issues"] = "; ".join(r["issues"]) if r["issues"] else "none"
            writer.writerow(r)

    total      = len(results)
    n_complete = sum(1 for r in results if r["complete"])

    summary_text = f"""
{'='*80}
VALIDATION SUMMARY  [Nominatim / OpenStreetMap]
{'='*80}

API:                {NOMINATIM_BASE}
Total Processed:    {total}
✅ Valid:           {stats['VALID']:4d} ({stats['VALID']/total*100:.1f}%)
⚠️  Needs Review:   {stats['REVIEW']:4d} ({stats['REVIEW']/total*100:.1f}%)
❌ Invalid:         {stats['INVALID']:4d} ({stats['INVALID']/total*100:.1f}%)
🔴 Errors:          {stats['ERROR']:4d} ({stats['ERROR']/total*100:.1f}%)

Complete Addresses: {n_complete} ({n_complete/total*100:.1f}%)

Validation method:  Nominatim structured + freetext geocoding + local fuzzy match
Match thresholds:   VALID >= {SCORE_VALID}/100  |  REVIEW >= {SCORE_REVIEW}/100
Rate limit:         {RATE_LIMIT_S}s per request (OSM ToS compliance)
Data source:        OpenStreetMap (nominatim.openstreetmap.org)

Output Files:
  * CSV:      {output_csv}
  * JSON:     {output_json}
  * Summary:  {output_summary}

{'='*80}
"""
    print(summary_text)
    with open(output_summary, "w", encoding="utf-8") as f:
        f.write(summary_text)
        f.write("\n\nDETAILED RESULTS:\n" + "=" * 80 + "\n\n")
        for r in results:
            f.write(f"[{r['id']}] {r['name']}\n")
            f.write(f"  Status:    {r['status']} ({r['granularity']})\n")
            f.write(f"  Original:  {r['original_address']}\n")
            f.write(f"  Matched:   {r['formatted_address']}\n")
            if r["osm_type"]:
                f.write(f"  OSM:       {r['osm_type']}/{r['osm_id']}\n")
            if r["issues"] and r["issues"] != "none":
                f.write(f"  Issues:    {r['issues']}\n")
            f.write("\n")

    print(f"✅ Done!  Results in:  {run_folder}\n")


# ============================================================================
# CLI
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Validate addresses against Nominatim/OpenStreetMap (free, no API key, 1 req/s)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python nominatim_validate.py --csv ../datasets/stratified_sample_~1000.csv --limit 20
  python nominatim_validate.py --csv ../datasets/stratified_sample_~1000.csv
        """,
    )
    parser.add_argument("--csv",    type=str, required=True)
    parser.add_argument("--limit",  type=int, default=None)
    parser.add_argument("--output", type=str, default="output")
    args = parser.parse_args()
    validate_addresses(csv_path=args.csv, limit=args.limit, output_dir=args.output)


if __name__ == "__main__":
    main()
