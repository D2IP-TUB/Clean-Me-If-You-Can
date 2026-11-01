import csv
from pathlib import Path

from eval_by_error_type import evaluate, load_cell_error_types, parse_error_types


def test_parse_error_types_splits_pipe_and_drops_clean():
    assert parse_error_types("Typo|Token_Subset") == ["Typo", "Token_Subset"]
    assert parse_error_types("Abbreviation") == ["Abbreviation"]
    assert parse_error_types("Clean") == []
    assert parse_error_types("Abbreviation|Formatting") == ["Abbreviation", "Formatting"]


def _write_csv(path: Path, fieldnames, rows):
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


def test_multilabel_cell_is_counted_in_every_type(tmp_path):
    labels = tmp_path / "cell_labels.csv"
    cells = tmp_path / "cells.csv"
    _write_csv(
        labels,
        ["row_index", "feature", "dirty_value", "clean_value", "labels"],
        [
            {"row_index": 0, "feature": "road", "dirty_value": "st",
             "clean_value": "street", "labels": "Typo|Token_Subset"},
            {"row_index": 1, "feature": "road", "dirty_value": "st",
             "clean_value": "street", "labels": "Typo"},
            {"row_index": 2, "feature": "name", "dirty_value": "ok",
             "clean_value": "ok", "labels": "Clean"},
        ],
    )
    _write_csv(
        cells,
        ["row_id", "col_name", "is_actual_error",
         "det_tp", "det_fp", "det_fn", "cor_tp", "cor_fp", "cor_fn"],
        [
            {"row_id": 0, "col_name": "road", "is_actual_error": 1,
             "det_tp": 1, "det_fp": 0, "det_fn": 0, "cor_tp": 1, "cor_fp": 0, "cor_fn": 0},
            {"row_id": 1, "col_name": "road", "is_actual_error": 1,
             "det_tp": 0, "det_fp": 0, "det_fn": 1, "cor_tp": 0, "cor_fp": 0, "cor_fn": 1},
            {"row_id": 2, "col_name": "name", "is_actual_error": 0,
             "det_tp": 0, "det_fp": 0, "det_fn": 0, "cor_tp": 0, "cor_fp": 0, "cor_fn": 0},
        ],
    )

    cell_dict = load_cell_error_types(labels)
    df = evaluate(str(cells), cell_dict).set_index("error_type")

    assert int(df.loc["Typo", "n_cells"]) == 2
    assert int(df.loc["Token_Subset", "n_cells"]) == 1
    assert int(df.loc["Typo", "det_tp"]) == 1
    assert int(df.loc["Token_Subset", "det_tp"]) == 1
    assert int(df.loc["Typo", "cor_tp"]) == 1
    assert int(df.loc["Token_Subset", "cor_tp"]) == 1
    assert "Typo|Token_Subset" not in df.index


def test_load_accepts_legacy_error_type_column(tmp_path):
    legacy = tmp_path / "cell_error_types.csv"
    _write_csv(
        legacy,
        ["row_index", "feature", "dirty_value", "clean_value", "error_type"],
        [{"row_index": 0, "feature": "road", "dirty_value": "st",
          "clean_value": "street", "error_type": "Typo"}],
    )
    assert load_cell_error_types(legacy)[(0, "road")] == ["Typo"]
