"""Download official gazetteer files for France, Spain, and Australia."""

from __future__ import annotations

import argparse
import json
import logging
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UA = "manual_labeling-locality-fix/1.0"

logger = logging.getLogger("download_gazetteers")

INSEE_COG_ZIP = "https://www.insee.fr/fr/statistiques/fichier/8740222/cog_ensemble_2026_csv.zip"
LAPOSTE_HEXASMAL = "https://data.laposte.fr/data-fair/api/v1/datasets/laposte-hexasmal/raw"
INE_MUNI_XLSX = "https://www.ine.es/daco/daco42/codmun/diccionario26.xlsx"
GEONAMES_ES_ZIP = "https://download.geonames.org/export/zip/ES.zip"
GNAF_SOURCE_ZIP = "https://publicdata.au/d/gnaf/v/2026-08-17/source.zip"
ABS_LGA_QUERY = (
    "https://geo.abs.gov.au/arcgis/rest/services/ASGS2024/LGA/FeatureServer/0/query"
    "?where=1%3D1&outFields=*&returnGeometry=false&f=json&resultRecordCount=2000"
)


def fetch(url: str, dest: Path, timeout: int = 600) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 0:
        logger.info("skip existing %s (%.1f MB)", dest, dest.stat().st_size / 1e6)
        return dest
    logger.info("GET %s -> %s", url, dest)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp, dest.open("wb") as f:
        while True:
            chunk = resp.read(8 * 1024 * 1024)
            if not chunk:
                break
            f.write(chunk)
    logger.info("wrote %s (%.1f MB)", dest, dest.stat().st_size / 1e6)
    return dest


def unzip(zip_path: Path, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(out_dir)
        logger.info("extracted %s -> %s (%d files)", zip_path, out_dir, len(z.namelist()))


def download_fr(base: Path) -> None:
    raw = base / "gazetteer" / "raw"
    fetch(INSEE_COG_ZIP, raw / "cog_ensemble_2026_csv.zip")
    unzip(raw / "cog_ensemble_2026_csv.zip", raw / "cog")
    fetch(LAPOSTE_HEXASMAL, raw / "laposte_hexasmal.csv")


def download_es(base: Path) -> None:
    raw = base / "gazetteer" / "raw"
    fetch(INE_MUNI_XLSX, raw / "ine_diccionario.xlsx")
    fetch(GEONAMES_ES_ZIP, raw / "geonames_ES.zip")
    unzip(raw / "geonames_ES.zip", raw / "geonames")


def download_au(base: Path) -> None:
    raw = base / "gazetteer" / "raw"
    fetch(ABS_LGA_QUERY, raw / "abs_lga.json", timeout=120)
    zip_path = raw / "gnaf_source.zip"
    if not zip_path.exists() or zip_path.stat().st_size < 1_000_000_000:
        fetch(GNAF_SOURCE_ZIP, zip_path, timeout=3600)
    out = raw / "gnaf"
    if not any(out.rglob("*LOCALITY_psv.psv")):
        logger.info("extracting LOCALITY/STATE psv files from %s", zip_path)
        out.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path) as z:
            wanted = [
                n
                for n in z.namelist()
                if n.upper().endswith(("_LOCALITY_PSV.PSV", "_STATE_PSV.PSV", "_LOCALITY_ALIAS_PSV.PSV"))
                or n.upper().endswith(("AUTHORITY_CODE_STATE_PSV.PSV",))
            ]
            logger.info("matched %d zip members", len(wanted))
            for name in wanted:
                z.extract(name, out)


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--countries", default="fr,es,au")
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        stream=sys.stdout,
    )
    wanted = {c.strip().lower() for c in args.countries.split(",") if c.strip()}
    if "fr" in wanted:
        download_fr(args.root / "fr_fix")
    if "es" in wanted:
        download_es(args.root / "es_fix")
    if "au" in wanted:
        download_au(args.root / "au_fix")


if __name__ == "__main__":
    main()
