"""Default paths for the Canada NAR scripts."""


from pathlib import Path

ROOT = Path(__file__).resolve().parent
PARENT = ROOT.parent

DATA = ROOT / "data"
RAW = DATA / "raw"
INDEXES = DATA / "indexes"
SLICES = DATA / "slices"
SAMPLES = DATA / "samples"
RESULTS = ROOT / "results"
LOGS = ROOT / "logs"
DOCS = ROOT / "docs"
SCRIPTS = ROOT / "scripts"

PARENT_NAMED = PARENT / "data" / "named"
PARENT_RAW = PARENT / "data" / "raw"


def nar_zip() -> Path:
    """June 2026 NAR zip: canada/data/raw first, then the parent US data/raw dump."""
    local = sorted(RAW.glob("*.zip*"))
    parent = sorted(PARENT_RAW.glob("*202606*")) + sorted(PARENT_RAW.glob("*NAR*"))
    for path in local + parent:
        if path.is_file() and path.stat().st_size > 0:
            return path
    return RAW / "NAR_202606.zip"
