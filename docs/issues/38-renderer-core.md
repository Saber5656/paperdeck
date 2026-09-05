# Title

[W5] 38 Implement the renderer core (IR → HTML)

## Summary

Implement `src/paperdeck/render/html.py` and the jinja2 templates: pure-function rendering
of every IR node type to the HTML structure the viewer expects, with strict escaping,
per DESIGN §15.1–15.3.

## Context

The renderer is the T5 (XSS) boundary: all engine/LLM-derived text crosses into HTML
here. It also defines the DOM contract (`pd-*` classes, ids, data attributes) that
viewer issues 41–46 program against.

## Scope

- `render_document(doc: Document, assets_bundle: AssetsBundle, settings) -> str` where
  `AssetsBundle` (issue 39) carries inlined CSS/JS/CSP hashes — this issue may stub it.
- Templates `document.html.j2`, `_block.j2`, `_inline.j2`, `_head.j2`.
- The DOM contract (documented in a module-level docstring, normative for the viewer).

## Detailed Requirements

1. jinja2 `Environment(autoescape=True, undefined=StrictUndefined)`; templates loaded via
   `importlib.resources`; `|safe` appears only where `AssetsBundle` content is injected
   (grep-tested).
2. Render every §10.2/§10.3 node per DESIGN §15.2, including: equation wrappers
   (`div.pd-eq` with `data-latex`/`data-number`, image variant with
   `img[alt="equation (unverified LaTeX attached)"]` + `button.pd-copy-latex[data-latex]`
   labeled `Copy LaTeX (unverified)`); inline math spans; RefLink/Cite anchors
   (`a.pd-ref[data-kind]`); inert refs as `span.pd-ref-dead[title]`; figures with
   placeholder box when `asset_id` is None (alt_text shown); grid tables with
   `th[scope]`, colspan/rowspan; image tables; lists/quotes/code/footnotes (backlink
   `a.pd-fn-back`); bibliography `ol.pd-bib > li[id]`; Unhandled → `div.pd-unhandled`
   plain text.
3. Head: `<meta charset>`, `<title>` = plain-text title, viewport meta, CSP placeholder
   slot (39 fills), `<script type="application/json" id="pd-data">` carrying
   `{macros, docId, warnings_count}` (JSON with `</` escaped as `<\/` — script-context
   safety).
4. Metadata header + provenance footer per DESIGN §15.2 (engine, versions, warning list
   collapsible, LLM cost line when `provenance.llm`). The fixed page header also emits
   the control slots the viewer wires up: `button#pd-toc-toggle` and
   `button#pd-theme-toggle` (inert until viewer JS attaches; part of the DOM contract).
5. ToC: server-side `<nav id="pd-toc"><ol>…` from the section tree (viewer only wires
   behavior — 43).
6. docId: `sha256(canonical IR JSON)[:16]` computed here.
7. External links: only `ExtLink` renders `href` to non-fragment URLs, always with
   `rel="noopener noreferrer" target="_blank"`.
8. Deterministic output (no timestamps beyond provenance.created_at value from IR).

## Acceptance Criteria

- Golden HTML snapshots for a kitchen-sink IR fixture (every node type) — byte-stable.
- SEC-AC: IR strings `<script>alert(1)</script>`, `"><img onerror=…`, and a latex value
  ending `</script>` render escaped everywhere they can appear (text, data-latex,
  alt, title, JSON island) — asserted by parsing the output and by absence of raw
  substrings.
- SEC-AC: `|safe` grep test (only the two audited sinks).
- DOM contract asserted: ids unique; every `a.pd-ref[href]` targets an existing id;
  `#pd-data` parses as JSON.
- External-link contract: every rendered `ExtLink` anchor carries
  `rel="noopener noreferrer"` and `target="_blank"`, and non-`ExtLink` nodes never
  produce an external `href` (parsed-output assertion over the kitchen-sink fixture).
- StrictUndefined: rendering with a missing field fails loudly (test with broken fixture).

## Validation

`uv run pytest tests/unit/test_renderer.py -q`

## Dependencies

05, 06 (the `AssetsBundle` input is stubbed here and completed by the asset-inlining
issue).

## Non-goals

Asset inlining/CSP hashing (39), validator (40), any JS behavior (41–46), CSS (47).

## Design References

DESIGN §15.1–15.3, §16 (DOM contract consumers), §20.2 T5; R5 (copy-latex UX).
