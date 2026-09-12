"""Engine selection state machine and fallback recording."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from importlib import import_module
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

import click

from paperdeck.engines import Engine, EngineContext
from paperdeck.errors import (
    AllEnginesFailedError,
    ConfigError,
    ConversionError,
    FallbackNote,
    SecurityError,
)
from paperdeck.input.cache import CacheManager
from paperdeck.input.resolver import InputSpec
from paperdeck.ir.model import Document
from paperdeck.ir.validate import validate_document
from paperdeck.llm.cost import CostEstimate
from paperdeck.logsetup import progress

if TYPE_CHECKING:
    from paperdeck.config import Settings


_NAMES = ("arxiv-html", "latex", "pdf")
_REASONS = {
    "html-unavailable",
    "html-stub",
    "html-no-content",
    "html-missing-title",
    "html-low-quality",
    "pandoc-missing",
    "eprint-is-pdf-only",
    "no-main-tex",
    "offline-uncached",
    "llm-not-configured",
    "cost-declined",
}


def _registry(engine_registry: Mapping[str, Engine] | None) -> dict[str, Engine]:
    """Load concrete engines lazily so fake registries need no optional engines."""
    if engine_registry is not None:
        return dict(engine_registry)
    specs = {
        "arxiv-html": ("paperdeck.engines.arxiv_html.parse_content", "ArxivHtmlEngine"),
        "latex": ("paperdeck.engines.latex.engine", "LatexEngine"),
        "pdf": ("paperdeck.engines.pdf.engine", "PdfEngine"),
    }
    loaded: dict[str, Engine] = {}
    for name, (module_name, class_name) in specs.items():
        module = import_module(module_name)
        loaded[name] = getattr(module, class_name)()
    return loaded


def plan(
    spec: InputSpec,
    engine: str = "auto",
    settings: Settings | None = None,
    cache: CacheManager | None = None,
    engine_registry: Mapping[str, Engine] | None = None,
) -> list[str]:
    """Return ordered engine names for an input.

    Cache probing is deferred to ``Engine.available`` so unavailable attempts
    can be recorded by ``run_plan``.
    """
    del settings, cache, engine_registry
    auto = {
        "arxiv": ["arxiv-html", "latex", "pdf"],
        "latex-local": ["latex"],
        "pdf-local": ["pdf"],
    }
    allowed = {
        "arxiv": set(_NAMES),
        "latex-local": {"latex"},
        "pdf-local": {"pdf"},
    }
    if engine == "auto":
        return list(auto[spec.kind])
    if engine not in _NAMES:
        raise click.UsageError(f"unknown engine {engine!r}; choose auto, arxiv-html, latex, or pdf")
    if engine not in allowed[spec.kind]:
        raise click.UsageError(
            f"engine {engine!r} cannot process input kind {spec.kind!r}; use --engine auto"
        )
    return [engine]


def _local_base_url(settings: Any) -> bool:
    host = urlparse(str(settings.llm.base_url)).hostname or ""
    return host.lower() in {"localhost", "127.0.0.1", "::1"}


def _pdf_configured(ctx: EngineContext) -> bool:
    return bool(ctx.settings.resolve_api_key()) or _local_base_url(ctx.settings)


def _fallback(
    engine: str,
    reason: str,
    detail: str,
    notes: list[FallbackNote],
    next_engine: str | None,
) -> None:
    note = FallbackNote(engine, reason, detail)
    notes.append(note)
    transition = f"falling back to {next_engine}" if next_engine else "exhausted"
    progress(f"engine: {engine} failed ({reason}) -> {transition}")


def run_plan(
    engine_plan: Sequence[str],
    ctx: EngineContext,
    registry: Mapping[str, Engine] | None = None,
) -> Document:
    """Run names in order and attach skipped attempts to winning provenance."""
    engines = _registry(registry)
    notes: list[FallbackNote] = []
    for index, name in enumerate(engine_plan):
        next_engine = engine_plan[index + 1] if index + 1 < len(engine_plan) else None
        engine = engines.get(name)
        if engine is None:
            _fallback(
                name,
                "convert-failed:unknown-engine",
                "engine is not registered",
                notes,
                next_engine,
            )
            continue
        progress(f"engine: trying {engine.name}")
        if name == "pdf" and ctx.settings.offline:
            _fallback(
                name,
                "offline-uncached",
                "PDF engine requires an online LLM request",
                notes,
                next_engine,
            )
            continue
        if name == "pdf" and not _pdf_configured(ctx):
            _fallback(
                name,
                "llm-not-configured",
                "configure an API key or local LLM endpoint",
                notes,
                next_engine,
            )
            continue
        available, reason = engine.available(ctx)
        if not available:
            _fallback(
                name,
                reason or "offline-uncached",
                reason or "engine unavailable",
                notes,
                next_engine,
            )
            continue
        if name == "pdf" and not ctx.confirm_cost(CostEstimate(usd=0.0)):
            _fallback(name, "cost-declined", "cost confirmation declined", notes, next_engine)
            continue
        try:
            document = engine.convert(ctx)
        except SecurityError:
            raise
        except ConfigError as exc:
            reason_code = "llm-not-configured" if name == "pdf" else f"convert-failed:{exc.code}"
            _fallback(name, reason_code, exc.user_message, notes, next_engine)
            continue
        except ConversionError as exc:
            reason_code = exc.code if exc.code in _REASONS else f"convert-failed:{exc.code}"
            _fallback(name, reason_code, exc.user_message, notes, next_engine)
            continue
        provenance = document.provenance.model_copy(update={"fallbacks": notes})
        result = document.model_copy(update={"provenance": provenance})
        validate_document(result, ctx.settings.limits)
        return result
    raise AllEnginesFailedError(
        "All conversion engines failed", "choose another engine or inspect the report", notes
    )
