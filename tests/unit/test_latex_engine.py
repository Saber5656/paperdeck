import tarfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from paperdeck.config import load_settings
from paperdeck.engines import EngineContext
from paperdeck.engines.latex.engine import LatexEngine, _acquire_source
from paperdeck.errors import ConversionError
from paperdeck.input.arxiv import ArxivMeta
from paperdeck.input.cache import CacheManager
from paperdeck.input.resolver import InputSpec


@pytest.mark.skipif(__import__("shutil").which("pandoc") is None, reason="Pandoc is required")
def test_latex_engine_converts_real_source_with_cross_node_features(tmp_path: Path) -> None:
    (tmp_path / "main.tex").write_text(
        r"""\documentclass{article}
\title{A Small Paper}
\author{Ada Example}
\begin{document}
\begin{abstract}A compact abstract.\end{abstract}
\section{Results}\label{sec:results}
Equation~\ref{eq:one} and Figure~\ref{fig:plot}.
\begin{align}
  x &= 1 \label{eq:one}\\
  y &= 2 \nonumber\\
  z &= 3
\end{align}
\begin{figure}
  \includegraphics{plot.png}
  \caption{A plot}\label{fig:plot}
\end{figure}
\begin{table}
\caption{Values}
\begin{tabular}{cc}
A & B\\
1 & 2
\end{tabular}
\end{table}
Text with a note.\footnote{A note with $x^2$.}
\end{document}
""",
        encoding="utf-8",
    )
    # A valid 1x1 PNG keeps the test independent of image toolkits.
    (tmp_path / "plot.png").write_bytes(
        __import__("base64").b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
        )
    )
    settings = load_settings(None, {})
    context = EngineContext(
        spec=InputSpec("latex-local", path=tmp_path, original=str(tmp_path)),
        settings=settings,
        cache=CacheManager(tmp_path / "cache"),
        workdir=tmp_path,
        confirm_cost=lambda _estimate: True,
    )

    document = LatexEngine().convert(context)

    assert [item.text for item in document.meta.title] == ["A", " ", "Small", " ", "Paper"]
    assert document.meta.authors == ["Ada Example"]
    assert document.meta.abstract is not None
    assert any(block.type == "equation" for block in document.body[0].children)
    equations = [
        block
        for section in document.body
        if section.type == "section"
        for block in section.children
        if block.type == "equation"
    ]
    assert [equation.number for equation in equations] == ["1", None, "2"]
    assert document.labels["eq:one"].startswith("eq-")
    assert document.labels["fig:plot"].startswith("fig-")
    assert document.footnotes and document.footnotes[0].number == "1"
    assert document.assets and next(iter(document.assets.values())).width_px == 1
    assert all("\ue000" not in str(block.model_dump()) for block in document.body)


@pytest.mark.skipif(__import__("shutil").which("pandoc") is None, reason="Pandoc is required")
def test_latex_engine_extracts_local_tar_archive(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "main.tex").write_text(
        r"""\documentclass{article}
\begin{document}
\section{Archive input}
Works.
\end{document}
""",
        encoding="utf-8",
    )
    archive = tmp_path / "paper.tar.gz"
    with tarfile.open(archive, "w:gz") as output:
        output.add(source / "main.tex", arcname="main.tex")
    settings = load_settings(None, {})
    context = EngineContext(
        spec=InputSpec("latex-local", path=archive, archive=True, original=str(archive)),
        settings=settings,
        cache=CacheManager(tmp_path / "cache"),
        workdir=tmp_path,
        confirm_cost=lambda _estimate: True,
    )

    document = LatexEngine().convert(context)

    assert document.source.kind == "local"
    assert document.body[0].type == "section"


def test_latex_engine_rejects_pdf_only_arxiv(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    class FakeClient:
        def __init__(self, _netgate: object, _cache: object) -> None:
            pass

        def metadata(self, _arxiv_id: str, _version: int | None) -> SimpleNamespace:
            return SimpleNamespace(id="2401.12345", resolved_version=1)

        def eprint(self, _arxiv_id: str, _version: int) -> SimpleNamespace:
            return SimpleNamespace(kind="pdf-only", path=tmp_path / "paper.pdf")

    monkeypatch.setattr("paperdeck.engines.latex.engine.ArxivClient", FakeClient)
    settings = load_settings(None, {})
    context = EngineContext(
        spec=InputSpec("arxiv", arxiv_id="2401.12345", original="2401.12345"),
        settings=settings,
        cache=CacheManager(tmp_path / "cache"),
        workdir=tmp_path,
        confirm_cost=lambda _estimate: True,
    )

    with pytest.raises(ConversionError) as exc:
        LatexEngine().convert(context)
    assert getattr(exc.value, "code", None) == "eprint-is-pdf-only"


def test_latex_engine_available_checks_pandoc_and_arxiv_kind(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr("paperdeck.engines.latex.engine.pandoc_version", lambda: (3, 11))
    settings = load_settings(None, {})
    arxiv = EngineContext(
        spec=InputSpec("arxiv", arxiv_id="2401.12345", original="2401.12345"),
        settings=settings,
        cache=CacheManager(tmp_path / "cache"),
        workdir=tmp_path,
        confirm_cost=lambda _estimate: True,
    )
    missing = EngineContext(
        spec=InputSpec("latex-local", original="missing"),
        settings=settings,
        cache=CacheManager(tmp_path / "cache"),
        workdir=tmp_path,
        confirm_cost=lambda _estimate: True,
    )
    engine = LatexEngine()
    assert engine.available(arxiv) == (True, "available")
    assert engine.available(missing) == (False, "eprint-is-pdf-only")
    monkeypatch.setattr("paperdeck.engines.latex.engine.pandoc_version", lambda: None)
    assert engine.available(arxiv) == (False, "pandoc-missing")


def test_latex_engine_acquisition_rejects_missing_inputs(tmp_path: Path) -> None:
    settings = load_settings(None, {})
    context = EngineContext(
        spec=InputSpec("latex-local", original="missing"),
        settings=settings,
        cache=CacheManager(tmp_path / "cache"),
        workdir=tmp_path,
        confirm_cost=lambda _estimate: True,
    )
    with pytest.raises(ConversionError, match="source path") as exc:
        _acquire_source(context, tmp_path / "staging")
    assert exc.value.code == "source-missing"


@pytest.mark.skipif(__import__("shutil").which("pandoc") is None, reason="Pandoc is required")
def test_latex_engine_preserves_arxiv_metadata_links(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import paperdeck.engines.latex.engine as engine_module

    source = tmp_path / "source"
    source.mkdir()
    (source / "main.tex").write_text(
        "\\documentclass{article}\n\\begin{document}\nCached.\n\\end{document}\n",
        encoding="utf-8",
    )
    metadata = ArxivMeta(
        id="2401.12345",
        latest_version=1,
        resolved_version=1,
        title="Cached title",
        authors=["Cached Author"],
        abstract="Cached abstract",
        updated="2024-01-01T00:00:00Z",
        abs_url="https://arxiv.org/abs/2401.12345v1",
        doi="10.1234/cached",
        categories=["cs.CL"],
    )
    monkeypatch.setattr(engine_module, "_acquire_source", lambda _ctx, _staging: (source, metadata))
    settings = load_settings(None, {})
    context = EngineContext(
        spec=InputSpec("arxiv", arxiv_id="2401.12345", original="2401.12345"),
        settings=settings,
        cache=CacheManager(tmp_path / "cache"),
        workdir=tmp_path,
        confirm_cost=lambda _estimate: True,
    )
    document = LatexEngine().convert(context)
    assert [(link.kind, link.url) for link in document.meta.links] == [
        ("arxiv", "https://arxiv.org/abs/2401.12345v1"),
        ("doi", "https://doi.org/10.1234/cached"),
    ]
