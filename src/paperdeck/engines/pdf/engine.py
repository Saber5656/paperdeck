"""PDF engine orchestration."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ...errors import ConversionError
from ...llm.cache import LlmCache
from ...llm.client import LlmClient
from ...llm.cost import Ledger, estimate_pdf_run
from .assemble import assemble_pdf
from .blocks import build_blocks
from .citations import extract_bibliography
from .equations import process_equations
from .extract import open_pdf
from .segment import segment


class PdfEngine:
    name = "pdf"

    def available(self, ctx: Any) -> tuple[bool, str]:
        path = getattr(ctx.spec, "path", None)
        if path is None or not Path(path).exists():
            return False, "pdf-artifact-missing"
        host = str(ctx.settings.llm.base_url).lower()
        if not ctx.settings.resolve_api_key() and "localhost" not in host and "127.0.0.1" not in host:
            return False, "llm-not-configured"
        return True, "available"

    def convert(self, ctx: Any) -> Any:
        path = Path(getattr(ctx.spec, "path", ctx.spec))
        with open_pdf(path, ctx.settings.limits) as pdfdoc:
            pages = [pdfdoc.page_chars(index) for index in range(pdfdoc.page_count)]
            blocks = build_blocks(pages)
            char_count = sum(len(block.text) for block in blocks)
            estimate = estimate_pdf_run(pdfdoc.page_count, char_count, 0, ctx.settings)
            if not ctx.confirm_cost(estimate):
                raise ConversionError("LLM cost estimate was declined", "Re-run with cost confirmation to use the PDF engine.", "cost-declined")
            try:
                from ...netgate import NetGate
                netgate = NetGate(ctx.settings)
            except Exception:
                netgate = getattr(ctx, "netgate", None)
            cache = LlmCache(ctx.cache, enabled=bool(ctx.settings.llm.cache)) if ctx.cache is not None else None
            ledger = Ledger(ctx.settings)
            llm = LlmClient(ctx.settings, netgate, cache=cache, on_usage=ledger.record)
            seg = segment(blocks, llm)
            equations = process_equations(seg, blocks, pdfdoc, llm, ledger, _Allocator())
            bib_blocks = [block for block in blocks if seg.roles.get(block.id) and seg.roles[block.id].role == "bib_entry"]
            bib = extract_bibliography(bib_blocks, llm, ledger, _Allocator()) if bib_blocks else ([], {}, [], ["pdf-bib-empty"])
            return assemble_pdf(seg, blocks, equations, bib, pdfdoc, ctx.settings, source=getattr(ctx.spec, "source", None))


class _Allocator:
    def __init__(self) -> None:
        self.counts = {"asset": 0, "eq": 0, "bib": 0, "fig": 0, "tab": 0, "sec": 0, "para": 0}

    def next(self, kind: str) -> str:
        self.counts[kind] = self.counts.get(kind, 0) + 1
        return f"{kind}-{self.counts[kind]}"


__all__ = ["PdfEngine"]
