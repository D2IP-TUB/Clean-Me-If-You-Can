"""Download WDC schema.org class-specific N-Quads.

Usage:
  python -m shared.download --subset Book --subset Movie --full
"""

from __future__ import annotations

import argparse
import re
import time
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

import requests
from tqdm import tqdm

from shared.io import project_root

BASE_URL = "https://data.dws.informatik.uni-mannheim.de/structureddata/2024-12/quads/classspecific"
USER_AGENT = "other-domains-wdc-downloader/1.0 (book research)"


def _session() -> requests.Session:
    s = requests.Session()
    s.headers["User-Agent"] = USER_AGENT
    return s


def sample_url(subset_name: str) -> str:
    return f"{BASE_URL}/{subset_name}/{subset_name}_sample.txt"


def list_part_gz_urls(subset_name: str, session: requests.Session | None = None) -> list[str]:
    session = session or _session()
    url = f"{BASE_URL}/{subset_name}/"
    r = session.get(url, timeout=60)
    r.raise_for_status()
    parts = sorted({int(n) for n in re.findall(r"part_(\d+)\.gz", r.text, re.IGNORECASE)})
    return [f"{url}part_{i}.gz" for i in parts]


def _remote_changed(url: str, dest: Path, session: requests.Session, timeout: tuple[float, float]) -> bool:
    if not dest.exists() or dest.stat().st_size <= 0:
        return True
    try:
        r = session.head(url, timeout=timeout, allow_redirects=True)
        r.raise_for_status()
    except requests.RequestException:
        return True
    cl = r.headers.get("Content-Length")
    if cl:
        try:
            if int(cl) != dest.stat().st_size:
                return True
        except ValueError:
            pass
    lm = r.headers.get("Last-Modified")
    if lm:
        try:
            remote = parsedate_to_datetime(lm)
            if remote.tzinfo is None:
                remote = remote.replace(tzinfo=timezone.utc)
            local = datetime.fromtimestamp(dest.stat().st_mtime, tz=timezone.utc)
            if remote > local + timedelta(seconds=2):
                return True
        except (TypeError, ValueError, OverflowError):
            pass
    if cl:
        return False
    return False


def download_file(
    url: str,
    dest: Path,
    session: requests.Session | None = None,
    skip_existing: bool = True,
    timeout: tuple[float, float] = (30, 300),
    refresh_if_newer: bool = False,
) -> bool:
    session = session or _session()
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    if skip_existing and dest.exists() and dest.stat().st_size > 0:
        if not refresh_if_newer or not _remote_changed(url, dest, session, timeout):
            return False
        dest.unlink()
        if tmp.exists():
            tmp.unlink()
    existing = tmp.stat().st_size if tmp.exists() else 0
    headers = {"Range": f"bytes={existing}-"} if existing else {}
    r = session.get(url, stream=True, timeout=timeout, headers=headers)
    if existing and r.status_code == 206:
        mode = "ab"
        total = existing + int(r.headers.get("Content-Length") or 0)
    elif r.status_code == 200:
        mode = "wb"
        existing = 0
        total = int(r.headers.get("Content-Length") or 0)
    else:
        r.raise_for_status()
        mode = "wb"
        total = int(r.headers.get("Content-Length") or 0)
    with open(tmp, mode) as f, tqdm(
        total=total or None,
        initial=existing,
        unit="B",
        unit_scale=True,
        desc=dest.name,
        leave=False,
    ) as bar:
        for chunk in r.iter_content(chunk_size=1 << 20):
            if chunk:
                f.write(chunk)
                bar.update(len(chunk))
    tmp.replace(dest)
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Download WDC schema.org subset files.")
    parser.add_argument(
        "--subset",
        action="append",
        dest="subsets",
        metavar="NAME",
        default=None,
        help="Subset name (repeatable). Default: Book.",
    )
    parser.add_argument(
        "--sample",
        action="store_true",
        help="Download {Subset}_sample.txt.",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Download all part_*.gz shards (~3.7 GB for Book).",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="Output root (default: other_domains/data/wdc).",
    )
    parser.add_argument(
        "--no-skip-existing",
        action="store_true",
        help="Re-download even if the file already exists.",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.0,
        help="Seconds between shard requests (default 1.0).",
    )
    args = parser.parse_args()

    if not args.sample and not args.full:
        parser.error("Pass --sample and/or --full.")

    subsets = [s.strip() for s in (args.subsets or ["Book"]) if s.strip()]
    out_dir = (args.out_dir or (project_root() / "data" / "wdc")).resolve()
    skip = not args.no_skip_existing
    session = _session()

    for subset in subsets:
        print(f"--- {subset} ---")
        if args.sample:
            url = sample_url(subset)
            dest = out_dir / subset / f"{subset}_sample.txt"
            print(f"  sample {url}")
            try:
                if download_file(url, dest, session=session, skip_existing=skip):
                    print(f"  Downloaded {dest} ({dest.stat().st_size} bytes)")
                else:
                    print(f"  Skip (exists) {dest} ({dest.stat().st_size} bytes)")
            except Exception as e:
                print(f"  Error sample: {e}")
        if args.full:
            try:
                urls = list_part_gz_urls(subset, session)
            except Exception as e:
                print(f"  Failed to list parts: {e}")
                continue
            print(f"  {len(urls)} part file(s).")
            time.sleep(args.delay)
            for url in urls:
                name = url.rstrip("/").split("/")[-1]
                dest = out_dir / subset / name
                try:
                    if download_file(url, dest, session=session, skip_existing=skip):
                        print(f"  Downloaded {name} ({dest.stat().st_size} bytes)")
                    else:
                        print(f"  Skip (exists) {name} ({dest.stat().st_size} bytes)")
                except Exception as e:
                    print(f"  Error {name}: {e}")
                time.sleep(args.delay)

    print("Done.")


if __name__ == "__main__":
    main()
