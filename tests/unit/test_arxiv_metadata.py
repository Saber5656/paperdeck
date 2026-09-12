from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from paperdeck.errors import SecurityError
from paperdeck.input.arxiv import ArxivClient
from paperdeck.input.cache import CacheManager

ATOM = (
    b'<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom" '
    b'xmlns:arxiv="http://arxiv.org/schemas/atom"><entry>'
    b'<id>https://arxiv.org/abs/hep-th/9901001v2</id>'
    b'<title> A  title\n </title><summary>A\nsummary</summary>'
    b'<updated>2026-01-01T00:00:00Z</updated><author><name>Alice</name></author>'
    b'<link rel="alternate" href="https://arxiv.org/abs/hep-th/9901001v2"/>'
    b'<category term="hep-th"/><arxiv:doi>10.1234/test</arxiv:doi></entry></feed>'
)


class FakeGate:
    def __init__(self, response: httpx.Response, offline: bool = False):
        self.response, self.offline = response, offline
        self.settings = SimpleNamespace(fetch=SimpleNamespace(max_download_mb=1))
        self.calls = 0

    def client(self, purpose: str):
        assert purpose == "arxiv"

        def handler(request: httpx.Request) -> httpx.Response:
            self.calls += 1
            return self.response

        return httpx.Client(transport=httpx.MockTransport(handler))


def test_metadata_fields_and_cache(tmp_path: Path) -> None:
    gate = FakeGate(httpx.Response(200, content=ATOM))
    meta = ArxivClient(gate, CacheManager(tmp_path / "paperdeck")).metadata("hep-th/9901001", None)
    assert meta.id == "hep-th/9901001" and meta.latest_version == 2 and meta.resolved_version == 2
    assert meta.title == "A title" and meta.authors == ["Alice"] and meta.doi == "10.1234/test"
    assert gate.calls == 1


def test_dtd_rejected_before_cache(tmp_path: Path) -> None:
    payload = b'<!DOCTYPE foo [<!ENTITY x SYSTEM "file:///etc/passwd">]>' + ATOM
    gate = FakeGate(httpx.Response(200, content=payload))
    with pytest.raises(SecurityError) as exc:
        ArxivClient(gate, CacheManager(tmp_path / "paperdeck")).metadata("2401.12345", None)
    assert exc.value.code == "xml-dtd"
    assert (
        not list((tmp_path / "paperdeck").rglob("meta.xml"))
        if (tmp_path / "paperdeck").exists()
        else True
    )
