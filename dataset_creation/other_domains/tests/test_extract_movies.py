from pathlib import Path

from movies.schema import MOVIE_CONFIG
from shared.extract import extract_from_file

MOVIES = Path(__file__).parent / "fixtures" / "movies_min.nq"


def test_extract_movie():
    movies = list(extract_from_file(MOVIES, MOVIE_CONFIG, subset="Movie"))
    by_url = {r["crawl_metadata"]["url"]: r["data"] for r in movies}
    assert "https://example.org/empty-movie" not in by_url
    movie = by_url["https://example.org/movie"]
    assert movie["name"] == "The Godfather"
    assert movie["director"] == ["Francis Ford Coppola"]
    assert movie["actor"] == ["Marlon Brando"]
