import gzip
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from paperdeck.errors import ConfigError, FetchError, SecurityError
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
    with pytest.raises(ConfigError) as exc:
        NetGate(settings(base_url="http://api.example.test/v1"))
    assert getattr(exc.value, "code", None) == "llm-http-not-local"


def test_download_success_status_and_network_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("paperdeck.netgate._ARXIV_RATE_LIMITER.wait", lambda: None)
    gate = NetGate(
        settings(),
        transport=httpx.MockTransport(lambda request: httpx.Response(200, content=b"ok")),
    )
    destination = tmp_path / "artifact"
    assert gate.download("https://export.arxiv.org/x", destination, "arxiv") == destination
    assert destination.read_bytes() == b"ok" and not destination.with_name("artifact.tmp").exists()

    status_gate = NetGate(
        settings(),
        transport=httpx.MockTransport(lambda request: httpx.Response(503)),
    )
    with pytest.raises(FetchError) as exc:
        status_gate.download("https://export.arxiv.org/x", tmp_path / "status", "arxiv")
    assert exc.value.code == "http-503"

    error_gate = NetGate(
        settings(),
        transport=httpx.MockTransport(
            lambda request: (_ for _ in ()).throw(httpx.ConnectError("down"))
        ),
    )
    with pytest.raises(FetchError) as exc:
        error_gate.download("https://export.arxiv.org/x", tmp_path / "error", "arxiv")
    assert exc.value.code == "network-error"


def test_arxiv_http_is_upgraded_and_llm_authority_is_exact(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("paperdeck.netgate._ARXIV_RATE_LIMITER.wait", lambda: None)
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200, content=b"ok")

    gate = NetGate(settings(), transport=httpx.MockTransport(handler))
    gate.client("arxiv").get("http://export.arxiv.org/x")
    assert seen[0].startswith("https://export.arxiv.org/")
    gate.client("llm").get("https://api.example.test/v1/chat/completions")
    with pytest.raises(SecurityError):
        gate.client("llm").get("https://api.example.test:8443/v1/chat/completions")


def test_arxiv_client_uses_one_connection_and_http_boundary_is_unique() -> None:
    client = NetGate(settings()).client("arxiv")
    transport = client._transport  # type: ignore[attr-defined]
    pool = transport.inner._pool  # type: ignore[attr-defined]
    assert pool._max_connections == 1  # type: ignore[attr-defined]
    source_root = Path(__file__).parents[2] / "src" / "paperdeck"
    direct_httpx_imports = [
        path
        for path in source_root.rglob("*.py")
        if path.name != "netgate.py"
        and (
            "import httpx" in path.read_text(encoding="utf-8")
            or "from httpx" in path.read_text(encoding="utf-8")
        )
    ]
    assert direct_httpx_imports == []


def test_rate_limiter_waits_only_when_interval_remains() -> None:
    now = [0.0]
    sleeps: list[float] = []

    def clock() -> float:
        return now[0]

    def sleep(delay: float) -> None:
        sleeps.append(delay)
        now[0] += delay

    from paperdeck.netgate import RateLimiter

    limiter = RateLimiter(3.0, clock=clock, sleeper=sleep)
    limiter.wait()
    now[0] += 1.0
    limiter.wait()
    now[0] += 3.0
    limiter.wait()
    assert sleeps == [2.0]
