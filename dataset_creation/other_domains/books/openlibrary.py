"""Open Library lookup by ISBN."""

from __future__ import annotations

import json
import re
from pathlib import Path

import requests
from loguru import logger

from shared.sqlite_index import connect_sqlite
from shared.text import ensure_string

USER_AGENT = "other-domains-book-validator/0.1 (research; Open Library)"
ISBN_URL = "https://openlibrary.org/isbn/{isbn}.json"

__all__ = ["OpenLibraryDumpValidator", "OpenLibraryValidator", "ensure_string", "normalize_isbn"]


def normalize_isbn(raw: str | None) -> str | None:
    if not raw:
        return None
    digits = re.sub(r"[^0-9Xx]", "", raw)
    if len(digits) in (10, 13):
        return digits.upper()
    return None


def _authors_from_edition(edition: dict) -> list[str]:
    names: list[str] = []
    for a in edition.get("authors") or []:
        if isinstance(a, dict) and a.get("name"):
            names.append(a["name"])
        elif isinstance(a, dict) and a.get("key"):
            names.append(a["key"])
    return names


def _flatten_edition(edition: dict, *, match: str) -> dict:
    isbns: list[str] = []
    for key in ("isbn_13", "isbn_10", "isbn"):
        val = edition.get(key)
        if isinstance(val, list):
            isbns.extend(str(x) for x in val if x)
        elif val:
            isbns.append(str(val))
    publishers = edition.get("publishers") or []
    if isinstance(publishers, str):
        publishers = [publishers]
    works = edition.get("works") or []
    work_key = None
    if works and isinstance(works[0], dict):
        work_key = works[0].get("key")
    return {
        "openlibrary_key": edition.get("key"),
        "work_key": work_key,
        "title": edition.get("title"),
        "authors": _authors_from_edition(edition),
        "isbn": isbns or None,
        "publish_date": edition.get("publish_date"),
        "publishers": publishers or None,
        "number_of_pages": edition.get("number_of_pages"),
        "languages": edition.get("languages"),
        "match": match,
    }


class OpenLibraryValidator:
    def __init__(
        self,
        session: requests.Session | None = None,
        timeout: float = 20.0,
    ):
        self.timeout = timeout
        if session is None:
            self.session = requests.Session()
            self.session.headers["User-Agent"] = USER_AGENT
        else:
            self.session = session

    def lookup_isbn(self, isbn: str) -> dict | None:
        url = ISBN_URL.format(isbn=isbn)
        try:
            resp = self.session.get(url, timeout=self.timeout, allow_redirects=True)
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as e:
            logger.warning(f"Open Library ISBN error {isbn}: {e}")
            return None
        except ValueError as e:
            logger.warning(f"Open Library ISBN JSON error {isbn}: {e}")
            return None
        if not isinstance(data, dict) or not data.get("title"):
            return None
        return _flatten_edition(data, match="isbn")

    def query_validator(
        self,
        *,
        title: str | None,
        author: str | None,
        isbn: str | None,
        isbn_only: bool = False,
    ) -> dict | None:
        isbn_norm = normalize_isbn(isbn)
        if not isbn_norm:
            return None
        hit = self.lookup_isbn(isbn_norm)
        if not hit:
            return None
        return hit

    def record_query_validator(self, record: dict, *, isbn_only: bool = False) -> dict | None:
        data = record.get("data") or {}
        query = {
            "title": ensure_string(data.get("name")),
            "author": ensure_string(data.get("author")),
            "isbn": ensure_string(data.get("isbn")) or ensure_string(data.get("gtin13")),
        }
        if not any(query.values()):
            return None
        result = self.query_validator(**query, isbn_only=isbn_only)
        if result is None:
            return None
        return {"kb": result, "crawl": record, "entity_query": query}


def _loads_list(val) -> list:
    if val is None:
        return []
    if isinstance(val, (list, tuple)):
        return list(val)
    if isinstance(val, str):
        try:
            parsed = json.loads(val)
        except json.JSONDecodeError:
            return [val] if val else []
        if isinstance(parsed, list):
            return parsed
    return []


class OpenLibraryDumpValidator(OpenLibraryValidator):
    def __init__(self, sqlite_path: Path | str):
        self.conn = connect_sqlite(sqlite_path, read_only=True)

    def _edition_kb(self, key: str, *, match: str) -> dict | None:
        row = self.conn.execute(
            "SELECT key, work_key, title, authors, publish_date, publishers, "
            "number_of_pages, languages FROM editions WHERE key = ?",
            (key,),
        ).fetchone()
        if not row or not row[2]:
            return None
        isbns = [
            r[0]
            for r in self.conn.execute("SELECT isbn FROM isbn WHERE edition_key = ?", (key,)).fetchall()
        ]
        languages = row[7]
        if isinstance(languages, str):
            try:
                languages = json.loads(languages)
            except json.JSONDecodeError:
                pass
        authors = _loads_list(row[3])
        publishers = _loads_list(row[5]) or None
        return {
            "openlibrary_key": row[0],
            "work_key": row[1],
            "title": row[2],
            "authors": authors,
            "isbn": isbns or None,
            "publish_date": row[4],
            "publishers": publishers,
            "number_of_pages": row[6],
            "languages": languages,
            "match": match,
        }

    def lookup_isbn(self, isbn: str) -> dict | None:
        row = self.conn.execute("SELECT edition_key FROM isbn WHERE isbn = ?", [isbn]).fetchone()
        if not row:
            return None
        return self._edition_kb(row[0], match="isbn")
