#!/usr/bin/env python3
"""Score Canadian addresses against a local NAR index."""


from __future__ import annotations

import argparse
import csv
from collections import Counter
from pathlib import Path

from nar_join import join_from_index, load_query_rows, postal_code
from paths import INDEXES, RESULTS, SLICES


def fights_only(queries: list[dict]) -> list[dict]:
    out = []
    for q in queries:
        if postal_code(q.get("dirty_zip") or "") != postal_code(q.get("clean_zip") or ""):
            out.append(q)
    return out


def address_key(q: dict) -> tuple[str, ...]:
    return (
        postal_code(q.get("clean_zip") or ""),
        (q.get("house_number") or "").strip(),
        (q.get("road") or "").casefold().strip(),
        (q.get("locality") or "").casefold().strip(),
        q.get("state") or "",
    )


def unique_addresses(queries: list[dict]) -> list[dict]:
    """One row per clean house+street+city+province+LDU (drops id/name/url dupes)."""
    by: dict[tuple[str, ...], dict] = {}
    for q in queries:
        k = address_key(q)
        if k not in by:
            rec = dict(q)
            rec["n_dupes"] = 1
            rec["_dirty_pcs"] = {postal_code(q.get("dirty_zip") or "")}
            by[k] = rec
        else:
            by[k]["n_dupes"] += 1
            dz = postal_code(q.get("dirty_zip") or "")
            by[k]["_dirty_pcs"].add(dz)
            if dz and not postal_code(by[k].get("dirty_zip") or ""):
                by[k]["dirty_zip"] = q.get("dirty_zip") or ""
                by[k]["dirty_house"] = q.get("dirty_house") or by[k].get("dirty_house") or ""
                by[k]["dirty_road"] = q.get("dirty_road") or by[k].get("dirty_road") or ""
    out = []
    for rec in by.values():
        rec["n_dirty_zips"] = str(len(rec.pop("_dirty_pcs")))
        rec["n_dupes"] = str(rec["n_dupes"])
        out.append(rec)
    return out


def kind(row: dict) -> str:
    d, c = postal_code(row.get("dirty_zip") or ""), postal_code(row.get("clean_zip") or "")
    if not d:
        return "dirty_blank"
    if d == c:
        return "agree"
    return "both_differ"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--dirty", default=str(SLICES / "slice_ca_dirty.csv"))
    p.add_argument("--clean", default=str(SLICES / "slice_ca_clean.csv"))
    p.add_argument("--nar-index", default=str(INDEXES / "nar_ca.sqlite"))
    p.add_argument("--out", default="")
    p.add_argument(
        "--unique-address",
        action="store_true",
        help="Dedupe to unique clean house+street+city+province+LDU; score all of them",
    )
    p.add_argument(
        "--fights-only",
        action="store_true",
        help="Keep only dirty PC <> clean PC (blank vs a code counts)",
    )
    args = p.parse_args()
    if args.unique_address and args.fights_only:
        raise SystemExit("use --unique-address or --fights-only, not both")
    out_path = Path(
        args.out
        or (
            RESULTS / "unique_nar.csv"
            if args.unique_address
            else RESULTS / "nar_fights.csv"
            if args.fights_only
            else RESULTS / "nar_ca.csv"
        )
    )

    queries = load_query_rows(Path(args.dirty), Path(args.clean))
    print(f"joinable CA rows (house+street): {len(queries)}", flush=True)
    if args.unique_address:
        queries = unique_addresses(queries)
        print(f"unique clean addresses: {len(queries)}", flush=True)
    elif args.fights_only:
        queries = fights_only(queries)
        print(f"PC fights: {len(queries)}", flush=True)

    print(f"joining NAR {args.nar_index}...", flush=True)
    nar_rows = join_from_index(
        queries,
        Path(args.nar_index),
        unique_zip_fallback=True,
        dirty_retry=True,
    )

    out_rows = []
    for nar in nar_rows:
        rec = {
            "id": nar["id"],
            "name": nar["name"],
            "state": nar["state"],
            "kind": kind(nar),
            "dirty_pc": postal_code(nar["dirty_zip"]),
            "clean_pc": postal_code(nar["clean_zip"]),
            "n_dupes": nar.get("n_dupes") or "1",
            "n_dirty_zips": nar.get("n_dirty_zips") or "1",
            "nar_pcs": nar["nar_pcs"],
            "n_nar_pcs": nar.get("n_nar_pcs") or "0",
            "match_method": nar.get("match_method") or "",
            "nar_decision": nar["decision"],
        }
        out_rows.append(rec)

    fields = [
        "id", "name", "state", "kind", "dirty_pc", "clean_pc",
        "n_dupes", "n_dirty_zips", "nar_pcs", "n_nar_pcs", "match_method",
        "nar_decision",
    ]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(out_rows)
    print(f"wrote {out_path} ({len(out_rows)} rows)", flush=True)

    print("\nkind:")
    for k, n in Counter(r["kind"] for r in out_rows).most_common():
        print(f"  {k:14} {n}")
    print("\nNAR by kind x decision:")
    for k, n in Counter((r["kind"], r["nar_decision"]) for r in out_rows).most_common():
        print(f"  {k[0]:14} {k[1]:12} {n}")
    print("\nmatch_method:")
    for k, n in Counter(r["match_method"] or "(none)" for r in out_rows).most_common():
        print(f"  {k:18} {n}")
    print("\nNAR:")
    for k, n in Counter(r["nar_decision"] for r in out_rows).most_common():
        print(f"  {k:12} {n}")
    fights = [r for r in out_rows if r["kind"] != "agree"]
    exact = [r for r in out_rows if r["match_method"] == "exact"]
    exact_fights = [r for r in exact if r["kind"] != "agree"]
    if fights and len(fights) != len(out_rows):
        scored = sum(1 for r in fights if r["nar_decision"] in {"keep_clean", "keep_dirty"})
        print(f"\nPC fights: {len(fights)}")
        print("NAR fights (all methods):")
        for k, n in Counter(r["nar_decision"] for r in fights).most_common():
            print(f"  {k:12} {n}")
        print(f"  keep_*      {scored} ({100.0 * scored / len(fights):.1f}%)")
    if exact_fights:
        scored_e = sum(
            1 for r in exact_fights if r["nar_decision"] in {"keep_clean", "keep_dirty"}
        )
        print(f"\nHeadline (match_method=exact) fights: {len(exact_fights)}")
        print("NAR exact fights:")
        for k, n in Counter(r["nar_decision"] for r in exact_fights).most_common():
            print(f"  {k:12} {n}")
        print(
            f"  keep_*      {scored_e} ({100.0 * scored_e / len(exact_fights):.1f}%)"
        )
        print("\nHeadline (match_method=exact) all kinds:")
        for k, n in Counter(r["nar_decision"] for r in exact).most_common():
            print(f"  {k:12} {n}")


if __name__ == "__main__":
    main()
