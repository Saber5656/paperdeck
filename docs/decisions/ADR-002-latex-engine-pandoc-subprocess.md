# ADR-002: LaTeX engine uses pandoc as a subprocess plus a paperdeck-owned resolution layer

- Status: Accepted
- Date: 2026-07-08
- Deciders: Fable (architecture), informed by docs/research/02

## Context

The `latex` engine must convert a LaTeX source tree to IR deterministically, without
compiling TeX (security: TeX is Turing-complete with filesystem access — see ADR-007) and
without heavyweight installs (LaTeXML requires Perl and is slow). pandoc is a single static
binary with a machine-stable JSON AST whose `Math` nodes carry raw LaTeX — ideal for KaTeX
rendering — but its cross-reference and numbering resolution is too weak for paperdeck's core
feature and must be owned by us.

## Decision

1. Invoke `pandoc -f latex+raw_tex -t json` as a hardened subprocess (explicit args list, no
   shell, CPU/wall timeout, output size cap, minimal env). pandoc is an **external tool
   dependency**, not a Python package: `paperdeck doctor` checks its presence and minimum
   version; conversion fails with an actionable install hint when missing.
2. Before pandoc: detect the main `.tex` (documentclass heuristic + common filenames), and
   flatten `\input`/`\include` **with path confinement** to the extracted source root.
3. After pandoc: a paperdeck resolution layer walks the AST in document order and replays
   LaTeX counter semantics (section/equation/figure/table counters; `equation`, `align`,
   `gather`, `multline` row numbering; `\nonumber`/`\notag`; starred forms; `\numberwithin`)
   to assign numbers, then resolves `\label`/`\ref`/`\eqref`/`\cref`/`\cite` (parsed from
   `raw_tex` inlines where pandoc did not) into IR anchors and links.
4. Bibliography: parse `\bibitem` entries from the included `.bbl` first, fall back to `.bib`
   (via a tolerant parser), producing `BibEntry` IR nodes.
5. Preamble `\newcommand`/`\def`/`\DeclareMathOperator` definitions are extracted and shipped
   in the document payload for KaTeX `macros` (ADR-003).

GPL note: pandoc is GPL-licensed; invoking it as a separate process does not affect
paperdeck's MIT licensing (no linking, no distribution of pandoc by us).

## Consequences

- Positive: trivial cross-platform install; deterministic; the hard logic (numbering/refs)
  is explicit, unit-testable Python instead of an opaque tool behavior.
- Negative: complex preambles/packages degrade parsing; numbering replay can diverge from the
  paper's actual PDF in exotic cases. Mitigations: warnings when `\ref` targets are
  unresolved; documented per-paper fallback to the `pdf` engine; fidelity limits stated in
  README.
- LaTeXML-local remains a possible v2 optional backend; rejected for v1 (install weight,
  duplicates `arxiv-html`).
