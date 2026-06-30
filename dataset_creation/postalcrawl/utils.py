import gzip
import json
from pathlib import Path


def project_root() -> Path:
    return Path(__file__).parent.parent


def write_to_jsongz(data: dict, outfile: Path):
    with gzip.open(outfile, "wt", encoding="utf-8") as zipfile:
        json.dump(data, zipfile, indent=2)


def read_from_jsongz(infile: Path) -> dict | list:
    with gzip.open(infile, "rt", encoding="utf-8") as zipfile:
        data = json.load(zipfile)
    return data
