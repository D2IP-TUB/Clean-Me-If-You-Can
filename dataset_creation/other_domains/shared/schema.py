"""Extract configuration for one schema.org type."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EntityConfig:
    type_name: str
    predicates: dict[str, str]
    nested_keys: frozenset[str]
    multi_keys: frozenset[str]
    keep_any: tuple[str, ...]
