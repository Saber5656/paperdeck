import pytest

from paperdeck.engines.latex.ast_map import MappedDoc, RawSpan
from paperdeck.engines.latex.bib import BibRef
from paperdeck.engines.latex.refs import resolve_references
from paperdeck.errors import ConversionError
from paperdeck.ir.model import Equation, Figure, Paragraph, Section, Table, Text


def test_reference_resolution_covers_styles_citations_and_footnotes() -> None:
    spans = [
        RawSpan(
            "\ue0000\ue001",
            r"\ref{eq} \eqref{eq} \cref{fig,tab} \autoref{sec} \ref{nope}",
            "inline",
        ),
        RawSpan("\ue0001\ue001", r"\citep[see][p. 2]{a,missing}", "inline"),
        RawSpan("\ue0002\ue001", r"\footnote{note $x^2$}", "inline"),
        RawSpan("\ue0003\ue001", r"\weirdcmd{x}", "inline"),
    ]
    body = [
        Section(
            id="sec-1",
            level=1,
            number="1",
            title=[],
            children=[
                Equation(
                    id="eq-1", number="2", content_kind="latex", latex="x", latex_verified=True
                ),
                Figure(id="fig-1", number="3", caption=[]),
                Table(id="tab-1", number="4", caption=[], content_kind="grid", rows=[]),
                Paragraph(
                    id="para-1",
                    content=[
                        Text(text="\ue0000\ue001"),
                        Text(text="\ue0001\ue001"),
                        Text(text="\ue0002\ue001"),
                        Text(text="\ue0003\ue001"),
                    ],
                ),
            ],
        )
    ]
    doc = MappedDoc(body, [], [], None, [], spans, {}, {}, {}, set())
    result = resolve_references(
        doc,
        {"eq": "eq-1", "fig": "fig-1", "tab": "tab-1", "sec": "sec-1"},
        {"a": BibRef("bib-1", "5", None)},
    )
    rendered = result.body[0].children[-1]
    assert isinstance(rendered, Paragraph)
    assert any(item.type == "ref_link" and item.text == "(2)" for item in rendered.content)
    assert any(item.type == "cite" and item.bib_ids == ["bib-1"] for item in rendered.content)
    assert result.footnotes and result.footnotes[0].number == "1"
    assert any(item.code == "unresolved-ref" for item in result.warnings)
    assert any(item.code == "cite-unresolved:missing" for item in result.warnings)
    assert any(item.code.startswith("raw-tex-dropped") for item in result.warnings)


def test_reference_resolution_rejects_unmatched_sentinel() -> None:
    doc = MappedDoc(
        [Paragraph(id="p", content=[Text(text="\ue0009\ue001")])],
        [],
        [],
        None,
        [],
        [],
        {},
        {},
        {},
        set(),
    )
    with pytest.raises(ConversionError, match="sentinel"):
        resolve_references(doc, {}, {})


def test_reference_resolution_ignores_known_structural_commands() -> None:
    spans = [
        RawSpan("\ue0000\ue001", r"\maketitle", "inline"),
        RawSpan("\ue0001\ue001", r"\bibliographystyle{plain}", "inline"),
    ]
    doc = MappedDoc(
        [
            Paragraph(id="p-1", content=[Text(text="\ue0000\ue001")]),
            Paragraph(id="p-2", content=[Text(text="\ue0001\ue001")]),
        ],
        [],
        [],
        None,
        [],
        spans,
        {},
        {},
        {},
        set(),
    )
    result = resolve_references(doc, {}, {})
    assert all(paragraph.content == [] for paragraph in result.body)
    assert not any(item.code.startswith("raw-tex-dropped") for item in result.warnings)


def test_reference_resolution_ignores_extracted_bibliography_block() -> None:
    raw = r"\begin{thebibliography}{9}\bibitem{x} X.\end{thebibliography}"
    doc = MappedDoc(
        [Paragraph(id="p", content=[Text(text="\ue0000\ue001")])],
        [],
        [],
        None,
        [],
        [RawSpan("\ue0000\ue001", raw, "block")],
        {},
        {},
        {},
        set(),
    )
    result = resolve_references(doc, {}, {"x": BibRef("bib-1", "1", None)})
    assert not any(item.code.startswith("raw-tex-dropped") for item in result.warnings)
