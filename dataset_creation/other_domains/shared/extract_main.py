"""Extract schema.org entities from WDC N-Quads.

Usage:
  python -m shared.extract_main --input-dir ./data/wdc --out-dir ./data/extracted --domain book
"""

from __future__ import annotations

import argparse
from pathlib import Path

from loguru import logger

from shared.extract import DOMAIN_SUBSETS, DOMAINS, SUBSET_CONFIGS, extract_from_file
from shared.io import project_root, write_to_jsongz


def _process_one(
    in_path: Path,
    out_path: Path,
    input_dir: Path,
    domain: str | None,
    wdc_release: str,
    skip: bool,
) -> tuple[bool, str]:
    if skip and out_path.exists():
        return True, "skip"
    try:
        try:
            rel = in_path.relative_to(input_dir)
            source_file = str(rel)
            subset_name = rel.parts[0] if len(rel.parts) > 1 else in_path.stem
        except ValueError:
            source_file = str(in_path)
            subset_name = in_path.stem
        config = SUBSET_CONFIGS.get(subset_name)
        if config is None and domain is not None:
            config = DOMAINS.get(domain)
        if config is None:
            return False, f"no extract config for subset {subset_name!r}"
        records = list(
            extract_from_file(
                in_path,
                config,
                subset=subset_name,
                source_file=source_file,
                wdc_release=wdc_release,
            )
        )
        if not records:
            return True, "empty"
        write_to_jsongz(records, out_path)
        return True, str(len(records))
    except Exception as e:
        try:
            with open(out_path.with_suffix(".error"), "w") as ef:
                ef.write(str(e))
        except Exception:
            pass
        return False, str(e)


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract typed entities from WDC N-Quads.")
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, default=None)
    parser.add_argument(
        "--domain",
        choices=sorted(DOMAIN_SUBSETS),
        default=None,
        help="Only subsets for this domain (book, movies). Default: all known subsets.",
    )
    parser.add_argument("--subset", type=str, default=None, help="Only this subset subdir, e.g. Book.")
    parser.add_argument("--wdc-release", type=str, default="2024-12")
    parser.add_argument("--no-skip-existing", action="store_true")
    parser.add_argument(
        "--parts-only",
        action="store_true",
        help="Only process part_*.gz shards (skip *_sample.txt).",
    )
    args = parser.parse_args()

    input_dir = args.input_dir.resolve()
    out_root = (args.out_dir or (project_root() / "data" / "extracted")).resolve()
    skip = not args.no_skip_existing

    files = list(input_dir.rglob("*.txt")) + list(input_dir.rglob("*.gz"))
    pairs: list[tuple[Path, Path]] = []
    for f in sorted(files):
        if args.subset is not None and args.subset not in f.parts:
            continue
        if args.domain is not None:
            allowed = DOMAIN_SUBSETS[args.domain]
            if not any(name in f.parts for name in allowed):
                continue
        if args.parts_only and "part_" not in f.name:
            continue
        try:
            rel = f.relative_to(input_dir)
        except ValueError:
            continue
        subset_guess = rel.parts[0] if len(rel.parts) > 1 else None
        if subset_guess not in SUBSET_CONFIGS:
            continue
        out_name = f.with_suffix("").name + ".json.gz"
        if f.suffix == ".gz":
            out_name = f.name[: -len(".gz")] + ".json.gz"
            if out_name.endswith(".txt.json.gz"):
                out_name = out_name.replace(".txt.json.gz", ".json.gz")
        pairs.append((f, out_root / rel.parent / out_name))

    if not pairs:
        logger.error(f"No N-Quads files found under {input_dir}")
        return

    logger.info(f"Extracting {len(pairs)} file(s)")
    for in_path, out_path in pairs:
        ok, msg = _process_one(in_path, out_path, input_dir, args.domain, args.wdc_release, skip)
        if not ok:
            logger.error(f"Error {in_path}: {msg}")
        elif msg == "skip":
            logger.info(f"Skip {out_path}")
        elif msg == "empty":
            logger.warning(f"No records {in_path}")
        else:
            logger.info(f"Wrote {msg} records -> {out_path}")


if __name__ == "__main__":
    main()
