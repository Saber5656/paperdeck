import io
import json
import os
import re
import subprocess
import tarfile
from pathlib import Path

import pytest
from bs4 import BeautifulSoup

ROOT = Path(__file__).parents[2]
CORPUS = ROOT / "tests" / "fixtures" / "latex"
GOLDENS = ROOT / "tests" / "goldens" / "latex"


def _portable_html(html: str) -> str:
    """Normalize the one environment-dependent value in rendered HTML."""
    return re.sub(r"(<p>pandoc )[^<]+(</p>)", r"\1VERSION\2", html)


def _assert_or_update_golden(path: Path, html: str, update: bool) -> None:
    normalized = _portable_html(html)
    if update:
        path.write_text(normalized, encoding="utf-8")
        return
    assert path.is_file(), f"missing HTML golden: {path}"
    assert path.read_text(encoding="utf-8") == normalized


def _semantic_snapshot(html: str) -> dict[str, object]:
    soup = BeautifulSoup(html, "html.parser")
    return {
        "title": soup.select_one(".pd-document-header h1").get_text(" ", strip=True),
        "sections": [item.get_text(" ", strip=True) for item in soup.select("section > h2")],
        "equations": [item.get("data-number") for item in soup.select(".pd-eq")],
        "has_csp": bool(soup.select_one('meta[http-equiv="Content-Security-Policy"]')),
    }


def _extended_snapshot(html: str) -> dict[str, object]:
    soup = BeautifulSoup(html, "html.parser")
    return {
        "title": soup.select_one(".pd-document-header h1").get_text(" ", strip=True),
        "sections": [item.get_text(" ", strip=True) for item in soup.select("section > h2")],
        "figures": len(soup.select('figure[id^="fig-"]')),
        "tables": len(soup.select('figure[id^="tab-"]')),
        "figure_refs": len(soup.select('a.pd-ref[href^="#fig-"]')),
        "table_refs": len(soup.select('a.pd-ref[href^="#tab-"]')),
        "bib_refs": len(soup.select('a.pd-ref[href^="#bib-"]')),
        "bib_entries": len(soup.select('li[id^="bib-"]')),
        "math": len(soup.select(".pd-math")),
        "code": len(soup.select("code")),
    }


@pytest.mark.pandoc
def test_latex_corpus_cli_and_standalone_validator(
    tmp_path: Path, request: pytest.FixtureRequest
) -> None:
    update_goldens = bool(request.config.getoption("--update-goldens"))
    for name in ("minimal", "equations"):
        output = tmp_path / f"{name}.html"
        environment = os.environ.copy()
        environment.update(
            {
                "PAPERDECK_OFFLINE": "1",
                "XDG_CACHE_HOME": str(tmp_path / "cache"),
            }
        )
        result = subprocess.run(  # noqa: S603
            [
                "uv",
                "run",
                "paperdeck",
                "-q",
                "convert",
                str(CORPUS / name / "main.tex"),
                "--engine",
                "latex",
                "--offline",
                "--yes",
                "-o",
                str(output),
            ],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == str(output)
        _assert_or_update_golden(GOLDENS / f"{name}.html", output.read_text(), update_goldens)
        report = json.loads((Path(str(output) + ".report.json")).read_text())
        assert report["engine"] == "latex"
        assert report["llm"]["calls"] == 0
        assert {"resolve", "convert", "render", "validate", "write"} <= set(report["timings_ms"])
        standalone = subprocess.run(  # noqa: S603
            ["uv", "run", "python", "-m", "paperdeck.render.validate", str(output)],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        assert standalone.returncode == 0, standalone.stdout + standalone.stderr
        expected = json.loads((GOLDENS / f"{name}.json").read_text())
        assert _semantic_snapshot(output.read_text()) == expected


def test_html_golden_detects_content_corruption(tmp_path: Path) -> None:
    content = (GOLDENS / "minimal.html").read_text(encoding="utf-8")
    corrupted = content.replace("Minimal Golden", "Corrupted Golden", 1)
    golden = tmp_path / "minimal.html"
    golden.write_text(corrupted, encoding="utf-8")
    with pytest.raises(AssertionError):
        _assert_or_update_golden(golden, content, False)


def _seed_arxiv_cache(cache_home: Path) -> None:
    cache = cache_home / "paperdeck" / "arxiv" / "2401.12345" / "1"
    cache.mkdir(parents=True)
    metadata = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>https://arxiv.org/abs/2401.12345v1</id>
    <title>Offline Cached Paper</title>
    <summary>Cached abstract.</summary>
    <updated>2024-01-02T00:00:00Z</updated>
    <author><name>Offline Author</name></author>
    <link rel="alternate" href="https://arxiv.org/abs/2401.12345v1" />
    <arxiv:doi>10.1234/offline.paper</arxiv:doi>
  </entry>
</feed>
"""
    (cache / "meta.xml").write_bytes(metadata)
    source = io.BytesIO()
    with tarfile.open(fileobj=source, mode="w:gz") as archive:
        payload = b"\\documentclass{article}\n\\begin{document}\nCached source.\n\\end{document}\n"
        info = tarfile.TarInfo("main.tex")
        info.size = len(payload)
        archive.addfile(info, io.BytesIO(payload))
    (cache / "source.tar.gz").write_bytes(source.getvalue())


@pytest.mark.pandoc
def test_latex_cached_arxiv_cli_offline(tmp_path: Path) -> None:
    _seed_arxiv_cache(tmp_path / "cache")
    output = tmp_path / "cached.html"
    environment = os.environ.copy()
    environment.update(
        {
            "PAPERDECK_OFFLINE": "1",
            "XDG_CACHE_HOME": str(tmp_path / "cache"),
            "PAPERDECK_FAKE_NOW": "2000-01-01T00:00:00+00:00",
        }
    )
    result = subprocess.run(  # noqa: S603
        [
            "uv",
            "run",
            "paperdeck",
            "-q",
            "convert",
            "2401.12345",
            "--engine",
            "latex",
            "--offline",
            "--yes",
            "-o",
            str(output),
        ],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "Offline Cached Paper" in output.read_text()
    report = json.loads((Path(str(output) + ".report.json")).read_text())
    assert report["engine"] == "latex"


@pytest.mark.pandoc
def test_latex_extended_corpus_cli_and_validator(tmp_path: Path) -> None:
    names = (
        "figures_tables",
        "bib_bbl",
        "bib_natbib",
        "macros",
        "multifile",
        "pathological",
    )
    for name in names:
        output = tmp_path / f"{name}.html"
        environment = os.environ.copy()
        environment.update(
            {
                "PAPERDECK_OFFLINE": "1",
                "XDG_CACHE_HOME": str(tmp_path / "cache"),
                "PAPERDECK_FAKE_NOW": "2000-01-01T00:00:00+00:00",
            }
        )
        result = subprocess.run(  # noqa: S603
            [
                "uv",
                "run",
                "paperdeck",
                "-q",
                "convert",
                str(CORPUS / name / "main.tex"),
                "--engine",
                "latex",
                "--offline",
                "--yes",
                "-o",
                str(output),
            ],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, f"{name}: {result.stderr}"
        standalone = subprocess.run(  # noqa: S603
            ["uv", "run", "python", "-m", "paperdeck.render.validate", str(output)],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        assert standalone.returncode == 0, f"{name}: {standalone.stdout}{standalone.stderr}"
        report = json.loads((Path(str(output) + ".report.json")).read_text())
        assert report["engine"] == "latex"
        assert report["llm"]["calls"] == 0
        html = output.read_text()
        assert "\ue000" not in html and "\ue001" not in html
        expected = json.loads((GOLDENS / f"{name}.json").read_text())
        assert _extended_snapshot(html) == expected["snapshot"]
        assert [warning["code"] for warning in report["warnings"]] == expected["warnings"]
        if name == "pathological":
            code = BeautifulSoup(html, "html.parser").select_one("code")
            assert code is not None and "<script>alert(1)</script>" in code.get_text()
