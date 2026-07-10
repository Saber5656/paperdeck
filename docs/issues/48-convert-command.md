# Title

[W6] 48 Implement the `convert` command orchestration and run report

## Summary

Implement `paperdeck convert` in `cli.py` plus `report.py`: the end-to-end pipeline
(resolve → acquire → select/run engines → render → validate → atomic write), interactive
cost confirmation, progress output contract, and the run-report JSON, per DESIGN §6.1 and
§19.3.

## Context

The user-facing spine that composes everything W0–W5 built; its output contract (stdout
path, stderr progress, exit codes, report file) is what scripts and tests rely on.

## Scope

- `convert` command with the full §6.1 option table.
- `report.py`: `RunReport` model + writer.
- Cost confirmation TTY interaction (using issue 29's `format_estimate`).
- Output writing: atomic, `--force`, slug default naming.

## Detailed Requirements

1. Option set and semantics exactly per DESIGN §6.1 table (`-o`, `--engine`, `--offline`,
   `--force`, `--max-cost`, `--yes`, `--no-llm-cache`); `--offline` also settable via
   `PAPERDECK_OFFLINE` (04).
2. Flow: `resolve` (07) → build `EngineContext` (settings override merge; `confirm_cost`
   closure = print estimate → `click.confirm` unless `--yes`; non-TTY stdin without
   `--yes` → decline with hint) → `plan`+`run_plan` (26) → `build_bundle` (39) →
   `render_document` (38) → `validate_html` (40; violations → `SecurityError` — a
   paperdeck bug by definition, message says so) → atomic write (`.tmp` + `os.replace`)
   → write `<output>.report.json` → print absolute output path to stdout (the ONLY
   stdout line).
3. Output path: default `<output.default_dir>/<slug>.html`; existing without `--force`
   → `OutputExistsError` (exit 10) *before* any conversion work (fail fast).
4. Progress lines (stderr, suppressed by `-q`): `resolving…`, `fetching <what>…`,
   `engine <name>: converting…`, fallback lines (26's wording), `rendering…`,
   `validating…`, `done in <s> (engine=<name>, warnings=<n>, cost=$<x>)`.
5. `RunReport` fields exactly per DESIGN §19.3 (the normative field set): `{input,
   engine, fallbacks, timings_ms: {stage: ms}, warnings: [{code, message}],
   llm: {calls, cache_hits, tokens_in, tokens_out, estimated_usd, actual_usd},
   output: {path, bytes, asset_count, dropped_assets}, versions: {paperdeck, pandoc?,
   katex}}`; schema documented in `report.py`; always written on success; on failure,
   written best-effort with `error: {code, exit}` added.
6. Ctrl-C (KeyboardInterrupt): exit 130, partial tmp files cleaned, one-line message.
7. All timing via injected monotonic clock (testability).

## Acceptance Criteria

- E2E tests (stub engines + fixture IR): happy path writes output + report (schema
  round-trips), stdout exactly one absolute path; `--force` matrix; default slug naming;
  fallback progress lines match 26's outputs; `--yes` skips prompt, non-TTY declines
  without it (subprocess test with closed stdin); cost-declined pdf-only input →
  exit 5 table; validator violation → exit 9 and no output file; Ctrl-C simulation
  (SIGINT to subprocess) → 130 + no `.tmp` remnants.
- Report content: timings keys for every executed stage; llm zeros for deterministic
  engines.
- `-q` silences progress but not the stdout path or errors.
- SEC-AC: with the API key env set, the full e2e stderr, stdout, and the written
  `.report.json` contain no key material (redaction wired end-to-end); a stub engine
  returning HTML that fails the self-containment validator exits 9 and leaves no output
  file (validator gate cannot be bypassed by any engine).

## Validation

`uv run pytest tests/e2e/test_convert_command.py -q`

## Dependencies

02, 03, 07, 26, 29, 38, 39, 40.

## Non-goals

`fetch/cache/doctor` (49–50); shell completion (v2).

## Design References

DESIGN §6.1, §6.4, §14.6, §19.3, §15.6 (validator gate).
