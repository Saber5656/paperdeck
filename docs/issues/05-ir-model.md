# Title

[W0] 05 Implement the IR data model (pydantic)

## Summary

Implement `src/paperdeck/ir/model.py`: the complete Intermediate Representation as frozen
pydantic v2 models — `Document`, all Block nodes, all Inline nodes, `Asset`, `BibEntry`,
`Warning`, provenance — field-for-field per DESIGN §10.1–10.3, 10.5.

## Context

The IR is the contract between three engines and the renderer; every downstream issue
depends on these exact field names and invariants.

## Scope

- All model classes with discriminated unions (`type` literal field on every node, e.g.
  `type: Literal["section"]`).
- Model-level invariant validators (Equation invariants; ExtLink scheme rule).
- No I/O, no schema export (issue 06), no anchor logic (issue 06).

## Detailed Requirements

1. Field tables of DESIGN §10.1 (Document), §10.2 (Section, Paragraph, Equation, Figure,
   Table+Cell, ListBlock, Quote, CodeBlock, FootnoteDef, Unhandled, **BibEntry** — id,
   number?, label? (natbib display label), key?, content, urls with kind
   doi|arxiv|generic) and §10.3 (Text, Emph, Strong, Sub, Sup, Code, Math, RefLink, Cite,
   ExtLink, FootnoteRef, LineBreak) are normative — implement exactly, with
   `Block = Annotated[Union[...], Field(discriminator="type")]` and likewise `Inline`.
2. Equation validators (pydantic `model_validator`): `content_kind=="latex"` ⇒ `latex`
   non-empty ∧ `latex_verified is True` ∧ `asset_id is None`; `content_kind=="image"` ⇒
   `asset_id` set ∧ `latex_verified is False`. `confidence` in [0,1] when present.
3. Table validator: `content_kind=="grid"` ⇒ `rows` set; `=="image"` ⇒ `asset_id` set.
   `Cell.colspan/rowspan ≥ 1`.
4. `ExtLink` validator: scheme ∈ {https, http, mailto} else `ValueError` (engines catch and
   degrade per DESIGN §10.3 — the *model* rejects).
5. `Asset.mime` ∈ {image/png, image/jpeg, image/svg+xml}; `data_b64` non-empty base64
   (validated cheaply: charset + padding, not decoded).
6. `RefLink.kind` ∈ {eq, fig, tab, sec, bib, fn}; empty-string `target_id` allowed
   (inert form).
7. All models `model_config = ConfigDict(frozen=True, extra="forbid")`.
8. Convenience constructors kept out — engines build nodes explicitly (mechanical clarity).

## Acceptance Criteria

- Unit tests: round-trip `model_dump()`/reconstruct for a document exercising every node
  type; every invariant violation raises with a message naming the field; discriminated
  union parses from plain dicts (`Document.model_validate(json)`).
- `extra="forbid"` verified by test (unknown field rejected).
- SEC-AC: `ExtLink` and `BibEntry.urls` reject `javascript:`, `data:`, `file:`, and
  `vbscript:` schemes at model level (T5 pre-renderer gate; renderer escaping is defense
  in depth, not the only line).
- mypy strict passes (no `Any` in public signatures).

## Validation

`uv run pytest tests/unit/test_ir_model.py -q`

## Dependencies

01, 02.

## Non-goals

JSON Schema export, anchor allocation, cross-node referential validation (all issue 06).

## Design References

DESIGN §10.1–10.3, §10.5; ADR-001 (shared IR rationale).
