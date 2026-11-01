"""schema.org predicates extracted for Book."""

from shared.schema import EntityConfig

BOOK_CONFIG = EntityConfig(
    type_name="Book",
    predicates={
        "name": "name",
        "author": "author",
        "isbn": "isbn",
        "gtin13": "gtin13",
        "identifier": "identifier",
        "datePublished": "datePublished",
        "copyrightYear": "copyrightYear",
        "publisher": "publisher",
        "numberOfPages": "numberOfPages",
        "bookFormat": "bookFormat",
        "inLanguage": "inLanguage",
        "sameAs": "sameAs",
        "url": "url",
    },
    nested_keys=frozenset({"author", "publisher"}),
    multi_keys=frozenset({"author", "identifier", "sameAs"}),
    keep_any=("name", "isbn", "gtin13"),
)
