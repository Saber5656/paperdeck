# Title

[W2] 15 Implement pandoc AST → IR structural mapping

## Summary

Implement `src/paperdeck/engines/latex/ast_map.py`: walk the pandoc JSON AST and build the
IR block/inline skeleton (no numbering, no ref resolution), per DESIGN §12.3.

## Context

This is the core translation layer of the latex engine; later passes (counters, refs)
operate on its output plus positional metadata it must preserve.

## Scope

- `map_ast(ast: dict, alloc: AnchorAllocator) -> MappedDoc` where `MappedDoc` holds:
  `body: list[Block]`; `meta_title/meta_authors/meta_abstract`; `footnotes`;
  `raw_spans: list[RawSpan]`; `env_map: dict[str, str]` (equation anchor id -> source
  math environment name, for issue 17); `image_targets: dict[str, str]` (figure anchor
  id -> includegraphics target path, for issue 21); `source_ids: dict[str, str]`
  (pandoc attr id -> anchor id); `unnumbered_sections: set[str]` (anchor ids of
  `section*` headers); `warnings`.
- `RawSpan` = `{placeholder_id: str, tex: str, context: "inline"|"block"}` - every
  `RawInline (tex)` is replaced by a sentinel `Text` inline; every `RawBlock (tex)` is
  replaced by a `Paragraph` containing a single sentinel `Text` inline
  (`context="block"`) so block-position directives (`\appendix`, loose `\label`)
  survive to the resolution passes. Both recorded for issues 16-18 to resolve.

## Detailed Requirements

1. Handle exactly the pandoc node set of DESIGN §12.3 with these mappings:
   `Header(level, attr, inlines)` → `Section` (tree built by level nesting; attr id
   recorded into a `source_ids` side map); `Para/Plain` → `Paragraph`;
   `Math(InlineMath)` → `Math` inline; `Math(DisplayMath)` → `Equation(content_kind=
   latex, latex_verified=True)` — one per DisplayMath (row splitting happens in 17);
   `Figure(attr, caption, content)`/`Image` → `Figure` (image target path recorded, asset
   filled by 21); `Table` → `Table(grid)` mapping pandoc cell structure incl. col/rowspan
   and header rows; `BulletList/OrderedList` → `ListBlock`; `BlockQuote` → `Quote`;
   `CodeBlock` → `CodeBlock`; `Note` → `FootnoteDef` + `FootnoteRef` (numbered by order);
   `Cite(citations, inlines)` → `Cite` sentinel carrying keys + rendered text (resolution
   in 18); `Link` → `ExtLink` (scheme filter; invalid scheme → Text + warning);
   `Str/Space/SoftBreak/LineBreak/Emph/Strong/Superscript/Subscript/Code` → obvious
   inlines; `Span/Div` → transparent (children lifted).
2. Anything else (`SmallCaps`, `Strikeout`, `RawBlock(html)`, `Definition lists`, …) →
   `Unhandled` with plain-text extraction + warning `pandoc-node-unhandled:<type>`.
3. Title/authors/abstract from pandoc `meta` when present (`title`, `author`); an
   `abstract` environment appears as body content — detect leading `Div` with class
   `abstract` or an `Unhandled` raw `\begin{abstract}` pair and lift to meta.abstract.
4. Every produced block gets its anchor from `alloc` at creation, in document order.
5. The walker must be non-recursive on inline depth (explicit stack) — pathological
   nesting cannot hit Python recursion limits (SEC hardening; cap depth 200 → warning +
   flatten).
6. Placeholder sentinel scheme (`…` private-use chars) must be stripped from
   any text that reaches final IR (guarantee delivered together with issues 16/18; this
   issue adds the invariant check helper `assert_no_sentinels(doc)` used by engine
   assembly).

## Acceptance Criteria

- Golden tests: canned pandoc AST JSON fixtures (committed) for each mapping row above →
  IR snapshot; unhandled node → Unhandled + warning; malformed AST (unknown `t`) degrades,
  never crashes.
- Section nesting: levels 1→3→2 sequence produces correct tree (level jumps tolerated).
- Depth cap test: 500-deep nested Emph flattens with warning.
- Side-map coverage: fixtures assert `env_map` (equation env recorded), `image_targets`
  (figure path recorded), `source_ids` (header attr id recorded),
  `unnumbered_sections` (`section*`), abstract lifting to `meta_abstract`, every block
  carrying an allocator-issued anchor, and `RawBlock` → sentinel-Paragraph placement.
- SEC-AC: a `Link` with `javascript:` target degrades to Text + warning; a
  `RawBlock (html)` never emits its content into any IR text field (Unhandled text is
  the plain-text extraction only).
- mypy strict.

## Validation

`uv run pytest tests/unit/test_ast_map.py -q`

## Dependencies

01, 05, 06, 14 (AST shape).

## Non-goals

Numbering (17), raw-tex parsing (16), citation/bib resolution (18, 20), graphics bytes (21).

## Design References

DESIGN §12.3; §10 (IR).
