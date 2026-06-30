import argparse
import asyncio
from pathlib import Path
from typing import Iterable, Iterator

from loguru import logger
from tqdm import tqdm
from tqdm.asyncio import tqdm as tqdm_asyncio

from postalcrawl.record import Record
from postalcrawl.utils import project_root, read_from_jsongz, write_to_jsongz
from postalcrawl.validate.osm_validator import OsmValidator

PROJECT_ROOT = project_root()
DEFAULT_EXTRACT_ROOT = PROJECT_ROOT / "data" / "extracted"
DEFAULT_VALIDATE_ROOT = DEFAULT_EXTRACT_ROOT.parent / "validated"
DEFAULT_NOMINATIM_URL = "http://localhost:9020"
# DEFAULT_NOMINATIM_URL = "https://nominatim.openstreetmap.org"
DEFAULT_MAX_CONCURRENT = 512


def iterate_nested_dicts(records: Iterable[Record[dict]]) -> Iterator[Record[dict]]:
    def get_all_subdicts(root: dict | list) -> Iterator[dict]:
        """yield all sub-dicts in a nested dict/list structure"""
        if isinstance(root, dict):
            yield root
            for v in root.values():
                yield from get_all_subdicts(v)
        elif isinstance(root, list):
            for item in root:
                yield from get_all_subdicts(item)

    for record in records:
        data = record["data"]
        for subdict in get_all_subdicts(data):
            out: Record[dict] = {"data": subdict, "crawl_metadata": record["crawl_metadata"]}
            yield out


async def gather_nominatim_requests(
    tasks: list,
    *,
    desc: str,
) -> list:
    """Run Nominatim coroutines with a tqdm bar (rate in req/s)."""
    if not tasks:
        return []
    return await tqdm_asyncio.gather(
        *tasks,
        desc=desc,
        unit="req",
        leave=False,
    )


def dict_contains_address(record: Record[dict]) -> bool:
    data = record["data"]
    if "address" not in data.keys():
        return False
    address = data.get("address")
    if not isinstance(address, dict):
        return False
    if address.get("@type") != "PostalAddress":
        return False
    return True


async def main(
    extract_root: Path,
    validate_root: Path,
    nominatim_url: str,
    max_concurrent: int,
    skip_existing: bool = False,
    connect_timeout: float = 10.0,
    read_timeout: float = 60.0,
    async_cap_timeout: float | None = 90.0,
):
    # Sort directories by total compressed size (smallest first) so quick subsets
    # finish early and progress is visible sooner; within each dir sort by filename.
    all_files_unsorted = list(extract_root.glob("**/*.json.gz"))
    dir_size: dict[Path, int] = {}
    for f in all_files_unsorted:
        dir_size[f.parent] = dir_size.get(f.parent, 0) + f.stat().st_size
    all_files = sorted(all_files_unsorted, key=lambda f: (dir_size[f.parent], f.name))
    async with OsmValidator(
        nominatim_url,
        max_concurrent=max_concurrent,
        connect_timeout=connect_timeout,
        read_timeout=read_timeout,
        async_cap_timeout=async_cap_timeout,
    ) as validator:
        for extract_file in tqdm(all_files, desc="Files", unit="file"):
            outfile = validate_root / extract_file.relative_to(extract_root)
            outfile.parent.mkdir(parents=True, exist_ok=True)
            if skip_existing and outfile.exists():
                tqdm.write(f"Skipping existing file: {outfile}")
                continue

            records: list[Record[dict]] = read_from_jsongz(extract_file)
            gen = (rec for rec in records)
            gen = iterate_nested_dicts(gen)
            gen = (rec for rec in gen if dict_contains_address(rec))
            gen = (validator.record_query_validator(rec) for rec in gen)
            tasks = list(gen)
            logger.info(f"{extract_file.parent.name}/{extract_file.name}: {len(tasks)} records")
            results = await gather_nominatim_requests(
                tasks,
                desc=f"Nominatim {extract_file.name[:48]}",
            )
            results = [res for res in results if res is not None]
            write_to_jsongz(results, outfile=outfile)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Validate extracted postal addresses with OSM Nominatim."
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=DEFAULT_EXTRACT_ROOT,
        help="Directory containing extracted .json.gz files "
        "(default: data/extracted under project root).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_VALIDATE_ROOT,
        help="Directory to write validated .json.gz files "
        "(default: data/validated under project root).",
    )
    parser.add_argument(
        "--nominatim-url",
        type=str,
        default=DEFAULT_NOMINATIM_URL,
        help="Base URL of Nominatim instance (default: http://localhost:9020).",
    )
    parser.add_argument(
        "--max-concurrent",
        type=int,
        default=DEFAULT_MAX_CONCURRENT,
        help="Maximum number of concurrent Nominatim requests.",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip output files that already exist.",
    )
    parser.add_argument(
        "--connect-timeout",
        type=float,
        default=10.0,
        help="TCP connect timeout in seconds for each Nominatim request (default: 10).",
    )
    parser.add_argument(
        "--read-timeout",
        type=float,
        default=60.0,
        help="Per-request read timeout in seconds (default: 60).",
    )
    parser.add_argument(
        "--async-cap-timeout",
        type=float,
        default=90.0,
        help="Hard asyncio ceiling per request in seconds, including JSON parse "
        "(default: 90; use 0 to disable).",
    )
    parser.add_argument(
        "--input-file",
        type=Path,
        default=None,
        help="If set, validate only this .json.gz file (output: --output-dir / filename).",
    )
    parser.add_argument(
        "--log-file",
        type=Path,
        default=None,
        help="If set, write file-level progress (file name + record count) to this path.",
    )
    args = parser.parse_args()

    if args.log_file:
        args.log_file.parent.mkdir(parents=True, exist_ok=True)
        # Only capture __main__ log lines (file-level info) — no osm_validator spam.
        logger.add(
            args.log_file,
            level="INFO",
            filter=lambda r: r["name"] == "__main__",
            format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}",
        )

    if args.input_file is not None:
        cap = None if args.async_cap_timeout == 0 else args.async_cap_timeout

        async def run_single():
            async with OsmValidator(
                args.nominatim_url,
                max_concurrent=args.max_concurrent,
                connect_timeout=args.connect_timeout,
                read_timeout=args.read_timeout,
                async_cap_timeout=cap,
            ) as validator:
                records = read_from_jsongz(args.input_file)
                gen = (rec for rec in records)
                gen = iterate_nested_dicts(gen)
                gen = (rec for rec in gen if dict_contains_address(rec))
                tasks = [validator.record_query_validator(rec) for rec in gen]
                results = await gather_nominatim_requests(
                    tasks,
                    desc=f"Nominatim {args.input_file.name[:48]}",
                )
                results = [r for r in results if r is not None]
                outfile = args.output_dir / args.input_file.name
                outfile.parent.mkdir(parents=True, exist_ok=True)
                write_to_jsongz(results, outfile=outfile)
                logger.info("Wrote %s", outfile)
        asyncio.run(run_single())
    else:
        cap = None if args.async_cap_timeout == 0 else args.async_cap_timeout
        asyncio.run(
            main(
                extract_root=args.input_dir,
                validate_root=args.output_dir,
                nominatim_url=args.nominatim_url,
                max_concurrent=args.max_concurrent,
                skip_existing=args.skip_existing,
                connect_timeout=args.connect_timeout,
                read_timeout=args.read_timeout,
                async_cap_timeout=cap,
            )
        )
