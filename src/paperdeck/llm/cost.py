"""LLM cost contracts placeholder."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CostEstimate:
    """Estimated USD charge used by EngineContext's confirmation callback."""

    usd: float
