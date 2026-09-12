# ruff: noqa: E501
from pathlib import Path

from bs4 import BeautifulSoup

from paperdeck.engines.arxiv_html.parse_content import parse_content
from paperdeck.engines.arxiv_html.parse_structure import parse_structure
from paperdeck.input.arxiv import HtmlArtifact
from paperdeck.ir.anchors import AnchorAllocator
from paperdeck.ir.model import Cite, Equation, FootnoteRef, Math, RefLink


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
