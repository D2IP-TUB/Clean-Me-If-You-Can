"""Match extracted books to Open Library by ISBN.

Records with no ISBN, or no catalogue hit, are dropped.

Usage:
  python -m books.validate --dump-index data/openlibrary/openlibrary.sqlite
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

from loguru import logger
from tqdm import tqdm

from books.openlibrary import OpenLibraryDumpValidator, OpenLibraryValidator, ensure_string, normalize_isbn
from shared.io import project_root, read_from_jsongz, write_to_jsongz


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate extracted books with Open Library.")
    parser.add_argument("--input-dir", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--delay", type=float, default=0.25, help="Seconds between Open Library requests.")
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--skip-existing", action="store_true")
    parser.add_argument(
        "--file",
        type=Path,
        default=None,
        help="Validate a single extracted .json.gz instead of walking --input-dir.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Max records per file, or max ISBN lookups when --isbn-only.",
    )
    parser.add_argument(
        "--isbn-only",
        action="store_true",
        help="Only look up records that have an ISBN.",
    )
    parser.add_argument(
        "--dump-index",
        type=Path,
        default=None,
        help="SQLite index from `python -m books.index_dump`. Skips the live API.",
    )
    parser.add_argument(
        "--parts-only",
        action="store_true",
        help="Skip *_sample.json.gz files.",
    )
    args = parser.parse_args()

    extracted_root = (args.input_dir or (project_root() / "data" / "extracted")).resolve()
    output_dir = (args.output_dir or (project_root() / "data" / "validated")).resolve()
    if args.file is not None:
        files = [args.file.resolve()]
    else:
        files = sorted(extracted_root.glob("**/*.json.gz"))
    if not files:
        logger.error(f"No extracted .json.gz files under {extracted_root}")
        return

    if args.dump_index is not None:
        validator: OpenLibraryValidator = OpenLibraryDumpValidator(args.dump_index)
        args.delay = 0.0
        logger.info(f"Using dump index {args.dump_index}")
    else:
        validator = OpenLibraryValidator(timeout=args.timeout)
    for extract_file in files:
        try:
            rel = extract_file.relative_to(extracted_root)
        except ValueError:
            rel = Path(extract_file.name)
        outfile = output_dir / rel
        if args.skip_existing and outfile.exists():
            logger.info(f"Skip existing {outfile}")
            continue
        if args.parts_only and "part_" not in extract_file.name:
            continue
        records = read_from_jsongz(extract_file)
        if not isinstance(records, list):
            logger.error(f"Expected a list in {extract_file}")
            continue
        if args.limit is not None and not args.isbn_only:
            records = records[: args.limit]
        hits: list[dict] = []
        misses = 0
        lookups = 0
        for rec in tqdm(records, desc=extract_file.name[:48], unit="rec"):
            if args.isbn_only:
                isbn = ensure_string((rec.get("data") or {}).get("isbn")) or ensure_string(
                    (rec.get("data") or {}).get("gtin13")
                )
                if not normalize_isbn(isbn):
                    misses += 1
                    continue
            result = validator.record_query_validator(rec, isbn_only=args.isbn_only)
            lookups += 1
            if result is None:
                misses += 1
            else:
                hits.append(result)
            if args.delay:
                time.sleep(args.delay)
            if args.isbn_only and args.limit is not None and lookups >= args.limit:
                break
        write_to_jsongz(hits, outfile)
        logger.info(f"{extract_file.name}: {len(hits)} validated, {misses} dropped -> {outfile}")


if __name__ == "__main__":
    main()
