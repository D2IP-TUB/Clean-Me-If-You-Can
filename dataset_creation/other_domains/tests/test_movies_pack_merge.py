import gzip
import json
from pathlib import Path

from movies.merge import merge_movies
from movies.pack import pack_movies, row_from_record


def _rec(name, clean_title, imdb_id="tt0068646"):
    return {
        "kb": {
            "title": clean_title,
            "director": ["Francis Ford Coppola"],
            "actor": ["Marlon Brando"],
            "release_date": "1972-03-14",
            "runtime": 175,
            "genre": ["Drama"],
            "production_company": ["Paramount"],
            "original_language": "en",
            "match": "imdb_id",
            "imdb_id": imdb_id,
        },
        "crawl": {
            "data": {
                "@type": "Movie",
                "name": name,
                "director": ["F. Coppola"],
                "sameAs": [f"http://www.imdb.com/title/{imdb_id}/"],
            },
            "crawl_metadata": {
                "url": "https://example.org/p",
                "provenance": {"graph_iri": "https://example.org/p", "subset": "Movie"},
            },
        },
        "entity_query": {"imdb_id": imdb_id, "title": name},
    }


def test_row_from_record_maps_dirty_and_clean_fields():
    row = row_from_record(_rec("Godfather (1972)", "The Godfather"))
    assert row["title"] == "Godfather (1972)"
    assert row["target_title"] == "The Godfather"
    assert row["target_director"] == "Francis Ford Coppola"
    assert row["imdb_id"] == "tt0068646"
    assert row["match"] == "imdb_id"


def test_pack_writes_flat_layout(tmp_path: Path):
    validated = tmp_path / "validated" / "Movie"
    validated.mkdir(parents=True)
    with gzip.open(validated / "part_0.json.gz", "wt", encoding="utf-8") as f:
        json.dump([_rec("Godfather (1972)", "The Godfather")], f)
    pack_dir = tmp_path / "pack" / "Movie"
    pack_movies(validated, pack_dir)
    packed = (pack_dir / "values_experiment.csv").read_text()
    assert "Godfather (1972)" in packed
    header = packed.splitlines()[0]
    assert "production_company" not in header
    assert "language" not in header
    assert "provenance_graph_iri" in header
    assert not (pack_dir / "named").exists()
    assert not (pack_dir / "unnamed").exists()


def test_merge_only_pulls_movie_subset_not_siblings(tmp_path: Path):
    validated = tmp_path / "validated" / "Movie"
    validated.mkdir(parents=True)
    with gzip.open(validated / "part_0.json.gz", "wt", encoding="utf-8") as f:
        json.dump([_rec("Godfather (1972)", "The Godfather")], f)
    pack_root = tmp_path / "pack"
    pack_movies(validated, pack_root / "Movie")

    other = pack_root / "Book"
    other.mkdir(parents=True)
    (other / "values_experiment.csv").write_text("id,title\nzzz,Interloper\n")
    (other / "targets_experiment.csv").write_text("id,title\nzzz,Interloper\n")
    (other / "provenance.csv").write_text("id\nzzz\n")

    merge_movies(pack_root, tmp_path / "merged")
    merged = (tmp_path / "merged" / "merged_values_experiment.csv").read_text()
    assert "Godfather" in merged
    assert "Interloper" not in merged
    assert "source_subset" not in merged.splitlines()[0]
    assert "provenance_graph_iri" not in merged.splitlines()[0]
