"""CSV helpers: keep every cell as the literal string from the file."""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Iterable

import pandas as pd


def read_csv_as_strings(
    path: Path,
    usecols: Iterable[str] | None = None,
    **kwargs,
) -> pd.DataFrame:
    return pd.read_csv(
        path,
        dtype=str,
        keep_default_na=False,
        na_filter=False,
        usecols=list(usecols) if usecols is not None else None,
        **kwargs,
    )


def norm_name(value: str) -> str:
    value = re.sub(r"\s+", " ", value).strip().casefold()
    value = value.replace(".", "")
    value = value.replace("œ", "oe").replace("æ", "ae")
    value = re.sub(r"\s*/\s*", "/", value)
    return value


def strip_marks(value: str) -> str:
    """Drop combining accents so É/E and Ç/C compare equal."""
    decomposed = unicodedata.normalize("NFD", value or "")
    return unicodedata.normalize(
        "NFC", "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    )


def count_marks(value: str) -> int:
    """Accents plus apostrophes: the marks a gazetteer tends to lose."""
    decomposed = unicodedata.normalize("NFD", value or "")
    return sum(1 for ch in decomposed if unicodedata.combining(ch) or ch in "'’`")


def loose_name(value: str) -> str:
    """Fold hyphens, apostrophes, and accents."""
    value = norm_name(value).replace("’", "'").replace("`", "'")
    value = strip_marks(value)
    value = value.replace("'", "")
    value = value.replace("-", " ")
    return re.sub(r"\s+", " ", value).strip()


def in_native_script(value: str, country_code: str) -> bool:
    """True when every letter is Latin."""
    if not country_code:
        return False
    for ch in value or "":
        if not ch.isalpha():
            continue
        if not unicodedata.name(ch, "").startswith("LATIN"):
            return False
    return True


def richer_spelling(canonical: str, *sources: str) -> str:
    """Keep a source spelling that has more accents or apostrophes than the gazetteer.

    A gazetteer form that dropped accents or apostrophes does not replace a
    source that still has them. An all-capitals scrape is not a spelling source.
    """
    best = canonical
    for source in sources:
        raw = re.sub(r"\s+", " ", source or "").strip()
        if not raw or raw.isupper():
            continue
        if loose_name(raw) != loose_name(best):
            continue
        plain = lambda text: re.sub(r"['’`]", "", strip_marks(text)).casefold()
        if count_marks(raw) > count_marks(best) and plain(raw) == plain(best):
            best = raw
    return best


def norm_postcode(value: str) -> str:
    return re.sub(r"\s+", "", value).strip().upper()


def bilingual_parts(value: str) -> list[str]:
    if not value:
        return []
    parts = [p.strip() for p in re.split(r"\s*/\s*", value)]
    return [p for p in parts if p]


def bilingual_first(value: str) -> str:
    parts = bilingual_parts(value)
    return parts[0] if parts else value.strip()


_ARTICLE = r"(El|La|Los|Las|A|O|As|Os|L['’])"
_TRAILING_PC_UNIT = re.compile(r"\s+\d+$")


def invert_article_name(value: str) -> str | None:
    raw = re.sub(r"\s+", " ", value or "").strip()
    if not raw:
        return None
    comma = re.match(rf"^(.+),\s+{_ARTICLE}$", raw, flags=re.I)
    if comma:
        article = comma.group(2).replace("’", "'")
        return f"{article} {comma.group(1)}".replace("' ", "'")
    leading = re.match(rf"^{_ARTICLE}\s+(.+)$", raw, flags=re.I)
    if leading:
        article = leading.group(1).replace("’", "'")
        return f"{leading.group(2)}, {article}"
    return None


def _name_core(value: str) -> str:
    return _TRAILING_PC_UNIT.sub("", re.sub(r"\s+", " ", value or "").strip())


def names_match(a: str, b: str) -> bool:
    if not a or not b:
        return False
    cores = [_name_core(a), _name_core(b)]
    na, nb = norm_name(cores[0]), norm_name(cores[1])
    if na == nb:
        return True
    a_parts = {norm_name(_name_core(p)) for p in bilingual_parts(a)} or {na}
    b_parts = {norm_name(_name_core(p)) for p in bilingual_parts(b)} or {nb}
    if a_parts & b_parts:
        return True
    fa = {strip_marks(part) for part in a_parts} | {strip_marks(na)}
    fb = {strip_marks(part) for part in b_parts} | {strip_marks(nb)}
    return bool(fa & fb)


def title_locality(value: str) -> str:
    raw = (value or "").strip()
    if raw.isupper() and re.search(r"[A-Z]", raw):
        return raw.title()
    return raw


def refresh_cell_labels(path: Path, field_values: dict[str, list[str]]) -> None:
    """Overwrite clean_value for named address fields using new_row_index order."""
    if not path.exists() or not field_values:
        return
    df = read_csv_as_strings(path)
    if "new_row_index" not in df.columns or "feature" not in df.columns:
        return
    idx = pd.to_numeric(df["new_row_index"], errors="coerce")
    for field, values in field_values.items():
        mask = df["feature"] == field
        mapped = idx.map(lambda i, vals=values: vals[int(i)] if pd.notna(i) and 0 <= int(i) < len(vals) else None)
        take = mask & mapped.notna()
        df.loc[take, "clean_value"] = mapped[take]
    df.to_csv(path, index=False)
