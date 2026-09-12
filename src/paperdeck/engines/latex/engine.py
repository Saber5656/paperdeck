"""End-to-end LaTeX conversion pipeline."""

from __future__ import annotations

import re
import shutil
from datetime import UTC, datetime
from pathlib import Path

from paperdeck.engines import EngineContext
from paperdeck.ir.anchors import AnchorAllocator
from paperdeck.ir.model import Document, Meta, Provenance, Source, Warning
from paperdeck.ir.validate import validate_document

from .ast_map import assert_no_sentinels, map_ast
from .bib import parse_bibliography
from .counters import assign_numbers
from .graphics import resolve_graphics
from .macros import extract_macros
from .pandoc import pandoc_version, run_pandoc
from .project import prepare
from .refs import resolve_references


class LatexEngine:
    name = "latex"

    def available(self, ctx: EngineContext) -> tuple[bool, str]:
        version = pandoc_version()
        if version is None or version < (3, 0):
            return False, "pandoc-missing"
        original = Path(ctx.spec.original)
        if original.suffix.lower() not in {".tex", ".tar", ".gz", ".tgz"} and not original.is_dir():
            return False, "eprint-is-pdf-only"
        return True, "available"

    def convert(self, ctx: EngineContext) -> Document:
        source = Path(ctx.spec.original)
        project = prepare(source)
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
            document = Document(
                source=Source(kind="local", original=str(source)),
                provenance=Provenance(
                    engine=self.name,
                    engine_versions={"pandoc": f"{result.version[0]}.{result.version[1]}"},
                    created_at=datetime.now(UTC).isoformat(),
                    fallbacks=[],
                ),
                meta=Meta(
                    title=mapped.meta_title,
                    authors=mapped.meta_authors,
                    abstract=mapped.meta_abstract,
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
