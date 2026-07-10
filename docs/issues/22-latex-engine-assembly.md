# Title

[W2] 22 Assemble the latex engine and its golden fixture corpus

## Summary

Implement `src/paperdeck/engines/latex/engine.py` (the `Engine`-protocol class wiring
issues 13–21 into one pipeline) and commit the latex golden fixture corpus, per DESIGN
§12.10.

## Context

Integrator issue for wave 2: after this, `latex` conversion produces validated IR
end-to-end from a source tree, and the corpus becomes the regression net for all later
changes.

## Scope

- `class LatexEngine` (`name = "latex"`): `available(ctx)` (pandoc present? source
  artifact tex/tar? → reasons `pandoc-missing`/`eprint-is-pdf-only`), `convert(ctx)`
  running: acquire source (local path or `ArxivClient.eprint`) → tarsafe extract (archive
  case) → project prepare (13) → pandoc (14) → ast map (15) → macros (19) → bib (20) →
  counters (17) → refs (18) → graphics (21) → `ir.validate` (06) → `Document`.
- Fixture corpus `tests/fixtures/latex/` + golden IR snapshots + corpus test.

## Detailed Requirements

1. Provenance filled per DESIGN §10.1: engine `latex`, `pandoc` version, created_at
   (injected clock for testability), warnings aggregated from every stage in stage order.
2. Meta: title/authors/abstract from AST meta (15); for arXiv inputs, missing fields
   backfilled from `ArxivMeta` (11); `meta.links` gets the abs URL + DOI when known.
3. Stage timing recorded (`stats.timings_ms` dict) for the run report (48).
4. Failure semantics: any stage's `ConversionError`/`SecurityError` aborts the engine and
   propagates to selection (26); partial temp dirs cleaned (context managers).
5. Corpus (each a minimal complete LaTeX project, committed as plain files):
   `minimal/` (title+2 sections+paragraphs), `equations/` (equation, align w/ nonumber,
   `\[…\]`, eqref/cref uses, numberwithin variant), `figures_tables/` (2 figures incl. pdf
   graphic, 1 table, refs), `bib_bbl/` (numeric .bbl + citep), `bib_natbib/` (author-year
   labels), `macros/` (newcommand/DeclareMathOperator usage), `multifile/` (input/include
   nesting), `pathological/` (unknown env, broken ref, stray raw tex — exercises every
   degradation warning).
6. Golden test: for each corpus project, `LatexEngine.convert` (pandoc-marked) → IR
   `model_dump_json(indent=2)` compared byte-exact to committed snapshot
   (`<name>.ir.json`); snapshot regeneration via `pytest --update-goldens` flag
   (documented in CONTRIBUTING by issue 53).

## Acceptance Criteria

- All 8 corpus projects convert; snapshots committed; `pathological` produces exactly its
  documented warning set and zero raw TeX in any text field (asserted by scan).
- `available()` reason strings match DESIGN §9 vocabulary.
- End-to-end wall time for the corpus ≤ 60 s in CI (soft; marked slow).
- `assert_no_sentinels` runs and passes on every corpus output.
- SEC-AC: converting an archive fixture containing a `../`-traversal member fails with
  `SecurityError` before any pipeline stage runs (tarsafe integration proven at engine
  level), and a corpus source containing `<script>alert(1)</script>` in a paragraph
  reaches IR as inert text only.

## Validation

`uv run pytest tests/engine/test_latex_engine.py -q` (CI: with pandoc installed)

## Dependencies

10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21.

## Non-goals

Engine selection (26); rendering (38+); arxiv-html/pdf engines.

## Design References

DESIGN §12.10, §9 (reason vocabulary), §21 (golden strategy).
