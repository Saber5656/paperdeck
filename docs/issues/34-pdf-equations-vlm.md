# Title

[W4] 34 Implement equation cropping and VLM LaTeX transcription

## Summary

Implement `src/paperdeck/engines/pdf/equations.py`: crop display-equation blocks to PNG
assets, obtain best-effort LaTeX from the VLM with budget-aware degradation, and produce
image-primary `Equation` data, per DESIGN §13.4 and requirement R5.

## Context

R5 is a core UX/safety decision: readers must never be shown a wrong formula as truth.
Images are ground truth; VLM LaTeX is explicitly-unverified copy text.

## Scope

- `process_equations(seg: SegmentResult, blocks, pdfdoc: PdfDoc, llm, ledger, alloc) ->
  EquationsResult` = `{equations: dict[block_id, EquationDraft], assets: dict[str, Asset],
  warnings}` where `EquationDraft = {anchor_id, number?: str, asset_id, latex?: str,
  confidence?: float}`.

## Detailed Requirements

1. For each block with role `display_equation` (in reading order): crop from
   `pdfdoc.bitmap(page, 2.0).crop_png(bbox, pad_pt=6)` → `Asset{mime=image/png,
   origin.page}`; asset id from a dedicated sequence.
2. Numbering: `number_text` from segmentation (e.g. `(3)` → `3`, tolerant of `3a`,
   `III` kept verbatim); absent → sequential fallback `E1, E2, …` **not** rendered in
   parentheses (DESIGN §13.4); duplicate numbers allowed with warning
   `pdf-eq-number-duplicate`.
3. VLM transcription per equation: prompt `equation_latex.md` + the PNG; schema
   `pdf_equation_latex.v1`; `max_tokens` 1024. Before each call:
   `ledger.remaining_allows(per_call_estimate)` — false → stop ALL remaining VLM calls,
   add warning `vlm-budget-exhausted` (equations keep images, no latex), continue
   pipeline (DESIGN §13.4).
4. Returned latex sanity filter (defense beyond schema): reject (drop latex + warning
   `vlm-latex-rejected`) when latex is empty, > 4000 chars, or contains any of
   `\input`, `\include`, `\write`, `\csname`, `\href`, `\url` (KaTeX-irrelevant/risky
   commands have no business in a transcription).
5. `confidence` recorded verbatim; no thresholding in v1 (DESIGN §24 unknown 3 note in
   code comment).
6. Resulting drafts always `content_kind="image"`, `latex_verified=False` (enforced again
   by IR model invariants, issue 05).
7. Crop failures (zero-area bbox, page render fail) → skip block to `Unhandled` text +
   warning `pdf-eq-crop-failed`.

## Acceptance Criteria

- FakeLLM tests: happy transcription (latex+confidence stored); budget exhaustion mid-way
  stops later VLM calls (ledger stub) while assets still produced; each sanity-filter
  trigger; number parsing table (`(3)`→`3`, `(3a)`→`3a`, none→`E<n>`).
- Crop integration (reportlab fixture with a black-box "equation" region): asset bytes
  non-empty PNG, origin.page correct.
- SEC-AC: VLM response latex `\href{javascript:x}{y}` is rejected by the filter.
- One ledger record per VLM call, purpose `equation`.

## Validation

`uv run pytest tests/unit/test_pdf_equations.py -q`

## Dependencies

05, 27, 29, 30, 31, 33.

## Non-goals

Rendering the copy-button UX (38/42 per DESIGN §15.2); confidence thresholds (v2);
inline math (v1 non-goal).

## Design References

DESIGN §13.4, §15.2, R5; §20.2 T4; §24 unknown 3.
