# Title

[W6] 51 Build the latex-path E2E suite and full viewer regression run

## Summary

Assemble the end-to-end regression suite for the deterministic paths: corpus →
`paperdeck convert` (real pandoc) → rendered HTML → self-containment validator → the
full Playwright feature matrix on real converted documents (not synthetic fixtures),
per DESIGN §21 integration gates.

## Context

Issues 41–47 tested viewer features on hand-built fixture pages; this issue proves the
whole pipeline produces documents where every feature works together, and pins that with
golden HTML.

## Scope

- `tests/e2e/test_pipeline_latex.py`: convert every issue-22 corpus project through the
  actual CLI (subprocess), assert exit 0, report contents, validator green.
- Golden HTML snapshots for 2 corpus projects (`minimal`, `equations`) — byte-exact
  (provenance timestamp neutralized via injected clock env `PAPERDECK_FAKE_NOW`, added
  as a hidden test-only env respected by the clock injection from 48).
- `tests/e2e/test_pipeline_viewer.py`: Playwright over the converted `equations` +
  `bib_bbl` outputs — cross-feature scenario script.
- `--engine latex` forcing and `--offline` (pre-seeded cache) paths.

## Detailed Requirements

1. CLI invoked as a subprocess (`uv run paperdeck …`) — tests the console-script wiring,
   argument parsing, exit codes, and stdout contract, not Python internals.
2. Viewer scenario (single browser session per document): deep-link `#eq-2` lands
   correctly → hover an `\eqref` link shows popup with matching equation number → click
   jumps + flash → Back restores → open ToC, click a section, spy highlights it → toggle
   dark theme → reload → theme persisted AND position restored (toast) → `?` overlay
   lists all bindings → print emulation hides chrome. Run on chromium + webkit.
3. Validator run both in-pipeline (already) and re-run standalone on the artifacts
   (`python -m paperdeck.render.validate`) — belt and suspenders.
4. Golden regeneration via `--update-goldens` documented; CI never regenerates.
5. Suite markers: `@pytest.mark.pandoc` + `@pytest.mark.playwright`; total runtime budget
   ≤ 5 min in CI.
6. `PAPERDECK_FAKE_NOW` must be refused outside pytest (guard: only honored when
   `PYTEST_CURRENT_TEST` env present) — no prod-behavior backdoor.

## Acceptance Criteria

- All corpus projects convert via CLI with exit 0 and validator-clean output; goldens
  stable across two runs.
- Viewer scenario passes on both engines' browsers (chromium, webkit).
- Report assertions: engine `latex`, zero llm tokens, stage timings present.
- Offline path: with pre-seeded cache and `--offline`, an arXiv-id fixture converts
  (stubbed cache seed) — proves the A2 selection row end-to-end.
- `PAPERDECK_FAKE_NOW` guard test (set outside pytest-sim → ignored).

## Validation

`uv run pytest tests/e2e/test_pipeline_latex.py tests/e2e/test_pipeline_viewer.py -q`

## Dependencies

22, 42, 43, 44, 45, 46, 48.

## Non-goals

pdf-engine E2E (52); live-arXiv network tests (never in CI; manual sweep per DESIGN §21).

## Design References

DESIGN §21 (gates, golden strategy), §9 A2, §6.1; ADR-006.
