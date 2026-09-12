from paperdeck.engines.latex.refs import CiteUse, FootnoteInline, OtherTex, RefUse, parse_raw_tex


def test_raw_tex_directives_are_ordered_and_cover_input() -> None:
    source = "before \\ref{eq:a,fig:b} \\citep[e.g.][p. 2]{one,two} \\footnote{x {y}} after"
    directives = parse_raw_tex(source)
    assert isinstance(directives[1], RefUse)
    assert isinstance(directives[2], OtherTex)
    assert any(isinstance(item, CiteUse) and item.postnote == "p. 2" for item in directives)
    assert any(isinstance(item, FootnoteInline) for item in directives)
    assert [item.span for item in directives] == sorted(item.span for item in directives)
    assert "".join(source[start:end] for start, end in [item.span for item in directives]) == source


def test_malformed_and_large_footnotes_are_total() -> None:
    malformed = parse_raw_tex("\\ref{unterminated")
    assert len(malformed) == 1 and isinstance(malformed[0], OtherTex)
    large = parse_raw_tex("\\footnote{" + "x" * 10001 + "}")
    assert (
        isinstance(large[0], FootnoteInline)
        and large[0].truncated
        and len(large[0].tex_body) == 10000
    )
