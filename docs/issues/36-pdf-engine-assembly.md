# Title

[W4] 36 Assemble the pdf engine (figures, tables, IR construction)

## Summary

Implement `src/paperdeck/engines/pdf/assemble.py` and `engine.py`: geometric
figure/caption pairing, table image crops, splice application, numbers_map construction,
and the `PdfEngine` class wiring extract → blocks → segment → equations → citations →
IR, per DESIGN §13.6.

## Context

Integrator of wave 4: after this, any PDF converts end-to-end (with FakeLLM in tests).

## Scope

- Figure pairing, table crops, paragraph splicing, meta assembly, provenance/confidence.
- `class PdfEngine` (`name="pdf"`): `available(ctx)` (PDF artifact present/fetchable; LLM
  configured → reason `llm-not-configured`), `convert(ctx)` with cost confirmation via
  `ctx.confirm_cost` (estimate from issue 29 using page/char/eq counts).

## Detailed Requirements

1. Figures: for each `figure_caption` block — candidate region = largest rectangular area
   above or beside the caption (same column) not covered by classified text blocks on
   that page, minimum 40×40 pt; crop → PNG asset; `Figure{caption, number from
   number_text, asset}`; no candidate → captionless `Figure` placeholder + warning
   `pdf-figure-region-missing`. Deterministic geometry only (documented formula:
   maximal empty rectangle between caption top and previous text block bottom, clamped
   to column).
2. Tables: bounding union of the caption's `links_to_block` table_body blocks (fallback:
   nearest table_body above/below) → crop → `Table{content_kind="image", asset_id,
   caption}`.
3. numbers_map: from produced Equation/Figure/Table numbers + section numbers assigned
   here. Section numbering rule (self-contained): dotted counters per heading level
   (`1`, `1.1`, `1.2`, `2`, …), children reset when a parent increments; no
   appendix/letter switching on the pdf engine (PDF headings carry their own text; the
   assigned numbers exist solely to make `Section 4.1`-style structural refs
   resolvable) — then `link_structural_refs` (35) runs and splices apply.
4. Splice application: convert each paragraph's `(start,end,node)` list into IR inline
   sequence (`Text` segments between splices); assert non-overlap (leftmost-longest
   already applied in 35).
5. Meta: title role → `meta.title` (fallback: PDF metadata title via pypdfium2, then file
   stem + warning); authors from `author_line` split on `,;` and `and`; abstract role →
   `meta.abstract`.
6. Confidence/provenance: every LLM-derived node gets `confidence` (segmentation has none
   per-block in v1 → omit; equations carry VLM confidence); `provenance.llm` filled from
   ledger (model, calls, tokens, cost).
7. `convert()` order: caps/extract (31) → blocks (32) → estimate + `ctx.confirm_cost`
   (decline → `ConversionError("cost-declined")` for selection — distinct from the
   mid-run `CostLimitError` budget stop, DESIGN §14.6) → segment (33) → equations (34) →
   citations (35) → assemble → `ir.validate`.
8. Golden pipeline test: reportlab-generated 4-page synthetic paper (title, abstract, 2
   sections, 2 numbered "equations" (boxes), 1 figure+caption, numeric bib + `[1]`
   markers, `Eq. (1)`/`Fig. 1` mentions) + FakeLLM canned responses → committed IR
   snapshot.

## Acceptance Criteria

- Golden test passes deterministically (two runs byte-identical).
- Figure pairing unit tests: above-caption, beside-caption (2-col), no-region cases.
- Splice application: paragraph with 3 mixed markers → exact inline sequence.
- SEC-AC: cost-confirmation declined → `ConversionError("cost-declined")` with **zero**
  LLM transport calls (T11: no spend without consent); a scripted FakeLLM response whose
  bib entry text embeds `<script>` reaches IR as plain string data only (T4→T5 handoff).
- `ir.validate` green on golden; all warnings carry codes from the fixed vocabularies.

## Validation

`uv run pytest tests/unit/test_pdf_assemble.py tests/engine/test_pdf_engine.py -q`

## Dependencies

05, 06, 12, 29, 31, 32, 33, 34, 35.

## Non-goals

Real-model quality tuning (post-v1); inline math; table grid reconstruction (v2).

## Design References

DESIGN §13.6, §9 (reasons), §14.6; R4/R5.
