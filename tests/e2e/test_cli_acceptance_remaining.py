from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

from click.testing import CliRunner

from paperdeck import cli
from paperdeck.input.cache import CacheManager
from tests.e2e.test_pipeline_pdf import _config, _paper

ROOT = Path(__file__).parents[2]
DOCTOR_GOLDEN = ROOT / "tests" / "goldens" / "cli" / "doctor-offline.json"
CACHE_LS_GOLDEN = ROOT / "tests" / "goldens" / "cli" / "cache-ls.txt"


def test_cache_ls_matches_golden_and_scoped_clear_reports_exact_bytes(
    tmp_path: Path, monkeypatch
) -> None:
    cache = CacheManager(tmp_path / "paperdeck")
    cache.put("arxiv/2401.12345/2/meta.xml", b"x" * 1024)
    cache.put("arxiv/2401.12345/2/paper.pdf", b"y" * 2048)
    cache.put("arxiv/2402.1/1/source.tex", b"z" * 1024)
    llm_file = cache.llm_dir("model") / "request.json"
    llm_file.parent.mkdir(parents=True)
    llm_file.write_bytes(b"q" * 2048)
    monkeypatch.setattr(cli, "_cache", lambda: cache)

    listing = CliRunner().invoke(cli.main, ["cache", "ls"])
    assert listing.exit_code == 0, listing.output
    assert listing.stdout == CACHE_LS_GOLDEN.read_text(encoding="utf-8")

    cleared = CliRunner().invoke(cli.main, ["cache", "clear", "2401.12345", "--yes"])
    assert cleared.exit_code == 0, cleared.output
    assert cleared.stdout == "Freed 3072 bytes\n"
    assert not cache.arxiv_dir("2401.12345", 2).exists()
    assert cache.arxiv_dir("2402.1", 1).joinpath("source.tex").is_file()
    assert llm_file.is_file()


def test_cache_clear_closed_stdin_declines_in_a_real_subprocess(tmp_path: Path) -> None:
    env = {**os.environ, "XDG_CACHE_HOME": str(tmp_path / "cache")}
    result = subprocess.run(
        [sys.executable, "-m", "paperdeck.cli", "cache", "clear"],
        cwd=ROOT,
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert "--yes" in result.stderr


def test_convert_closed_stdin_declines_pdf_cost_in_a_real_subprocess(tmp_path: Path) -> None:
    pdf = tmp_path / "paper.pdf"
    config = tmp_path / "config.toml"
    output = tmp_path / "paper.html"
    _paper(pdf, "A paragraph.")
    _config(config, "http://127.0.0.1:9/v1")
    env = {
        **os.environ,
        "FAKE_API_KEY": "synthetic-key",
        "XDG_CACHE_HOME": str(tmp_path / "cache"),
    }
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "paperdeck.cli",
            "--config",
            str(config),
            "convert",
            str(pdf),
            "-o",
            str(output),
        ],
        cwd=ROOT,
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 5
    assert "non-interactive" in result.stderr.lower()
    assert not output.exists()
    assert not list(tmp_path.glob("*.tmp")) + list(tmp_path.glob(".*.tmp"))


def test_convert_sigint_returns_130_and_cleans_atomic_temps(tmp_path: Path) -> None:
    source = tmp_path / "paper.tex"
    output = tmp_path / "paper.html"
    source.write_text("fixture", encoding="utf-8")
    script = r'''
import threading
from pathlib import Path

from paperdeck import cli
from paperdeck.engines import select
from paperdeck.input import resolver
from paperdeck.input.resolver import InputSpec
from tests.fixtures.reader import document

import os

source = Path(os.environ["PAPERDECK_TEST_SOURCE"])
spec = InputSpec("latex-local", path=source, original=str(source))
resolver.resolve = lambda _value: spec
select.plan = lambda *_args: ["blocking"]

def blocking(*_args):
    Path(os.environ["PAPERDECK_TEST_READY"]).touch()
    threading.Event().wait()
    return document()

select.run_plan = blocking
cli.main(["convert", str(source), "-o", os.environ["PAPERDECK_TEST_OUTPUT"]])
'''
    env = {
        **os.environ,
        "PAPERDECK_TEST_SOURCE": str(source),
        "PAPERDECK_TEST_OUTPUT": str(output),
        "PAPERDECK_TEST_READY": str(tmp_path / "ready"),
        "XDG_CACHE_HOME": str(tmp_path / "cache"),
    }
    process = subprocess.Popen(
        [sys.executable, "-c", script],
        cwd=ROOT,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        deadline = time.monotonic() + 5
        while not (tmp_path / "ready").exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert (tmp_path / "ready").exists(), "CLI subprocess did not reach blocking engine"
        process.send_signal(subprocess.signal.SIGINT)
        stdout, stderr = process.communicate(timeout=10)
    except Exception:
        process.kill()
        process.communicate()
        raise
    assert process.returncode == 130, (stdout, stderr)
    assert "Interrupted" in stderr
    assert not output.exists()
    assert not list(tmp_path.glob("*.tmp")) + list(tmp_path.glob(".*.tmp"))


def test_doctor_offline_matches_json_golden_and_reports_platform_hint(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(cli, "_cache", lambda: CacheManager(tmp_path / "paperdeck"))
    monkeypatch.setattr("shutil.which", lambda _name: None)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    result = CliRunner().invoke(cli.main, ["doctor", "--offline", "--json"])
    assert result.exit_code == 0, result.output
    checks = json.loads(result.stdout)["checks"]
    expected = json.loads(DOCTOR_GOLDEN.read_text(encoding="utf-8"))["checks"]
    assert [(item["name"], item["status"]) for item in checks] == [
        (item["name"], item["status"]) for item in expected
    ]
    assert all(item["status"] != "fail" for item in checks)
    pandoc = next(item for item in checks if item["name"] == "pandoc")
    expected_hint = "brew install pandoc" if sys.platform == "darwin" else "apt install pandoc"
    assert expected_hint in pandoc["detail"]
    network = next(item for item in checks if item["name"] == "network")
    assert "skipped" in network["detail"].lower()
