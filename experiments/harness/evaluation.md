# Evaluation algorithm

All systems are scored by `evaluate.py`. The cell-level rules match
`raha.dataset.Dataset.get_data_cleaning_evaluation`. Labeled training rows
are **not** held out.

Source: [`evaluate.py`](evaluate.py).

## Inputs

| Name | Meaning |
|---|---|
| `dirty_df` | Dirty table. Column order is the index used in cell keys. |
| `clean_df` | Ground-truth table, same shape. |
| `detected_cells` | `{(row, col_idx): proposed_value_or_""}` — cells the system flags. |
| `corrected_cells` | `{(row, col_idx): corrected_value}` or empty / `None`. |
| `labeled_rows` | Row indices used for training. Recorded only; not excluded. |

A cell is the pair `(row_index, column_index)`.

Full-table repair systems (Horizon, HoloClean, UniClean) first turn the
repaired CSV into `corrected_cells` with `diff_repaired`: every cell whose
normalized repaired value differs from the dirty value.

## 1. Normalize

Every string comparison uses `normalize`:

1. HTML-unescape.
2. Collapse tabs, newlines, and spaces to a single space.
3. Strip leading/trailing whitespace.
4. Lowercase with `str.lower` (not `casefold`, so German `ẞ` stays distinct from `ss`).

Case-only differences are not errors.

## 2. Gold errors

```
actual_errors[(i, j)] = normalize(clean[i, j])
    for every cell where normalize(dirty[i, j]) != normalize(clean[i, j])
```

- `n_actual = |actual_errors|`
- A clean cell is any cell not in `actual_errors`.

## 3. Precision / recall / F1

```
P = 0                  if n_pred   == 0 else TP / n_pred
R = 0                  if n_actual == 0 else TP / n_actual
F1 = 0                 if P + R    == 0 else 2PR / (P + R)
```

Empty predictions and empty gold sets score as zeros, not NaN.

## 4. Detection

A detection is a key present in `detected_cells`. The proposed string is
ignored for detection (an empty proposal still counts as a flag).

```
TP_det = |{ cell in detected_cells | cell in actual_errors }|
n_pred_det = |detected_cells|

det_precision = TP_det / n_pred_det
det_recall    = TP_det / n_actual
det_f1        = harmonic mean
```

| | Gold error | Gold clean |
|---|---|---|
| Flagged | TP | FP |
| Not flagged | FN | TN (unused) |

So detection precision is “of the cells you flagged, how many were actually dirty.”
A system that flags many clean cells gets low precision even when recall is high.

### Detection-only variant

`evaluate_detection()` scores the same detection formula and does not
compute correction. The string stored in `detected_cells` is recorded as
`det_signal` only; it is never compared to gold.

## 5. Correction

Two modes. If `corrected_cells` is non-empty, use the **separate-dict**
mode. Otherwise fall back to the **detection-proposal** mode (Raha-style:
the detection dict also carries a repair string).

### Separate `corrected_cells` (Horizon, HoloClean, UniClean, …)

Corrections on **clean** cells are ignored. They are neither TP nor FP.

```
TP_cor = |{ cell in corrected_cells
            | cell in actual_errors
            and normalize(corrected_cells[cell]) == actual_errors[cell] }|

n_pred_cor = |{ cell in corrected_cells | cell in actual_errors }|

cor_precision = TP_cor / n_pred_cor
cor_recall    = TP_cor / n_actual
```

| System wrote a value | Gold error, value matches clean | Gold error, value wrong | Gold clean |
|---|---|---|---|
| Yes | TP | counted in `n_pred_cor` but not TP (hurts P) | ignored |
| No | FN (hurts R) | FN | ignored |

`cor_recall` is over **all gold errors**, not over detected errors. An
undetected dirty cell is a correction FN.

### Detection-proposal fallback (`corrected_cells` empty)

```
TP_cor = |{ cell in detected_cells
            | cell in actual_errors
            and proposed != ""
            and normalize(proposed) == actual_errors[cell] }|

n_pred_cor = |detected_cells|     # same denominator as detection
```

A flag with an empty proposal cannot be a correction TP.

## 6. Per-column scores

The same formulas, restricted to cells with that `col_idx`.

- `n_actual` = gold errors in the column.
- `n_pred` (detection) = flagged cells in the column.
- `n_pred` (correction, separate-dict) = corrected cells in the column that are gold errors.
- A column with no gold errors and no predictions scores P = R = F1 = 0.

Written to `column_metrics.csv` and as `det_f1_<col>`, `cor_precision_<col>`, … on the summary.

## 7. Outputs

Each run directory gets:

| File | Contents |
|---|---|
| `summary.csv` | Overall P/R/F1, counts, runtime, plus flattened per-column keys |
| `column_metrics.csv` | One row per column |
| `cells.csv` | Every cell: dirty/clean, det/cor flags, TP/FP/FN bits |
| `run_config.json` | Run metadata |

`cells.csv` correction bits on a **clean** cell that the system rewrote
are all 0 (ignored). An untouched gold error is `cor_fn = 1`.
