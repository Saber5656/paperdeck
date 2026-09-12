import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from paperdeck import cli
from paperdeck.engines import select
from paperdeck.errors import AllEnginesFailedError, FallbackNote
from paperdeck.input.cache import CacheManager
from paperdeck.render import validate
from tests.fixtures.reader import document


@pytest.fixture
def fixture_engine(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "_cache", lambda: CacheManager(tmp_path / "cache"))
    monkeypatch.setattr(select, "plan", lambda *args: ["latex"], raising=False)
    monkeypatch.setattr(select, "run_plan", lambda *_: document(), raising=False)
    source = tmp_path / "paper.tex"
    source.write_text("fixture")
    return source, tmp_path / "output.html"


def test_cli_writes_report_force_matrix_and_stdout(fixture_engine):
    source, output = fixture_engine
    args = ["-q", "convert", str(source), "-o", str(output)]
    result = CliRunner().invoke(cli.main, args)
    assert result.exit_code == 0, result.output
    assert result.stdout == str(output) + "\n"
    assert result.stderr == ""
    report = json.loads(Path(str(output) + ".report.json").read_text())
    assert report["output"]["bytes"] == output.stat().st_size
    assert report["engine"] == "latex"
    assert report["versions"]["katex"]
    assert not list(output.parent.glob("*.tmp"))
    assert CliRunner().invoke(cli.main, args).exit_code == 10
    assert CliRunner().invoke(cli.main, args + ["--force"]).exit_code == 0


def test_validator_failure_leaves_no_output(fixture_engine, monkeypatch):
    source, output = fixture_engine
    monkeypatch.setattr(
        validate, "validate_html", lambda _: [validate.Violation("external-resource", "injected")]
    )
    result = CliRunner().invoke(cli.main, ["convert", str(source), "-o", str(output)])
    assert result.exit_code == 9
    assert not output.exists()
    report = json.loads(Path(str(output) + ".report.json").read_text())
    assert report["error"]["exit"] == 9


def test_failure_reports_fallbacks_and_redacts_secrets(fixture_engine, monkeypatch):
    source, output = fixture_engine
    secret = "zz-customsecret987654"  # noqa: S105 -- synthetic redaction fixture
    monkeypatch.setenv("OPENAI_API_KEY", secret)

    def fail(_plan, context):
        context.run_metrics.update(actual_usd=0.02, calls=2, cache_hits=1)
        raise AllEnginesFailedError(
            secret, "Try another input", [FallbackNote("latex", "test", secret)]
        )

    monkeypatch.setattr(select, "run_plan", fail)
    result = CliRunner().invoke(cli.main, ["-vv", "convert", str(source), "-o", str(output)])
    assert result.exit_code == 5
    assert secret not in result.output
    raw = Path(str(output) + ".report.json").read_text()
    assert secret not in raw
    assert json.loads(raw)["fallbacks"][0]["engine"] == "latex"
    assert json.loads(raw)["llm"]["actual_usd"] == 0.02
    assert json.loads(raw)["llm"]["calls"] == 2


def test_interrupt_cleans_up(fixture_engine, monkeypatch):
    source, output = fixture_engine

    def interrupt(*_):
        raise KeyboardInterrupt()

    monkeypatch.setattr(select, "run_plan", interrupt)
    result = CliRunner().invoke(cli.main, ["convert", str(source), "-o", str(output)])
    assert result.exit_code == 130
    assert not output.exists()
    assert not list(output.parent.glob("*.tmp"))
