# ruff: noqa: E501
import base64
from pathlib import Path

from bs4 import BeautifulSoup

from paperdeck.engines.arxiv_html.parse_structure import parse_structure
from paperdeck.input.arxiv import HtmlArtifact
from paperdeck.ir.anchors import AnchorAllocator
from paperdeck.ir.model import CodeBlock, Figure, ListBlock, Paragraph, Quote, Table, Unhandled


def _parse(tmp_path: Path, html: str, assets: dict[str, bytes] | None = None):
    page = tmp_path / "html" / "index.html"
    (page.parent / "assets").mkdir(parents=True)
    asset_map: dict[str, str] = {}
    for source, data in (assets or {}).items():
        name = source.rsplit("/", 1)[-1]
        (page.parent / "assets" / name).write_bytes(data)
        asset_map[source] = name
    artifact = HtmlArtifact(page, asset_map, [], "fixture")
    return parse_structure(BeautifulSoup(html, "html.parser"), artifact, AnchorAllocator(), None)


def test_structure_maps_tree_table_list_and_safe_svg(tmp_path: Path) -> None:
    html = """<html><body><h1 class="ltx_title_document">Paper</h1><div class="ltx_page_main">
    <section class="ltx_section" id="sec:intro"><h2 class="ltx_title"><span class="ltx_tag">1</span> Intro</h2>
    <div class="ltx_para" id="p"><p class="ltx_p">body</p></div>
    <figure class="ltx_figure" id="fig"><img src="fig.svg" alt="plot"><figcaption class="ltx_caption">cap</figcaption></figure>
    <figure class="ltx_table"><table class="ltx_tabular"><tr><th colspan="2">A</th></tr><tr><td rowspan="2">B</td><td>C</td></tr></table></figure>
    <ul class="ltx_itemize"><li class="ltx_item">one</li><li class="ltx_item">two</li></ul></section></div></body></html>"""
    result = _parse(tmp_path, html, {"fig.svg": b"<svg><script>alert(1)</script><path/></svg>"})
    section = result.body[0]
    assert section.title[0].text == "Intro"
    assert result.source_id_map["sec:intro"] == section.id
    assert any(isinstance(item, Figure) and item.asset_id for item in section.children)
    table = next(item for item in section.children if isinstance(item, Table))
    assert table.rows and table.rows[0][0].header and table.rows[0][0].colspan == 2
    listing = next(item for item in section.children if isinstance(item, ListBlock))
    assert len(listing.items) == 2
    assert any(w.code == "svg-script-stripped" for w in result.warnings)
    payload = base64.b64decode(next(iter(result.assets.values())).data_b64)
    assert b"<script" not in payload


def test_structure_unknown_and_duplicate_ids_are_safe(tmp_path: Path) -> None:
    html = """<html><body><h1 class="ltx_title_document">P</h1><div class="ltx_page_main"><section class="ltx_section" id="s"><div class="ltx_para" id="dup"><p class="ltx_p">a</p></div><div class="ltx_para" id="dup"><p class="ltx_p">b</p></div><p class="ltx_p" id="direct">direct</p><div class="ltx_future">raw</div></section></div></body></html>"""
    result = _parse(tmp_path, html)
    children = result.body[0].children
    assert sum(isinstance(item, Unhandled) for item in children) == 1
    assert any(w.code == "html-id-duplicate" for w in result.warnings)
    assert any(
        isinstance(item, Paragraph) and item.content[0].text == "direct" for item in children
    )
    assert any(w.code.startswith("ltx-class-unhandled:") for w in result.warnings)


def test_structure_handles_missing_assets_nested_tables_quotes_and_code(tmp_path: Path) -> None:
    html = """<html><head><title>P</title></head><body><section class="ltx_section">
    <figure class="ltx_figure"><img src="missing.png"/><div class="ltx_caption">missing</div></figure>
    <figure class="ltx_table"><table class="ltx_tabular"><tr><td><table><tr><td>nested</td></tr></table></td></tr></table></figure>
    <blockquote class="ltx_quote">quoted</blockquote><pre class="ltx_verbatim">code</pre>
    </section></body></html>"""
    result = _parse(tmp_path, html)
    children = result.body[0].children
    assert any(isinstance(item, Figure) and item.asset_id is None for item in children)
    assert any(isinstance(item, Unhandled) for item in children)
    assert any(isinstance(item, Quote) for item in children)
    assert any(isinstance(item, CodeBlock) and item.text == "code" for item in children)
    assert any(item.code == "figure-image-missing" for item in result.warnings)
    assert any(item.code == "nested-tabular-unhandled" for item in result.warnings)


def test_structure_keeps_supported_siblings_and_excludes_frontmatter(tmp_path: Path) -> None:
    html = """<html><body><div class="ltx_page_main"><article class="ltx_document">
    <div class="ltx_para"><p class="ltx_p">frontmatter license</p></div>
    <h1 class="ltx_title ltx_title_document">B<span class="ltx_text ltx_font_bold">E</span>RT</h1>
    <div class="ltx_authors"><span class="ltx_creator ltx_role_author"><span class="ltx_personname">Ada<span class="ltx_note ltx_role_footnotemark">1</span></span></span></div>
    <div class="ltx_abstract"><h6 class="ltx_title ltx_title_abstract">Abstract</h6><p class="ltx_p">B<span class="ltx_text ltx_font_bold">E</span>RT is useful.</p></div>
    <div class="ltx_para"><p class="ltx_p">Intro before sections.</p></div>
    <section class="ltx_section" id="s"><h2 class="ltx_title"><span class="ltx_tag">1</span> Body</h2><div class="ltx_para"><p class="ltx_p">Main.</p></div></section>
    <section class="ltx_appendix" id="a"><h2 class="ltx_title"><span class="ltx_tag">A</span> Appendix</h2><div class="ltx_para"><p class="ltx_p">Appendix.</p></div></section>
    </article></div></body></html>"""
    result = _parse(tmp_path, html)

    assert result.authors == ["Ada"]
    assert result.meta_title[0].text == "BERT"
    assert result.abstract[0].content[0].text == "BERT is useful."
    assert [item.type for item in result.body] == ["paragraph", "section", "section"]
    assert result.body[0].content[0].text == "Intro before sections."
    assert result.body[2].title[0].text == "Appendix"


def test_structure_normalizes_figure_and_table_caption_numbers(tmp_path: Path) -> None:
    html = """<html><body><div class="ltx_page_main"><section class="ltx_section">
    <figure class="ltx_figure" id="f"><figcaption class="ltx_caption"><span class="ltx_tag ltx_tag_figure">Figure 1: </span>Caption.</figcaption></figure>
    <figure class="ltx_table" id="t"><figcaption class="ltx_caption"><span class="ltx_tag ltx_tag_table">Table 2: </span>Data.</figcaption><table class="ltx_tabular"><tr><td>x</td></tr></table></figure>
    </section></div></body></html>"""
    result = _parse(tmp_path, html)
    section = result.body[0]
    figure = next(item for item in section.children if isinstance(item, Figure))
    table = next(item for item in section.children if isinstance(item, Table))

    assert figure.number == "1"
    assert table.number == "2"
