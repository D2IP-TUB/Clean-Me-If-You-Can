"""
Domain-specific KATARA detect + correct.

Faithful Python port of SimplifiedPatternDiscovery.usingDomainSpecificKB
from the REDS Java KATARA (Chu et al.). The YAGO/DBpedia interactive path
is not used; only the domain-specific KB directory is.

Type rule
  A column is typed by the first .type.txt / .rel.txt subject-set whose
  coverage is strictly greater than `type_coverage` (Java default 0.2).
  Values outside that set are detections with an empty repair.

Pair rule
  A column pair (i, j) is constrained by every relation whose
  subject→object matches cover at least `pair_coverage` of rows (Java
  default 0.15). Every non-matching row flags both cells. If the subject
  is in the KB, the mapped object is the repair for column j.

Type and pair matching are both case-insensitive when `ignore_case` is
true (the default). The KB still supplies the repair string as stored.
"""

from __future__ import annotations

import os
import pickle
from collections import defaultdict
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple


Cell = Tuple[int, int]
KB = Tuple[List[Set[str]], Dict[str, Dict[str, str]]]

_KB_MEMO: Dict[str, KB] = {}


def _read_lines(path: str) -> Iterable[str]:
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            yield line.rstrip("\n\r")


def load_domain_specific_kb(kb_dir: str, cache_path: Optional[str] = None) -> KB:
    """Load every *.type.txt and *.rel.txt under kb_dir (sorted by name)."""
    kb_dir = os.path.abspath(kb_dir)
    if kb_dir in _KB_MEMO:
        return _KB_MEMO[kb_dir]
    if not os.path.isdir(kb_dir):
        raise FileNotFoundError(f"KATARA KB directory not found: {kb_dir}")

    if cache_path is None:
        cache_path = os.path.join(os.path.dirname(kb_dir), ".katara_kb_cache.pkl")
    signature = _kb_signature(kb_dir)
    if cache_path and os.path.exists(cache_path):
        try:
            with open(cache_path, "rb") as f:
                cached = pickle.load(f)
            if cached.get("signature") == signature:
                kb = (cached["types"], cached["rels"])
                _KB_MEMO[kb_dir] = kb
                return kb
        except Exception:
            pass

    types: List[Set[str]] = []
    rels: Dict[str, Dict[str, str]] = {}
    for name in sorted(os.listdir(kb_dir)):
        path = os.path.join(kb_dir, name)
        if not os.path.isfile(path):
            continue
        if name.endswith(".type.txt"):
            types.append(set(_read_lines(path)))
        elif name.endswith(".rel.txt"):
            subjects: Set[str] = set()
            for line in _read_lines(path):
                parts = line.split("\t")
                if len(parts) < 3:
                    continue
                sub, pred, obj = parts[0], parts[1], parts[2]
                subjects.add(sub)
                rels.setdefault(pred, {})[sub] = obj
            types.append(subjects)

    if cache_path:
        try:
            os.makedirs(os.path.dirname(cache_path) or ".", exist_ok=True)
            with open(cache_path, "wb") as f:
                pickle.dump(
                    {"signature": signature, "types": types, "rels": rels},
                    f,
                    protocol=pickle.HIGHEST_PROTOCOL,
                )
        except OSError:
            pass

    kb = (types, rels)
    _KB_MEMO[kb_dir] = kb
    return kb


def _kb_signature(kb_dir: str) -> Tuple[str, int, int, int]:
    names = [
        name
        for name in os.listdir(kb_dir)
        if name.endswith(".type.txt") or name.endswith(".rel.txt")
    ]
    n = 0
    newest = 0
    total = 0
    for name in names:
        st = os.stat(os.path.join(kb_dir, name))
        n += 1
        newest = max(newest, int(st.st_mtime))
        total += int(st.st_size)
    return (os.path.abspath(kb_dir), n, newest, total)


def detect_and_correct(
    rows: Sequence[Sequence[str]],
    types_list: Sequence[Set[str]],
    rel2sub2obj: Mapping[str, Mapping[str, str]],
    type_coverage: float = 0.2,
    pair_coverage: float = 0.15,
    ignore_case: bool = True,
) -> Tuple[Dict[Cell, str], Dict[Cell, str]]:
    """
    Return (detected_cells, corrected_cells).

    detected_cells maps every flagged (row, col) to the proposed repair or "".
    corrected_cells contains only cells with a non-empty KB repair.
    """
    detected: Dict[Cell, str] = {}
    corrected: Dict[Cell, str] = {}
    if not rows:
        return detected, corrected
    n_rows = len(rows)
    n_cols = len(rows[0])
    if n_rows == 0 or n_cols == 0:
        return detected, corrected

    _detect_types(
        rows, types_list, detected, type_coverage, ignore_case, n_rows, n_cols
    )
    _detect_pairs(
        rows,
        rel2sub2obj,
        detected,
        corrected,
        pair_coverage,
        ignore_case,
        n_rows,
        n_cols,
    )
    return detected, corrected


def remap_cells(
    cells: Mapping[Cell, str], col_index: Sequence[int]
) -> Dict[Cell, str]:
    """Map subset-column indices back onto the full table."""
    return {(i, col_index[j]): v for (i, j), v in cells.items()}


def _detect_types(
    rows: Sequence[Sequence[str]],
    types_list: Sequence[Set[str]],
    detected: Dict[Cell, str],
    type_coverage: float,
    ignore_case: bool,
    n_rows: int,
    n_cols: int,
) -> None:
    for col in range(n_cols):
        values = [str(row[col]) for row in rows]
        for domain_values in types_list:
            if ignore_case:
                lower = {v.lower() for v in domain_values}
                count = sum(
                    1
                    for value in values
                    if value.lower() in lower or value in domain_values
                )
            else:
                count = sum(1 for value in values if value in domain_values)
            if (count / n_rows) <= type_coverage:
                continue
            if ignore_case:
                lower = {v.lower() for v in domain_values}
                for row_i, value in enumerate(values):
                    if value.lower() in lower or value in domain_values:
                        continue
                    detected[(row_i, col)] = ""
            else:
                for row_i, value in enumerate(values):
                    if value in domain_values:
                        continue
                    detected[(row_i, col)] = ""
            break


def _detect_pairs(
    rows: Sequence[Sequence[str]],
    rel2sub2obj: Mapping[str, Mapping[str, str]],
    detected: Dict[Cell, str],
    corrected: Dict[Cell, str],
    pair_coverage: float,
    ignore_case: bool,
    n_rows: int,
    n_cols: int,
) -> None:
    if not rel2sub2obj:
        return

    def _key(value: str) -> str:
        return value.lower() if ignore_case else value

    sub_index: Dict[str, List[Tuple[str, str]]] = defaultdict(list)
    lookups: Dict[str, Dict[str, str]] = {}
    for rel in sorted(rel2sub2obj):
        lookup = {}
        for sub, obj in rel2sub2obj[rel].items():
            lookup[_key(sub)] = obj
            sub_index[_key(sub)].append((rel, obj))
        lookups[rel] = lookup

    for i in range(n_cols):
        for j in range(n_cols):
            if i == j:
                continue
            counts: Dict[str, int] = defaultdict(int)
            for row in rows:
                subject = _key(str(row[i]))
                obj = _key(str(row[j]))
                for rel, mapped in sub_index.get(subject, ()):
                    if _key(mapped) == obj:
                        counts[rel] += 1
            for rel in sorted(counts):
                if (counts[rel] / n_rows) < pair_coverage:
                    continue
                mapping = lookups[rel]
                for row_i, row in enumerate(rows):
                    subject = _key(str(row[i]))
                    obj = _key(str(row[j]))
                    if subject in mapping and _key(mapping[subject]) == obj:
                        continue
                    detected.setdefault((row_i, i), "")
                    if subject in mapping:
                        repair = mapping[subject]
                        detected[(row_i, j)] = repair
                        corrected[(row_i, j)] = repair
                    else:
                        detected.setdefault((row_i, j), "")
