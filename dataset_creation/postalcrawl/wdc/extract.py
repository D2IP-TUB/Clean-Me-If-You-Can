"""
Extract PostalAddress records from WDC N-Quads (schema.org subsets).

Reads part_*.gz or sample .txt files, parses N-Quads, collects all quads per graph,
identifies PostalAddress entities, and emits records compatible with the
postalcrawl validate step (data.address with @type PostalAddress + crawl_metadata.url).
"""

from __future__ import annotations

import gzip
from pathlib import Path
from typing import Iterator

from postalcrawl.record import Record

from postalcrawl.wdc.nquads import (
    ADDRESS_PREDICATE_IRIS,
    ADDRESS_PREDICATES,
    NAME_PREDICATES,
    PARENT_ENTITY_PREDICATES,
    POSTAL_ADDRESS_TYPES,
    RDF_TYPE_IRIS,
    VCARD_ADDRESS_PREDICATES,
    VCARD_ADDRESS_TYPES,
    Quad,
    parse_nquads_line,
    strip_literal,
)


def _open_lines(path: Path) -> Iterator[str]:
    """Yield decoded lines from a file, gzipped or plain."""
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8", errors="replace") as f:
            yield from f
    else:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            yield from f


def _collect_quads_by_graph(lines: Iterator[str]) -> dict[str, list[Quad]]:
    """Group quads by graph (source URL)."""
    by_graph: dict[str, list[Quad]] = {}
    for line in lines:
        quad = parse_nquads_line(line)
        if quad is None:
            continue
        by_graph.setdefault(quad.graph, []).append(quad)
    return by_graph


def _object_to_value(q_object: str, object_lang: str | None = None) -> str | dict | None:
    """Convert quad object to a value: string, or {"@value": s, "@language": lang} when lang is set. None for blank nodes."""
    if not q_object:
        return None
    if q_object.startswith('"') or q_object.startswith("'"):
        s = strip_literal(q_object)
        if object_lang:
            return {"@value": s, "@language": object_lang}
        return s
    if q_object.startswith("<") and q_object.endswith(">"):
        return q_object[1:-1]
    return None


def _address_object_from_quads(quads: list[Quad], subject: str) -> dict | None:
    """Build a schema.org address dict from quads for the given PostalAddress subject."""
    address: dict[str, str | dict] = {"@type": "PostalAddress"}
    for q in quads:
        if q.subject != subject:
            continue
        key = ADDRESS_PREDICATES.get(q.predicate)
        if key is None:
            continue
        value = _object_to_value(q.object, getattr(q, "object_lang", None))
        if value is not None:
            address[key] = value
    # require at least one of the main address fields
    def _has_value(d: dict, k: str) -> bool:
        v = d.get(k)
        return bool(v.get("@value", v) if isinstance(v, dict) else v)
    if not any(_has_value(address, k) for k in ("streetAddress", "addressLocality", "postalCode")):
        return None
    return address


def _address_object_from_quads_vcard(quads: list[Quad], subject: str) -> dict | None:
    """Build a schema.org-shaped address dict from vCard Address quads (same keys as schema.org for pipeline compatibility)."""
    address: dict[str, str | dict] = {"@type": "PostalAddress"}
    for q in quads:
        if q.subject != subject:
            continue
        key = VCARD_ADDRESS_PREDICATES.get(q.predicate)
        if key is None:
            continue
        value = _object_to_value(q.object, getattr(q, "object_lang", None))
        if value is not None:
            address[key] = value
    def _has_value(d: dict, k: str) -> bool:
        v = d.get(k)
        return bool(v.get("@value", v) if isinstance(v, dict) else v)
    if not any(_has_value(address, k) for k in ("streetAddress", "addressLocality", "postalCode")):
        return None
    return address


def _parent_subject_for_address(quads: list[Quad], address_subject: str, graph: str) -> str | None:
    """Find the parent entity subject that has schema.org/address pointing to this address."""
    for q in quads:
        if q.graph != graph or q.predicate not in ADDRESS_PREDICATE_IRIS:
            continue
        if q.object == address_subject:
            return q.subject
    return None


def _parent_name_for_address(
    quads: list[Quad], address_subject: str, graph: str
) -> str | dict | None:
    """Find a parent entity that has schema.org/address pointing to this address; return its name (with @language if present)."""
    parent = _parent_subject_for_address(quads, address_subject, graph)
    if parent is None:
        return None
    for q in quads:
        if q.subject != parent or q.predicate not in NAME_PREDICATES:
            continue
        if q.graph != graph:
            continue
        if q.object.startswith('"') or q.object.startswith("'"):
            return _object_to_value(q.object, getattr(q, "object_lang", None))
    return None


def _parent_entity_properties(
    quads: list[Quad], parent_subject: str, graph: str
) -> dict:
    """Collect parent entity properties (telephone, openingHours, url, etc.) as a flat dict.
    openingHours can be multiple; we store as list of strings."""
    out: dict = {}
    opening_hours: list[str] = []
    for q in quads:
        if q.subject != parent_subject or q.graph != graph:
            continue
        key = PARENT_ENTITY_PREDICATES.get(q.predicate)
        if key is None:
            continue
        value = _object_to_value(q.object, getattr(q, "object_lang", None))
        if value is None:
            continue
        if key == "openingHours":
            opening_hours.append(value)
        else:
            if key not in out:
                out[key] = value
    if opening_hours:
        out["openingHours"] = opening_hours
    return out


def extract_postal_addresses_from_quads(
    quads_by_graph: dict[str, list[Quad]],
    *,
    subset: str | None = None,
    source_file: str | None = None,
    wdc_release: str = "2024-12",
) -> Iterator[Record[dict]]:
    """Yield postalcrawl records (data + crawl_metadata) for each PostalAddress found."""
    for graph, quads in quads_by_graph.items():
        # find all subjects that are of type PostalAddress
        postal_subjects: set[str] = set()
        for q in quads:
            if q.predicate not in RDF_TYPE_IRIS:
                continue
            if q.object not in POSTAL_ADDRESS_TYPES:
                continue
            postal_subjects.add(q.subject)
        for subj in postal_subjects:
            address = _address_object_from_quads(quads, subj)
            if address is None:
                continue
            parent_subject = _parent_subject_for_address(quads, subj, graph)
            name = _parent_name_for_address(quads, subj, graph)
            parent_props = _parent_entity_properties(quads, parent_subject, graph) if parent_subject else {}
            data: dict = {
                "address": address,
                "name": name,
                **parent_props,
            }
            # Provenance: graph (page URL), subset, source file, WDC release
            crawl_metadata: dict = {
                "url": graph.strip("<>"),
                "source": "wdc-nquads",
                "provenance": {
                    "graph_iri": graph.strip("<>"),
                    "wdc_release": wdc_release,
                },
            }
            if subset is not None:
                crawl_metadata["provenance"]["subset"] = subset
            if source_file is not None:
                crawl_metadata["provenance"]["source_file"] = source_file
            yield {
                "data": data,
                "crawl_metadata": crawl_metadata,
            }


def extract_postal_addresses_from_quads_vcard(
    quads_by_graph: dict[str, list[Quad]],
    *,
    subset: str | None = None,
    source_file: str | None = None,
    wdc_release: str = "2024-12",
) -> Iterator[Record[dict]]:
    """Yield postalcrawl records for each vCard Address (html-mf-adr). Same record shape as schema.org path."""
    for graph, quads in quads_by_graph.items():
        address_subjects: set[str] = set()
        for q in quads:
            if q.predicate not in RDF_TYPE_IRIS:
                continue
            if q.object not in VCARD_ADDRESS_TYPES:
                continue
            address_subjects.add(q.subject)
        for subj in address_subjects:
            address = _address_object_from_quads_vcard(quads, subj)
            if address is None:
                continue
            data: dict = {"address": address, "name": None}
            crawl_metadata: dict = {
                "url": graph.strip("<>"),
                "source": "wdc-nquads",
                "provenance": {
                    "graph_iri": graph.strip("<>"),
                    "wdc_release": wdc_release,
                    "format": "html-mf-adr",
                },
            }
            if subset is not None:
                crawl_metadata["provenance"]["subset"] = subset
            if source_file is not None:
                crawl_metadata["provenance"]["source_file"] = source_file
            yield {"data": data, "crawl_metadata": crawl_metadata}


def extract_from_file(
    path: Path,
    *,
    subset: str | None = None,
    source_file: str | None = None,
    wdc_release: str = "2024-12",
    vocabulary: str = "schema",
) -> Iterator[Record[dict]]:
    """Read a single WDC N-Quads file (or .gz) and yield extracted address records.
    vocabulary: 'schema' for class-specific schema.org (part_*.gz), 'vcard' for html-mf-adr (*.nq-*.gz)."""
    lines = _open_lines(path)
    by_graph = _collect_quads_by_graph(lines)
    if vocabulary == "vcard":
        yield from extract_postal_addresses_from_quads_vcard(
            by_graph,
            subset=subset,
            source_file=source_file,
            wdc_release=wdc_release,
        )
    else:
        yield from extract_postal_addresses_from_quads(
            by_graph,
            subset=subset,
            source_file=source_file,
            wdc_release=wdc_release,
        )


def extract_from_directory(
    directory: Path,
    pattern: str = "*.gz",
) -> Iterator[Record[dict]]:
    """Yield records from all matching files under directory (e.g. part_*.gz)."""
    directory = Path(directory)
    if not directory.is_dir():
        return
    for path in sorted(directory.glob(pattern)):
        if path.is_file():
            yield from extract_from_file(path)
