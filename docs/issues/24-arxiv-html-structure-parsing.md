# Title

[W3] 24 Implement arxiv-html structure parsing (sections, paragraphs, figures, tables, assets)

## Summary

Implement `src/paperdeck/engines/arxiv_html/parse_structure.py`: map the LaTeXML `ltx_*`
DOM skeleton to IR blocks with assets, following the normative mapping table in DESIGN
§11.3.

## Context

First half of the arxiv-html converter: document tree, block content, figures/tables and
their image assets (already fetched to cache by issue 12).

## Scope

- `parse_structure(soup: BeautifulSoup, artifact: HtmlArtifact, alloc: AnchorAllocator,
  limits) -> StructureResult` = `{meta, body (with math/ref placeholders as raw elements
  retained for issue 25), assets, source_id_map: dict[html_id, anchor_id],
  labels: dict[str, str] (destined for Document.labels), warnings}`.

## Detailed Requirements

1. Implement every row of the DESIGN §11.3 table: title, authors, abstract, section
   hierarchy from `ltx_section/ltx_subsection/ltx_subsubsection` (level from class;
   heading tag text number split from title text via the `.ltx_tag` child), paragraphs
   (`.ltx_para > .ltx_p`), figures (`figure.ltx_figure` + `.ltx_caption` + `img`), tables
   (`figure.ltx_table` wrapping `table.ltx_tabular` → `Table(grid)` with
   colspan/rowspan/th detection; nested tabulars → image-less `Unhandled` + warning),
   lists (`.ltx_itemize/.ltx_enumerate`), quotes, verbatim → `CodeBlock`.
2. Every element with an `id` attribute that maps to an IR block records
   `html_id → anchor_id` in `source_id_map` (issue 25 resolves `ltx_ref` hrefs through
   it); labels also copied into `Document.labels`.
3. Assets: `<img src>` resolved through `HtmlArtifact` map (issue 12) to cached bytes;
   mime by magic bytes; svg accepted per DESIGN §10.5 policy (embedded later via `<img>`
   only) with `<script` bytes stripped defensively (byte-level filter + warning
   `svg-script-stripped`); missing/skipped images → placeholder figure + warning
   `figure-image-missing`.
4. Unknown `ltx_*` block classes → `Unhandled` (visible text preserved) + warning
   `ltx-class-unhandled:<class>` (deduplicated per class).
5. Math elements (`<math>`) and `.ltx_equation*` blocks are **not** converted here — they
   are collected as opaque placeholders (same sentinel technique as issue 15, ids into a
   side list) for issue 25.
6. Robustness: parser must tolerate missing wrappers (paragraph directly under section),
   duplicated ids (second occurrence gets fresh anchor + warning `html-id-duplicate`).

## Acceptance Criteria

- Golden test on a captured healthy arxiv-html fixture (committed, trimmed to ~150 KB):
  IR snapshot with correct section tree depth, figure/table extraction, asset count, and
  `source_id_map` size.
- Table fixture with colspan/rowspan + header row → exact `Cell` grid snapshot.
- SEC-AC: svg asset containing `<script>` bytes is stripped + warned; img with cross-host
  src yields placeholder (asset never fetched here — asserted).
- Unknown-class fixture → `Unhandled` + single deduplicated warning.

## Validation

`uv run pytest tests/unit/test_html_structure.py -q`

## Dependencies

05, 06, 23 (the `HtmlArtifact` type arrives transitively through the fetch-gate issue).

## Non-goals

Math/refs/citations/footnotes (25); fetching (12); quality decisions (23).

## Design References

DESIGN §11.3, §10.5 (SVG policy); ADR-007 §4/§6.
