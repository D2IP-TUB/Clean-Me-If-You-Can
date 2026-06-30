"""
Extract PostalAddress from WDC schema.org N-Quads (step 1 for WDC).

Reads N-Quads from:
- Sample files: wdc/sample/*.txt (e.g. LocalBusinesses.txt, Hospital.txt)
- Full data: directory produced by download_postal_subsets.py (e.g. data/wdc/LocalBusiness/part_*.gz)

Writes one .json.gz per input file under --out-dir, in the same format as the
WDC extract output (list of {data, crawl_metadata}) consumed by the validate step.

Usage:
  # From samples (e.g. wdc/sample/LocalBusinesses.txt)
  python -m postalcrawl.wdc.extract_main --input-dir ./wdc/sample --out-dir ./data/extracted_wdc

  # From full WDC download (data/wdc/LocalBusiness/part_0.gz, ...)
  python -m postalcrawl.wdc.extract_main --input-dir ./data/wdc --out-dir ./data/extracted_wdc

  # Single subset
  python -m postalcrawl.wdc.extract_main --input-dir ./data/wdc --out-dir ./data/extracted_wdc --subset LocalBusiness

  # Microformat html-mf-adr (e.g. from WDC format-specific downloads)
  python -m postalcrawl.wdc.extract_main --input-dir /path/to/micro-format --out-dir /path/to/micro-format-extracted --format vcard --jobs 8
"""

from __future__ import annotations

import argparse
from pathlib import Path

from loguru import logger
from tqdm import tqdm

import joblib
from postalcrawl.utils import write_to_jsongz
from postalcrawl.wdc.extract import extract_from_file


def _process_one(
    in_path: Path,
    out_path: Path,
    input_dir: Path,
    wdc_release: str,
    skip: bool,
    vocabulary: str = "schema",
) -> tuple[bool, str]:
    """Extract one file and write output. Returns (success, message)."""
    if skip and out_path.exists():
        return True, "skip"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        try:
            rel = in_path.relative_to(input_dir)
            source_file_str = str(rel)
            parts = rel.parts
            subset_name = parts[0] if len(parts) > 1 else in_path.stem
        except ValueError:
            source_file_str = str(in_path)
            subset_name = in_path.stem
        records = list(
            extract_from_file(
                in_path,
                subset=subset_name,
                source_file=source_file_str,
                wdc_release=wdc_release,
                vocabulary=vocabulary,
            )
        )
        if not records:
            return True, "empty"
        write_to_jsongz(records, out_path)  # type: ignore[arg-type]
        return True, str(len(records))
    except Exception as e:
        try:
            error_file = out_path.with_suffix(".error")
            with open(error_file, "w") as ef:
                ef.write(str(e))
        except Exception:
            pass
        return False, str(e)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract PostalAddress records from WDC N-Quads (step 1 for WDC).",
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        required=True,
        help="Directory containing WDC N-Quads: either subset subdirs (e.g. data/wdc with LocalBusiness/, Hospital/) or flat .txt/.gz files (e.g. wdc/sample/).",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        required=True,
        help="Directory to write extracted .json.gz files (structure mirrors input).",
    )
    parser.add_argument(
        "--subset",
        type=str,
        default=None,
        help="If set, only process this subset subdir (e.g. LocalBusiness).",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        default=True,
        help="Skip input files whose output .json.gz already exists (default: True).",
    )
    parser.add_argument(
        "--no-skip-existing",
        action="store_true",
        help="Re-extract even if output exists.",
    )
    parser.add_argument(
        "--wdc-release",
        type=str,
        default="2024-12",
        help="WDC release identifier for provenance (default: 2024-12).",
    )
    parser.add_argument(
        "--jobs",
        type=int,
        default=1,
        metavar="N",
        help="Number of files to process in parallel (default: 1). Use e.g. 8 or 16 for speed.",
    )
    parser.add_argument(
        "--format",
        choices=("schema", "vcard"),
        default="schema",
        help="Input format: schema = class-specific schema.org N-Quads (part_*.gz); vcard = html-mf-adr microformat N-Quads (*.nq-*.gz). Default: schema.",
    )
    args = parser.parse_args()

    skip = args.skip_existing and not args.no_skip_existing
    out_root = args.out_dir.resolve()
    out_root.mkdir(parents=True, exist_ok=True)

    input_dir = args.input_dir.resolve()
    if not input_dir.is_dir():
        logger.error(f"Not a directory: {input_dir}")
        return

    pairs: list[tuple[Path, Path]] = []
    vocabulary = args.format
    if vocabulary == "vcard":
        # Microformat html-mf-adr only: dpef.html-mf-adr.nq-00000.gz
        all_gz = list(input_dir.rglob("*.nq-*.gz"))
        all_txt = []
    else:
        # Schema.org: class-specific part_*.gz and format-specific *.nq-*.gz (html-microdata, html-embedded-jsonld, html-rdfa)
        part_gz = list(input_dir.rglob("part_*.gz"))
        nq_gz = [f for f in input_dir.rglob("*.nq-*.gz") if "mf-adr" not in f.name]
        all_gz = part_gz + nq_gz
        all_txt = list(input_dir.rglob("*.txt"))
    for f in sorted(set(all_gz)) + sorted(all_txt):
        if vocabulary == "vcard":
            pass  # already only *.nq-*.gz
        elif f.suffix != ".txt" and not (f.suffix == ".gz" and ("part_" in f.name or ".nq-" in f.name)):
            continue
        if args.subset is not None and args.subset not in f.parts:
            continue
        try:
            rel = f.relative_to(input_dir)
        except ValueError:
            continue
        out_name = f.with_suffix("").name + ".json.gz"
        out_path = out_root / rel.parent / out_name
        pairs.append((f, out_path))

    if not pairs:
        logger.warning(f"No N-Quads files found under {input_dir}")
        return

    logger.info(f"Processing {len(pairs)} file(s) with {args.jobs} job(s)...")

    if args.jobs <= 1:
        for in_path, out_path in tqdm(pairs):
            ok, msg = _process_one(in_path, out_path, input_dir, args.wdc_release, skip, vocabulary)
            if not ok:
                logger.error(f"Error {in_path}: {msg}")
            elif msg == "skip":
                pass
            elif msg != "empty":
                logger.info(f"Wrote {msg} records -> {out_path}")
    else:
        tasks = [
            joblib.delayed(_process_one)(in_path, out_path, input_dir, args.wdc_release, skip, vocabulary)
            for in_path, out_path in pairs
        ]
        results = joblib.Parallel(n_jobs=args.jobs, verbose=10, backend="loky")(
            tasks
        )
        for (in_path, out_path), (ok, msg) in zip(pairs, results):
            if not ok:
                logger.error(f"Error {in_path}: {msg}")
            elif msg not in ("skip", "empty"):
                logger.info(f"Wrote {msg} records -> {out_path}")
        written = sum(1 for ok, msg in results if ok and msg not in ("skip", "empty"))
        skipped = sum(1 for ok, msg in results if msg == "skip")
        logger.info(f"Done. Wrote {written} files, skipped {skipped} (existing).")
        return
    logger.info("Done.")


if __name__ == "__main__":
    main()
