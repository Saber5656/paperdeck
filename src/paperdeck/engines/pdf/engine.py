"""PDF engine orchestration."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from ...errors import ConversionError
from ...llm.cache import LlmCache
from ...llm.client import LlmClient
from ...llm.cost import Ledger, estimate_pdf_run
from ...netgate import NetGate
from .assemble import assemble_pdf
from .blocks import build_blocks
from .citations import extract_bibliography
from .equations import process_equations
from .extract import open_pdf
from .segment import segment


class PdfEngine:
    name = "pdf"

    def available(self, ctx: Any) -> tuple[bool, str]:
        kind = getattr(ctx.spec, "kind", None)
        if kind == "pdf-local":
            path = getattr(ctx.spec, "path", None)
            if path is None or not Path(path).exists():
                return False, "pdf-artifact-missing"
        elif kind == "arxiv":
            if not getattr(ctx.spec, "arxiv_id", None):
                return False, "arxiv-id-missing"
        else:
            return False, "pdf-input-kind"
        host = (urlparse(str(ctx.settings.llm.base_url)).hostname or "").lower()
        if not ctx.settings.resolve_api_key() and host not in {"localhost", "127.0.0.1", "::1"}:
            return False, "llm-not-configured"
        return True, "available"

    def convert(self, ctx: Any) -> Any:
        path = getattr(ctx.spec, "path", None)
        source = None
        if getattr(ctx.spec, "kind", None) == "arxiv":
            from ...input.arxiv import ArxivClient

            netgate = getattr(ctx, "netgate", None)
            if netgate is None:
                netgate = NetGate(ctx.settings)
            arxiv = ArxivClient(netgate, ctx.cache)
            meta = arxiv.metadata(ctx.spec.arxiv_id, ctx.spec.version)
            version = ctx.spec.version or meta.resolved_version
            path = arxiv.pdf(meta.id, version)
            from ...ir.model import Source

            source = Source(
                kind="arxiv",
                original=ctx.spec.original or meta.abs_url,
                arxiv_id=meta.id,
                version=f"v{version}",
            )
        if path is None:
            raise ConversionError(
                "PDF input path is missing",
                "Provide a local PDF or an arXiv identifier.",
                "pdf-input-missing",
            )
        path = Path(path)
        with open_pdf(path, ctx.settings.limits) as pdfdoc:
            pages = [pdfdoc.page_chars(index) for index in range(pdfdoc.page_count)]
            blocks = build_blocks(pages)
            char_count = sum(len(block.text) for block in blocks)
            equation_count = sum(
                1 for block in blocks if re.search(r"(?:=|∫|∑|\\(?:frac|begin|sum))", block.text)
            )
            estimate = estimate_pdf_run(pdfdoc.page_count, char_count, equation_count, ctx.settings)
            if not ctx.confirm_cost(estimate):
                raise ConversionError(
                    "LLM cost estimate was declined",
                    "Re-run with cost confirmation to use the PDF engine.",
                    "cost-declined",
                )
            netgate = getattr(ctx, "netgate", None) or NetGate(ctx.settings)
            cache = (
                LlmCache(ctx.cache, enabled=bool(ctx.settings.llm.cache))
                if ctx.cache is not None
                else None
            )
            ledger = Ledger(ctx.settings)
            ctx.run_metrics.update(
                {
                    "calls": 0,
                    "cache_hits": 0,
                    "tokens_in": 0,
                    "tokens_out": 0,
                    "estimated_usd": estimate.usd,
                    "actual_usd": 0.0,
                }
            )

            def record_usage(
                purpose: str, model: str, usage: dict[str, Any], cache_hit: bool
            ) -> None:
                ledger.record(purpose, model, usage, cache_hit)
                records = ledger.records
                ctx.run_metrics.update(
                    {
                        "calls": len(records),
                        "cache_hits": ledger.cache_hits,
                        "tokens_in": sum(
                            int(item["usage"].get("prompt_tokens", 0) or 0) for item in records
                        ),
                        "tokens_out": sum(
                            int(item["usage"].get("completion_tokens", 0) or 0) for item in records
                        ),
                        "actual_usd": ledger.spent_usd(),
                    }
                )

            llm = LlmClient(ctx.settings, netgate, cache=cache, on_usage=record_usage)
            seg = segment(blocks, llm, ledger=ledger)
            equations = process_equations(seg, blocks, pdfdoc, llm, ledger, _Allocator())
            bib_blocks = [
                block
                for block in blocks
                if seg.roles.get(block.id) and seg.roles[block.id].role == "bib_entry"
            ]
            bib = (
                extract_bibliography(bib_blocks, llm, ledger, _Allocator())
                if bib_blocks
                else ([], {}, [], ["pdf-bib-empty"])
            )
            document = assemble_pdf(
                seg,
                blocks,
                equations,
                bib,
                pdfdoc,
                ctx.settings,
                source=source,
                llm=llm,
                ledger=ledger,
            )
            from ...ir.model import LlmProvenance

            records = ledger.records
            usage_in = sum(int(item["usage"].get("prompt_tokens", 0) or 0) for item in records)
            usage_out = sum(int(item["usage"].get("completion_tokens", 0) or 0) for item in records)
            llm_provenance = LlmProvenance(
                model=ctx.settings.llm.model,
                vlm_model=ctx.settings.llm.vlm_model,
                calls=len(records),
                tokens_in=usage_in,
                tokens_out=usage_out,
                cost_usd=float(ledger.spent_usd() or 0.0),
            )
            ctx.run_metrics.update(
                {
                    "estimated_usd": estimate.usd,
                    "actual_usd": ledger.spent_usd(),
                    "cache_hits": ledger.cache_hits,
                    "calls": len(records),
                }
            )
            provenance = document.provenance.model_copy(update={"llm": llm_provenance})
            return document.model_copy(update={"provenance": provenance})


class _Allocator:
    def __init__(self) -> None:
        self.counts = {"asset": 0, "eq": 0, "bib": 0, "fig": 0, "tab": 0, "sec": 0, "para": 0}

    def next(self, kind: str) -> str:
        self.counts[kind] = self.counts.get(kind, 0) + 1
        return f"{kind}-{self.counts[kind]}"


__all__ = ["PdfEngine"]
