import gzip
import io
import tarfile
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
    b"<id>https://arxiv.org/abs/hep-th/9901001v2</id>"
    b"<title> A  title\n </title><summary>A\nsummary</summary>"
    b"<updated>2026-01-01T00:00:00Z</updated><author><name>Alice</name></author>"
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


class DownloadGate(FakeGate):
    def __init__(self, payloads: dict[str, bytes], offline: bool = False):
        super().__init__(httpx.Response(200), offline)
        self.payloads = payloads

    def download(self, url: str, destination: Path, purpose: str) -> Path:
        self.calls += 1
        destination.write_bytes(self.payloads[url])
        return destination


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


def test_html_page_fetches_same_host_assets_and_uses_offline_cache(tmp_path: Path) -> None:
    page_url = "https://export.arxiv.org/html/2401.12345v2"
    asset_url = "https://export.arxiv.org/html/fig.png"
    html = b'<html><img src="fig.png"><img src="https://evil.test/x.png"></html>'
    gate = DownloadGate({page_url: html, asset_url: b"\x89PNG\r\n\x1a\nbytes"})
    cache = CacheManager(tmp_path / "paperdeck")
    artifact = ArxivClient(gate, cache).html_page("2401.12345", 2)
    assert artifact is not None and artifact.asset_map["fig.png"].endswith(".png")
    assert "https://evil.test/x.png" in artifact.skipped_images
    calls = gate.calls
    offline_gate = DownloadGate({})
    cached = ArxivClient(offline_gate, cache).html_page("2401.12345", 2)
    assert cached is not None and offline_gate.calls == 0 and calls >= 2


def test_eprint_classifies_tar_gzip_single_and_pdf(tmp_path: Path) -> None:
    tar_bytes = io.BytesIO()
    with tarfile.open(fileobj=tar_bytes, mode="w") as archive:
        data = b"\\documentclass{article}"
        member = tarfile.TarInfo("main.tex")
        member.size = len(data)
        archive.addfile(member, io.BytesIO(data))
    gate = DownloadGate({"https://export.arxiv.org/e-print/2401.12345v1": tar_bytes.getvalue()})
    client = ArxivClient(gate, CacheManager(tmp_path / "cache"))
    assert client.eprint("2401.12345", 1).kind == "tar-gz"

    gz_gate = DownloadGate(
        {"https://export.arxiv.org/e-print/2401.12346v1": gzip.compress(b"\\documentclass{x}")}
    )
    assert ArxivClient(gz_gate, CacheManager(tmp_path / "gz")).eprint("2401.12346", 1).kind == "tex"

    pdf_gate = DownloadGate({"https://export.arxiv.org/e-print/2401.12347v1": b"%PDF-1.7\n"})
    assert (
        ArxivClient(pdf_gate, CacheManager(tmp_path / "pdf")).eprint("2401.12347", 1).kind
        == "pdf-only"
    )
