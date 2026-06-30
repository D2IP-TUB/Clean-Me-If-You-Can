"""
Minimal N-Quads parser for WDC schema.org data.

Each line: subject predicate object graph .
Subject/object: <uri> | _:blankId | "literal"^^<datatype>|@lang
"""

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


# Schema.org PostalAddress type IRIs (http and https); with and without angle brackets
RDF_TYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"
RDF_TYPE_IRIS = (RDF_TYPE, f"<{RDF_TYPE}>")
_POSTAL_IRIS = (
    "http://schema.org/PostalAddress",
    "https://schema.org/PostalAddress",
)
POSTAL_ADDRESS_TYPES = _POSTAL_IRIS + tuple(f"<{u}>" for u in _POSTAL_IRIS)

# Map predicate IRIs to short names for address object (with and without angle brackets)
# Core address
_ADDRESS_KEYS = {
    "http://schema.org/streetAddress": "streetAddress",
    "http://schema.org/addressLocality": "addressLocality",
    "http://schema.org/postalCode": "postalCode",
    "http://schema.org/addressRegion": "addressRegion",
    "http://schema.org/addressCountry": "addressCountry",
    # PostalAddress extras
    "http://schema.org/extendedAddress": "extendedAddress",
    "http://schema.org/postOfficeBoxNumber": "postOfficeBoxNumber",
    # ContactPoint (inherited)
    "http://schema.org/telephone": "telephone",
    "http://schema.org/email": "email",
    "http://schema.org/faxNumber": "faxNumber",
    "http://schema.org/areaServed": "areaServed",
    "http://schema.org/availableLanguage": "availableLanguage",
    "http://schema.org/contactType": "contactType",
    # Thing (inherited)
    "http://schema.org/name": "name",
    "http://schema.org/description": "description",
    "http://schema.org/url": "url",
    "http://schema.org/alternateName": "alternateName",
    "http://schema.org/identifier": "identifier",
}
ADDRESS_PREDICATES = dict(_ADDRESS_KEYS)
for k, v in list(_ADDRESS_KEYS.items()):
    ADDRESS_PREDICATES[f"<{k}>"] = v
ADDRESS_PREDICATES.update({
    "https://schema.org/streetAddress": "streetAddress",
    "https://schema.org/addressLocality": "addressLocality",
    "https://schema.org/postalCode": "postalCode",
    "https://schema.org/addressRegion": "addressRegion",
    "https://schema.org/addressCountry": "addressCountry",
    "https://schema.org/extendedAddress": "extendedAddress",
    "https://schema.org/postOfficeBoxNumber": "postOfficeBoxNumber",
    "https://schema.org/telephone": "telephone",
    "https://schema.org/email": "email",
    "https://schema.org/faxNumber": "faxNumber",
    "https://schema.org/areaServed": "areaServed",
    "https://schema.org/availableLanguage": "availableLanguage",
    "https://schema.org/contactType": "contactType",
    "https://schema.org/name": "name",
    "https://schema.org/description": "description",
    "https://schema.org/url": "url",
    "https://schema.org/alternateName": "alternateName",
    "https://schema.org/identifier": "identifier",
})
for k in list(ADDRESS_PREDICATES.keys()):
    if k.startswith("https://") and f"<{k}>" not in ADDRESS_PREDICATES:
        ADDRESS_PREDICATES[f"<{k}>"] = ADDRESS_PREDICATES[k]

# --- vCard (W3C 2006) for microformat html-mf-adr ---
# https://www.w3.org/2006/vcard/ns-2006.html
VCARD_NS = "http://www.w3.org/2006/vcard/ns#"
_VCARD_ADDRESS_IRIS = (f"{VCARD_NS}Address",)
VCARD_ADDRESS_TYPES = _VCARD_ADDRESS_IRIS + tuple(f"<{u}>" for u in _VCARD_ADDRESS_IRIS)
_VCARD_KEYS = {
    f"{VCARD_NS}street-address": "streetAddress",
    f"{VCARD_NS}locality": "addressLocality",
    f"{VCARD_NS}region": "addressRegion",
    f"{VCARD_NS}postal-code": "postalCode",
    f"{VCARD_NS}country-name": "addressCountry",
    f"{VCARD_NS}extended-address": "extendedAddress",
}
VCARD_ADDRESS_PREDICATES = dict(_VCARD_KEYS)
for k, v in list(_VCARD_KEYS.items()):
    VCARD_ADDRESS_PREDICATES[f"<{k}>"] = v

# Parent entity name (for record "name" field)
NAME_PREDICATES = (
    "http://schema.org/name",
    "https://schema.org/name",
    "http://schema.org/legalName",
    "https://schema.org/legalName",
    "<http://schema.org/name>",
    "<https://schema.org/name>",
    "<http://schema.org/legalName>",
    "<https://schema.org/legalName>",
)
ADDRESS_PREDICATE = "http://schema.org/address"
ADDRESS_PREDICATE_HTTPS = "https://schema.org/address"
ADDRESS_PREDICATE_IRIS = (
    ADDRESS_PREDICATE,
    ADDRESS_PREDICATE_HTTPS,
    f"<{ADDRESS_PREDICATE}>",
    f"<{ADDRESS_PREDICATE_HTTPS}>",
)

# Parent entity (e.g. LocalBusiness) properties to copy into data alongside address
# Keys: predicate IRI (with <...> variants added below); value: key in output data
_PARENT_KEYS = {
    "http://schema.org/telephone": "telephone",
    "http://schema.org/email": "email",
    "http://schema.org/url": "url",
    "http://schema.org/sameAs": "sameAs",
    "http://schema.org/openingHours": "openingHours",
    "http://schema.org/latitude": "latitude",
    "http://schema.org/longitude": "longitude",
}
PARENT_ENTITY_PREDICATES = dict(_PARENT_KEYS)
for k, v in list(_PARENT_KEYS.items()):
    PARENT_ENTITY_PREDICATES[f"<{k}>"] = v
PARENT_ENTITY_PREDICATES.update({
    "https://schema.org/telephone": "telephone",
    "https://schema.org/email": "email",
    "https://schema.org/url": "url",
    "https://schema.org/sameAs": "sameAs",
    "https://schema.org/openingHours": "openingHours",
    "https://schema.org/latitude": "latitude",
    "https://schema.org/longitude": "longitude",
})
for k in list(PARENT_ENTITY_PREDICATES.keys()):
    if k.startswith("https://") and f"<{k}>" not in PARENT_ENTITY_PREDICATES:
        PARENT_ENTITY_PREDICATES[f"<{k}>"] = PARENT_ENTITY_PREDICATES[k]


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
    # graph is the 4th term; in WDC it's always <https://...>
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
    return Quad(subject=subject, predicate=predicate, object=obj, graph=graph, object_lang=object_lang)


def strip_literal(value: str) -> str:
    """Remove quotes and unescape a literal."""
    if not value or (value[0] != '"' and value[0] != "'"):
        return value
    if len(value) >= 2:
        value = value[1:-1]
    value = value.replace("\\n", "\n").replace("\\t", "\t").replace('\\"', '"')
    return _fix_mojibake(value)


def _fix_mojibake(s: str) -> str:
    """Fix UTF-8 text that was incorrectly decoded as Latin-1/CP1252 (e.g. Cyrillic mojibake)."""
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
