"""Merge packed movie CSVs and drop duplicate dirty rows."""

from __future__ import annotations

import argparse
from pathlib import Path

from movies.pack import EXPERIMENT_COLUMNS
from shared.io import project_root
from shared.pack_common import merge_flat_datasets

SUBSETS = ["Movie"]


def merge_movies(pack_dir: Path, out_dir: Path) -> None:
    merge_flat_datasets(pack_dir, out_dir, EXPERIMENT_COLUMNS, subset_names=SUBSETS)


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge packed movie CSVs.")
    parser.add_argument("--pack-dir", type=Path, default=None)
    parser.add_argument("--out-dir", type=Path, default=None)
    args = parser.parse_args()
    pack_dir = (args.pack_dir or (project_root() / "data" / "pack")).resolve()
    out_dir = (args.out_dir or (project_root() / "data" / "merged" / "movies")).resolve()
    merge_movies(pack_dir, out_dir)


if __name__ == "__main__":
    main()
