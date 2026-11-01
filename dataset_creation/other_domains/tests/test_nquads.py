from shared.nquads import parse_nquads_line, strip_literal


def test_parse_book_name_quad():
    line = (
        '<http://example.org/book1> <http://schema.org/name> '
        '"The Hobbit"@en <https://example.org/page> .\n'
    )
    quad = parse_nquads_line(line)
    assert quad is not None
    assert quad.subject == "<http://example.org/book1>"
    assert "schema.org/name" in quad.predicate
    assert strip_literal(quad.object) == "The Hobbit"
    assert quad.object_lang == "en"
    assert quad.graph == "<https://example.org/page>"
