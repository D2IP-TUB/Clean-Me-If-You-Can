"""Derive gazetteers and write the fixed clean files.

    python3 locality_fix/run_pipeline.py
    python3 locality_fix/run_pipeline.py --countries fr

The United Kingdom extract and locality fix stay in uk_fix/. Pass --download
to fetch the France, Spain, and Australia gazetteers, or --extract to rebuild
those slices from full_named/ first. The UK step always re-extracts its slice.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import derive_gazetteers  # noqa: E402
import download_gazetteers  # noqa: E402
import extract_unique  # noqa: E402
import fix_localities  # noqa: E402
import fix_regions  # noqa: E402
import refresh_labels  # noqa: E402

logger = logging.getLogger("run_pipeline")

COUNTRIES = ("uk", "fr", "es", "au")
SHARED = ("fr", "es", "au")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=derive_gazetteers.ROOT)
    parser.add_argument(
        "--countries",
        default="uk,fr,es,au",
        help="comma-separated: uk, fr, es, au",
    )
    parser.add_argument(
        "--download",
        action="store_true",
        help="fetch raw gazetteers before deriving",
    )
    parser.add_argument(
        "--extract",
        action="store_true",
        help="rebuild the country slices from full_named/ before deriving",
    )
    args = parser.parse_args(argv)
    countries = [part.strip().lower() for part in args.countries.split(",") if part.strip()]
    unknown = [code for code in countries if code not in COUNTRIES]
    if unknown:
        parser.error(f"unknown countries: {', '.join(unknown)}")
    shared = [code for code in countries if code in SHARED]
    shared_joined = ",".join(shared)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        stream=sys.stdout,
    )

    if args.download and shared:
        download_gazetteers.main(["--root", str(args.root), "--countries", shared_joined])
    if args.extract and shared:
        extract_unique.main(["--root", str(args.root), "--countries", shared_joined])

    if shared:
        derive_gazetteers.main(["--root", str(args.root), "--countries", shared_joined])
        for country in shared:
            logger.info("fix localities: %s", country)
            fix_localities.main(["--country", country, "--root", str(args.root)])
            logger.info("fix regions: %s", country)
            fix_regions.main(["--country", country, "--root", str(args.root)])

    if "uk" in countries:
        uk_dir = args.root / "uk_fix"
        sys.path.insert(0, str(uk_dir))
        import run_uk  # noqa: E402

        logger.info("fix UK localities")
        run_uk.main(["--uk-dir", str(uk_dir)])
    logger.info("refresh cell labels: %s", ",".join(countries))
    refresh_labels.main(["--root", str(args.root), "--countries", ",".join(countries)])
    logger.info("done: %s", ",".join(countries))


if __name__ == "__main__":
    main()
