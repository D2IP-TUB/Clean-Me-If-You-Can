#!/usr/bin/env python3
"""
Run v3 error-type analysis on one dirty/clean pair with heatmaps.

Wrapper around error_taxonomy/analyze_error_types.py CLI.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "error_taxonomy" / "analyze_error_types.py"


def main() -> None:
    if len(sys.argv) < 3:
        print(
            "Usage: python run_single_dataset.py <dirty.csv> <clean.csv> [output_dir]",
            file=sys.stderr,
        )
        sys.exit(1)

    dirty = Path(sys.argv[1]).resolve()
    clean = Path(sys.argv[2]).resolve()
    out = Path(sys.argv[3]).resolve() if len(sys.argv) > 3 else Path("output/single_run")

    cmd = [
        sys.executable,
        str(SCRIPT),
        "--values",
        str(dirty),
        "--targets",
        str(clean),
        "--output_dir",
        str(out),
    ]
    raise SystemExit(subprocess.call(cmd))


if __name__ == "__main__":
    main()
