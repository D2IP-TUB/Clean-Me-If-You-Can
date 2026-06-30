import html
from typing import Any


def ensure_string(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        # this case mostly happens when country uses https://schema.org/Country
        return ensure_string(value.get("name"))
    if isinstance(value, list):
        strings = [ensure_string(v) for v in value]
        return ", ".join(s for s in strings if s)
    if isinstance(value, int) or isinstance(value, float):
        return str(value)
    raise TypeError(f"Unsupported type {type(value)}")


def remove_escaped_slashes(value: str) -> str:
    return value.replace("\\/", "/")


def reverse_unicode_escape(s: str) -> str:
    if "\\u" in s.lower():
        return s.encode("utf-8").decode("unicode_escape")
    return s


def html_unescape(s: str) -> str:
    if "&" in s:
        return html.unescape(s)
    return s


def clear_string(value: Any) -> str | None:
    s = ensure_string(value)
    if s is None:
        return None
    s = remove_escaped_slashes(s)
    s = reverse_unicode_escape(s)
    s = html_unescape(s)
    s = s.replace("\n", " ")  # replace newlines with space
    s = s.strip()  # remove leading and trailing whitespace
    if not s:
        return None
    return s
