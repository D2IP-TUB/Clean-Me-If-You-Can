"""Extract the UK slice and write the fixed clean localities.

    python3 uk_fix/run_uk.py
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

UK_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(UK_DIR))

import derive_os_open_names  # noqa: E402
import extract_uk_unique  # noqa: E402
import fix_uk_localities  # noqa: E402

logger = logging.getLogger("run_uk")

DERIVED_FILES = (
    "settlements.csv",
    "admin_units.csv",
    "postcode_to_place.csv",
)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=extract_uk_unique.DEFAULT_INPUT_DIR,
        help="directory with full_dirty.csv, full_clean.csv and cell_labels.csv",
    )
    parser.add_argument("--uk-dir", type=Path, default=UK_DIR)
    parser.add_argument(
        "--derive",
        action="store_true",
        help="rebuild the OS Open Names tables even when they already exist",
    )
    parser.add_argument(
        "--ni-placenames",
        type=Path,
        default=None,
        help="OSNI place-names CSV; default is the file beside the GeoPackage",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        stream=sys.stdout,
    )

    extract_uk_unique.main(
        [
            "--input-dir",
            str(args.input_dir),
            "--output-dir",
            str(args.uk_dir),
            "--prefix",
            "uk",
        ]
    )

    derived = args.uk_dir / "os_open_names" / "derived"
    missing = [name for name in DERIVED_FILES if not (derived / name).is_file()]
    if args.derive or missing:
        if missing and not args.derive:
            logger.info("gazetteer tables missing (%s); deriving them", ", ".join(missing))
        derive_os_open_names.main(
            [
                "--gpkg",
                str(args.uk_dir / "os_open_names" / "Data" / "opname_gb.gpkg"),
                "--out-dir",
                str(derived),
                "--clean",
                str(args.uk_dir / "uk_clean.csv"),
            ]
        )
    else:
        logger.info("using existing gazetteer tables in %s", derived)

    fix_args = [
        "--uk-dir",
        str(args.uk_dir),
        "--derived-dir",
        str(derived),
    ]
    if args.ni_placenames is not None:
        fix_args.extend(["--ni-placenames", str(args.ni_placenames)])
    fix_uk_localities.main(fix_args)
    logger.info(
        "done: %s and %s",
        args.uk_dir / "uk_clean_locality_fixed.csv",
        args.uk_dir / "locality_fix_decisions.csv",
    )


if __name__ == "__main__":
    main()
