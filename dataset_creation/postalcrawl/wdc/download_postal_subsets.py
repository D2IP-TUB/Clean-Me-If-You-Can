"""
Download full WDC schema.org subsets that contain PostalAddress.

Discovers subsets from the Web Data Commons schema.org subsets page, lists
part_*.gz chunk files via the server directory index, and downloads them
into a local directory per subset.

Usage:
  python -m postalcrawl.wdc.download_postal_subsets --out-dir ./data/wdc
  python -m postalcrawl.wdc.download_postal_subsets --out-dir ./data/wdc --subset LocalBusiness --subset Place
"""

from __future__ import annotations

import argparse
import re
import time
from pathlib import Path

import requests

SUBSETS_PAGE = "https://webdatacommons.org/structureddata/2024-12/stats/schema_org_subsets.html"
BASE_URL = "https://data.dws.informatik.uni-mannheim.de/structureddata/2024-12/quads/classspecific"
USER_AGENT = "postalcrawl-wdc-downloader/1.0 (address research)"


def _session() -> requests.Session:
    s = requests.Session()
    s.headers["User-Agent"] = USER_AGENT
    return s


def get_subsets_with_postal_address(session: requests.Session | None = None) -> list[str]:
    """Fetch the WDC subsets page and return subset names whose Related Classes include PostalAddress."""
    session = session or _session()
    r = session.get(SUBSETS_PAGE, timeout=60)
    r.raise_for_status()
    html = r.text
    # Table rows: find <tr>...</tr> that contain both a schema.org subset link and PostalAddress
    # Link in first column: <a href="http://schema.org/SubsetName">SubsetName</a>
    subset_names: list[str] = []
    # Match rows that contain a link to schema.org and later PostalAddress in the same row
    tr_pattern = re.compile(r"<tr[^>]*>(.*?)</tr>", re.DOTALL | re.IGNORECASE)
    link_pattern = re.compile(r'<a\s+href="https?://schema\.org/([^"/]+)"[^>]*>', re.IGNORECASE)
    for m in tr_pattern.finditer(html):
        row = m.group(1)
        if "PostalAddress" not in row:
            continue
        link_m = link_pattern.search(row)
        if link_m:
            subset_names.append(link_m.group(1))
    return subset_names


def list_part_gz_urls(subset_name: str, session: requests.Session | None = None) -> list[str]:
    """List part_*.gz filenames from the subset directory index and return full URLs."""
    session = session or _session()
    url = f"{BASE_URL}/{subset_name}/"
    r = session.get(url, timeout=60)
    r.raise_for_status()
    # Apache-style listing: "part_0.gz", "part_1.gz", ...
    part_pattern = re.compile(r"part_(\d+)\.gz", re.IGNORECASE)
    names = part_pattern.findall(r.text)
    # Sort numerically and build URLs
    parts = sorted(set(int(n) for n in names))
    return [f"{url}part_{i}.gz" for i in parts]


def download_file(
    url: str,
    dest: Path,
    session: requests.Session | None = None,
    skip_existing: bool = True,
) -> bool:
    """Download url to dest. Returns True if downloaded, False if skipped."""
    if skip_existing and dest.exists():
        return False
    session = session or _session()
    dest.parent.mkdir(parents=True, exist_ok=True)
    r = session.get(url, stream=True, timeout=120)
    r.raise_for_status()
    with open(dest, "wb") as f:
        for chunk in r.iter_content(chunk_size=1 << 20):
            if chunk:
                f.write(chunk)
    return True


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download WDC schema.org subsets that contain PostalAddress (full part_*.gz chunks)."
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("data/wdc"),
        help="Directory to save subset data (default: data/wdc); each subset goes in out-dir/<SubsetName>/",
    )
    parser.add_argument(
        "--subset",
        action="append",
        dest="subsets",
        metavar="NAME",
        help="Download only these subset(s); can be repeated. If not set, all subsets with PostalAddress are used.",
    )
    parser.add_argument(
        "--list-only",
        action="store_true",
        help="Only list subset names that have PostalAddress; do not download.",
    )
    parser.add_argument(
        "--no-skip-existing",
        action="store_true",
        help="Re-download part files even if they already exist.",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.0,
        help="Seconds to wait between requests (default 1.0).",
    )
    args = parser.parse_args()

    session = _session()

    if args.subsets:
        subset_names = [s.strip() for s in args.subsets if s.strip()]
    else:
        print("Fetching schema.org subsets page...")
        subset_names = get_subsets_with_postal_address(session)
        print(f"Found {len(subset_names)} subset(s) with PostalAddress.")

    if not subset_names:
        print("No subsets to process.")
        return

    if args.list_only:
        for name in sorted(subset_names):
            print(name)
        return

    args.out_dir = args.out_dir.resolve()
    skip = not args.no_skip_existing

    for subset in sorted(subset_names):
        print(f"\n--- {subset} ---")
        try:
            urls = list_part_gz_urls(subset, session)
        except Exception as e:
            print(f"  Failed to list files: {e}")
            continue
        if not urls:
            print("  No part_*.gz files found.")
            continue
        print(f"  {len(urls)} part file(s).")
        time.sleep(args.delay)
        for url in urls:
            name = url.rstrip("/").split("/")[-1]
            dest = args.out_dir / subset / name
            try:
                if download_file(url, dest, session=session, skip_existing=skip):
                    print(f"  Downloaded {name}")
                else:
                    print(f"  Skip (exists) {name}")
            except Exception as e:
                print(f"  Error {name}: {e}")
            time.sleep(args.delay)

    print("\nDone.")


if __name__ == "__main__":
    main()
