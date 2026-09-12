import json

from bs4 import BeautifulSoup

from paperdeck.config import load_settings
from paperdeck.ir.model import Document
from paperdeck.render.assets import build_bundle
from paperdeck.render.html import render_document
from paperdeck.render.validate import validate_html


def document():
    return Document.model_validate(
        {
            "schema_version": "1",
            "source": {"kind": "local", "original": "example.tex"},
            "provenance": {
                "engine": "latex",
                "engine_versions": {"paperdeck": "0.1.0.dev0", "katex": "0.18.7"},
                "created_at": "2026-09-12T00:00:00Z",
                "fallbacks": [],
            },
            "meta": {
                "title": [{"type": "text", "text": "A <script>alert(1)</script> paper"}],
                "authors": ["Example Author"],
                "links": [],
            },
            "body": [
                {
                    "type": "section",
                    "id": "sec-1",
                    "level": 1,
                    "number": "1",
                    "title": [{"type": "text", "text": "Introduction"}],
                    "children": [
                        {
                            "type": "paragraph",
                            "id": "para-1",
                            "content": [
                                {"type": "text", "text": "See "},
                                {
                                    "type": "ref_link",
                                    "target_id": "eq-1",
                                    "kind": "eq",
                                    "text": "(1)",
                                },
                                {
                                    "type": "ext_link",
                                    "url": "https://example.com",
                                    "content": [{"type": "text", "text": "source"}],
                                },
                            ],
                        },
                        {
                            "type": "equation",
                            "id": "eq-1",
                            "number": "1",
                            "content_kind": "latex",
                            "latex": "x < y",
                            "latex_verified": True,
                        },
                    ],
                }
            ],
            "macros": {"\\bad": "</script><img onerror=alert(1)>"},
        }
    )


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
