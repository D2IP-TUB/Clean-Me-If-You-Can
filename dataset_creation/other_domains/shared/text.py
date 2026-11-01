"""Flatten extracted values to strings."""

from __future__ import annotations

import re
from typing import Any


def ensure_string(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        s = re.sub(r"\s+", " ", value).strip()
        return s or None
    if isinstance(value, dict):
        if "@value" in value:
            return ensure_string(value.get("@value"))
        return ensure_string(value.get("name"))
    if isinstance(value, list):
        parts = [ensure_string(v) for v in value]
        joined = ", ".join(p for p in parts if p)
        return joined or None
    if isinstance(value, (int, float)):
        return str(value)
    return None
