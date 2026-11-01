#!/usr/bin/env python3
"""Score US addresses against a local NAD index."""


from __future__ import annotations

import argparse
import csv
from collections import Counter
from pathlib import Path

from nad_join import join_from_index, load_query_rows, zip5
from paths import INDEXES, RESULTS, SLICES


def fights_only(queries: list[dict]) -> list[dict]:
    out = []
    for q in queries:
        if zip5(q.get("dirty_zip") or "") != zip5(q.get("clean_zip") or ""):
            out.append(q)
    return out


def address_key(q: dict) -> tuple[str, ...]:
    return (
        zip5(q.get("clean_zip") or ""),
        (q.get("house_number") or "").strip(),
        (q.get("road") or "").casefold().strip(),
        (q.get("locality") or "").casefold().strip(),
        q.get("state") or "",
    )


def unique_addresses(queries: list[dict]) -> list[dict]:
    """One row per clean house+street+city+state+ZIP (drops id/name/url dupes)."""
    by: dict[tuple[str, ...], dict] = {}
    for q in queries:
        k = address_key(q)
        if k not in by:
            rec = dict(q)
            rec["n_dupes"] = 1
            rec["_dirty_zips"] = {zip5(q.get("dirty_zip") or "")}
            by[k] = rec
        else:
            by[k]["n_dupes"] += 1
            dz = zip5(q.get("dirty_zip") or "")
            by[k]["_dirty_zips"].add(dz)
            if dz and not zip5(by[k].get("dirty_zip") or ""):
                by[k]["dirty_zip"] = q.get("dirty_zip") or ""
                by[k]["dirty_house"] = q.get("dirty_house") or by[k].get("dirty_house") or ""
                by[k]["dirty_road"] = q.get("dirty_road") or by[k].get("dirty_road") or ""
    out = []
    for rec in by.values():
        rec["n_dirty_zips"] = str(len(rec.pop("_dirty_zips")))
        rec["n_dupes"] = str(rec["n_dupes"])
        out.append(rec)
    return out


def kind(row: dict) -> str:
    d, c = zip5(row.get("dirty_zip") or ""), zip5(row.get("clean_zip") or "")
    if not d:
        return "dirty_blank"
    if d == c:
        return "agree"
    return "both_differ"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--dirty", default=str(SLICES / "slice_us_dirty.csv"))
    p.add_argument("--clean", default=str(SLICES / "slice_us_clean.csv"))
    p.add_argument("--nad-index", default=str(INDEXES / "nad_us.sqlite"))
    p.add_argument("--out", default="")
    p.add_argument(
        "--unique-address",
        action="store_true",
        help="Dedupe to unique clean house+street+city+state+ZIP; score all of them",
    )
    p.add_argument(
        "--fights-only",
        action="store_true",
        help="Keep only dirty ZIP5 <> clean ZIP5 (blank vs a ZIP counts)",
    )
    args = p.parse_args()
    if args.unique_address and args.fights_only:
        raise SystemExit("use --unique-address or --fights-only, not both")
    out_path = Path(
        args.out
        or (
            RESULTS / "unique_nad.csv"
            if args.unique_address
            else RESULTS / "nad_fights.csv"
            if args.fights_only
            else RESULTS / "nad_us.csv"
        )
    )

    queries = load_query_rows(Path(args.dirty), Path(args.clean))
    print(f"joinable US rows (house+street): {len(queries)}", flush=True)
    if args.unique_address:
        queries = unique_addresses(queries)
        print(f"unique clean addresses: {len(queries)}", flush=True)
    elif args.fights_only:
        queries = fights_only(queries)
        print(f"ZIP fights: {len(queries)}", flush=True)

    print(f"joining NAD {args.nad_index}...", flush=True)
    nad_rows = join_from_index(
        queries,
        Path(args.nad_index),
        unique_zip_fallback=True,
        dirty_retry=True,
    )

    out_rows = []
    for nad in nad_rows:
        rec = {
            "id": nad["id"],
            "name": nad["name"],
            "state": nad["state"],
            "kind": kind(nad),
            "dirty_zip": zip5(nad["dirty_zip"]),
            "clean_zip": zip5(nad["clean_zip"]),
            "n_dupes": nad.get("n_dupes") or "1",
            "n_dirty_zips": nad.get("n_dirty_zips") or "1",
            "nad_zips": nad["nad_zips"],
            "n_nad_zips": nad.get("n_nad_zips") or "0",
            "match_method": nad.get("match_method") or "",
            "nad_decision": nad["decision"],
        }
        out_rows.append(rec)

    fields = [
        "id", "name", "state", "kind", "dirty_zip", "clean_zip",
        "n_dupes", "n_dirty_zips", "nad_zips", "n_nad_zips", "match_method",
        "nad_decision",
    ]
    with out_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(out_rows)
    print(f"wrote {out_path} ({len(out_rows)} rows)", flush=True)

    print("\nkind:")
    for k, n in Counter(r["kind"] for r in out_rows).most_common():
        print(f"  {k:14} {n}")
    print("\nNAD by kind x decision:")
    for k, n in Counter((r["kind"], r["nad_decision"]) for r in out_rows).most_common():
        print(f"  {k[0]:14} {k[1]:12} {n}")
    print("\nmatch_method:")
    for k, n in Counter(r["match_method"] or "(none)" for r in out_rows).most_common():
        print(f"  {k:18} {n}")
    print("\nNAD:")
    for k, n in Counter(r["nad_decision"] for r in out_rows).most_common():
        print(f"  {k:12} {n}")
    fights = [r for r in out_rows if r["kind"] != "agree"]
    exact = [r for r in out_rows if r["match_method"] == "exact"]
    exact_fights = [r for r in exact if r["kind"] != "agree"]
    if fights and len(fights) != len(out_rows):
        scored = sum(1 for r in fights if r["nad_decision"] in {"keep_clean", "keep_dirty"})
        print(f"\nZIP fights: {len(fights)}")
        print("NAD fights (all methods):")
        for k, n in Counter(r["nad_decision"] for r in fights).most_common():
            print(f"  {k:12} {n}")
        print(f"  keep_*      {scored} ({100.0 * scored / len(fights):.1f}%)")
    if exact_fights:
        scored_e = sum(
            1 for r in exact_fights if r["nad_decision"] in {"keep_clean", "keep_dirty"}
        )
        print(f"\nHeadline (match_method=exact) fights: {len(exact_fights)}")
        print("NAD exact fights:")
        for k, n in Counter(r["nad_decision"] for r in exact_fights).most_common():
            print(f"  {k:12} {n}")
        print(
            f"  keep_*      {scored_e} ({100.0 * scored_e / len(exact_fights):.1f}%)"
        )
        print("\nHeadline (match_method=exact) all kinds:")
        for k, n in Counter(r["nad_decision"] for r in exact).most_common():
            print(f"  {k:12} {n}")


if __name__ == "__main__":
    main()
