"""Default paths for the US NAD scripts."""


from pathlib import Path

ROOT = Path(__file__).resolve().parent

DATA = ROOT / "data"
RAW = DATA / "raw"
INDEXES = DATA / "indexes"
SLICES = DATA / "slices"
SAMPLES = DATA / "samples"
NAMED = DATA / "named"

RESULTS = ROOT / "results"
LOGS = ROOT / "logs"
DOCS = ROOT / "docs"
SCRIPTS = ROOT / "scripts"
ARCHIVE = ROOT / "archive"
