import gzip
from pathlib import Path

from movies.identifiers import extract_imdb_id
from movies.imdb_dataset import IMDbDatasetValidator
from movies.index_imdb import build_index


def _write_tsv(path: Path, header: list[str], rows: list[list[str]]) -> None:
    with gzip.open(path, "wt", encoding="utf-8", newline="") as f:
        f.write("\t".join(header) + "\n")
        for row in rows:
            f.write("\t".join(row) + "\n")


def _write_fixture_dump(imdb_dir: Path) -> None:
    imdb_dir.mkdir(parents=True, exist_ok=True)
    _write_tsv(
        imdb_dir / "title.basics.tsv.gz",
        [
            "tconst",
            "titleType",
            "primaryTitle",
            "originalTitle",
            "isAdult",
            "startYear",
            "endYear",
            "runtimeMinutes",
            "genres",
        ],
        [
            [
                "tt0068646",
                "movie",
                "The Godfather",
                "The Godfather",
                "0",
                "1972",
                "\\N",
                "175",
                "Crime,Drama",
            ],
        ],
    )
    _write_tsv(
        imdb_dir / "title.crew.tsv.gz",
        ["tconst", "directors", "writers"],
        [["tt0068646", "nm0000338", "\\N"]],
    )
    _write_tsv(
        imdb_dir / "title.principals.tsv.gz",
        ["tconst", "ordering", "nconst", "category", "job", "characters"],
        [
            ["tt0068646", "1", "nm0000008", "actor", "\\N", '["Michael"]'],
            ["tt0068646", "2", "nm0000199", "actor", "\\N", '["Vito"]'],
        ],
    )
    _write_tsv(
        imdb_dir / "name.basics.tsv.gz",
        ["nconst", "primaryName", "birthYear", "deathYear", "primaryProfession", "knownForTitles"],
        [
            ["nm0000338", "Francis Ford Coppola", "1939", "\\N", "director", "tt0068646"],
            ["nm0000008", "Marlon Brando", "1924", "2004", "actor", "tt0068646"],
            ["nm0000199", "Al Pacino", "1940", "\\N", "actor", "tt0068646"],
        ],
    )


def test_build_index_and_lookup_movie(tmp_path: Path):
    imdb_dir = tmp_path / "imdb"
    _write_fixture_dump(imdb_dir)
    sqlite_path = tmp_path / "imdb.sqlite"
    build_index(imdb_dir, sqlite_path)

    v = IMDbDatasetValidator(sqlite_path)
    result = v.lookup_movie("tt0068646")
    assert result is not None
    assert result["title"] == "The Godfather"
    assert result["director"] == ["Francis Ford Coppola"]
    assert result["actor"] == ["Marlon Brando", "Al Pacino"]
    assert result["release_date"] == "1972"
    assert result["runtime"] == "175"
    assert result["genre"] == ["Crime", "Drama"]
    assert result["match"] == "imdb_dump"
    assert v.lookup_movie("tt0000000") is None


def test_movie_query_validator_end_to_end(tmp_path: Path):
    imdb_dir = tmp_path / "imdb"
    _write_fixture_dump(imdb_dir)
    sqlite_path = tmp_path / "imdb.sqlite"
    build_index(imdb_dir, sqlite_path)

    v = IMDbDatasetValidator(sqlite_path)
    record = {"data": {"name": "The Godfather", "sameAs": ["http://www.imdb.com/title/tt0068646/"]}}
    assert extract_imdb_id(record["data"]) == "tt0068646"
    out = v.movie_query_validator(record)
    assert out is not None
    assert out["kb"]["title"] == "The Godfather"
    assert out["entity_query"]["imdb_id"] == "tt0068646"
    assert out["crawl"] is record
    assert v.movie_query_validator({"data": {"name": "No link"}}) is None


def test_movie_query_validator_requires_imdb_id(tmp_path: Path):
    imdb_dir = tmp_path / "imdb"
    _write_fixture_dump(imdb_dir)
    sqlite_path = tmp_path / "imdb.sqlite"
    build_index(imdb_dir, sqlite_path)

    v = IMDbDatasetValidator(sqlite_path)
    record = {"data": {"name": "The Godfather (Restored)", "director": ["Francis Ford Coppola"]}}
    assert extract_imdb_id(record["data"]) is None
    assert v.movie_query_validator(record) is None
    assert v.movie_query_validator({"data": {}}) is None


def test_movie_query_validator_keeps_title_mismatch(tmp_path: Path):
    imdb_dir = tmp_path / "imdb"
    _write_fixture_dump(imdb_dir)
    sqlite_path = tmp_path / "imdb.sqlite"
    build_index(imdb_dir, sqlite_path)

    v = IMDbDatasetValidator(sqlite_path)
    record = {
        "data": {
            "name": "Totally Different Title",
            "sameAs": ["http://www.imdb.com/title/tt0068646/"],
        }
    }
    out = v.movie_query_validator(record)
    assert out is not None
    assert out["kb"]["imdb_id"] == "tt0068646"
    assert out["kb"]["match"] == "imdb_dump"
