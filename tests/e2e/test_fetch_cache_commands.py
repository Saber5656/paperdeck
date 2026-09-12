"""Command contracts using a real cache and fixture-backed arXiv transport."""

import json

import httpx
import pytest
from click.testing import CliRunner

from paperdeck import cli
from paperdeck.input.arxiv import ArxivClient
from paperdeck.input.cache import CacheManager
from paperdeck.netgate import NetGate


@pytest.fixture
def cached_client(tmp_path, monkeypatch):
    cache = CacheManager(tmp_path / "paperdeck")
    monkeypatch.setattr(cli, "_cache", lambda: cache)
    monkeypatch.setattr("paperdeck.netgate.RateLimiter.wait", lambda _: None)
    seen = []

    def response(request):
        seen.append(str(request.url))
        if "api/query" in str(request.url):
            return httpx.Response(200, text='''<feed xmlns="http://www.w3.org/2005/Atom">
<entry><id>http://arxiv.org/abs/2401.12345v2</id><title>Example</title>
<summary>Abstract</summary><updated>2026-01-01T00:00:00Z</updated>
<author><name>A. Researcher</name></author></entry></feed>''')
        if "/pdf/" in str(request.url):
            return httpx.Response(200, content=b"%PDF-1.7\nfixture")
        return httpx.Response(404)

    real = ArxivClient

    def client(gate, manager):
        return real(NetGate(gate.settings, transport=httpx.MockTransport(response)), manager)

    monkeypatch.setattr("paperdeck.input.arxiv.ArxivClient", client)
    return cache, seen


def test_fetch_pdf_repeat_hits_cache_and_clear_is_scoped(cached_client):
    cache, seen = cached_client
    runner = CliRunner()
    first = runner.invoke(cli.main, ["fetch", "2401.12345v2", "--kind", "pdf"])
    assert first.exit_code == 0, first.output
    assert first.stdout.startswith("pdf: ")
    before = len(seen)
    second = runner.invoke(cli.main, ["fetch", "2401.12345v2", "--kind", "pdf"])
    assert second.exit_code == 0, second.output
    assert len(seen) == before
    other = cache.arxiv_dir("2402.12345", 1)
    other.mkdir(parents=True)
    (other / "pdf.pdf").write_bytes(b"keep")
    listing = runner.invoke(cli.main, ["cache", "ls"])
    assert listing.exit_code == 0
    assert "2401.12345" in listing.stdout
    assert "llm-cache" in listing.stdout
    cleared = runner.invoke(cli.main, ["cache", "clear", "2401.12345", "--yes"])
    assert cleared.exit_code == 0, cleared.output
    assert cleared.stdout.startswith("Freed ")
    assert (other / "pdf.pdf").read_bytes() == b"keep"
    assert not cache.arxiv_dir("2401.12345", 2).exists()


def test_fetch_all_tolerates_missing_html_and_single_kind_fails(cached_client):
    _, seen = cached_client
    runner = CliRunner()
    result = runner.invoke(cli.main, ["fetch", "2401.12345v2"])
    assert result.exit_code == 0, result.output
    assert "html: not available" in result.stdout
    result = runner.invoke(cli.main, ["fetch", "2401.12345v2", "--kind", "source"])
    assert result.exit_code == 4, result.output
    before = len(seen)
    result = runner.invoke(cli.main, ["fetch", "../../etc/passwd"])
    assert result.exit_code in {2, 3}
    assert len(seen) == before


def test_clear_all_including_model_cache(cached_client):
    cache, _ = cached_client
    path = cache.llm_dir("model")
    path.mkdir(parents=True)
    (path / "request.json").write_text(json.dumps({"fixture": True}))
    result = CliRunner().invoke(cli.main, ["cache", "clear", "--yes"])
    assert result.exit_code == 0, result.output
    assert not list(cache.root.rglob("*.json"))
