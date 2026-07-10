# Title

[W4] 35 Implement PDF citations and bibliography extraction

## Summary

Implement `src/paperdeck/engines/pdf/citations.py`: LLM-normalized bibliography entries,
deterministic numeric citation linking, LLM-assisted author-year mapping, and structural
reference detection (`Eq. (3)`, `Fig. 2`), per DESIGN §13.5.

## Context

Recreates the reference graph on the path where no source markup exists — deterministic
regex first, LLM only where text alone is ambiguous.

## Scope

- `extract_bibliography(bib_blocks, llm, ledger, alloc) -> (list[BibEntry],
  numeric_index: dict[str, str], entry_anchor_by_index: list[str], warnings)`.
- `link_citations(paragraph_texts, bib, llm) -> per-paragraph inline splice list`
  (marker span → `Cite`).
- `link_structural_refs(paragraph_texts, numbers_map) -> splice list` (marker span →
  `RefLink`), where `numbers_map` = `{("eq"|"fig"|"tab"|"sec", number_str) → anchor_id}`
  built by the assembler (36) and passed in.

## Detailed Requirements

1. Bibliography: concatenate `bib_entry` blocks (reading order) → one `pdf_bib.v1` call
   (chunked at 30 000 chars with entry-boundary hints); entries → `BibEntry` with anchors;
   `number` normalized (`[12]`→`12`); `urls` scheme-filtered (https/http only here — no
   mailto in bib) else dropped + warning; empty result → warnings `pdf-bib-empty`, engine
   continues without citations.
2. Numeric markers (deterministic, no LLM): regex over paragraph text for
   `\[(\d{1,3}(?:\s*[,;]\s*\d{1,3})*(?:\s*[-–]\s*\d{1,3})?)\]` — expand ranges
   (`[3-5]`→3,4,5; cap 50 expanded), map via `numeric_index`; unknown number → marker left
   as plain text + warning `cite-number-unknown:<n>` (never a dead link).
3. Author-year: candidate spans matched by
   `\((?:[A-Z][A-Za-z'’-]+[^()]{0,60}?\d{4}[a-z]?(?:;[^()]{0,80})*)\)`; all candidates sent
   in ONE `pdf_cite_map.v1` call with the numbered entry list; returned
   `entry_indices` validated in-range; unmapped → plain text + warning. Zero candidates →
   zero LLM calls (cost hygiene).
4. Structural refs (deterministic): regex family (case-insensitive, word-bounded):
   `(?:Eq\.?|Equation)\s*\(?(\d+[a-z]?)\)?`, `(?:Fig\.?|Figure)\s*(\d+[a-z]?)`,
   `(?:Table|Tab\.?)\s*(\d+)`, `(?:Sec\.?|Section|§)\s*(\d+(?:\.\d+)*)` → `RefLink` when
   the number exists in `numbers_map`; no matching number → the text is left untouched —
   no link, no warning (DESIGN §13.5: prose mentions of other papers' figures are
   common; warnings would be noise).
5. Splice representation: `(start, end, node)` on the paragraph's final merged text;
   overlaps resolved by leftmost-longest; splicing itself happens in 36.
6. All LLM calls recorded with purposes `bib`/`cite-map`.

## Acceptance Criteria

- FakeLLM tests: bib normalization happy path incl. chunking at the boundary; url scheme
  filtering; numeric matrix (`[3]`, `[3,5]`, `[3-5]`, `[3;7]`, `[99]`-unknown, range >50
  capped) — expected splice snapshots; author-year one-call batching (call count
  asserted), in-range validation; structural-ref table incl. `§4.1` and `Eq. (3a)`;
  overlap resolution case.
- SEC-AC: bib entry url `javascript:alert(1)` dropped with warning.
- Zero-candidate short-circuit: no cite-map call issued (transport count).

## Validation

`uv run pytest tests/unit/test_pdf_citations.py -q`

## Dependencies

05, 06, 27, 30, 33.

## Non-goals

Splice application and numbers_map construction (36); external metadata enrichment (v2).

## Design References

DESIGN §13.5; §10.3 (Cite/RefLink); §20.2 T4.
