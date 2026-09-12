from pathlib import Path

import pytest

from paperdeck.config import load_settings
from paperdeck.errors import ConfigError


def test_defaults_and_precedence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = tmp_path / "config.toml"
    config.write_text('[llm]\nmodel = "file-model"\nmax_cost_usd = 2.0\n', encoding="utf-8")
    monkeypatch.setenv("PAPERDECK_LLM_MODEL", "env-model")
    settings = load_settings(config, {"llm.model": "cli-model", "offline": True})
    assert settings.llm.model == "cli-model"
    assert settings.llm.max_cost_usd == 2.0
    assert settings.offline is True


def test_unknown_keys_and_schema_version(tmp_path: Path) -> None:
    bad = tmp_path / "bad.toml"
    bad.write_text('[llm]\nmodle = "x"\n', encoding="utf-8")
    with pytest.raises(ConfigError, match="llm.modle"):
        load_settings(bad, {})
    bad.write_text("schema_version = 2\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="schema_version"):
        load_settings(bad, {})


def test_invalid_ranges_aggregate(tmp_path: Path) -> None:
    bad = tmp_path / "bad.toml"
    bad.write_text('[llm]\ntimeout_s = 0\nbase_url = "ftp://bad"\n', encoding="utf-8")
    with pytest.raises(ConfigError) as exc:
        load_settings(bad, {})
    assert "timeout_s" in str(exc.value) and "base_url" in str(exc.value)
