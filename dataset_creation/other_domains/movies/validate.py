"""Match extracted movies to IMDb by tt id.

Usage:
  python -m movies.validate --imdb-index data/imdb/imdb_index.sqlite
"""

from __future__ import annotations

import argparse
from pathlib import Path

from loguru import logger
from tqdm import tqdm

from movies.imdb_dataset import IMDbDatasetValidator
from shared.io import project_root, read_from_jsongz, write_to_jsongz
from shared.text import ensure_string


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate extracted movies with the IMDb dump.")
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=None,
        help="Root to walk for *.json.gz (default: data/extracted/Movie).",
    )
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument(
        "--imdb-index",
        type=Path,
        default=None,
        help="SQLite index from `python -m movies.index_imdb` (default: data/imdb/imdb_index.sqlite).",
    )
    parser.add_argument("--skip-existing", action="store_true")
    parser.add_argument(
        "--file",
        type=Path,
        default=None,
        help="Validate a single extracted .json.gz instead of walking --input-dir.",
    )
    parser.add_argument("--limit", type=int, default=None, help="Max records per file.")
    args = parser.parse_args()

    extracted_root = (args.input_dir or (project_root() / "data" / "extracted" / "Movie")).resolve()
    output_dir = (args.output_dir or (project_root() / "data" / "validated" / "Movie")).resolve()
    index = (args.imdb_index or (project_root() / "data" / "imdb" / "imdb_index.sqlite")).resolve()
    if not index.exists():
        logger.error(f"Missing IMDb index {index}. Run `python -m movies.index_imdb` first.")
        return
    if args.file is not None:
        files = [args.file.resolve()]
    else:
        files = sorted(extracted_root.glob("**/*.json.gz"))
    if not files:
        logger.error(f"No extracted .json.gz files under {extracted_root}")
        return

    validator = IMDbDatasetValidator(index)
    logger.info(f"Using IMDb index {index}")

    for extract_file in files:
        try:
            rel = extract_file.relative_to(extracted_root)
        except ValueError:
            rel = Path(extract_file.name)
        outfile = output_dir / rel
        if args.skip_existing and outfile.exists():
            logger.info(f"Skip existing {outfile}")
            continue
        records = read_from_jsongz(extract_file)
        if not isinstance(records, list):
            logger.error(f"Expected a list in {extract_file}")
            continue
        if args.limit is not None:
            records = records[: args.limit]

        hits: list[dict] = []
        skipped = 0
        kb_miss = 0
        match_counts: dict[str, int] = {}
        for rec in tqdm(records, desc=extract_file.name[:48], unit="rec"):
            data = rec.get("data") or {}
            if not ensure_string(data.get("name")):
                skipped += 1
                continue
            result = validator.movie_query_validator(rec)
            if result is None:
                kb_miss += 1
            else:
                hits.append(result)
                m = result["kb"].get("match", "unknown")
                match_counts[m] = match_counts.get(m, 0) + 1
        write_to_jsongz(hits, outfile)
        match_info = f" {match_counts}" if match_counts else ""
        logger.info(
            f"{extract_file.name}: {len(hits)} validated{match_info}, {skipped} no-title, "
            f"{kb_miss} kb-miss -> {outfile}"
        )


if __name__ == "__main__":
    main()
