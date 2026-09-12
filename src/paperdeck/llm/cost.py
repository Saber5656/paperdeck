"""Cost estimation and hard budget accounting for model calls."""
from __future__ import annotations

import math
import threading
from dataclasses import dataclass, field
from typing import Any

from ..errors import CostLimitError


@dataclass(frozen=True)
class CostEstimate:
    calls: int
    tokens_in: int
    tokens_out: int
    usd: float | None
    assumptions: list[str] = field(default_factory=list)
    model: str | None = None


def _pricing(settings: Any, model: str | None = None) -> tuple[float, float] | None:
    name = model or settings.llm.model
    p = settings.llm.pricing.get(name)
    if p is None:
        return None
    return float(p.input_per_mtok), float(p.output_per_mtok)


def estimate_pdf_run(page_count: int, char_count: int, equation_count: int, settings: Any) -> CostEstimate:
    """Return a rough ±50% estimate before any network call."""
    pages = max(0, int(page_count))
    chars = max(0, int(char_count))
    equations = max(0, int(equation_count))
    cpt = float(settings.llm.estimate.chars_per_token)
    seg_calls = math.ceil(pages / 8) if pages else 0
    seg_in = (math.ceil(chars / cpt) + 500 * seg_calls) if seg_calls else 0
    vlm_in = equations * (int(settings.llm.estimate.image_tokens_flat) + 200)
    bib_calls = 2 if chars else 0
    tokens_in = seg_in + vlm_in + (bib_calls * 500 if chars else 0)
    calls = seg_calls + equations + bib_calls
    tokens_out = sum(min(seg_in // seg_calls if seg_calls else 0, 4096) for _ in range(seg_calls))
    tokens_out += equations * 1024 + bib_calls * min(max(500, chars // 20), 4096)
    model = settings.llm.model
    price = _pricing(settings)
    assumptions = ["rough estimate; actual token use may vary by ±50%"]
    if price is None:
        usd = None
        assumptions.append(f"no pricing configured for {model}; budget enforcement switches to token count")
    else:
        usd = tokens_in * price[0] / 1_000_000 + tokens_out * price[1] / 1_000_000
    return CostEstimate(calls, tokens_in, tokens_out, usd, assumptions, model)


class Ledger:
    """Thread-safe runtime usage ledger. Cached replays have zero billable usage."""

    def __init__(self, settings: Any, *, model: str | None = None) -> None:
        self.settings = settings
        self.model = model or settings.llm.model
        self._lock = threading.RLock()
        self._records: list[dict[str, Any]] = []
        self._tokens_in = 0
        self._tokens_out = 0
        self._spent: float | None = 0.0 if _pricing(settings, self.model) is not None else None
        self.cache_hits = 0

    @property
    def records(self) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(r) for r in self._records]

    def record(self, purpose: str, model: str, usage: dict[str, Any], cache_hit: bool) -> None:
        with self._lock:
            original = dict(usage)
            pin = 0 if cache_hit else int(usage.get("prompt_tokens", 0) or 0)
            pout = 0 if cache_hit else int(usage.get("completion_tokens", 0) or 0)
            if cache_hit:
                self.cache_hits += 1
            self._tokens_in += pin
            self._tokens_out += pout
            price = _pricing(self.settings, model)
            if self._spent is not None and price is not None:
                self._spent += pin * price[0] / 1_000_000 + pout * price[1] / 1_000_000
            self._records.append({"purpose": purpose, "model": model, "usage": {**usage, "prompt_tokens": pin, "completion_tokens": pout}, "cache_hit": cache_hit, "usage_original": original if cache_hit else None})

    def spent_usd(self) -> float | None:
        with self._lock:
            return self._spent

    def token_count(self) -> int:
        with self._lock:
            return self._tokens_in + self._tokens_out

    def check_budget(self, next_call_estimate_usd: float | None, *, next_tokens: int = 0) -> None:
        with self._lock:
            limit = float(self.settings.llm.max_cost_usd)
            if self._spent is None:
                if self.token_count() + next_tokens > 2_000_000:
                    raise CostLimitError("LLM token budget exceeded", "Reduce the PDF size or configure model pricing.", float(self.token_count() + next_tokens), 2_000_000.0)
                return
            amount = float(next_call_estimate_usd or 0)
            if self._spent + amount > limit:
                raise CostLimitError(f"LLM cost limit exceeded (${self._spent + amount:.2f} > ${limit:.2f})", "Increase max_cost_usd or use the LLM cache.", self._spent + amount, limit)

    def remaining_allows(self, estimate: float | int | None) -> bool:
        try:
            self.check_budget(float(estimate) if estimate is not None else 0.0)
        except CostLimitError:
            return False
        return True


def format_estimate(est: CostEstimate) -> str:
    amount = f"~${est.usd:.2f}" if est.usd is not None else "unknown (no pricing configured)"
    model = est.model or "configured model"
    lines = [f"LLM cost estimate: {amount} ({est.calls} calls, ~{est.tokens_in:,} in / ~{est.tokens_out:,} out tokens, model {model})"]
    lines.extend(est.assumptions)
    lines.append("Proceed? [y/N]")
    return "\n".join(lines)


__all__ = ["CostEstimate", "Ledger", "estimate_pdf_run", "format_estimate"]
