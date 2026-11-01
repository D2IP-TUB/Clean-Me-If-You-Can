"""Point cell-label clean values at the fixed locality, region, and postcode."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from io_csv import read_csv_as_strings  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
FIELDS = ("locality", "region", "postcode")
FINAL = {
    "uk": "uk_clean_locality_fixed.csv",
    "fr": "fr_clean_fixed.csv",
    "es": "es_clean_fixed.csv",
    "au": "au_clean_fixed.csv",
}
logger = logging.getLogger("refresh_labels")


def relabel(dirty: str, new: str, old_label: str, special) -> tuple[str, bool]:
    """Return (label, certain). `certain` is False when the old label is kept."""
    if dirty.strip().lower() == new.strip().lower():
        return "Clean", True
    if dirty.strip() == "":
        return "Missing", True
    if special is not None:
        try:
            if special(dirty, new):
                return "Special_Character", True
        except Exception:  # noqa: BLE001
            pass
    if old_label == "Clean":
        return "Unlabeled", False
    return old_label, False


def refresh(country: str, root: Path) -> None:
    folder = root / f"{country}_fix"
    orig = read_csv_as_strings(folder / f"{country}_clean.csv")
    final = read_csv_as_strings(folder / FINAL[country])
    if len(orig) != len(final):
        raise ValueError(f"{country}: original {len(orig)} rows, fixed {len(final)} rows")
    labels_path = folder / f"{country}_cell_labels.csv"
    labels = read_csv_as_strings(labels_path)
    idx = pd.to_numeric(labels["new_row_index"], errors="coerce")
    special = None

    recheck = []
    counts = {"Clean": 0, "Special_Character": 0, "Unlabeled": 0, "kept": 0}
    for field in FIELDS:
        if field not in final.columns:
            continue
        mask = labels["feature"] == field
        positions = {int(i): pos for pos, i in zip(labels.index[mask], idx[mask]) if pd.notna(i)}
        for i, pos in positions.items():
            if 0 <= i < len(final):
                labels.at[pos, "clean_value"] = final.at[i, field]
        changed = [i for i in range(len(final)) if final.at[i, field] != orig.at[i, field]]
        for i in changed:
            pos = positions.get(i)
            if pos is None:
                continue
            new = final.at[i, field]
            labels.at[pos, "clean_value"] = new
            label, certain = relabel(
                labels.at[pos, "dirty_value"], new, labels.at[pos, "labels"], special
            )
            if label != labels.at[pos, "labels"]:
                counts[label] = counts.get(label, 0) + 1
            labels.at[pos, "labels"] = label
            if certain:
                continue
            if label == labels.at[pos, "labels"] and label != "Unlabeled":
                counts["kept"] += 1
            recheck.append(
                {
                    "new_row_index": str(i),
                    "id": final.at[i, "id"],
                    "feature": field,
                    "dirty_value": labels.at[pos, "dirty_value"],
                    "original_clean": orig.at[i, field],
                    "fixed_clean": new,
                    "label_now": label,
                }
            )
    labels.to_csv(labels_path, index=False)
    pd.DataFrame(
        recheck,
        columns=[
            "new_row_index", "id", "feature", "dirty_value",
            "original_clean", "fixed_clean", "label_now",
        ],
    ).to_csv(folder / "cell_labels_to_recheck.csv", index=False)
    logger.info("%s: %s; %d cells listed for relabeling", country, counts, len(recheck))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--countries", default="uk,fr,es,au")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout)
    for country in [c.strip() for c in args.countries.split(",") if c.strip()]:
        refresh(country, args.root)


if __name__ == "__main__":
    main()
