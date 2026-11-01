from unittest.mock import Mock

from books.openlibrary import OpenLibraryValidator, normalize_isbn


def test_normalize_isbn_strips_punctuation():
    assert normalize_isbn("978-1-4738-9980-3") == "9781473899803"
    assert normalize_isbn("0-306-40615-2") == "0306406152"
    assert normalize_isbn("") is None
    assert normalize_isbn("5_8_97502_622_978") == "5897502622978"


def test_isbn_hit_looks_up_once():
    session = Mock()
    isbn_resp = Mock()
    isbn_resp.status_code = 200
    isbn_resp.json.return_value = {
        "key": "/books/OL1M",
        "title": "The Hobbit",
        "isbn_13": ["9780261102217"],
        "publishers": ["Allen & Unwin"],
        "authors": [{"name": "J. R. R. Tolkien"}],
    }
    session.get.return_value = isbn_resp
    v = OpenLibraryValidator(session=session)
    record = {
        "data": {"name": "The Hobbit", "isbn": "978-0-261-10221-7", "author": "Tolkien"},
        "crawl_metadata": {},
    }
    out = v.record_query_validator(record)
    assert out is not None
    assert out["kb"]["match"] == "isbn"
    assert out["kb"]["title"] == "The Hobbit"
    assert out["entity_query"]["isbn"] == "978-0-261-10221-7"
    assert session.get.call_count == 1


def test_unknown_isbn_is_dropped():
    session = Mock()
    isbn_resp = Mock()
    isbn_resp.status_code = 404
    session.get.return_value = isbn_resp
    v = OpenLibraryValidator(session=session)
    out = v.record_query_validator({"data": {"name": "The Hobbit", "isbn": "9780261102217"}})
    assert out is None
    assert session.get.call_count == 1


def test_no_hit_returns_none():
    session = Mock()
    v = OpenLibraryValidator(session=session)
    assert v.record_query_validator({"data": {"name": "zzzz-not-a-book-xxxx"}}) is None
    session.get.assert_not_called()


def test_isbn_only_drops_unknown_isbn():
    session = Mock()
    isbn_resp = Mock()
    isbn_resp.status_code = 404
    session.get.return_value = isbn_resp
    v = OpenLibraryValidator(session=session)
    out = v.record_query_validator(
        {"data": {"name": "The Hobbit", "isbn": "9780261102217"}},
        isbn_only=True,
    )
    assert out is None
    assert session.get.call_count == 1
