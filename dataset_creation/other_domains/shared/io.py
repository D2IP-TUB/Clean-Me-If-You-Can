import gzip
import json
from pathlib import Path


def project_root() -> Path:
    """Return the repository root."""
    return Path(__file__).resolve().parent.parent


def write_to_jsongz(data: dict | list, outfile: Path, indent: int | None = None) -> None:
    outfile.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(outfile, "wt", encoding="utf-8") as zipfile:
        json.dump(data, zipfile, indent=indent)


def read_from_jsongz(infile: Path) -> dict | list:
    with gzip.open(infile, "rt", encoding="utf-8") as zipfile:
        return json.load(zipfile)
