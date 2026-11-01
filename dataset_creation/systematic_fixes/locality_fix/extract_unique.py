"""Extract unique addresses per country from full_named in one pass.

Reads full_dirty.csv / full_clean.csv once, then streams cell_labels.csv once,
and writes {prefix}_dirty.csv, {prefix}_clean.csv, {prefix}_cell_labels.csv
into each country output directory.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from io_csv import read_csv_as_strings  # noqa: E402

DEFAULT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT_DIR = DEFAULT_ROOT / "full_named"

ADDRESS_FIELDS = [
    "road",
    "house_number",
    "postcode",
    "locality",
    "region",
    "country",
    "country_code",
]
CELL_LABELS_CHUNK_SIZE = 2_000_000
MATCH_MODES = ("whitespace", "raw", "whitespace+case")

DEFAULT_COUNTRIES = (
    ("gb", "uk", "uk_fix"),
    ("fr", "fr", "fr_fix"),
    ("es", "es", "es_fix"),
    ("au", "au", "au_fix"),
)

logger = logging.getLogger("extract_unique")


def match_key(values: pd.Series, match_mode: str) -> pd.Series:
    if match_mode == "raw":
        return values
    key = values.str.replace(r"\s+", " ", regex=True).str.strip()
    if match_mode == "whitespace+case":
        key = key.str.casefold()
    return key


def select_rows(dirty: pd.DataFrame, clean: pd.DataFrame, country_code: str, match_mode: str):
    is_country = clean["country_code"].str.strip().str.lower() == country_code
    logger.info("records with clean country_code=%r: %d", country_code, int(is_country.sum()))
    candidates = dirty.loc[is_country, ADDRESS_FIELDS].apply(match_key, match_mode=match_mode)
    kept = candidates.drop_duplicates(keep="first").index
    logger.info(
        "unique dirty addresses (%s matching) for %s: %d (dropped %d duplicates)",
        match_mode,
        country_code,
        len(kept),
        int(is_country.sum()) - len(kept),
    )
    return kept.to_numpy()


def extract_cell_labels(path: Path, country_kept: dict[str, np.ndarray], n_records: int):
    """Return {country: labels_df} keeping only selected record rows."""
    maps = {}
    for code, kept in country_kept.items():
        idx = np.full(n_records, -1, dtype=np.int64)
        if len(kept):
            idx[kept] = np.arange(len(kept), dtype=np.int64)
        maps[code] = idx

    chunks = {code: [] for code in country_kept}
    seen = 0
    reader = pd.read_csv(
        path,
        dtype=str,
        keep_default_na=False,
        na_filter=False,
        chunksize=CELL_LABELS_CHUNK_SIZE,
    )
    for chunk in reader:
        seen += len(chunk)
        orig = chunk["row_index"].to_numpy(dtype=np.int64)
        for code, idxmap in maps.items():
            new_index = idxmap[orig]
            keep = new_index >= 0
            if not keep.any():
                continue
            part = chunk.loc[keep].copy()
            part.insert(1, "new_row_index", new_index[keep])
            chunks[code].append(part)
        logger.info("cell_labels: scanned %d rows", seen)

    out = {}
    for code, parts in chunks.items():
        if parts:
            labels = pd.concat(parts, ignore_index=True)
            labels = labels.sort_values("new_row_index", kind="stable", ignore_index=True)
        else:
            labels = pd.DataFrame()
        out[code] = labels
        logger.info("cell_labels for %s: %d rows", code, len(labels))
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument(
        "--countries",
        default="fr,es,au",
        help="comma-separated ISO country_code values (clean side)",
    )
    parser.add_argument(
        "--match",
        choices=MATCH_MODES,
        default="whitespace",
    )
    parser.add_argument(
        "--skip-cell-labels",
        action="store_true",
        help="only write dirty/clean extracts",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        stream=sys.stdout,
    )

    wanted = [c.strip().lower() for c in args.countries.split(",") if c.strip()]
    jobs = []
    for code, prefix, folder in DEFAULT_COUNTRIES:
        if code in wanted:
            jobs.append((code, prefix, args.root / folder))
    extra = [c for c in wanted if c not in {j[0] for j in jobs}]
    for code in extra:
        jobs.append((code, code, args.root / f"{code}_fix"))

    logger.info("reading %s", args.input_dir / "full_dirty.csv")
    dirty = read_csv_as_strings(args.input_dir / "full_dirty.csv")
    logger.info("reading %s", args.input_dir / "full_clean.csv")
    clean = read_csv_as_strings(args.input_dir / "full_clean.csv")
    if len(dirty) != len(clean):
        raise ValueError(f"row count mismatch: dirty={len(dirty)} clean={len(clean)}")
    if not dirty["id"].equals(clean["id"]):
        raise ValueError("dirty and clean files are not aligned row by row on id")
    logger.info("loaded %d aligned records", len(dirty))

    kept = {}
    for code, prefix, out_dir in jobs:
        out_dir.mkdir(parents=True, exist_ok=True)
        rows = select_rows(dirty, clean, code, args.match)
        if len(rows) == 0:
            logger.warning("no records for country_code=%r", code)
        kept[code] = rows
        dirty.iloc[rows].to_csv(out_dir / f"{prefix}_dirty.csv", index=False)
        clean.iloc[rows].to_csv(out_dir / f"{prefix}_clean.csv", index=False)
        logger.info("wrote %s (%d rows)", out_dir / f"{prefix}_clean.csv", len(rows))

    if args.skip_cell_labels:
        return

    labels_by = extract_cell_labels(
        args.input_dir / "cell_labels.csv",
        {code: kept[code] for code, _, _ in jobs},
        n_records=len(dirty),
    )
    for code, prefix, out_dir in jobs:
        path = out_dir / f"{prefix}_cell_labels.csv"
        labels_by[code].to_csv(path, index=False)
        logger.info("wrote %s (%d rows)", path, len(labels_by[code]))


if __name__ == "__main__":
    main()
