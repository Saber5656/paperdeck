# Title

[W0] 03 Implement logging setup with secret redaction

## Summary

Implement `src/paperdeck/logsetup.py`: stderr logging with verbosity levels and a
root-level redaction filter that masks API keys and Authorization values, per DESIGN
§19.1–19.2.

## Context

The redaction filter is a security control (DESIGN §20.2 T8): no log line, at any level,
may contain key material. Central setup keeps all modules on plain `logging.getLogger`.

## Scope

- `configure_logging(verbosity: int, api_key_env: str = "OPENAI_API_KEY") -> None`
  (0=WARNING, 1=INFO, ≥2=DEBUG). Callable more than once: idempotent for handlers, and a
  later call updates the redactor's `api_key_env` (bootstrap order: CLI configures early
  with the default, reconfigures after `Settings` load).
- `RedactionFilter(logging.Filter)` applied to the root handler.
- `redact(text: str) -> str` — public pure function applying the same masking rules;
  used by the CLI error handler (issue 02 §6) and anywhere text bypasses `logging`.
- `progress(msg: str) -> None` — stderr progress helper gated by `-q` (module-level
  quiet flag set by `configure_logging`).
- CLI wiring (`-v` count / `-q`).

## Detailed Requirements

1. Handler: `logging.StreamHandler(sys.stderr)`, format `%(levelname)s %(name)s: %(message)s`
   (DEBUG adds `%(asctime)s`). stdout is never used for logs (DESIGN §6.1 contract).
2. `RedactionFilter` masks, in `record.getMessage()` output and in `record.args`:
   - the exact value of `os.environ.get(<api_key_env>)` when set and length ≥ 8
     (the filter receives the env-var *name* at configure time; it re-reads the value
     lazily so late `Settings` loading still works);
   - any token matching `sk-[A-Za-z0-9_-]{8,}`;
   - any `Authorization: Bearer <x>` → `Authorization: Bearer ***`.
   Replacement is `***`. Filter must be allocation-light (compiled regexes at module load).
3. `-q` sets level ERROR and suppresses progress prints (progress uses a
   `progress(msg)` helper in this module that writes to stderr only when not quiet).
4. Idempotent: calling `configure_logging` twice must not duplicate handlers.

## Acceptance Criteria

- Unit tests: verbosity mapping; duplicate-call idempotency (incl. api_key_env update on
  reconfigure); progress gating by `-q`.
- SEC-AC: with the key env var set to `zz-customsecret987654` (deliberately NOT matching
  the `sk-` pattern), logging a string embedding it produces `***` — proves the
  env-value rule independently of the token-shape rule.
- SEC-AC: `sk-test1234567890` and `Authorization: Bearer xyz…` are masked at every
  verbosity; tests assert the raw values appear in **no** captured output stream.
- mypy strict; ruff `S` rules pass.

## Validation

`uv run pytest tests/unit/test_logsetup.py -q`

## Dependencies

01, 02.

## Non-goals

Run-report JSON (issue 48); LLM prompt logging specifics (issue 27 uses this filter).

## Design References

DESIGN §19.1–19.2, §20.2 T8; ADR-007 §5.
