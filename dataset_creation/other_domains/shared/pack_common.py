"""Dirty/clean/provenance CSV helpers used by books and movies."""

from __future__ import annotations

import csv
import uuid
from pathlib import Path

from loguru import logger


def _dedup_value(value) -> str:
    # lower, not casefold: ß must stay distinct from ss.
    return str(value or "").strip().lower()


def unique_rows(rows: list[dict]) -> list[dict]:
    seen: set[tuple] = set()
    out: list[dict] = []
    for row in rows:
        sig = tuple(sorted((k, _dedup_value(row.get(k))) for k in row))
        if sig in seen:
            continue
        seen.add(sig)
        out.append(row)
    return out


def keep_complete_gt(rows: list[dict], experiment_columns: list[str]) -> list[dict]:
    kept: list[dict] = []
    for row in rows:
        if all(str(row.get(f"target_{c}") or "").strip() for c in experiment_columns):
            kept.append(row)
    dropped = len(rows) - len(kept)
    logger.info(
        f"complete GT: {len(kept):,}/{len(rows):,} rows "
        f"(dropped {dropped:,} with any empty clean cell)"
    )
    return kept


def assign_ids(rows: list[dict]) -> list[dict]:
    out = []
    for row in rows:
        new = dict(row)
        new["id"] = str(uuid.uuid4())
        out.append(new)
    return out


def write_csv(path: Path, rows: list[dict], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({c: row.get(c) or "" for c in columns})


def write_flat_dataset(
    dataset_dir: Path,
    rows: list[dict],
    experiment_columns: list[str],
    provenance_columns: list[str],
    extra_id_columns: tuple[str, ...] = (),
) -> None:
    rows = keep_complete_gt(rows, experiment_columns)
    dirty_cols = ["id"] + list(experiment_columns) + ["provenance_graph_iri"]
    clean_map = {f"target_{c}": c for c in experiment_columns}
    clean_cols = ["id"] + list(clean_map.values())
    prov_cols = ["id"] + list(provenance_columns)

    dirty_rows = [{c: r.get(c) for c in dirty_cols} for r in rows]
    clean_rows = []
    for r in rows:
        out = {"id": r["id"]}
        for src, dest in clean_map.items():
            out[dest] = r.get(src)
        clean_rows.append(out)
    extra_cols = (
        ["id"]
        + list(experiment_columns)
        + [f"target_{c}" for c in experiment_columns]
        + list(provenance_columns)
    )

    write_csv(dataset_dir / "values_experiment.csv", dirty_rows, dirty_cols)
    write_csv(dataset_dir / "targets_experiment.csv", clean_rows, clean_cols)
    write_csv(dataset_dir / "values.csv", rows, dirty_cols + list(extra_id_columns))
    write_csv(
        dataset_dir / "targets.csv",
        [
            {**{clean_map[s]: r.get(s) for s in clean_map}, "id": r["id"],
             **{c: r.get(c) for c in extra_id_columns}}
            for r in rows
        ],
        clean_cols + list(extra_id_columns),
    )
    write_csv(dataset_dir / "provenance.csv", rows, prov_cols)
    write_csv(dataset_dir / "dataset_full.csv", rows, extra_cols)


def read_csv(path: Path) -> list[dict]:
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def deduplicate_by_dirty(
    dirty: list[dict],
    clean: list[dict],
    provenance: list[dict],
    experiment_columns: list[str],
) -> tuple[list[dict], list[dict], list[dict], list[str]]:
    dirty_by_id = {r["id"]: r for r in dirty}
    clean_by_id = {r["id"]: r for r in clean}
    prov_by_id = {r["id"]: r for r in provenance}
    sig_fields = [c for c in experiment_columns if c in (dirty[0].keys() if dirty else [])]
    seen: set[tuple] = set()
    kept_ids: list[str] = []
    removed: list[str] = []
    for row in dirty:
        sig = tuple((k, _dedup_value(row.get(k, ""))) for k in sig_fields)
        if sig in seen:
            removed.append(row["id"])
            continue
        seen.add(sig)
        kept_ids.append(row["id"])
    kept_dirty = [dirty_by_id[i] for i in kept_ids]
    kept_clean = [clean_by_id[i] for i in kept_ids if i in clean_by_id]
    kept_prov = [prov_by_id[i] for i in kept_ids if i in prov_by_id]
    return kept_dirty, kept_clean, kept_prov, removed


def merge_flat_datasets(
    pack_dir: Path,
    out_dir: Path,
    experiment_columns: list[str],
    subset_names: list[str] | None = None,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    if subset_names is not None:
        subset_dirs = [pack_dir / name for name in subset_names if (pack_dir / name).is_dir()]
    else:
        subset_dirs = [d for d in sorted(pack_dir.iterdir()) if d.is_dir()]
    if not subset_dirs:
        logger.error(f"No subset dirs in {pack_dir}")
        return

    dirty_frames: list[dict] = []
    clean_frames: list[dict] = []
    prov_frames: list[dict] = []
    for subset_dir in subset_dirs:
        dpath = subset_dir / "values_experiment.csv"
        cpath = subset_dir / "targets_experiment.csv"
        ppath = subset_dir / "provenance.csv"
        if not dpath.exists():
            logger.warning(f"Skip missing {dpath}")
            continue
        dirty_frames.extend(read_csv(dpath))
        clean_frames.extend(read_csv(cpath) if cpath.exists() else [])
        for row in read_csv(ppath) if ppath.exists() else []:
            row["source_subset"] = subset_dir.name
            prov_frames.append(row)

    dirty, clean, prov, removed = deduplicate_by_dirty(
        dirty_frames, clean_frames, prov_frames, experiment_columns
    )
    value_cols = ["id"] + list(experiment_columns)
    write_csv(
        out_dir / "merged_values_experiment.csv",
        dirty,
        value_cols if dirty else ["id"],
    )
    write_csv(
        out_dir / "merged_targets_experiment.csv",
        clean,
        list(clean[0].keys()) if clean else ["id"],
    )
    write_csv(out_dir / "merged_provenance.csv", prov, list(prov[0].keys()) if prov else ["id"])
    write_csv(out_dir / "duplicates.csv", [{"id": i} for i in removed], ["id"])
    logger.info(
        f"{len(dirty)} dirty / {len(clean)} clean "
        f"({len(removed)} dirty-dupes dropped) -> {out_dir}/merged_*"
    )
