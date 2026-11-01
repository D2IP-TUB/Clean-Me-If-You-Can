"""Extract an IMDb tt id from schema.org fields."""

from __future__ import annotations

import re
from typing import Any

IMDB_ID_RE = re.compile(r"imdb\.com/title/(tt\d+)", re.IGNORECASE)


def _flatten_to_strings(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        out: list[str] = []
        for v in value:
            out.extend(_flatten_to_strings(v))
        return out
    if isinstance(value, dict):
        s = value.get("@id") or value.get("url") or value.get("@value")
        return [str(s)] if s else []
    return [str(value)]


def extract_imdb_id(data: dict) -> str | None:
    for key in ("sameAs", "identifier"):
        value = data.get(key)
        for text in _flatten_to_strings(value):
            m = IMDB_ID_RE.search(text)
            if m:
                return m.group(1)
    return None
