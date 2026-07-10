# Title

[W7] 54 Implement the CI pipeline

## Summary

Create `.github/workflows/ci.yml` (plus Dependabot config): lint, types, tests with
coverage floor, security suite, license gate, vendored-checksum verification,
self-containment gate on goldens, and Playwright jobs, per DESIGN §21/§22 and ADR-005/007.

## Context

CI is where the security and quality gates become enforceable; several earlier issues
explicitly delegate their standing enforcement here.

## Scope

- `ci.yml` triggered on PR + push to main.
- `.github/dependabot.yml` (pip + github-actions ecosystems, weekly).
- Coverage and gate configuration.

## Detailed Requirements

1. Jobs (ubuntu-latest unless noted):
   - `lint`: `uv run ruff check .` + `uv run ruff format --check .`
   - `types`: `uv run mypy src/paperdeck`
   - `test` (matrix: ubuntu, macos): install pandoc (apt/brew), `uv run pytest -m "not
     playwright" --cov=paperdeck --cov-fail-under=85`; pandoc-marked tests are mandatory
     here (no skip: `-m` guard asserts pandoc present via a session fixture failing
     loudly).
   - `security`: `uv run pytest tests/security/ -q` (issue 52) — separate job so its
     status is individually visible/blockable.
   - `playwright`: `uv run playwright install --with-deps chromium webkit` + the
     playwright-marked suite.
   - `gates`: (a) license gate — `uv run pip-licenses --format=json` piped to
     `scripts/check_licenses.py` with the exact allowlist (ADR-005 §2): `MIT`,
     `BSD-2-Clause`, `BSD-3-Clause`, `Apache-2.0`, `ISC`, `Python-2.0`/`PSF-2.0`;
     dual-licensed packages pass if **any** of their licenses is allowlisted; anything
     else (incl. MPL, LGPL, unknown/UNKNOWN) fails with instructions; rule applies to
     **runtime** deps (`uv export --no-dev` package set) — dev-only deps are reported
     but not gated; (b) vendored checksums — `verify_vendored` CLI probe; (c) httpx
     containment grep (issue 08's rule) + viewer network-API grep (`fetch(|XMLHttpRequest|
     WebSocket` absent from viewer.js, issue 41's rule); (d) IR schema drift check
     (issue 06); (e) self-containment validator over committed golden HTML artifacts.
2. Action hygiene (ADR-007-consistent): all third-party actions pinned by full commit
   SHA; `permissions: contents: read` at workflow level; no secrets used anywhere in CI
   (tests never need keys — FakeLLM only); concurrency group canceling superseded runs.
3. `scripts/check_licenses.py` in scope here: reads pip-licenses JSON, applies the ADR
   allowlist to runtime deps only (classifies via `uv export --no-dev` package list),
   prints violations, exit 1.
4. Total CI wall time target ≤ 12 min (parallel jobs).
5. README badge added (53's file touched here in a one-line change).

## Acceptance Criteria

- All jobs green on the PR that introduces them (which necessarily runs against the
  then-current tree; job list may temporarily mark playwright `continue-on-error: false`
  only when 41+ landed — sequencing note: this issue lands after W5/W6 per plan order).
- SEC-AC: the license-gate unit test proves a GPL **runtime** dep fixture fails while a
  GPL dev-only dep passes (runtime-scope rule); the checksum gate fails on a tampered
  vendored file (local run evidence in the PR).
- SEC-AC: every third-party action is pinned by full commit SHA and workflow-level
  `permissions` is `contents: read` (grep-able assertions in a small
  `tests/unit/test_workflow_hygiene.py` that parses the YAML).
- Branch protection note: PR text reminds the maintainer to require `security` +
  `gates` + `test` as required checks (repo settings are manual, out of code scope).

## Validation

CI run on the PR itself + `uv run pytest tests/unit/test_check_licenses.py
tests/unit/test_workflow_hygiene.py -q`

## Dependencies

— (workflow grows with waves; its final gates require 06, 08, 37, 40, 41, 52 to have
landed — see plan order).

## Non-goals

Release workflow (55); Windows runners (v1 non-goal); nightly live-arXiv jobs (never —
manual sweep only).

## Design References

DESIGN §21, §22, §20.2 T9/T10, §20.3; ADR-005, ADR-007, ADR-008.
