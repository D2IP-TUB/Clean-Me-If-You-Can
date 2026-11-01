"""Extract schema.org entities from WDC N-Quads."""

from __future__ import annotations

import gzip
from pathlib import Path
from typing import Iterator

from books.schema import BOOK_CONFIG
from movies.schema import MOVIE_CONFIG
from shared.nquads import (
    RDF_TYPE_IRIS,
    Quad,
    parse_nquads_line,
    schema_org_iris,
    strip_literal,
)
from shared.schema import EntityConfig

SUBSET_CONFIGS: dict[str, EntityConfig] = {
    "Book": BOOK_CONFIG,
    "Movie": MOVIE_CONFIG,
}

DOMAIN_SUBSETS: dict[str, frozenset[str]] = {
    "book": frozenset({"Book"}),
    "movies": frozenset({"Movie"}),
}

DOMAINS: dict[str, EntityConfig] = {
    "book": BOOK_CONFIG,
    "movie": MOVIE_CONFIG,
}


def _predicate_map(config: EntityConfig) -> dict[str, str]:
    out: dict[str, str] = {}
    for local, key in config.predicates.items():
        for iri in schema_org_iris(local):
            out[iri] = key
    return out


def _open_lines(path: Path) -> Iterator[str]:
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8", errors="replace") as f:
            yield from f
    else:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            yield from f


def _collect_quads_by_graph(lines: Iterator[str]) -> dict[str, list[Quad]]:
    by_graph: dict[str, list[Quad]] = {}
    for line in lines:
        quad = parse_nquads_line(line)
        if quad is None:
            continue
        by_graph.setdefault(quad.graph, []).append(quad)
    return by_graph


def _object_to_value(q_object: str, object_lang: str | None = None) -> str | dict | None:
    if not q_object:
        return None
    if q_object.startswith('"') or q_object.startswith("'"):
        s = strip_literal(q_object)
        if not s.strip():
            return None
        if object_lang:
            return {"@value": s, "@language": object_lang}
        return s
    if q_object.startswith("<") and q_object.endswith(">"):
        return q_object[1:-1]
    return None


def _plain_text(value: str | dict | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, dict):
        s = value.get("@value")
        return str(s).strip() if s else None
    s = str(value).strip()
    return s or None


def _nested_name(quads: list[Quad], subject: str) -> str | dict | None:
    """Return name/legalName of a nested Person or Organization subject."""
    name_iris = schema_org_iris("name") + schema_org_iris("legalName")
    for q in quads:
        if q.subject != subject or q.predicate not in name_iris:
            continue
        value = _object_to_value(q.object, q.object_lang)
        if _plain_text(value):
            return value
    return None


def _dedupe(values: list) -> list:
    seen: set[str] = set()
    out = []
    for v in values:
        key = repr(v)
        if key in seen:
            continue
        seen.add(key)
        out.append(v)
    return out


def _has_keep_value(data: dict, keys: tuple[str, ...]) -> bool:
    for k in keys:
        v = data.get(k)
        if isinstance(v, list):
            if any(_plain_text(x) for x in v):
                return True
        elif _plain_text(v):
            return True
    return False


def extract_entities_from_quads(
    quads_by_graph: dict[str, list[Quad]],
    config: EntityConfig,
    *,
    subset: str | None = None,
    source_file: str | None = None,
    wdc_release: str = "2024-12",
) -> Iterator[dict]:
    type_iris = set(schema_org_iris(config.type_name))
    pred_map = _predicate_map(config)
    for graph, quads in quads_by_graph.items():
        subjects = {
            q.subject
            for q in quads
            if q.predicate in RDF_TYPE_IRIS and q.object in type_iris
        }
        for subj in subjects:
            data: dict = {"@type": config.type_name}
            buckets: dict[str, list] = {}
            for q in quads:
                if q.subject != subj:
                    continue
                key = pred_map.get(q.predicate)
                if key is None:
                    continue
                if q.object.startswith("_:") or (
                    key in config.nested_keys
                    and q.object.startswith("<")
                    and not q.object.startswith('"')
                ):
                    nested = _nested_name(quads, q.object)
                    if nested is None:
                        continue
                    value = nested
                else:
                    value = _object_to_value(q.object, q.object_lang)
                if value is None:
                    continue
                buckets.setdefault(key, []).append(value)
            for key, vals in buckets.items():
                vals = _dedupe(vals)
                if key in config.multi_keys:
                    data[key] = vals
                elif len(vals) == 1:
                    data[key] = vals[0]
                else:
                    data[key] = vals
            if not _has_keep_value(data, config.keep_any):
                continue
            crawl_metadata: dict = {
                "url": graph.strip("<>"),
                "source": "wdc-nquads",
                "provenance": {
                    "graph_iri": graph.strip("<>"),
                    "wdc_release": wdc_release,
                    "subset": subset or config.type_name,
                },
            }
            if source_file is not None:
                crawl_metadata["provenance"]["source_file"] = source_file
            yield {"data": data, "crawl_metadata": crawl_metadata}


def extract_from_file(
    path: Path,
    config: EntityConfig,
    *,
    subset: str | None = None,
    source_file: str | None = None,
    wdc_release: str = "2024-12",
) -> Iterator[dict]:
    by_graph = _collect_quads_by_graph(_open_lines(path))
    yield from extract_entities_from_quads(
        by_graph,
        config,
        subset=subset,
        source_file=source_file,
        wdc_release=wdc_release,
    )
