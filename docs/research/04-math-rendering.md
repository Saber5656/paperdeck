# Research: math rendering inside a self-contained HTML file

Date: 2026-07-08 (verified via web on this date)
Status: informs ADR-003 (KaTeX), DESIGN.md §15–16

## Requirement recap

Output is a single self-contained HTML file with **zero external requests** (user decision).
Math from the LaTeX/arXiv engines arrives as LaTeX strings; it must render beautifully
offline, in light and dark themes, and inside hover-preview popups.

## Options

| Option | Assessment |
|---|---|
| **KaTeX, client-side, vendored into the HTML** | MIT; ~small JS+CSS+woff2 fonts; renders synchronously and fast; `macros` option + `globalGroup` lets us inject the paper's own `\newcommand` definitions extracted from the preamble; `throwOnError:false` degrades a bad expression to visible error markup instead of crashing the page. Embedding as data-URIs adds roughly ~1 MB to the file — acceptable against the "few MB" budget. |
| MathJax v3/v4 client-side | Broader LaTeX coverage but significantly larger and slower; overkill for v1. Fallback candidate if KaTeX coverage proves insufficient (v2). |
| Build-time KaTeX render (HTML+CSS only, no JS math at runtime) | Requires a Node.js runtime as a *product* dependency of a Python CLI — unacceptable install weight. A pure-Python KaTeX re-implementation does not exist. |
| MathML (browser-native) | The arXiv-HTML engine already delivers MathML; MathML Core is supported in current Chrome/Firefox/Safari. However rendering quality/consistency still trails KaTeX, and the pandoc path produces LaTeX (not MathML) natively. |

## Decision input (adopted in ADR-003)

- **Render math with vendored KaTeX at page load**, from LaTeX strings stored in the DOM
  (`<span class="pd-math" data-latex="...">`).
- The arXiv-HTML engine keeps LaTeXML's `alttext` LaTeX and re-renders through KaTeX for
  visual consistency across engines (the MathML is not reused in v1 — single rendering path,
  single test surface).
- Preamble macros: the LaTeX engine extracts document `\newcommand`/`\def` definitions and
  ships them in the document payload; the viewer passes them to KaTeX `macros` at init.
- Unrenderable expressions: `throwOnError:false` + `.pd-math-error` styling showing raw
  LaTeX in monospace — the reader always sees *something* faithful.
- KaTeX is vendored by a pinned-version download script with recorded SHA-256 checksums
  (supply-chain control, ADR-008); fonts are embedded as data-URIs at render time.

## PDF-engine math (context)

PDF-engine equations are **images first** (cropped at high resolution from the page bitmap),
with VLM-produced LaTeX attached only as explicitly-unverified copy text (user decision).
Those images render as `<img src="data:...">` with the same block layout as KaTeX blocks, so
the viewer treats both uniformly.

## Sources

- [KaTeX options (macros, throwOnError, globalGroup)](https://katex.org/docs/options.html)
- [KaTeX auto-render extension](https://katex.org/docs/autorender.html)
- [KaTeX supported functions](https://katex.org/docs/supported.html)
