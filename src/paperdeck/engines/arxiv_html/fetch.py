"""Fetch orchestration for the arXiv HTML engine."""

from __future__ import annotations

from paperdeck.engines import EngineContext
from paperdeck.input.arxiv import ArxivClient, ArxivMeta, HtmlArtifact
from paperdeck.netgate import NetGate


def fetch_html(ctx: EngineContext, metadata: ArxivMeta | None = None) -> HtmlArtifact | None:
    """Resolve metadata and fetch the versioned HTML artifact."""
    if ctx.spec.kind != "arxiv" or not ctx.spec.arxiv_id:
        return None
    client = ArxivClient(NetGate(ctx.settings), ctx.cache)
    resolved = metadata or client.metadata(ctx.spec.arxiv_id, ctx.spec.version)
    return client.html_page(resolved.id, resolved.resolved_version)
