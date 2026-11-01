"""Look up movies in a local IMDb SQLite index."""

from __future__ import annotations

from pathlib import Path

from movies.identifiers import extract_imdb_id
from shared.sqlite_index import connect_sqlite
from shared.text import ensure_string

__all__ = ["IMDbDatasetValidator", "extract_imdb_id"]

ACTOR_CATEGORIES = ("actor", "actress", "self")
MAX_CAST = 10


class IMDbDatasetValidator:
    def __init__(self, sqlite_path: Path | str):
        self.conn = connect_sqlite(sqlite_path, read_only=True)

    def _names_for(self, nconsts: list[str]) -> list[str] | None:
        if not nconsts:
            return None
        placeholders = ",".join("?" * len(nconsts))
        rows = self.conn.execute(
            f"SELECT nconst, primary_name FROM names WHERE nconst IN ({placeholders})",
            nconsts,
        ).fetchall()
        by_id = {nconst: name for nconst, name in rows if name}
        names = [by_id[n] for n in nconsts if n in by_id]
        return names or None

    def _directors_for(self, tconst: str) -> list[str] | None:
        row = self.conn.execute("SELECT directors FROM crew WHERE tconst = ?", (tconst,)).fetchone()
        if not row or not row[0]:
            return None
        return self._names_for(row[0].split(","))

    def _cast_for(self, tconst: str, limit: int = MAX_CAST) -> list[str] | None:
        placeholders = ",".join("?" * len(ACTOR_CATEGORIES))
        rows = self.conn.execute(
            f"SELECT nconst FROM principals WHERE tconst = ? AND category IN ({placeholders}) "
            "ORDER BY ordering LIMIT ?",
            [tconst, *ACTOR_CATEGORIES, limit],
        ).fetchall()
        return self._names_for([r[0] for r in rows])

    def _title_row(self, tconst: str | None) -> dict | None:
        if not tconst:
            return None
        row = self.conn.execute(
            "SELECT title_type, primary_title, original_title, start_year, end_year, "
            "runtime_minutes, genres FROM titles WHERE tconst = ?",
            [tconst],
        ).fetchone()
        if not row:
            return None
        title_type, primary_title, original_title, start_year, end_year, runtime, genres = row
        return {
            "title_type": title_type,
            "title": primary_title,
            "original_title": original_title,
            "start_year": start_year,
            "end_year": end_year,
            "runtime": runtime,
            "genre": genres.split(",") if genres else None,
        }

    def lookup_movie(self, tconst: str) -> dict | None:
        title = self._title_row(tconst)
        if not title or not title.get("title"):
            return None
        return {
            "imdb_id": tconst,
            "title": title["title"],
            "original_title": title["original_title"],
            "director": self._directors_for(tconst),
            "actor": self._cast_for(tconst),
            "release_date": title["start_year"],
            "runtime": title["runtime"],
            "genre": title["genre"],
            "production_company": None,
            "original_language": None,
            "match": "imdb_dump",
        }

    def movie_query_validator(self, record: dict) -> dict | None:
        data = record.get("data") or {}
        title = ensure_string(data.get("name"))
        director = ensure_string(data.get("director"))

        imdb_id = extract_imdb_id(data)
        if not imdb_id:
            return None
        result = self.lookup_movie(imdb_id)
        if result is None:
            return None
        query = {"imdb_id": imdb_id, "title": title, "director": director}
        return {"kb": result, "crawl": record, "entity_query": query}
