# Title

[W3] 25 Implement arxiv-html content parsing (math, cross-refs, citations, bibliography, footnotes) and engine assembly

## Summary

Implement `src/paperdeck/engines/arxiv_html/parse_content.py` plus the
`ArxivHtmlEngine` class: convert LaTeXML math/reference/citation/bibliography constructs
into IR and wire fetch → gate → structure → content into the complete engine, per DESIGN
§11.4.

## Context

Second half of the arxiv-html converter and its integrator; after this issue the highest-
fidelity engine is complete.

## Scope

- Math: equations (`.ltx_equation`, `.ltx_equationgroup`) and inline `<math>` → IR via
  `alttext`.
- References/citations/footnotes/bibliography per DESIGN §11.4.
- `class ArxivHtmlEngine` (`name="arxiv-html"`), `available()` (arXiv input? html
  fetchable per cache/network state?), `convert()` producing validated `Document`.
- Engine golden fixture test.

## Detailed Requirements

1. Equations: for each `.ltx_equation`, `latex` = the contained `<math alttext>` value
   (LaTeXML stores LaTeX there); number from child `.ltx_tag` text (e.g. `(3)` → `3`);
   equationgroups yield one `Equation` per row with its own tag; missing `alttext` →
   `Unhandled` + warning `math-alttext-missing`. `latex_verified=True`
   (deterministic source), `content_kind="latex"`.
2. Inline `<math>` inside paragraphs → `Math{latex=alttext}`; missing alttext → `Text`
   with the element's text content + same warning.
3. Cross-refs: `a.ltx_ref[href^="#"]` → `RefLink` with `target_id =
   source_id_map[fragment]` (from issue 24), `kind` from the target block's IR type,
   display text = anchor text as-is; unresolved fragment → inert RefLink with
   `kind="sec"` as the fixed default (the §10.3 enum has no `unresolved`; `sec` is the
   least-misleading fallback) + warning `unresolved-ref` (where=fragment).
4. Citations: `.ltx_cite` descendants linking `#bib.*` → `Cite{bib_ids, text}` through the
   same map; a fragment missing from the map is dropped from `bib_ids` with `?` in its
   text slot + warning `cite-unresolved:<fragment>` (mirrors issue 18's rule).
5. Bibliography: `.ltx_bibliography .ltx_bibitem` → `BibEntry` (number from `.ltx_tag`,
   content inlines with ExtLink scheme filtering); ids recorded in `source_id_map` before
   citation resolution (two-pass: bibliography first).
6. Footnotes: `.ltx_note` → `FootnoteDef` + `FootnoteRef` at the marker position.
7. Engine assembly: `available()` returns true iff the input is an arXiv spec AND (the
   HTML artifact is cached OR network is permitted) — it performs no fetching and no
   gating; `convert()` = cached/`fetch_html` → `assess` (fail → `ConversionError` whose
   code is the gate reason, e.g. `html-low-quality`, which selection (26) records
   verbatim per DESIGN §9) → structure (24) → content (this) → meta backfill
   from `ArxivMeta` → `ir.validate` → Document with provenance (`engine="arxiv-html"`,
   KaTeX re-render note in `engine_versions`).
8. Macros: `Document.macros = {}` for this engine (LaTeXML already expanded user macros
   into the alttext) — documented in code.

## Acceptance Criteria

- Golden test on the healthy fixture (same as issue 24's, extended): equation numbers and
  latex extracted; a `\ref` link resolves to the right `eq-*` anchor; citations link to
  bib entries; footnote round-trip; snapshot IR committed.
- Equationgroup fixture → one Equation per row with distinct numbers.
- Gate-fail fixture → `ConversionError` carrying reason `html-low-quality`.
- SEC-AC: `alttext` containing `</script><script>alert(1)</script>` survives into IR as
  plain string data (model), and issue 38/40's tests prove it renders escaped (cross-ref
  noted; here assert IR string intact, no interpretation).

## Validation

`uv run pytest tests/unit/test_html_content.py tests/engine/test_arxiv_html_engine.py -q`

## Dependencies

11, 23, 24.

## Non-goals

Re-rendering MathML (ADR-003: KaTeX path only); fixing LaTeXML conversion defects
(gate routes those to `latex`).

## Design References

DESIGN §11.4, §9; ADR-001, ADR-003.
