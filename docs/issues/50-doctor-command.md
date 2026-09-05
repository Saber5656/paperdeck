# Title

[W6] 50 Implement the `doctor` command

## Summary

Implement `paperdeck doctor`: the environment self-check covering Python, pandoc, vendored
assets, config, API key presence, cache writability, and optional network reachability,
per DESIGN §6.3.

## Context

The pdf/latex engines have environmental prerequisites; doctor turns "it doesn't work"
into a checklist with per-OS fixes and is the debugging entry point support will ask for.

## Scope

- `doctor` command with table output and exit semantics (0 unless a REQUIRED check
  fails; network checks are warnings).

## Detailed Requirements

1. Checks, each rendering `[ok]/[warn]/[fail] <name>: <detail>`:
   - `python` (required): running version ≥ 3.11.
   - `config` (required): loads without `ConfigError`; on failure show the error verbatim.
   - `pandoc` (warn): found + version ≥ 3.0 (detail: path + version); missing → warn with
     per-OS install hint (macOS `brew install pandoc`, Debian/Ubuntu
     `apt install pandoc`, other: pandoc.org) and note "latex engine unavailable".
   - `katex-assets` (required): `verify_vendored` clean (37).
   - `api-key` (warn): env var named by `api_key_env` is set (report the NAME and
     `set (sk-***)` masked form / `not set`; never the value) — note "pdf engine
     unavailable" when absent and base_url non-localhost. No conflict with the `config`
     check: `load_settings` never resolves the key (DESIGN §14.1's fail-fast happens at
     `LlmClient` construction, which doctor does not perform).
   - `cache-writable` (required): create+delete a probe file under the cache root.
   - `network` (warn, skipped entirely under `--offline` with a note): HEAD
     `https://export.arxiv.org` and GET `<base_url>` root via netgate purposes — report
     reachable/latency or the error class only (no bodies).
2. Exit 0 when all required pass (warnings allowed); exit 1 otherwise (this command's
   contract; distinct from conversion exit codes — documented in help text).
3. `--json` flag: machine-readable `{checks: [{name, status, detail}]}` to stdout for CI
   debugging.
4. All checks isolated: one failing check never prevents the others from running.

## Acceptance Criteria

- E2E tests with seams (fake which/env/transport): full-pass table golden; each
  degradation path (pandoc missing → warn + hint containing the current platform's
  command; key unset; assets tampered → fail; cache dir read-only → fail; network down →
  warn); exit codes per contract; `--json` schema round-trip; `--offline` skips network
  with visible note.
- SEC-AC: output with key set never contains the key value (scan), only the masked form.

## Validation

`uv run pytest tests/e2e/test_doctor.py -q`

## Dependencies

04, 08, 14 (pandoc version helper), 37.

## Non-goals

Auto-fixing anything; deep LLM auth validation (a real completion call costs money —
reachability only).

## Design References

DESIGN §6.3; §20.2 T8 (masking).
