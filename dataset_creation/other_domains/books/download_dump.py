"""Download an Open Library dump from archive.org.

Default file: ol_dump_2026-08-31.txt.gz

Usage:
  python -m books.download_dump
"""

from __future__ import annotations

import argparse
from pathlib import Path

from shared.download import _session, download_file
from shared.io import project_root

DUMP_ID_DEFAULT = "ol_dump_2026-08-31"
ARCHIVE_DOWNLOAD = "https://archive.org/download/{dump_id}/{filename}"

COMBINED_FILE = "ol_dump_{date}.txt.gz"
SPLIT_FILES = {
    "editions": "ol_dump_editions_{date}.txt.gz",
    "authors": "ol_dump_authors_{date}.txt.gz",
    "works": "ol_dump_works_{date}.txt.gz",
}


def dump_date(dump_id: str) -> str:
    return dump_id.removeprefix("ol_dump_").removeprefix("ol_cdump_")


def file_url(dump_id: str, filename: str) -> str:
    return ARCHIVE_DOWNLOAD.format(dump_id=dump_id, filename=filename)


def main() -> None:
    parser = argparse.ArgumentParser(description="Download Open Library dumps.")
    parser.add_argument("--dump-id", default=DUMP_ID_DEFAULT, help="archive.org item id")
    parser.add_argument("--out-dir", type=Path, default=None)
    parser.add_argument(
        "--split",
        action="store_true",
        help="Download editions/authors/works split files instead of the combined dump.",
    )
    parser.add_argument(
        "--works",
        action="store_true",
        help="With --split, also fetch the works dump. Ignored for the combined dump.",
    )
    parser.add_argument("--no-skip-existing", action="store_true")
    args = parser.parse_args()

    out_dir = (args.out_dir or (project_root() / "data" / "openlibrary")).resolve()
    skip = not args.no_skip_existing
    session = _session()
    date = dump_date(args.dump_id)
    if args.split:
        kinds = ["authors", "editions"] + (["works"] if args.works else [])
        filenames = [SPLIT_FILES[k].format(date=date) for k in kinds]
    else:
        filenames = [COMBINED_FILE.format(date=date)]

    failed = False
    for filename in filenames:
        url = file_url(args.dump_id, filename)
        dest = out_dir / filename
        print(f"{filename}: {url}")
        try:
            if download_file(
                url,
                dest,
                session=session,
                skip_existing=skip,
                timeout=(60, 7200),
            ):
                print(f"  Downloaded {dest} ({dest.stat().st_size:,} bytes)")
            else:
                print(f"  Skip (exists) {dest} ({dest.stat().st_size:,} bytes)")
        except Exception as e:
            print(f"  Error: {e}")
            failed = True
    if failed:
        raise SystemExit(1)
    print("Done.")


if __name__ == "__main__":
    main()
