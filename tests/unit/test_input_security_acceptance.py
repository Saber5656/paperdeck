"""Acceptance boundaries for configuration, resolver, netgate and safe extraction."""

from __future__ import annotations

import gzip
import io
import re
import socket
import tarfile
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from pydantic import ValidationError

from paperdeck.config import load_settings
from paperdeck.errors import ConfigError, FetchError, InputError, SecurityError
from paperdeck.input.resolver import InputSpec, output_slug, resolve
from paperdeck.input.tarsafe import extract_tar, sniff_kind
from paperdeck.netgate import NetGate, RateLimiter


def _settings(
    *, offline: bool = False, base_url: str = "https://api.example.test/v1", max_mb: int = 1
):
    return SimpleNamespace(
        offline=offline,
        fetch=SimpleNamespace(timeout_s=2, max_download_mb=max_mb),
        llm=SimpleNamespace(base_url=base_url, timeout_s=2),
    )


def test_config_is_frozen_hashable_and_never_serializes_secret(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "zz-secret-config-value")
    settings = load_settings(None, {"llm.base_url": "http://localhost:11434/v1"})
    assert settings.resolve_api_key() == "zz-secret-config-value"
    assert "zz-secret-config-value" not in repr(settings)
    assert "zz-secret-config-value" not in settings.model_dump_json()
    assert hash(settings) == hash(settings)
    with pytest.raises(TypeError):
        settings.llm.pricing["new"] = settings.llm.pricing["gpt-5.6-terra"]
    with pytest.raises(TypeError):
        settings.llm.pricing.update({"new": settings.llm.pricing["gpt-5.6-terra"]})
    with pytest.raises(TypeError):
        settings.llm.pricing |= {"new": settings.llm.pricing["gpt-5.6-terra"]}
    with pytest.raises(ValidationError):
        settings.offline = True


def test_config_reports_invalid_ranges(tmp_path: Path) -> None:
    config = tmp_path / "invalid.toml"
    config.write_text("[llm]\ntimeout_s = 0\nmax_retries = 11\n", encoding="utf-8")
    with pytest.raises(ConfigError) as exc:
        load_settings(config, {})
    assert "timeout_s" in str(exc.value) and "max_retries" in str(exc.value)


@pytest.mark.parametrize(
    "raw",
    [
        "2401.1234",
        "2401.12345",
        "2401.12345v2",
        "arXiv:2401.12345",
        "arxiv:hep-th/9901001",
        "hep-th/9901001v3",
        "hep-th/9901001",
        "astro-ph.GA/1234567",
        "https://arxiv.org/abs/2401.12345",
        "https://www.arxiv.org/abs/2401.12345?x=1#frag",
        "http://export.arxiv.org/pdf/2401.12345.pdf",
        "https://arxiv.org/pdf/hep-th/9901001v2",
        "https://arxiv.org/html/2401.12345",
        "https://www.arxiv.org/html/hep-th/9901001v2",
        "http://export.arxiv.org/abs/astro-ph.GA/1234567",
        "ARXIV:2401.1234v4",
        "https://arxiv.org/pdf/2401.1234",
        "https://arxiv.org/abs/2401.12345v9",
        "https://export.arxiv.org/abs/hep-th/9901001v10",
        "http://www.arxiv.org/html/2401.12345v2",
        "2401.99999v1",
        "cs-ai/1234567",
        "math/1234567",
        "nucl-th/1234567v2",
        "quant-ph/1234567",
        "cond-mat/1234567v8",
    ],
)
def test_resolver_acceptance_forms(raw: str) -> None:
    result = resolve(raw)
    assert result.kind == "arxiv"
    assert result.arxiv_id and result.arxiv_id.count("v") == 0
    assert output_slug(result).startswith("arxiv-")


@pytest.mark.parametrize(
    "raw",
    [
        "ftp://arxiv.org/abs/2401.12345",
        "https://evil.example/abs/2401.12345",
        "https://arxiv.org/abs/2401",
        "https://arxiv.org/pdf/2401.12345.pdf.exe",
        "https://arxiv.org/foo/2401.12345",
        "24010.1234",
        "2401.123456v2",
        "ABC/1234567",
        "hep-th/123456",
        "not an id",
    ],
)
def test_resolver_rejects_unsafe_forms(raw: str) -> None:
    with pytest.raises(Exception) as exc:
        resolve(raw)
    assert "2401.12345" in str(exc.value) or "2401.12345" in getattr(exc.value, "hint", "")


def test_resolver_local_suffixes_directory_and_safe_slugs(tmp_path: Path) -> None:
    for name, archive in [
        ("paper.tex", False),
        ("paper.tar", True),
        ("paper.tar.gz", True),
        ("paper.tgz", True),
        ("paper.gz", True),
        ("paper.pdf", False),
    ]:
        path = tmp_path / name
        path.write_bytes(b"x")
        spec = resolve(str(path))
        assert spec.path == path.resolve() and spec.archive is archive
        assert output_slug(spec).replace("-", "").replace(".", "").isalnum()
    with pytest.raises(InputError):
        resolve(str(tmp_path))
    weird = InputSpec("pdf-local", path=tmp_path / "unsafe name!.pdf")
    assert output_slug(weird) == "unsafe-name-"


def test_resolver_slug_property_and_no_network_or_write_side_effects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail_write(*_args, **_kwargs):
        raise AssertionError("resolver attempted a write")

    def fail_network(*_args, **_kwargs):
        raise AssertionError("resolver attempted network access")

    monkeypatch.setattr(Path, "write_text", fail_write)
    monkeypatch.setattr(Path, "write_bytes", fail_write)
    monkeypatch.setattr(socket, "create_connection", fail_network)
    names = ["paper.tex", "paper name!.tex", "...pdf", "ümlaut.tar.gz", "x" * 80 + ".pdf"]
    for name in names:
        path = tmp_path / name
        path.touch()
        slug = output_slug(resolve(str(path)))
        assert re.fullmatch(r"[A-Za-z0-9._-]+", slug)
        assert slug == output_slug(resolve(str(path)))
    for raw in ("2401.12345", "arxiv:hep-th/9901001v2"):
        slug = output_slug(resolve(raw))
        assert re.fullmatch(r"[A-Za-z0-9._-]+", slug)


def test_netgate_user_agent_rate_limit_and_local_llm_cap(monkeypatch) -> None:
    seen: list[httpx.Request] = []
    gate = NetGate(
        _settings(),
        transport=httpx.MockTransport(
            lambda request: seen.append(request) or httpx.Response(200, text="ok")
        ),
    )
    monkeypatch.setattr("paperdeck.netgate._ARXIV_RATE_LIMITER.wait", lambda: None)
    response = gate.client("arxiv").get("http://export.arxiv.org/api/query")
    assert response.text == "ok" and seen[0].headers["user-agent"].startswith("paperdeck/")
    clock = iter([0.0, 1.0, 4.0])
    sleeps: list[float] = []
    limiter = RateLimiter(3.0, clock=lambda: next(clock), sleeper=sleeps.append)
    limiter.wait()
    limiter.wait()
    assert sleeps == [2.0]
    payload = b"x" * (20 * 1024 * 1024 + 1)
    local = NetGate(
        _settings(base_url="http://localhost:11434/v1"),
        transport=httpx.MockTransport(lambda request: httpx.Response(200, content=payload)),
    )
    with pytest.raises(FetchError, match="cap"):
        local.client("llm").get("http://localhost:11434/v1/chat/completions")


def test_netgate_exact_llm_authority_and_offline_before_transport() -> None:
    called = False

    def handler(_request):
        nonlocal called
        called = True
        return httpx.Response(200)

    gate = NetGate(
        _settings(offline=True, base_url="http://localhost:11434/v1"),
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(FetchError, match="disabled"):
        gate.client("llm").get("http://localhost:11434/v1/chat/completions")
    assert not called
    gate = NetGate(
        _settings(base_url="http://localhost:11434/v1"), transport=httpx.MockTransport(handler)
    )
    with pytest.raises(SecurityError, match="not allowed"):
        gate.client("llm").get("http://localhost:11435/v1/chat/completions")


def _tar_bytes(members: list[tuple[str, bytes, int | None]]):
    out = io.BytesIO()
    with tarfile.open(fileobj=out, mode="w") as archive:
        for name, data, mode in members:
            info = tarfile.TarInfo(name)
            info.size = len(data)
            if name.endswith("/"):
                info.type = tarfile.DIRTYPE
                info.size = 0
            if mode is not None:
                info.mode = mode
            archive.addfile(info, io.BytesIO(data))
    return out.getvalue()


def test_tar_member_count_permissions_and_gzip_sniff(tmp_path: Path) -> None:
    archive = tmp_path / "paper.tar"
    archive.write_bytes(
        _tar_bytes([("src/", b"", 0o777), ("src/main.tex", b"\\begin{document}", 0o777)])
    )
    limits = SimpleNamespace(max_archive_members=5, max_archive_total_mb=1)
    dest = tmp_path / "out"
    files = extract_tar(archive, dest, limits)
    assert files and (dest / "src/main.tex").stat().st_mode & 0o777 == 0o644
    assert sniff_kind(archive) == "tar"
    gz = tmp_path / "single.gz"
    gz.write_bytes(gzip.compress(b"\\documentclass{article}"))
    assert sniff_kind(gz) == "gzip-single"
    gz_tar = tmp_path / "archive.tar.gz"
    gz_tar.write_bytes(gzip.compress(archive.read_bytes()))
    assert sniff_kind(gz_tar) == "tar-gz"


def test_tar_header_count_bomb_is_rejected_before_writes(tmp_path: Path) -> None:
    archive = tmp_path / "many.tar"
    archive.write_bytes(_tar_bytes([(f"f{i}", b"x", None) for i in range(4)]))
    limits = SimpleNamespace(max_archive_members=3, max_archive_total_mb=1)
    destination = tmp_path / "dest"
    with pytest.raises(SecurityError, match="too many") as exc:
        extract_tar(archive, destination, limits)
    assert exc.value.code == "archive-too-many-members" and not destination.exists()
