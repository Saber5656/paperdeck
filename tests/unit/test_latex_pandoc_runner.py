from pathlib import Path

import pytest

from paperdeck.engines.latex import pandoc
from paperdeck.errors import ConversionError


def _stub(tmp_path: Path, body: str = "") -> Path:
    executable = tmp_path / "pandoc"
    executable.write_text(
        '#!/bin/sh\nif [ "$1" = "--version" ]; then echo "pandoc 3.11"; exit 0; fi\n' + body,
        encoding="utf-8",
    )
    executable.chmod(0o755)
    return executable


def test_pandoc_runner_success_warnings_and_argument_boundary(tmp_path: Path, monkeypatch) -> None:
    _stub(
        tmp_path, 'echo \'{"pandoc-api-version":[1,23],"meta":{},"blocks":[]}\'; echo warning >&2\n'
    )
    monkeypatch.setenv("PATH", str(tmp_path))
    source = tmp_path / "name with ;rm.tex"
    source.write_text("", encoding="utf-8")
    result = pandoc.run_pandoc(source, tmp_path, timeout_s=2)
    assert result.ast["blocks"] == []
    assert result.warnings == ["warning"]
    assert result.version == (3, 11)


def test_pandoc_runner_failure_modes(tmp_path: Path, monkeypatch) -> None:
    _stub(tmp_path, 'echo "bad json"; exit 0\n')
    monkeypatch.setenv("PATH", str(tmp_path))
    with pytest.raises(ConversionError) as bad_json:
        pandoc.run_pandoc(tmp_path / "source.tex", tmp_path, timeout_s=2)
    assert bad_json.value.code == "pandoc-bad-json"

    _stub(tmp_path, 'echo "failure" >&2; exit 2\n')
    with pytest.raises(ConversionError) as failed:
        pandoc.run_pandoc(tmp_path / "source.tex", tmp_path, timeout_s=2)
    assert failed.value.code == "pandoc-failed"

    _stub(tmp_path, "sleep 2\n")
    with pytest.raises(ConversionError) as timed_out:
        pandoc.run_pandoc(tmp_path / "source.tex", tmp_path, timeout_s=0)
    assert timed_out.value.code == "pandoc-timeout"


def test_pandoc_runner_version_and_shape_guards(monkeypatch) -> None:
    monkeypatch.setattr(pandoc.shutil, "which", lambda _name: None)
    assert pandoc.pandoc_version() is None
    with pytest.raises(ConversionError) as missing:
        pandoc.run_pandoc(Path("missing.tex"), Path("."))
    assert missing.value.code == "pandoc-missing"
    with pytest.raises(ConversionError) as shape:
        pandoc._parse_result(b"{}", b"", (3, 11))
    assert shape.value.code == "pandoc-bad-json"
