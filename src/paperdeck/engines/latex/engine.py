"""End-to-end LaTeX conversion pipeline."""

from __future__ import annotations

import re
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from paperdeck.engines import EngineContext
from paperdeck.errors import ConversionError
from paperdeck.input.arxiv import ArxivClient, ArxivMeta
from paperdeck.input.tarsafe import extract_tar, gunzip_file, sniff_kind
from paperdeck.ir.anchors import AnchorAllocator
from paperdeck.ir.model import Document, Meta, Paragraph, Provenance, Source, Text, Warning
from paperdeck.ir.validate import validate_document
from paperdeck.netgate import NetGate

from .ast_map import assert_no_sentinels, map_ast
from .bib import parse_bibliography
from .counters import assign_numbers
from .graphics import resolve_graphics
from .macros import extract_macros
from .pandoc import pandoc_version, run_pandoc
from .project import prepare
from .refs import resolve_references


def _acquire_source(ctx: EngineContext, staging: Path) -> tuple[Path, ArxivMeta | None]:
    source = ctx.spec.path
    source_meta: ArxivMeta | None = None
    if ctx.spec.kind == "arxiv":
        if not ctx.spec.arxiv_id:
            raise ConversionError(
                "arXiv input is missing its identifier",
                hint="Provide a valid arXiv ID.",
                code="arxiv-id-missing",
            )
        client = ArxivClient(NetGate(ctx.settings), ctx.cache)
        source_meta = client.metadata(ctx.spec.arxiv_id, ctx.spec.version)
        artifact = client.eprint(source_meta.id, source_meta.resolved_version)
        if artifact.kind == "pdf-only":
            raise ConversionError(
                "The arXiv e-print is PDF-only",
                hint="Use the PDF engine for this input.",
                code="eprint-is-pdf-only",
            )
        if artifact.kind == "tar-gz":
            source = staging / "extracted"
            extract_tar(artifact.path, source, ctx.settings.limits)
        else:
            source = artifact.path
    elif source is not None and ctx.spec.archive:
        kind = sniff_kind(source)
        if kind in {"tar", "tar-gz"}:
            extracted = staging / "extracted"
            extract_tar(source, extracted, ctx.settings.limits)
            source = extracted
        elif kind == "gzip-single":
            tex = staging / "source.tex"
            gunzip_file(source, tex, ctx.settings.fetch.max_download_mb)
            source = tex
        else:
            raise ConversionError(
                "LaTeX archive format was not recognized",
                hint="Provide a .tex, .tar, .tar.gz, or .tgz source.",
                code="eprint-unrecognized",
            )
    if source is None:
        raise ConversionError(
            "LaTeX source path is missing",
            hint="Provide a local TeX source or an arXiv identifier.",
            code="source-missing",
        )
    return source, source_meta


class LatexEngine:
    name = "latex"

    def available(self, ctx: EngineContext) -> tuple[bool, str]:
        version = pandoc_version()
        if version is None or version < (3, 0):
            return False, "pandoc-missing"
        if ctx.spec.kind == "arxiv":
            return True, "available"
        if ctx.spec.kind != "latex-local" or ctx.spec.path is None:
            return False, "eprint-is-pdf-only"
        return True, "available"

    def convert(self, ctx: EngineContext) -> Document:
        staging = Path(tempfile.mkdtemp(prefix="paperdeck-latex-source-"))
        try:
            source, source_meta = _acquire_source(ctx, staging)
            project = prepare(source)
        except Exception:
            shutil.rmtree(staging, ignore_errors=True)
            raise
        try:
            result = run_pandoc(project.flattened, project.root, ctx.settings.llm.timeout_s)
            allocator = AnchorAllocator()
            mapped = map_ast(result.ast, allocator)
            mapped.source_labels = set(
                re.findall(r"\\label\s*\{([^}]+)\}", project.flattened.read_text(encoding="utf-8"))
            )
            mapped.warnings.extend(project.warnings)
            mapped.warnings.extend(
                Warning(code="pandoc-warning", message=warning) for warning in result.warnings
            )
            macros, macro_warnings = extract_macros(project.preamble)
            mapped.warnings.extend(macro_warnings)
            mapped = assign_numbers(mapped, project.preamble)
            bibliography, bib_index, bib_warnings = parse_bibliography(project, allocator)
            mapped.warnings.extend(bib_warnings)
            mapped = resolve_references(mapped, mapped.labels, bib_index)
            assets, graphics_warnings = resolve_graphics(mapped, project, ctx.settings.limits)
            mapped.warnings.extend(graphics_warnings)
            title = mapped.meta_title
            authors = mapped.meta_authors
            abstract = mapped.meta_abstract
            if source_meta is not None:
                if not title:
                    title = [Text(text=source_meta.title)]
                if not authors:
                    authors = list(source_meta.authors)
                if abstract is None and source_meta.abstract:
                    abstract = [
                        Paragraph(
                            id=allocator.next("para"),
                            content=[Text(text=source_meta.abstract)],
                        )
                    ]
            document = Document(
                source=(
                    Source(
                        kind="arxiv",
                        original=ctx.spec.original,
                        arxiv_id=source_meta.id,
                        version=f"v{source_meta.resolved_version}",
                    )
                    if source_meta is not None
                    else Source(kind="local", original=ctx.spec.original)
                ),
                provenance=Provenance(
                    engine=self.name,
                    engine_versions={"pandoc": f"{result.version[0]}.{result.version[1]}"},
                    created_at=datetime.now(UTC).isoformat(),
                    fallbacks=[],
                ),
                meta=Meta(
                    title=title,
                    authors=authors,
                    abstract=abstract,
                    links=[],
                ),
                macros=macros,
                body=mapped.body,
                bibliography=bibliography,
                footnotes=mapped.footnotes,
                assets=assets,
                labels=mapped.labels,
                warnings=mapped.warnings,
            )
            document = document.model_copy(
                update={
                    "warnings": document.warnings + validate_document(document, ctx.settings.limits)
                }
            )
            assert_no_sentinels(document)
            return document
        finally:
            if project.tempdir is not None:
                shutil.rmtree(project.tempdir, ignore_errors=True)
            shutil.rmtree(staging, ignore_errors=True)
