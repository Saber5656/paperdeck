# Research: LaTeX → structured-document tooling comparison

Date: 2026-07-08 (verified via web on this date)
Status: informs ADR-001 (converter strategy), ADR-002 (pandoc engine), DESIGN.md §11–12

## Problem

The arXiv path must turn a LaTeX source tree into paperdeck's Intermediate Representation
(IR) **deterministically** (user decision: no LLM on the arXiv path). The critical outputs
are: section tree, display equations with correct numbering and `\label` anchors, figures and
tables with captions and numbers, in-text `\ref`/`\eqref`/`\cite` links, and the resolved
bibliography. Full visual fidelity is *not* the goal; a correct reference graph is.

## Candidates

| Candidate | What it is | Strengths | Weaknesses | License / install weight |
|---|---|---|---|---|
| **arXiv official HTML** (LaTeXML output, fetched) | Pre-converted HTML for every TeX submission since 2023-12 | Highest structural fidelity available without local tooling; equations as MathML + `alttext` LaTeX; stable `ltx_*` class vocabulary; labels/numbers already resolved | Only papers ≥ 2023-12; ~75→90% error-free rate; needs a quality gate; network required | n/a (fetched artifact) |
| **pandoc** (LaTeX reader → JSON AST) | Universal converter, single static binary | Trivial install (single binary, all platforms); machine-stable JSON AST; `Math` nodes carry raw LaTeX (ideal for KaTeX); expands simple `\newcommand`; `latex+raw_tex` preserves unknown commands for post-processing | Cross-reference/equation numbering resolution is weak (must be reimplemented); complex preambles degrade; TeX is Turing-complete so any static parse is partial | GPL-2.0+ **binary invoked via subprocess only** (no linking → no MIT contamination); not distributed by us |
| **LaTeXML** (local install) | Perl converter used by arXiv itself | Best-in-class fidelity; exact numbering | Heavy dependency (Perl + packages); slow (minutes/paper); harder for contributors to install; duplicates what arXiv already ran server-side | Free/public-domain; heavy install |
| **plasTeX / pylatexenc / custom parser** | Python LaTeX parsers | Pure-Python | plasTeX fidelity well below LaTeXML; pylatexenc is a tokenizer, not a document converter — building a document engine on it is a multi-month project | MIT-ish; huge effort |
| **Compile-then-parse (synctex/pdf)** | Run `latex` locally | Exact numbering | **Rejected outright for security**: compiling untrusted TeX executes a Turing-complete language with file-system access (`\write18`, `\openout`); sandboxing a TeX toolchain is out of scope | — |

## Analysis

- The two viable deterministic engines are **fetched arXiv HTML** (for recent papers) and
  **pandoc + a paperdeck-owned resolution layer** (for all papers, including local `.tex`
  and pre-2023-12 arXiv).
- pandoc's known weak spot — cross-reference and equation-number resolution — is exactly
  paperdeck's core feature, so the design must own that logic explicitly:
  scan the flattened source for `\label`, replay LaTeX counter semantics over the AST in
  document order (equation/figure/table/section counters, `\nonumber`/`\notag`, starred
  environments, `\numberwithin`), and resolve `\ref`/`\eqref`/`\cref` against that map.
  This is deterministic, unit-testable, and documented as an explicit algorithm
  (DESIGN.md §12.5).
- arXiv sources reliably contain the compiled `.bbl` (arXiv's build does not run BibTeX),
  so bibliography parsing targets `\bibitem` entries in `.bbl` first, raw `.bib` second.
- LaTeXML-local is rejected for v1: it duplicates the fetched-HTML engine's output at a much
  higher installation cost. Revisit for v2 as an optional offline high-fidelity backend.

## Recommendation (adopted in ADR-001/ADR-002)

Engine precedence for a given input:

1. `arxiv-html` — deterministic ingestion of official LaTeXML HTML (arXiv ≥ 2023-12, network
   available, quality gate passes)
2. `latex` — source tarball / local `.tex` via pandoc JSON AST + paperdeck resolution layer
3. `pdf` — LLM-assisted PDF engine (any PDF; the only engine for non-arXiv PDFs)

`--engine` forces a specific engine; every produced document records which engine ran.

## Sources

- [Pandoc User's Guide](https://pandoc.org/MANUAL.html)
- [pandoc-crossref input format restriction discussion](https://github.com/lierdakil/pandoc-crossref/issues/250)
- [Pandoc LaTeX→DOCX limitations write-up](https://hackmd.io/@wmvanvliet/rynY4IYXq)
- [Scaling Accessible Mathematics on arXiv (LaTeXML, MathML)](https://arxiv.org/abs/2605.16562)
- [HTML papers on arXiv](https://arxiv.org/abs/2402.08954)
