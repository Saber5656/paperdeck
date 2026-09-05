# Title

[W0] 02 Implement error taxonomy and exit-code mapping

## Summary

Implement `src/paperdeck/errors.py`: the `PaperdeckError` hierarchy, exit-code mapping, and
the CLI-level error presenter, exactly per DESIGN §18.

## Context

Every module raises from this hierarchy; the CLI converts exceptions to user-facing
messages and process exit codes. Defining it early keeps error handling uniform.

## Scope

- `errors.py` with all exception classes and the `EXIT_CODES` mapping.
- A `present_error(exc, verbose: int) -> tuple[str, int]` helper returning the rendered
  stderr text and exit code.
- Wiring in `cli.py`: a top-level try/except that uses `present_error`.

## Detailed Requirements

1. Base: `class PaperdeckError(Exception)` with fields `user_message: str`,
   `hint: str` (**required, no default** — DESIGN §18 mandates an actionable hint on
   every error; an empty string is a test failure), `code: str` (machine-readable slug,
   e.g. `"tar-traversal"`).
2. `@dataclass(frozen=True) class FallbackNote: engine: str; reason_code: str;
   detail: str` — defined here as the canonical attempt type (consumed by issue 26's
   selection machine and by IR provenance mapping).
3. Subclasses and exit codes exactly as DESIGN §18: `InputError`=3, `FetchError`=4,
   `AllEnginesFailedError`=5 (carries `attempts: list[FallbackNote]` and renders them as
   an aligned three-column table `ENGINE | REASON | DETAIL` in attempt order), `LlmError`=6,
   `CostLimitError`=7 (carries `estimate_usd`, `limit_usd`), `ConfigError`=8,
   `SecurityError`=9, `OutputExistsError`=10.
   Click's `UsageError` keeps exit 2; unexpected exceptions map to exit 1 with the
   bug-report hint `Please report: https://github.com/Saber5656/paperdeck/issues`.
4. Presentation format: `error: <user_message>` then `hint: <hint>`; at verbosity ≥2
   append the traceback. No color codes in v1.
5. `SecurityError` messages must never echo untrusted content verbatim beyond 120
   sanitized characters (control chars stripped) — SEC-AC.
6. Redaction of error output: the CLI top-level handler must pass the full rendered text
   (message, hint, table, traceback) through `logsetup.redact()` (issue 03 exposes it)
   before writing to stderr, so secrets can never leak via exception text (DESIGN §19.2,
   ADR-007 §5). `errors.py` itself stays redaction-free (no config dependency).

## Acceptance Criteria

- Unit tests cover every subclass → exit code, three-column table rendering of
  `AllEnginesFailedError` (from `FallbackNote`s), non-empty `hint:` line for every
  subclass, and traceback gating by verbosity.
- SEC-AC: a `SecurityError` constructed with a 10 KB malicious string containing ANSI
  escapes renders ≤ 200 chars with escapes stripped.
- SEC-AC: an exception whose message embeds `sk-test1234567890` and an
  `Authorization: Bearer …` header renders with both masked (`***`) on stderr, at every
  verbosity level including the traceback path (wiring test through the CLI handler).
- mypy strict passes; no other module imports `sys.exit` besides `cli.py`.

## Validation

`uv run pytest tests/unit/test_errors.py -q`

## Dependencies

— (The CLI-handler redaction wiring test lands together with the logging issue's
`redact()`; that tiny test module may ship in the logging PR if this one merges first.)

## Non-goals

Logging setup (03); actual raising sites (later issues).

## Design References

DESIGN §18, §19.1; ADR-007 (error content hygiene).
