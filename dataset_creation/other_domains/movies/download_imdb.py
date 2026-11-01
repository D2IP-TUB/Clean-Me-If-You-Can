"""Download IMDb non-commercial dataset TSVs.

https://datasets.imdbws.com
https://developer.imdb.com/non-commercial-datasets/

Usage:
  python -m movies.download_imdb
"""

from __future__ import annotations

import argparse
from pathlib import Path

from shared.download import _session, download_file
from shared.io import project_root

BASE_URL = "https://datasets.imdbws.com"

DEFAULT_FILES = [
    "title.basics",
    "title.crew",
    "title.principals",
    "name.basics",
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Download IMDb non-commercial dataset TSVs.")
    parser.add_argument("--out-dir", type=Path, default=None)
    parser.add_argument("--no-skip-existing", action="store_true")
    args = parser.parse_args()

    out_dir = (args.out_dir or (project_root() / "data" / "imdb")).resolve()
    skip = not args.no_skip_existing
    session = _session()
    files = DEFAULT_FILES

    for name in files:
        url = f"{BASE_URL}/{name}.tsv.gz"
        dest = out_dir / f"{name}.tsv.gz"
        print(f"{name}: {url}")
        try:
            if download_file(
                url,
                dest,
                session=session,
                skip_existing=skip,
                refresh_if_newer=True,
                timeout=(60, 900),
            ):
                print(f"  Downloaded {dest} ({dest.stat().st_size:,} bytes)")
            else:
                print(f"  Skip (exists) {dest} ({dest.stat().st_size:,} bytes)")
        except Exception as e:
            print(f"  Error: {e}")
    print("Done.")


if __name__ == "__main__":
    main()
