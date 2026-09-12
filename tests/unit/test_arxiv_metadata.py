import gzip
import io
import logging
import tarfile
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from paperdeck.config import load_settings
from paperdeck.errors import FetchError, InputError, SecurityError
from paperdeck.input.arxiv import ArxivClient
from paperdeck.input.cache import CacheManager
from paperdeck.netgate import NetGate

FIXTURE_ROOT = Path(__file__).parents[1] / "fixtures" / "arxiv"

ATOM = (
    b'<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom" '
    b'xmlns:arxiv="http://arxiv.org/schemas/atom"><entry>'
    b"<id>https://arxiv.org/abs/hep-th/9901001v2</id>"
    b"<title> A  title\n </title><summary>A\nsummary</summary>"
    b"<updated>2026-01-01T00:00:00Z</updated><author><name>Alice</name></author>"
    b'<link rel="alternate" href="https://arxiv.org/abs/hep-th/9901001v2"/>'
    b'<category term="hep-th"/><arxiv:doi>10.1234/test</arxiv:doi></entry></feed>'
)

MODERN_ATOM = ATOM.replace(b"hep-th/9901001v2", b"2401.12345v3").replace(b"Alice", b"Modern Author")


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
        self.urls: list[str] = []

    def download(self, url: str, destination: Path, purpose: str) -> Path:
        self.calls += 1
        self.urls.append(url)
        destination.write_bytes(self.payloads[url])
        return destination


class ScriptGate(DownloadGate):
    def __init__(self, payloads: dict[str, bytes], failures: dict[str, str]):
        super().__init__(payloads)
        self.failures = failures

    def download(self, url: str, destination: Path, purpose: str) -> Path:
        if url in self.failures:
            self.calls += 1
            raise FetchError("missing", "retry", self.failures[url])
        return super().download(url, destination, purpose)


def test_metadata_fields_and_cache(tmp_path: Path) -> None:
    gate = FakeGate(httpx.Response(200, content=ATOM))
    meta = ArxivClient(gate, CacheManager(tmp_path / "paperdeck")).metadata("hep-th/9901001", None)
    assert meta.id == "hep-th/9901001" and meta.latest_version == 2 and meta.resolved_version == 2
    assert meta.title == "A title" and meta.authors == ["Alice"] and meta.doi == "10.1234/test"
    assert gate.calls == 1


def test_metadata_version_and_offline_cache_rules(tmp_path: Path) -> None:
    cache = CacheManager(tmp_path / "paperdeck")
    cache.put("arxiv/2401.12345/2/meta.xml", MODERN_ATOM)
    online = FakeGate(httpx.Response(200, content=MODERN_ATOM))
    client = ArxivClient(online, cache)

    explicit = client.metadata("2401.12345", 2)
    assert explicit.resolved_version == 2 and online.calls == 0

    cache.put("arxiv/2401.12345/3/meta.xml", MODERN_ATOM)
    latest = client.metadata("2401.12345", None)
    assert latest.resolved_version == 3 and online.calls == 1

    offline = FakeGate(httpx.Response(500), offline=True)
    offline_client = ArxivClient(offline, cache)
    selected = offline_client.metadata("2401.12345", None)
    assert selected.resolved_version == 3 and offline.calls == 0

    with pytest.raises(FetchError) as exc:
        ArxivClient(
            FakeGate(httpx.Response(500), offline=True), CacheManager(tmp_path / "empty")
        ).metadata("2401.12345", None)
    assert exc.value.code == "offline"


@pytest.mark.parametrize(
    ("filename", "arxiv_id", "version"),
    [
        ("modern-2401.12345.xml", "2401.12345", 3),
        ("old-1706.03762.xml", "1706.03762", 7),
    ],
)
def test_captured_atom_fixtures_extract_modern_and_old_ids(
    filename: str, arxiv_id: str, version: int, tmp_path: Path
) -> None:
    payload = (FIXTURE_ROOT / filename).read_bytes()
    gate = FakeGate(httpx.Response(200, content=payload))

    meta = ArxivClient(gate, CacheManager(tmp_path / "paperdeck")).metadata(arxiv_id, None)

    assert meta.id == arxiv_id
    assert meta.latest_version == version
    assert meta.resolved_version == version
    assert meta.title and meta.authors and meta.abstract
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
    assert asset_url in gate.urls
    assert "https://evil.test/x.png" not in gate.urls
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


def test_metadata_invalid_not_found_and_version_errors(tmp_path: Path) -> None:
    with pytest.raises(FetchError) as exc:
        ArxivClient(
            FakeGate(httpx.Response(200, content=b"broken")), CacheManager(tmp_path / "bad")
        ).metadata("2401.12345", None)
    assert exc.value.code == "metadata-invalid-xml"
    empty = b'<feed xmlns="http://www.w3.org/2005/Atom"/>'
    with pytest.raises(InputError) as exc:
        ArxivClient(
            FakeGate(httpx.Response(200, content=empty)), CacheManager(tmp_path / "empty")
        ).metadata("2401.12345", None)
    assert exc.value.code == "arxiv-id-not-found"
    with pytest.raises(InputError) as exc:
        ArxivClient(
            FakeGate(httpx.Response(200, content=ATOM)), CacheManager(tmp_path / "version")
        ).metadata("hep-th/9901001", 3)
    assert exc.value.code == "arxiv-version-not-found"


def test_eprint_and_pdf_cache_hits_and_reject_bad_downloads(tmp_path: Path) -> None:
    cache = CacheManager(tmp_path / "paperdeck")
    cache.put("arxiv/2401.12345/1/source.tex", b"tex")
    cache.put("arxiv/2401.12345/1/paper.pdf", b"%PDF-1.7")
    gate = DownloadGate({})
    client = ArxivClient(gate, cache)
    assert client.eprint("2401.12345", 1).path.read_bytes() == b"tex"
    assert client.pdf("2401.12345", 1).read_bytes() == b"%PDF-1.7"

    bad = DownloadGate({"https://export.arxiv.org/e-print/2401.12346v1": b"garbage"})
    with pytest.raises(FetchError) as exc:
        ArxivClient(bad, CacheManager(tmp_path / "bad-eprint")).eprint("2401.12346", 1)
    assert exc.value.code == "eprint-unrecognized"
    bad_pdf = DownloadGate({"https://export.arxiv.org/pdf/2401.12346v1": b"not pdf"})
    with pytest.raises(FetchError) as exc:
        ArxivClient(bad_pdf, CacheManager(tmp_path / "bad-pdf")).pdf("2401.12346", 1)
    assert exc.value.code == "pdf-unrecognized"


def test_html_page_retries_second_host_and_invalid_asset_types_are_skipped(tmp_path: Path) -> None:
    first = "https://export.arxiv.org/html/2401.12345v1"
    second = "https://arxiv.org/html/2401.12345v1"
    html = b'<html><img src="bad.gif"><img src="data:image/png;base64,x"></html>'
    gate = ScriptGate(
        {second: html, "https://arxiv.org/html/bad.gif": b"GIF89a"}, {first: "http-404"}
    )
    artifact = ArxivClient(gate, CacheManager(tmp_path / "paperdeck")).html_page("2401.12345", 1)
    assert artifact is not None and artifact.asset_map == {} and len(artifact.skipped_images) == 2
    assert gate.calls == 3


def test_html_page_returns_none_when_both_hosts_return_404(tmp_path: Path) -> None:
    first = "https://export.arxiv.org/html/2401.12345v1"
    second = "https://arxiv.org/html/2401.12345v1"
    gate = ScriptGate({}, {first: "http-404", second: "http-404"})

    assert (
        ArxivClient(gate, CacheManager(tmp_path / "paperdeck")).html_page("2401.12345", 1) is None
    )
    assert gate.calls == 2


def test_html_page_enforces_two_hundred_image_limit(tmp_path: Path) -> None:
    page_url = "https://export.arxiv.org/html/2401.12345v1"
    sources = [f"img-{index}.png" for index in range(201)]
    html = ("<html>" + "".join(f'<img src="{source}">' for source in sources) + "</html>").encode()
    payloads = {page_url: html}
    payloads.update(
        {f"https://export.arxiv.org/html/{source}": b"\x89PNG\r\n\x1a\nimage" for source in sources}
    )
    gate = DownloadGate(payloads)

    artifact = ArxivClient(gate, CacheManager(tmp_path / "paperdeck")).html_page("2401.12345", 1)

    assert artifact is not None
    assert len(artifact.asset_map) == 200
    assert sources[-1] in artifact.skipped_images
    assert gate.calls == 201  # page + exactly 200 images


def test_html_page_uses_magic_bytes_over_image_content_type(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    page_url = "https://export.arxiv.org/html/2401.12345v1"
    asset_url = "https://export.arxiv.org/html/fig.png"
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if str(request.url) == page_url:
            return httpx.Response(200, content=b'<html><img src="fig.png"></html>')
        return httpx.Response(200, headers={"content-type": "image/png"}, content=b"not png")

    monkeypatch.setattr("paperdeck.netgate._ARXIV_RATE_LIMITER.wait", lambda: None)
    caplog.set_level(logging.INFO, logger="paperdeck.netgate")
    settings = load_settings(None, {})
    client = ArxivClient(
        NetGate(settings, transport=httpx.MockTransport(handler)),
        CacheManager(tmp_path / "paperdeck"),
    )

    artifact = client.html_page("2401.12345", 1)

    assert artifact is not None and artifact.asset_map == {}
    assert artifact.skipped_images == ["fig.png"]
    assert calls == [page_url, asset_url]
    assert "downloaded https://export.arxiv.org/html/2401.12345v1" in caplog.text


@pytest.mark.parametrize("method", ["eprint", "pdf", "html_page"])
def test_uncached_artifacts_fail_offline(method: str, tmp_path: Path) -> None:
    settings = load_settings(None, {"offline": True})
    client = ArxivClient(NetGate(settings), CacheManager(tmp_path / "paperdeck"))

    with pytest.raises(FetchError) as exc:
        getattr(client, method)("2401.12345", 1)
    assert exc.value.code == "offline"
