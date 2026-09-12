import gzip
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from paperdeck.errors import FetchError, SecurityError
from paperdeck.netgate import NetGate


def settings(
    *, offline: bool = False, base_url: str = "https://api.example.test/v1", max_mb: int = 1
):
    return SimpleNamespace(
        offline=offline,
        fetch=SimpleNamespace(timeout_s=2, max_download_mb=max_mb),
        llm=SimpleNamespace(base_url=base_url, timeout_s=2),
    )


def test_offline_blocks_before_transport() -> None:
    called = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200)

    gate = NetGate(settings(offline=True), transport=httpx.MockTransport(handler))
    with pytest.raises(FetchError) as exc:
        gate.client("arxiv").get("https://export.arxiv.org/api/query")
    assert exc.value.code == "offline" and not called


def test_redirect_host_is_rechecked(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("paperdeck.netgate._ARXIV_RATE_LIMITER.wait", lambda: None)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "https://evil.example/x"})

    gate = NetGate(settings(), transport=httpx.MockTransport(handler))
    with pytest.raises(SecurityError) as exc:
        gate.client("arxiv").get("https://export.arxiv.org/api/query")
    assert exc.value.code == "host-not-allowed"


def test_download_cap_leaves_no_destination(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("paperdeck.netgate._ARXIV_RATE_LIMITER.wait", lambda: None)
    payload = b"x" * (1024 * 1024 + 1)
    gate = NetGate(
        settings(),
        transport=httpx.MockTransport(lambda request: httpx.Response(200, content=payload)),
    )
    destination = tmp_path / "artifact"
    with pytest.raises(FetchError) as exc:
        gate.download("https://export.arxiv.org/x", destination, "arxiv")
    assert exc.value.code == "size-cap" and not destination.exists()


def test_decoded_response_cap_blocks_compressed_bomb(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("paperdeck.netgate._ARXIV_RATE_LIMITER.wait", lambda: None)
    payload = gzip.compress(b"x" * (1024 * 1024 + 1))
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, headers={"content-encoding": "gzip"}, content=payload)
    )
    gate = NetGate(settings(), transport=transport)
    with pytest.raises(FetchError) as exc:
        gate.client("arxiv").get("https://export.arxiv.org/x")
    assert exc.value.code == "size-cap"


def test_remote_plain_http_llm_is_rejected() -> None:
    with pytest.raises(Exception) as exc:
        NetGate(settings(base_url="http://api.example.test/v1"))
    assert getattr(exc.value, "code", None) == "llm-http-not-local"
