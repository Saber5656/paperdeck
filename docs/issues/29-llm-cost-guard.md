# Title

[W4] 29 Implement LLM cost estimation, ledger, and budget guard

## Summary

Implement `src/paperdeck/llm/cost.py`: pre-flight cost estimation, the running usage
ledger, and hard budget enforcement with the interactive confirmation contract, per DESIGN
§14.6.

## Context

The pdf engine spends real money; T11 (cost abuse) requires an explicit estimate,
user consent, and a hard stop.

## Scope

- `CostEstimate` (`calls: int`, `tokens_in: int`, `tokens_out: int`, `usd: float | None`,
  `assumptions: list[str]`).
- `estimate_pdf_run(page_count, char_count, equation_count, settings) -> CostEstimate`.
- `class Ledger:` `record(purpose, model, usage, cache_hit)`,
  `spent_usd() -> float | None`, `check_budget(next_call_estimate_usd)` raising
  `CostLimitError`.
- Confirmation helper `format_estimate(est) -> str` (exact CLI text).

## Detailed Requirements

1. Estimation formulas (documented as ±50% rough in the output text, DESIGN §14.6):
   segmentation calls = `ceil(pages/8)`, tokens_in per call ≈ page chars /
   `chars_per_token` + 500 overhead; VLM calls = equation_count, each
   `image_tokens_flat` + 200; bib/cite-map calls = 2, sized by bib chars; tokens_out
   assumed `min(tokens_in, 4096)` per call.
2. Pricing: `usd = Σ tokens × settings.llm.pricing[model]`; model absent from pricing →
   `usd=None` and assumptions gains `no pricing configured for <model>; budget enforcement
   switches to token count (warn at 2,000,000 tokens)`.
3. Ledger: thread-safe accumulation; `check_budget` raises `CostLimitError` when
   `spent + next > max_cost_usd` (or token-count rule when `usd=None`); VLM degradation
   hook: `remaining_allows(estimate) -> bool` used by issue 34 to stop VLM calls with
   warning `vlm-budget-exhausted` instead of aborting the run.
4. Confirmation text format (exact, for issue 48's prompt):
   `LLM cost estimate: ~$0.42 (23 calls, ~310k in / ~45k out tokens, model gpt-5.6-terra)`
   + one line per assumption + `Proceed? [y/N]`.
5. Actual-vs-estimate recorded in the run report structure (`llm.estimated_usd`,
   `llm.actual_usd`, `llm.cache_hits`).
6. Pure logic — no I/O, no prompting here (CLI owns TTY interaction).

## Acceptance Criteria

- Unit tests: formula outputs for a 30-page/40-eq synthetic (numbers pinned); unknown
  model → None-usd token fallback incl. 2M warn threshold; cache hits add $0 but count
  `cache_hits`; degradation hook boundary.
- SEC-AC: ledger accumulation raises `CostLimitError` at the exact budget boundary
  (T11 hard-stop proven; no call may take spend past `max_cost_usd`).
- Format test: byte-exact expected confirmation block for a fixed estimate.
- mypy strict; no float equality in tests (use pytest.approx).

## Validation

`uv run pytest tests/unit/test_llm_cost.py -q`

## Dependencies

02, 04, 27 (usage shape).

## Non-goals

TTY prompting (48); actual token counting via provider tokenizers (estimate is heuristic
by design).

## Design References

DESIGN §14.6, §20.2 T11, §19.3; ADR-004 §6.
