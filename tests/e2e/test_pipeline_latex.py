import io
import json
import os
import subprocess
import tarfile
from pathlib import Path

import pytest
from bs4 import BeautifulSoup

ROOT = Path(__file__).parents[2]
CORPUS = ROOT / "tests" / "fixtures" / "latex"
GOLDENS = ROOT / "tests" / "goldens" / "latex"


def _semantic_snapshot(html: str) -> dict[str, object]:
    soup = BeautifulSoup(html, "html.parser")
    return {
        "title": soup.select_one(".pd-document-header h1").get_text(" ", strip=True),
        "sections": [item.get_text(" ", strip=True) for item in soup.select("section > h2")],
        "equations": [item.get("data-number") for item in soup.select(".pd-eq")],
        "has_csp": bool(soup.select_one('meta[http-equiv="Content-Security-Policy"]')),
    }


@pytest.mark.pandoc
def test_latex_corpus_cli_and_standalone_validator(tmp_path: Path) -> None:
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
