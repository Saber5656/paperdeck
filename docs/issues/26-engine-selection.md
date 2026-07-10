# Title

[W3] 26 Implement the engine selection state machine

## Summary

Implement `src/paperdeck/engines/select.py`: build the engine attempt plan from
input kind, `--engine`, `--offline`, and cache state; execute engines in order with
recorded fallback reasons, exactly per the DESIGN §9 tables.

## Context

This is the conductor that realizes ADR-001's "best available engine per paper with no
silent fallback".

## Scope

- `plan(spec: InputSpec, engine_flag: str, settings: Settings, cache: CacheManager)
  -> list[Engine]` (validated; invalid forced combinations → `UsageError`; the A2
  offline row consults `cache` for artifact presence — this is why `cache` is a
  parameter).
- `run_plan(plan, ctx) -> tuple[Document, list[FallbackNote]]`.
- Registry wiring of the three engines (`engines/__init__.py` registry added here).

## Detailed Requirements

1. Plans exactly per DESIGN §9 rows A1/A2/L1/P1/F1. Forced-engine validation examples
   that must raise `UsageError` with explanatory text: `--engine arxiv-html` + local pdf;
   `--engine latex` + local pdf; `--engine pdf` + local tex.
2. Per-engine pre-gate via `Engine.available(ctx) -> (bool, reason)`; unavailable →
   `FallbackNote` (**the frozen dataclass defined in `errors.py` by issue 02** — do not
   redefine) appended, next engine tried. Reason codes are the fixed vocabulary:
   `html-unavailable`, `html-stub`, `html-no-content`, `html-missing-title`,
   `html-low-quality`, `pandoc-missing`, `eprint-is-pdf-only`, `no-main-tex`,
   `offline-uncached`, `llm-not-configured`, `cost-declined`, plus
   `convert-failed:<code>` for runtime `ConversionError`s.
3. `convert()` raising `ConversionError` → note + continue, with `reason_code` = the
   error's `code` when it is in the fixed vocabulary above, else `convert-failed:<code>`;
   raising `SecurityError` → **abort the whole run** (no fallback across security
   violations; DESIGN §20 posture).
4. `pdf` engine attempt triggers the cost confirmation callback (`ctx.confirm_cost`)
   before conversion; declined → note `cost-declined` and, being the last engine, exhaust.
5. Exhausted plan → `AllEnginesFailedError(attempts=notes)` (exit 5 table via issue 02).
6. One stderr progress line per transition (DESIGN §6.1 #3 wording).
7. Fallback notes are returned for provenance embedding (engine assembly already wrote
   engine-local provenance; `run_plan` attaches the cross-engine notes to the winning
   `Document.provenance.fallbacks`).

## Acceptance Criteria

- Unit tests with stub engines (recording calls): every plan row; forced-engine
  validation matrix; fallback on unavailable and on ConversionError; SecurityError
  aborts immediately (later engines not called — asserted); cost-declined path;
  exhaustion error carries all notes in order.
- Offline matrix: arXiv input with cached html / cached source / nothing → plans A2
  behavior per artifact presence (stub cache).
- Progress lines match the DESIGN §6.1 format (captured stderr).

## Validation

`uv run pytest tests/unit/test_select.py -q`

## Dependencies

02, 04, 07, 09 (cache probes). The three concrete engines plug in as they land — tests
use stubs; the `Engine` protocol comes from scaffolding.

## Non-goals

Cost estimation math (29); CLI wiring (48).

## Design References

DESIGN §9, §6.1; ADR-001; ADR-007 (no fallback across SecurityError).
