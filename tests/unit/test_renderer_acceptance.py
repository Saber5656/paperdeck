"""Portable output snapshots and public renderer trust-boundary acceptance."""

import base64
import hashlib
import json
import re
from pathlib import Path

import pytest
from bs4 import BeautifulSoup
from jinja2 import UndefinedError

from paperdeck.config import load_settings
from paperdeck.ir.model import Asset, AssetOrigin, Document, Equation, Figure, Text
from paperdeck.render.assets import build_bundle
from paperdeck.render.html import render
from paperdeck.render.validate import csp_for_scripts, validate_html
from tests.fixtures.reader import document, kitchen_sink_document

ROOT = Path(__file__).parents[2]
ASSETS = ROOT / "src/paperdeck/render/assets"


def test_kitchen_sink_html_golden(request):
    doc = kitchen_sink_document()
    html = render(doc, load_settings(None, {}))
    golden = ROOT / "tests/goldens/kitchen-sink.html"
    if request.config.getoption("--update-goldens"):
        golden.write_text(html)
    assert golden.read_text() == html
    assert render(doc, load_settings(None, {})) == html
    assert validate_html(html) == []
    soup = BeautifulSoup(html, "html.parser")
    for link in soup.select("a[href]"):
        if link["href"].startswith("#"):
            assert soup.select_one(link["href"])
        else:
            assert link["href"] == "https://example.com"
            assert link["rel"] == ["noopener", "noreferrer"]
            assert link["target"] == "_blank"


def test_hostile_strings_in_text_math_alt_and_json_are_only_data():
    hostile = '"><img onerror=alert(1)><script>alert(1)</script>'
    doc = document()
    doc = doc.model_copy(
        update={
            "meta": doc.meta.model_copy(update={"title": [Text(text=hostile)]}),
            "macros": {"\\bad": hostile},
            "assets": {
                "picture": Asset(
                    id="picture",
                    mime="image/png",
                    data_b64="eA==",
                    origin=AssetOrigin(engine="pdf"),
                )
            },
            "body": [
                Equation(id="eq-1", content_kind="latex", latex=hostile, latex_verified=True),
                Figure(
                    id="fig-1", asset_id="picture", alt_text=hostile, caption=[Text(text=hostile)]
                ),
            ],
        }
    )
    html = render(doc, load_settings(None, {}))
    soup = BeautifulSoup(html, "html.parser")
    assert hostile not in html
    assert soup.select_one("title").text == hostile
    assert soup.select_one("h1").text == hostile
    assert soup.select_one("#eq-1")["data-latex"] == hostile
    assert soup.select_one("#fig-1 img")["alt"] == hostile
    assert json.loads(soup.select_one("#pd-data").text)["macros"]["\\bad"] == hostile
    assert len(soup.select("script")) == 4
    assert not soup.select("[onerror]")
    assert validate_html(html) == []


def test_missing_template_field_fails_loudly(monkeypatch):
    original = Document.model_dump

    def broken(self, *args, **kwargs):
        value = original(self, *args, **kwargs)
        del value["meta"]["authors"]
        return value

    monkeypatch.setattr(Document, "model_dump", broken)
    with pytest.raises(UndefinedError, match="authors"):
        render(document(), load_settings(None, {}))


def test_font_rewrite_all_hashes_csp_and_bundle_determinism():
    doc, settings = document(), load_settings(None, {})
    first, second = build_bundle(doc, settings), build_bundle(doc, settings)
    assert first == second
    original = (ASSETS / "vendor/katex/katex.min.css").read_text()
    woff2_count = len(re.findall(r"url\(fonts/[^)]+\.woff2\)", original))
    urls = re.findall(r"url\(([^)]+)\)", first.style_text)
    assert woff2_count > 0 and len(urls) == woff2_count
    assert all(url.startswith("data:font/woff2;base64,") for url in urls)
    for script in first.scripts:
        assert (
            script.sha256_b64
            == base64.b64encode(hashlib.sha256(script.text.encode()).digest()).decode()
        )
    texts = ["first();", "second();"]
    hashes = " ".join(
        "'sha256-" + base64.b64encode(hashlib.sha256(s.encode()).digest()).decode() + "'"
        for s in texts
    )
    assert (
        csp_for_scripts(texts)
        == "default-src 'none'; img-src data:; style-src 'unsafe-inline'; script-src " + hashes
        + "; font-src data:; connect-src 'none'; form-action 'none'; "
        "base-uri 'none'; frame-ancestors 'none'"
    )
    assert first.csp_value.count("sha256-") == 4


def test_template_trusted_sinks_and_stylesheet_static_boundary():
    templates = ROOT / "src/paperdeck/render/templates"
    assert all("|safe" not in path.read_text() for path in templates.glob("*.j2"))
    css = (ASSETS / "viewer.css").read_text()
    assert not re.search(r"url\((?!data:)", css)
    without_variables = re.sub(r":root[^{}]*\{[^{}]*\}", "", css)
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", without_variables)
    before_motion = css.split("@media (prefers-reduced-motion: reduce)")[0]
    assert "!important" not in before_motion
    assert css.count("@media (prefers-reduced-motion: reduce)") == 1
