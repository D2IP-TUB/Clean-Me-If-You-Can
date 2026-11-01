"""Extract unique UK address records from the full_named dataset.

Selects records whose *clean* country_code is "gb", deduplicates them on the
*dirty* address fields (ignoring id, name and provenance_graph_iri), and writes
the matching dirty rows, clean rows and cell labels to three CSV files.

Everything is read as strings so values such as postcodes and house numbers are
never coerced to numbers and empty cells stay empty instead of becoming NaN.
The written rows always carry the original raw values; normalization applies
only to the key used to compare addresses.
"""

import argparse
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent
DEFAULT_INPUT_DIR = DEFAULT_OUTPUT_DIR.parent / "full_named"

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

logger = logging.getLogger("extract_uk_unique")


def read_csv_as_strings(path, usecols=None):
    """Read a CSV keeping every value as the literal string from the file."""
    return pd.read_csv(
        path,
        dtype=str,
        keep_default_na=False,
        na_filter=False,
        usecols=usecols,
    )


def match_key(values, match_mode):
    """Normalize a column of address values for comparison purposes only."""
    if match_mode == "raw":
        return values
    key = values.str.replace(r"\s+", " ", regex=True).str.strip()
    if match_mode == "whitespace+case":
        key = key.str.casefold()
    return key


def select_rows(dirty, clean, country_code, match_mode):
    """Return the original row indices of unique dirty addresses for a country."""
    is_country = clean["country_code"].str.strip().str.lower() == country_code
    logger.info("records with clean country_code=%r: %d", country_code, int(is_country.sum()))

    candidates = dirty.loc[is_country, ADDRESS_FIELDS].apply(match_key, match_mode=match_mode)
    kept = candidates.drop_duplicates(keep="first").index
    logger.info(
        "unique dirty addresses (%s matching): %d (dropped %d duplicates)",
        match_mode,
        len(kept),
        int(is_country.sum()) - len(kept),
    )
    return kept.to_numpy()


def extract_cell_labels(path, kept_rows, n_records):
    """Stream the cell-label file and keep only the rows of the selected records."""
    new_index_of = np.full(n_records, -1, dtype=np.int64)
    new_index_of[kept_rows] = np.arange(len(kept_rows), dtype=np.int64)

    chunks = []
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
        new_index = new_index_of[chunk["row_index"].to_numpy(dtype=np.int64)]
        chunk = chunk.loc[new_index >= 0].copy()
        chunk.insert(1, "new_row_index", new_index[new_index >= 0])
        chunks.append(chunk)
        logger.info("cell_labels: scanned %d rows, kept %d so far", seen, sum(map(len, chunks)))

    labels = pd.concat(chunks, ignore_index=True)
    return labels.sort_values("new_row_index", kind="stable", ignore_index=True)


def warn_on_unexpected_label_counts(labels, n_kept):
    counts = labels["new_row_index"].value_counts()
    if len(counts) != n_kept:
        logger.warning(
            "%d of %d selected records have no cell labels", n_kept - len(counts), n_kept
        )
    if counts.nunique() > 1:
        logger.warning(
            "records have differing numbers of cell labels: %s",
            counts.value_counts().to_dict(),
        )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--country-code", default="gb")
    parser.add_argument("--prefix", default="uk", help="prefix for the output file names")
    parser.add_argument(
        "--match",
        choices=MATCH_MODES,
        default="whitespace",
        help="how address values are compared when deduplicating",
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

    country_code = args.country_code.strip().lower()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    logger.info("reading %s", args.input_dir / "full_dirty.csv")
    dirty = read_csv_as_strings(args.input_dir / "full_dirty.csv")
    logger.info("reading %s", args.input_dir / "full_clean.csv")
    clean = read_csv_as_strings(args.input_dir / "full_clean.csv")

    if len(dirty) != len(clean):
        raise ValueError(f"row count mismatch: dirty={len(dirty)} clean={len(clean)}")
    if not dirty["id"].equals(clean["id"]):
        raise ValueError("dirty and clean files are not aligned row by row on id")
    logger.info("loaded %d aligned records", len(dirty))

    kept_rows = select_rows(dirty, clean, country_code, args.match)
    if len(kept_rows) == 0:
        raise ValueError(f"no records found with clean country_code={country_code!r}")

    outputs = {
        f"{args.prefix}_dirty.csv": dirty.iloc[kept_rows],
        f"{args.prefix}_clean.csv": clean.iloc[kept_rows],
    }
    if not args.skip_cell_labels:
        logger.info("reading %s", args.input_dir / "cell_labels.csv")
        labels = extract_cell_labels(
            args.input_dir / "cell_labels.csv", kept_rows, n_records=len(dirty)
        )
        warn_on_unexpected_label_counts(labels, len(kept_rows))
        outputs[f"{args.prefix}_cell_labels.csv"] = labels
    for name, frame in outputs.items():
        path = args.output_dir / name
        frame.to_csv(path, index=False)
        logger.info("wrote %s (%d rows)", path, len(frame))


if __name__ == "__main__":
    main()
