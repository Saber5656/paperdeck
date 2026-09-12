import json
from pathlib import Path

from click.testing import CliRunner

from paperdeck.cli import main


def test_doctor_offline_json_and_cache_path(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    monkeypatch.setenv("PAPERDECK_OFFLINE", "1")
    result = CliRunner().invoke(main, ["doctor", "--json"])
    assert result.exit_code == 0, result.output
    checks = json.loads(result.stdout)["checks"]
    assert {
        "python",
        "config",
        "pandoc",
        "katex-assets",
        "api-key",
        "cache-writable",
        "network",
    } == {c["name"] for c in checks}
    assert all(c["status"] != "fail" for c in checks)
    assert "skip" in next(c["detail"] for c in checks if c["name"] == "network").lower()
    result = CliRunner().invoke(main, ["cache", "path"])
    assert result.exit_code == 0
    assert Path(result.stdout.strip()).name == "paperdeck"


def test_convert_fail_fast_existing_output(tmp_path):
    source = tmp_path / "paper.tex"
    source.write_text("not latex")
    output = tmp_path / "paper.html"
    output.write_text("keep me")
    result = CliRunner().invoke(main, ["convert", str(source), "-o", str(output)])
    assert result.exit_code == 10, result.output
    assert output.read_text() == "keep me"


def test_reject_cache_clear_without_confirmation():
    result = CliRunner().invoke(main, ["cache", "clear"], input="")
    assert result.exit_code == 2


def test_convert_with_real_latex(tmp_path):
    source = tmp_path / "paper.tex"
    source.write_text(
        r"\documentclass{article}\title{A small paper}\author{A. Researcher}"
        r"\begin{document}\maketitle\section{Introduction}See Eq.~\eqref{eq:one}."
        r"\begin{equation}x^2+1=2\label{eq:one}\end{equation}\end{document}"
    )
    output = tmp_path / "paper.html"
    result = CliRunner().invoke(
        main, ["-q", "convert", str(source), "-o", str(output), "--offline"]
    )
    assert result.exit_code == 0, result.output
    assert result.stdout.strip() == str(output)
    assert result.stderr == ""
    report = json.loads(Path(str(output) + ".report.json").read_text())
    assert report["engine"] == "latex"
    assert report["versions"]["katex"]
    assert report["llm"]["calls"] == 0
    assert report["output"]["bytes"] == output.stat().st_size
    assert {"resolve", "convert", "render", "validate", "write"} <= report["timings_ms"].keys()
    from paperdeck.render.validate import validate_html

    assert validate_html(output.read_text()) == []
