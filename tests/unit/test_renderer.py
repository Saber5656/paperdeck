import json

from bs4 import BeautifulSoup

from paperdeck.config import load_settings
from paperdeck.render.assets import build_bundle
from paperdeck.render.html import render_document
from paperdeck.render.validate import validate_html
from tests.fixtures.reader import document


def test_render_escaping_csp_determinism_and_refs():
    doc = document()
    bundle = build_bundle(doc, load_settings(None, {}))
    html = render_document(doc, bundle, load_settings(None, {}))
    assert html == render_document(doc, bundle, load_settings(None, {}))
    assert validate_html(html) == []
    soup = BeautifulSoup(html, "html.parser")
    assert not soup.select("[onerror]")
    assert soup.title.get_text() == "A <script>alert(1)</script> paper"
    assert json.loads(soup.select_one("#pd-data").string)["macros"] == doc.macros
    assert all(soup.select_one(a["href"]) for a in soup.select("a.pd-ref[href]"))
    assert len(soup.select("[id]")) == len({e["id"] for e in soup.select("[id]")})
    assert soup.select_one('a[href="https://example.com"]')["rel"] == ["noopener", "noreferrer"]
    assert "url(fonts/" not in html
