from pathlib import Path

from books.schema import BOOK_CONFIG
from shared.extract import extract_from_file

FIXTURE = Path(__file__).parent / "fixtures" / "book_min.nq"


def test_extract_book_nested_author_and_publisher():
    records = list(extract_from_file(FIXTURE, BOOK_CONFIG, subset="Book", source_file="book_min.nq"))
    by_url = {r["crawl_metadata"]["url"]: r["data"] for r in records}
    assert "https://example.org/empty" not in by_url

    trafalgar = by_url["https://example.org/trafalgar"]
    assert trafalgar["name"] == "The Trafalgar Chronicle New Series 3"
    assert trafalgar["author"] == ["Jane Austen"]
    assert trafalgar["publisher"] == "Seaforth Publishing"
    assert trafalgar["bookFormat"] == "EBook"
    assert "@type" not in trafalgar or trafalgar["@type"] == "Book"

    isbn_only = by_url["https://example.org/isbn-only"]
    assert isbn_only["isbn"] == "9781473899803"
    assert "name" not in isbn_only
