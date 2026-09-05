# Title

[W4] 32 Implement deterministic PDF block clustering

## Summary

Implement `src/paperdeck/engines/pdf/blocks.py`: pure-function clustering of extracted
chars into lines and blocks, two-column detection, reading order, and repeated
header/footer removal, per DESIGN §13.2.

## Context

The LLM classifies blocks; this module decides what a block *is*. Being deterministic and
well-tested here keeps the LLM's job small and the pipeline reproducible.

## Scope

- `build_blocks(pages: list[PageChars]) -> list[RawBlock]` where
  `RawBlock = {id: "b<page>-<n>", page: int, bbox, text: str, font_size_median: float,
  line_count: int}`.
- Internals: `chars_to_lines`, `lines_to_blocks`, `detect_columns`, `strip_repeated`.

## Detailed Requirements

1. Lines: sort chars by (y descending, x ascending); group chars whose vertical overlap
   with the current line's box ≥ 50% of the smaller height; within a line, join chars,
   inserting a space when the x-gap > 0.35 × font size; line text NFC, internal
   whitespace collapsed.
2. Blocks: within a column, split at vertical gaps > 1.8 × median line height (median
   over the page's lines); also split when font-size median changes by > 25% between
   adjacent lines (heading boundaries).
3. Columns (fully numeric rule; applies only when the page has ≥ 20 text lines):
   histogram line horizontal extents into 8 pt x-bins; a candidate valley = a maximal
   run of consecutive bins, each overlapped by ≤ 2% of the page's lines, spanning
   ≥ 24 pt, whose center lies within the central 40% of page width. If a valley exists
   AND ≥ 60% of the page's lines lie entirely on one side of the valley center (left or
   right, summed), the page is 2-column; reading order = left column top-down, then
   right; single column otherwise. (3+ columns: treat as 1 with warning
   `layout-columns-unhandled`; DESIGN §24 unknown 7.)
4. Header/footer removal: normalize line text (digits → `#`); texts appearing at the same
   y-band (±6pt) on ≥ 60% of pages with ≥ 4 pages sampled are dropped (this removes page
   numbers/running titles); dropped content recorded once as warning
   `pdf-runners-stripped:<count>`.
5. Hyphenation repair is NOT here (13.3 merging rule; documented).
6. Block id stability: `b<page>-<index-within-page>` after ordering — deterministic for
   identical input.
7. Pure functions; no pypdfium2 import (operates on plain data), enabling table-driven
   synthetic tests.

## Acceptance Criteria

- Synthetic-data tests (hand-built char lists): line grouping incl. space insertion
  boundary (0.35 rule ±ε); gap split at exactly 1.8× (boundary test both sides);
  font-jump split; 2-column page ordered left-then-right; 1-column not falsely split
  (dense math page fixture); header/footer stripped on a 6-page synthetic with page
  numbers, but NOT stripped on a 3-page doc (min-pages rule).
- Determinism: shuffled input chars (same content) → identical blocks.
- Golden: reportlab 2-column fixture from issue 31's generator → block snapshot JSON.

## Validation

`uv run pytest tests/unit/test_pdf_blocks.py -q`

## Dependencies

01, 31 (data shapes; tests standalone).

## Non-goals

Role classification (33), equation detection (LLM's call in 33/34), 3+ column layouts.

## Design References

DESIGN §13.2, §24 unknown 7.
