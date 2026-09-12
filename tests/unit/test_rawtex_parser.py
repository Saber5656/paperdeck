import random

import pytest

from paperdeck.engines.latex.refs import (
    CiteUse,
    FootnoteInline,
    OtherTex,
    RefUse,
    parse_raw_tex,
)


@pytest.mark.parametrize(
    "source",
    [
        r"\label{a}",
        r"\label{a_b}",
        r"\label{a:b}",
        r"\label{a+b}",
        r"\label{a/b}",
        r"\ref{a}",
        r"\ref{a,b}",
        r"\ref { a }",
        r"\eqref{eq:one}",
        r"\cref{fig:a,tab:b}",
        r"\Cref{sec:a}",
        r"\autoref{fn:a}",
        r"\cite{k}",
        r"\citep{k}",
        r"\citet{k}",
        r"\citealp{k}",
        r"\citealt{k}",
        r"\citeauthor{k}",
        r"\citeyear{k}",
        r"\cite[p. 2]{k}",
        r"\citep[see][p. 2]{k}",
        r"\citep[see][p. 2]{a,b}",
        r"\footnote{plain}",
        r"\footnote{nested {group}}",
        r"\footnote{escaped \{ brace}",
        r"prefix \ref{a} suffix",
        r"\ref{a}\ref{b}",
        r"\cite{k}\footnote{n}",
        r"\foo{x}",
        r"\foo",
        r"\ref{bad key}",
        r"\cite{bad key}",
        r"\label{}",
        r"\ref{a,}",
        r"\footnote{unterminated",
        r"\cite[unterminated{k}",
        r"text % literal",
        r"\\",
        r"\begin{equation}x\end{equation}",
        r"\newcommand{\x}{y}",
    ],
)
def test_raw_tex_table_cases_are_total(source: str) -> None:
    directives = parse_raw_tex(source)
    assert directives
    assert [item.span for item in directives] == sorted(item.span for item in directives)


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


def test_raw_tex_seeded_fuzz_is_total_and_spans_cover_source() -> None:
    generator = random.Random(1601)  # noqa: S311 - deterministic parser fuzz input
    for _ in range(500):
        source = generator.randbytes(generator.randrange(160)).decode("latin-1")
        directives = parse_raw_tex(source)
        spans = [item.span for item in directives]
        assert spans == sorted(spans)
        assert all(
            end <= next_start for (_, end), (next_start, _) in zip(spans, spans[1:], strict=False)
        )
        assert "".join(source[start:end] for start, end in spans) == source
