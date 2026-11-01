"""N-Quads parser for WDC schema.org data."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator


@dataclass(frozen=True)
class Quad:
    subject: str
    predicate: str
    object: str
    graph: str
    object_lang: str | None = None  # language tag from literal, e.g. "ru-RU"


RDF_TYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"
RDF_TYPE_IRIS = (RDF_TYPE, f"<{RDF_TYPE}>")


def schema_org_iris(local_name: str) -> tuple[str, ...]:
    """http/https schema.org IRIs, with and without angle brackets."""
    http = f"http://schema.org/{local_name}"
    https = f"https://schema.org/{local_name}"
    return (http, https, f"<{http}>", f"<{https}>")


def _parse_term(line: str, start: int) -> tuple[str, int, str | None]:
    """Parse one term. Returns (value, next_index, language_tag or None for literals with @lang)."""
    i = start
    while i < len(line) and line[i] in " \t":
        i += 1
    if i >= len(line):
        return "", i, None
    if line[i] == "<":
        gt = line.find(">", i)
        if gt == -1:
            return "", len(line), None
        end = gt + 1
        return line[i:end], end, None
    if line[i] == "_" and line[i : i + 2] == "_:":
        j = i + 2
        while j < len(line) and line[j] not in " \t":
            j += 1
        return line[i:j], j, None
    if line[i] == '"':
        j = i + 1
        literal_end = None
        lang: str | None = None
        while j < len(line):
            if line[j] == "\\" and j + 1 < len(line):
                j += 2
                continue
            if line[j] == '"':
                literal_end = j + 1
                j += 1
                while j < len(line) and line[j] in " \t":
                    j += 1
                if j < len(line) and line[j] in "@^":
                    if line[j] == "^" and line[j : j + 2] == "^^":
                        gt = line.find(">", j)
                        k = gt + 1 if gt != -1 else j + 2
                        j = k
                    elif line[j] == "@":
                        j += 1
                        lang_start = j
                        while j < len(line) and line[j] not in " \t":
                            j += 1
                        lang = line[lang_start:j]
                    while j < len(line) and line[j] in " \t":
                        j += 1
                break
            j += 1
        if literal_end is not None:
            return line[i:literal_end], j, lang
        return line[i:j], j, None
    j = i
    while j < len(line) and line[j] not in " \t":
        j += 1
    return line[i:j], j, None


def parse_nquads_line(line: str) -> Quad | None:
    """Parse a single N-Quads line. Returns None for blank or invalid lines."""
    line = line.rstrip()
    if not line or line[-1] != ".":
        return None
    line = line[:-1].rstrip()  # remove trailing .
    if not line:
        return None
    last_angle = line.rfind("<")
    if last_angle == -1:
        return None
    gt = line.find(">", last_angle)
    if gt == -1:
        return None
    graph_end = gt + 1
    graph = line[last_angle:graph_end]
    rest = line[:last_angle].rstrip()
    if not rest:
        return None
    pos = 0
    subject, pos, _ = _parse_term(rest, pos)
    if not subject or pos >= len(rest):
        return None
    predicate, pos, _ = _parse_term(rest, pos)
    if not predicate or pos >= len(rest):
        return None
    obj, _, object_lang = _parse_term(rest, pos)
    return Quad(
        subject=subject,
        predicate=predicate,
        object=obj,
        graph=graph,
        object_lang=object_lang,
    )


def strip_literal(value: str) -> str:
    """Remove quotes and unescape a literal."""
    if not value or (value[0] != '"' and value[0] != "'"):
        return value
    if len(value) >= 2:
        value = value[1:-1]
    value = value.replace("\\n", "\n").replace("\\t", "\t").replace('\\"', '"')
    return _fix_mojibake(value)


def _fix_mojibake(s: str) -> str:
    """Fix UTF-8 text that was incorrectly decoded as Latin-1/CP1252."""
    try:
        import ftfy

        return ftfy.fix_text(s)
    except ImportError:
        pass
    try:
        return s.encode("latin-1").decode("utf-8")
    except (UnicodeDecodeError, UnicodeEncodeError):
        return s


def parse_nquads_stream(lines: Iterator[str]) -> Iterator[Quad]:
    """Yield parsed quads from an iterator of lines."""
    for line in lines:
        quad = parse_nquads_line(line)
        if quad is not None:
            yield quad
