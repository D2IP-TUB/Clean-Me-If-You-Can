#!/usr/bin/env python3
"""Run the error taxonomy on one dirty/clean pair.

Extra arguments are forwarded to error_taxonomy/analyze_error_types.py.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "error_taxonomy" / "analyze_error_types.py"


def main() -> None:
    if len(sys.argv) < 3:
        print(
            "Usage: python run_single_dataset.py <dirty.csv> <clean.csv> [output_dir] "
            "[--language_columns ...] [--parsing_columns ...] [--abbrev_columns ...]",
            file=sys.stderr,
        )
        sys.exit(1)

    dirty = Path(sys.argv[1]).resolve()
    clean = Path(sys.argv[2]).resolve()
    rest = sys.argv[3:]
    out_arg = None
    if rest and not rest[0].startswith("-"):
        out_arg = rest[0]
        rest = rest[1:]
    if rest and rest[0] == "--":
        rest = rest[1:]
    out = Path(out_arg).resolve() if out_arg else Path("output/single_run")

    cmd = [
        sys.executable,
        str(SCRIPT),
        "--values",
        str(dirty),
        "--targets",
        str(clean),
        "--output_dir",
        str(out),
        *rest,
    ]
    raise SystemExit(subprocess.call(cmd))


if __name__ == "__main__":
    main()
