import json

import pytest
from click.testing import CliRunner

from paperdeck import cli
from paperdeck.input.cache import CacheManager


@pytest.fixture
def doctor_environment(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "_cache", lambda: CacheManager(tmp_path / "paperdeck"))
    monkeypatch.setattr("shutil.which", lambda _: None)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)


def test_doctor_missing_dependencies_are_warnings(doctor_environment):
    result = CliRunner().invoke(cli.main, ["doctor", "--offline"])
    assert result.exit_code == 0, result.output
    assert "[warn] pandoc:" in result.output
    assert "install pandoc" in result.output
    assert "[warn] api-key:" in result.output


def test_doctor_isolates_failures_and_redacts_key(doctor_environment, tmp_path, monkeypatch):
    secret = "zz-customsecret987654"  # noqa: S105 -- synthetic fixture
    monkeypatch.setenv("OPENAI_API_KEY", secret)
    monkeypatch.setattr("paperdeck.render.vendor.verify_vendored", lambda _: ["changed.js"])

    def denied(**_):
        raise PermissionError()

    monkeypatch.setattr("tempfile.TemporaryFile", denied)
    result = CliRunner().invoke(cli.main, ["doctor", "--offline", "--json"])
    assert result.exit_code == 1, result.output
    assert secret not in result.output
    checks = {c["name"]: c for c in json.loads(result.stdout)["checks"]}
    assert checks["cache-writable"]["status"] == "fail"
    assert checks["katex-assets"]["status"] == "fail"
    assert checks["api-key"]["status"] == "ok"


def test_doctor_invalid_config_still_runs_other_checks(doctor_environment, tmp_path):
    config = tmp_path / "invalid.toml"
    config.write_text("unknown_setting = true")
    result = CliRunner().invoke(cli.main, ["--config", str(config), "doctor", "--json"])
    assert result.exit_code == 1
    checks = {c["name"]: c for c in json.loads(result.stdout)["checks"]}
    assert checks["config"]["status"] == "fail"
    assert checks["cache-writable"]["status"] == "ok"


def test_doctor_network_failure_is_warning(doctor_environment, monkeypatch):
    def unavailable(*_):
        raise ConnectionError("unavailable")

    monkeypatch.setattr("paperdeck.netgate.NetGate.client", unavailable)
    result = CliRunner().invoke(cli.main, ["doctor", "--json"])
    assert result.exit_code == 0, result.output
    checks = {c["name"]: c for c in json.loads(result.stdout)["checks"]}
    assert checks["network"]["status"] == "warn"
    assert "ConnectionError" in checks["network"]["detail"]
