# Title

[W0] 06 Implement anchor allocator, IR referential validation, and JSON Schema export

## Summary

Implement `src/paperdeck/ir/anchors.py` (AnchorAllocator), `src/paperdeck/ir/validate.py`
(cross-node validation per DESIGN §10.6), and the committed JSON Schema
`src/paperdeck/ir/schema/ir-v1.json` with a drift check.

## Context

Anchors are the addressing scheme for reference jumps; referential validation is the gate
every engine must pass before rendering (and feeds engine fallback).

## Scope

- `AnchorAllocator` with `next(kind) -> str` per DESIGN §10.4 prefixes
  (`sec, eq, fig, tab, bib, fn, para`), starting at 1, one instance per conversion.
- `validate_document(doc: Document, limits: LimitsSettings) -> list[Warning]` raising
  `ConversionError` on hard failures.
- `scripts/export_ir_schema.py` generating `ir-v1.json` from the pydantic models
  (`Document.model_json_schema()`), plus a pytest asserting the committed file matches.

## Detailed Requirements

1. Hard failures (raise): duplicate anchor id; `RefLink.target_id`/`FootnoteRef.target_id`
   non-empty but unresolvable; `Cite.bib_ids` containing unknown id; `asset_id` unknown;
   Equation/Table invariant breach that slipped past model validation; any `labels` value
   that is not an existing anchor id (message names the label).
2. Soft warnings (returned, code strings fixed here): `unresolved-ref` (inert RefLink;
   `where` carries the original name — engines append their context, e.g. issue 18 sets
   `where` to the LaTeX label), `orphan-asset` (asset never referenced), `empty-section`,
   `unnumbered-eqref-target`, `assets-over-budget` (decode-free estimate `len(b64)*3/4`
   exceeds `limits.embed_hard_max_mb` — enforcement by dropping is the renderer's job,
   DESIGN §15.5; never a validation failure).
3. Traversal is a single generic walker, exported for renderer/test reuse, with a defined
   order: `iter_blocks(doc)` yields body blocks pre-order (block, then its nested blocks
   via `children`/`items`/`content`), then `doc.footnotes`; `iter_inlines(block)` yields
   the block's own inline sequences (e.g. `Section.title`, `Paragraph.content`,
   `Figure.caption`, Table cell contents) and recurses into nested inline `content`.
   Bibliography entries and `meta.title`/`meta.abstract` are traversed explicitly by
   `validate_document` (documented; the walker itself covers body+footnotes only).
4. Schema export: deterministic output (sorted keys, 2-space indent, trailing newline) so
   the drift test is byte-exact. Schema `$id`:
   `https://github.com/Saber5656/paperdeck/schema/ir-v1.json`.
5. `labels` map: validator checks every value is an existing anchor id.

## Acceptance Criteria

- Unit tests: allocator sequencing/stability; each hard failure raises with the offending
  id/label in the message; each soft warning fires on a minimal fixture (incl.
  `assets-over-budget` and an invalid-`labels` hard failure); walker visits every node
  exactly once and in the documented order (counted against a hand-built document).
- Drift test fails when a model field is added without regenerating the schema (verified
  by test-time regeneration comparison, not by mutation).
- SEC-AC: a crafted document dict (LLM-output-shaped) with an unknown `asset_id` and a
  `RefLink` to a nonexistent id is rejected by `validate_document` — the §20.1
  "untrusted LLM output → schema validation → IR" gate demonstrably closes.
- `ir-v1.json` committed and importable via `importlib.resources`.

## Validation

`uv run pytest tests/unit/test_ir_validate.py tests/unit/test_ir_schema_drift.py -q`

## Dependencies

04, 05.

## Non-goals

Rendering; engine-specific label semantics (issues 17–18, 24–25).

## Design References

DESIGN §10.4, §10.6, §21 (contract tests).
