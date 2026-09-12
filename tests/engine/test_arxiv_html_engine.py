# ruff: noqa: E501

from pathlib import Path
from types import SimpleNamespace

import pytest

from paperdeck.config import load_settings
from paperdeck.engines import EngineContext
from paperdeck.engines.arxiv_html import fetch as fetch_module
from paperdeck.engines.arxiv_html import parse_content
from paperdeck.errors import ConversionError
from paperdeck.input.arxiv import HtmlArtifact
from paperdeck.input.cache import CacheManager
from paperdeck.input.resolver import InputSpec


def _ctx(tmp_path: Path) -> EngineContext:
    return EngineContext(
        InputSpec("arxiv", arxiv_id="2401.12345", original="2401.12345"),
        load_settings(None, {}),
        CacheManager(tmp_path / "cache"),
        tmp_path,
        lambda _: True,
    )


def test_engine_assembles_validated_document(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    html = '<html><head><title>P</title></head><body><h1 class="ltx_title_document">P</h1><section class="ltx_section"><div class="ltx_para"><p class="ltx_p">hello</p></div></section></body></html>'
    page = tmp_path / "index.html"
    page.write_text(html)
    artifact = HtmlArtifact(page, {}, [], "fixture")
    metadata = SimpleNamespace(
        id="2401.12345",
        resolved_version=1,
        authors=["A"],
        abs_url="https://arxiv.org/abs/2401.12345",
        doi=None,
    )

    class FakeClient:
        def __init__(self, *_: object) -> None:
            pass

        def metadata(self, *_: object) -> object:
            return metadata

    monkeypatch.setattr(parse_content, "ArxivClient", FakeClient)
    monkeypatch.setattr(parse_content, "fetch_html", lambda _ctx, _metadata=None: artifact)
    document = parse_content.ArxivHtmlEngine().convert(_ctx(tmp_path))
    assert document.provenance.engine == "arxiv-html"
    assert document.meta.title[0].text == "P"
    assert document.body[0].type == "section"


def test_engine_gate_failure_keeps_reason_code(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    page = tmp_path / "index.html"
    page.write_text(
        "<html><head><title>P</title></head><body><div>HTML is not available for this paper</div></body></html>"
    )
    artifact = HtmlArtifact(page, {}, [], "fixture")
    metadata = SimpleNamespace(
        id="2401.12345",
        resolved_version=1,
        authors=[],
        abs_url="https://arxiv.org/abs/2401.12345",
        doi=None,
    )

    class FakeClient:
        def __init__(self, *_: object) -> None:
            pass

        def metadata(self, *_: object) -> object:
            return metadata

    monkeypatch.setattr(parse_content, "ArxivClient", FakeClient)
    monkeypatch.setattr(parse_content, "fetch_html", lambda _ctx, _metadata=None: artifact)
    with pytest.raises(ConversionError, match="quality") as exc:
        parse_content.ArxivHtmlEngine().convert(_ctx(tmp_path))
    assert exc.value.code == "html-stub"


def test_fetch_html_rejects_local_specs_and_reuses_resolved_metadata(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    local = EngineContext(
        InputSpec("latex-local", path=tmp_path / "x.tex", original="x.tex"),
        load_settings(None, {}),
        CacheManager(tmp_path / "cache-local"),
        tmp_path,
        lambda _: True,
    )
    assert fetch_module.fetch_html(local) is None

    artifact = HtmlArtifact(tmp_path / "index.html", {}, [], "fixture")
    calls: list[tuple[str, int]] = []

    class FakeClient:
        def __init__(self, *_: object) -> None:
            pass

        def metadata(self, arxiv_id: str, version: int | None) -> object:
            raise AssertionError("metadata must not be fetched when supplied")

        def html_page(self, arxiv_id: str, version: int) -> HtmlArtifact:
            calls.append((arxiv_id, version))
            return artifact

    monkeypatch.setattr(fetch_module, "ArxivClient", FakeClient)
    monkeypatch.setattr(fetch_module, "NetGate", lambda settings: object())
    metadata = SimpleNamespace(id="2401.12345", resolved_version=3)
    result = fetch_module.fetch_html(_ctx(tmp_path), metadata)
    assert result == artifact and calls == [("2401.12345", 3)]
