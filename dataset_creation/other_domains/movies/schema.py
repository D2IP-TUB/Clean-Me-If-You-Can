"""schema.org predicates extracted for Movie."""

from shared.schema import EntityConfig

MOVIE_CONFIG = EntityConfig(
    type_name="Movie",
    predicates={
        "name": "name",
        "director": "director",
        "actor": "actor",
        "datePublished": "datePublished",
        "dateCreated": "dateCreated",
        "duration": "duration",
        "identifier": "identifier",
        "sameAs": "sameAs",
        "inLanguage": "inLanguage",
        "productionCompany": "productionCompany",
        "url": "url",
        "genre": "genre",
    },
    nested_keys=frozenset({"director", "actor", "productionCompany"}),
    multi_keys=frozenset({"director", "actor", "identifier", "sameAs", "genre"}),
    keep_any=("name",),
)
