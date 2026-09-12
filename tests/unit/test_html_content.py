# ruff: noqa: E501
from pathlib import Path

from bs4 import BeautifulSoup

from paperdeck.config import load_settings
from paperdeck.engines.arxiv_html.parse_content import parse_content
from paperdeck.engines.arxiv_html.parse_structure import parse_structure
from paperdeck.input.arxiv import HtmlArtifact
from paperdeck.ir.anchors import AnchorAllocator
from paperdeck.ir.model import (
    Cite,
    Document,
    Emph,
    Equation,
    ExtLink,
    FootnoteRef,
    LineBreak,
    Math,
    Meta,
    MetaLink,
    Provenance,
    RefLink,
    Source,
    Strong,
)
from paperdeck.render.html import render
from paperdeck.render.validate import validate_html


def test_content_resolves_math_refs_citations_and_footnotes(tmp_path: Path) -> None:
    html = """<html><head><title>P</title></head><body><h1 class="ltx_title_document">P</h1><div class="ltx_page_main"><section class="ltx_section" id="s"><h2 class="ltx_title">S</h2><div class="ltx_para"><p class="ltx_p"><math alttext="x^2">x²</math> <a class="ltx_ref" href="#eq">(1)</a> <span class="ltx_cite"><a href="#bib.b1">[1]</a></span> <span class="ltx_note" id="fn1"><span class="ltx_tag">1</span>note</span></p></div><div class="ltx_equation" id="eq"><span class="ltx_tag">(1)</span><math alttext="x=1">x=1</math></div></section><div class="ltx_bibliography"><li class="ltx_bibitem" id="bib.b1">Reference</li></div></div></body></html>"""
    page = tmp_path / "index.html"
    page.write_text(html)
    structure = parse_structure(
        BeautifulSoup(html, "html.parser"), HtmlArtifact(page, {}, [], ""), AnchorAllocator(), None
    )
    body, bibliography, footnotes = parse_content(structure)
    paragraph = body[0].children[0]
    kinds = paragraph.content
    assert any(isinstance(item, Math) and item.latex == "x^2" for item in kinds)
    assert any(isinstance(item, RefLink) and item.kind == "eq" for item in kinds)
    assert any(isinstance(item, Cite) and item.bib_ids == [bibliography[0].id] for item in kinds)
    assert any(
        isinstance(item, FootnoteRef) and item.target_id == footnotes[0].id for item in kinds
    )
    assert isinstance(body[0].children[1], Equation)


def test_content_missing_math_alttext_warns(tmp_path: Path) -> None:
    html = '<html><head><title>P</title></head><body><section class="ltx_section"><div class="ltx_para"><p class="ltx_p"><math>x</math></p></div></section></body></html>'
    page = tmp_path / "index.html"
    page.write_text(html)
    structure = parse_structure(
        BeautifulSoup(html, "html.parser"), HtmlArtifact(page, {}, [], ""), AnchorAllocator(), None
    )
    body, _, _ = parse_content(structure)
    assert body[0].children[0].content[0].type == "text"
    assert any(item.code == "math-alttext-missing" for item in structure.warnings)


def test_content_maps_inline_nodes_and_all_reference_kinds(tmp_path: Path) -> None:
    html = """<html><head><title>P</title></head><body><h1 class="ltx_title_document">P</h1>
    <section class="ltx_section" id="sec"><h2 class="ltx_title">S</h2>
    <div class="ltx_para"><p class="ltx_p"><a href="https://example.test">link</a><br/>
    <em>em</em><strong>strong</strong><sub>sub</sub><sup>sup</sup><code>code</code>
    <a class="ltx_ref" href="#fig">fig</a><a class="ltx_ref" href="#tab">tab</a>
    <a class="ltx_ref" href="#fn">fn</a><a class="ltx_ref" href="#missing">missing</a></p></div>
    <figure class="ltx_figure" id="fig"><figcaption class="ltx_caption">F</figcaption></figure>
    <figure class="ltx_table" id="tab"><table class="ltx_tabular"><tr><td>cell</td></tr></table></figure>
    <div class="ltx_equation" id="eqbad"><math>broken</math></div>
    <span class="ltx_note" id="fn"><span class="ltx_tag">1</span>note</span></section></body></html>"""
    page = tmp_path / "index.html"
    page.write_text(html)
    structure = parse_structure(
        BeautifulSoup(html, "html.parser"),
        HtmlArtifact(page, {}, [], ""),
        AnchorAllocator(),
        None,
    )
    body, _, _ = parse_content(structure)
    paragraph = body[0].children[0]
    content = paragraph.content
    assert any(isinstance(item, ExtLink) for item in content)
    assert any(isinstance(item, LineBreak) for item in content)
    assert any(isinstance(item, Emph) for item in content)
    assert any(isinstance(item, Strong) for item in content)
    assert any(isinstance(item, RefLink) and item.kind == "fig" for item in content)
    assert any(isinstance(item, RefLink) and item.kind == "tab" for item in content)
    assert any(isinstance(item, RefLink) and item.kind == "fn" for item in content)
    assert any(isinstance(item, RefLink) and item.target_id == "" for item in content)
    assert any(isinstance(item, Equation) is False for item in body[0].children)
    assert any(item.code == "math-alttext-missing" for item in structure.warnings)


def test_content_updates_table_cells_and_equation_group(tmp_path: Path) -> None:
    html = """<html><head><title>P</title></head><body><section class="ltx_section">
    <figure class="ltx_table" id="t"><table class="ltx_tabular"><tr><th>A</th><td>B</td></tr></table></figure>
    <div class="ltx_equationgroup"><div class="ltx_equation" id="e1"><span class="ltx_tag">(1)</span><math alttext="a"/></div><div class="ltx_equation" id="e2"><span class="ltx_tag">(2)</span><math alttext="b"/></div></div>
    </section></body></html>"""
    page = tmp_path / "index.html"
    page.write_text(html)
    structure = parse_structure(
        BeautifulSoup(html, "html.parser"),
        HtmlArtifact(page, {}, [], ""),
        AnchorAllocator(),
        None,
    )
    body, _, _ = parse_content(structure)
    section = body[0]
    table = next(item for item in section.children if item.type == "table")
    assert table.rows and table.rows[0][0].header
    equations = [item for item in section.children if isinstance(item, Equation)]
    assert [item.latex for item in equations] == ["a", "b"]


def test_equation_alttext_is_kept_as_data_even_when_it_looks_like_script(tmp_path: Path) -> None:
    payload = r"</script><script>alert(1)</script>"
    html = (
        '<html><head><title>P</title></head><body><section class="ltx_section">'
        '<div class="ltx_equation" id="eq"><span class="ltx_tag">(1)</span>'
        f'<math alttext="{payload}">ignored</math></div></section></body></html>'
    )
    page = tmp_path / "index.html"
    page.write_text(html)
    structure = parse_structure(
        BeautifulSoup(html, "html.parser"),
        HtmlArtifact(page, {}, [], ""),
        AnchorAllocator(),
        None,
    )

    body, _, _ = parse_content(structure)

    equation = next(item for item in body[0].children if isinstance(item, Equation))
    assert equation.latex == payload

    document = Document(
        source=Source(kind="arxiv", arxiv_id="2401.12345", version="1", original="fixture"),
        provenance=Provenance(
            engine="arxiv-html", engine_versions={}, created_at="now", fallbacks=[]
        ),
        meta=Meta(
            title=[],
            authors=[],
            links=[MetaLink(url="https://arxiv.org/abs/2401.12345", kind="arxiv")],
        ),
        body=body,
        bibliography=[],
        footnotes=[],
        assets=structure.assets,
        labels=structure.labels,
        warnings=structure.warnings,
    )
    rendered = render(document, load_settings(None, {}))
    assert validate_html(rendered) == []
    assert "&lt;/script&gt;" in rendered
    assert "</script><script>alert(1)</script>" not in rendered
