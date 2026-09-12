"""CLI error presentation and redaction acceptance matrix."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from paperdeck import cli
from paperdeck.engines import select
from paperdeck.input.cache import CacheManager


@pytest.fixture
def failing_conversion(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    monkeypatch.setattr(cli, "_cache", lambda: CacheManager(tmp_path / "cache"))
    monkeypatch.setattr(select, "plan", lambda *args: ["latex"], raising=False)

    def fail(*_args: object) -> object:
        raise RuntimeError(
            "zz-customsecret987654 sk-test1234567890 Authorization: Bearer xyz-secret"
        )

    monkeypatch.setattr(select, "run_plan", fail, raising=False)
    source = tmp_path / "paper.tex"
    source.write_text("fixture", encoding="utf-8")
    return source, tmp_path / "output.html"


@pytest.mark.parametrize("flags", [[], ["-v"], ["-v", "-v"]])
def test_cli_redacts_secrets_at_every_verbosity(
    failing_conversion: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch, flags: list[str]
) -> None:
    source, output = failing_conversion
    monkeypatch.setenv("OPENAI_API_KEY", "zz-customsecret987654")
    result = CliRunner().invoke(cli.main, [*flags, "convert", str(source), "-o", str(output)])
    assert result.exit_code == 1, result.output
    assert "zz-customsecret987654" not in result.output
    assert "sk-test1234567890" not in result.output
    assert "Bearer xyz-secret" not in result.output
    assert "***" in result.output
    report = json.loads(Path(str(output) + ".report.json").read_text(encoding="utf-8"))
    assert report["error"]["code"] == "unexpected"
