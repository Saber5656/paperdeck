# ADR-003: Math renders client-side with vendored KaTeX

- Status: Accepted
- Date: 2026-07-08
- Deciders: Fable (architecture), informed by docs/research/04

## Context

The output is a single self-contained HTML file with zero external requests. LaTeX/arXiv
engines produce math as LaTeX strings. Candidates: KaTeX client-side, MathJax client-side,
build-time rendering (needs Node.js at conversion time), browser MathML.

## Decision

- Math is stored in the DOM as escaped LaTeX (`<span class="pd-math" data-latex="...">`,
  display blocks analogous) and rendered at page load by a **vendored, pinned KaTeX** bundle
  embedded in the HTML (JS + CSS + woff2 fonts as data-URIs).
- KaTeX options: `throwOnError: false` (failed expressions show raw LaTeX with
  `.pd-math-error` styling), `macros` populated from the paper's extracted preamble
  definitions, `trust: false`.
- The `arxiv-html` engine re-renders from LaTeXML's `alttext` LaTeX through the same KaTeX
  path (MathML not reused in v1) so all engines share one rendering pipeline and one test
  surface.
- The `pdf` engine's equations are images (ADR-007 / user decision) and bypass KaTeX.
- KaTeX is vendored by `scripts/vendor_katex.py`: downloads a pinned version, verifies
  SHA-256 checksums recorded in a manifest, and commits the assets (ADR-008).

## Consequences

- Positive: no runtime/network dependency for readers; no Node.js dependency for users; one
  consistent math look across engines and themes; graceful degradation for unsupported LaTeX.
- Negative: +~1 MB per output file (fonts/JS); KaTeX's LaTeX coverage is below MathJax —
  acceptable for v1, MathJax swap documented as a v2 option if coverage complaints
  materialize; page-load render cost on very equation-heavy papers (mitigate: render
  synchronously before first paint only for above-the-fold, lazy-render the rest via
  IntersectionObserver — specified in DESIGN.md §16).
