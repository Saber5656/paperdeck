# ADR-001: Three-engine conversion strategy with automatic fallback

- Status: Accepted
- Date: 2026-07-08
- Deciders: user (requirements rounds 1–3), Fable (architecture)

## Context

User-confirmed requirements: hybrid input (arXiv at high quality via LaTeX source, arbitrary
PDFs best-effort), deterministic arXiv path, LLM-assisted PDF path. Research
(docs/research/01, 02) established that arXiv also publishes official LaTeXML HTML for every
TeX submission since 2023-12 (~97% availability, quality gate needed), which is strictly
higher-fidelity than anything we can produce locally with pandoc, at near-zero implementation
and runtime cost.

## Decision

paperdeck has exactly three conversion engines, all producing the same Intermediate
Representation (IR):

| Engine id | Input | Method | Determinism |
|---|---|---|---|
| `arxiv-html` | arXiv papers ≥ 2023-12 | Fetch official LaTeXML HTML, map `ltx_*` structure → IR | Deterministic |
| `latex` | arXiv e-print tarballs, local `.tex`/`.tar.gz` | pandoc JSON AST + paperdeck resolution layer → IR | Deterministic |
| `pdf` | Any PDF (arXiv or not) | pypdfium2 extraction + LLM structuring + VLM math → IR | LLM-dependent (cached) |

Selection for an arXiv input: try `arxiv-html`; if unavailable (pre-2023-12, network off,
HTTP error) or its quality gate fails (LaTeXML error markers exceed threshold), fall back to
`latex`; if that fails, fall back to `pdf` (with user-visible cost confirmation). Local
`.tex`/`.tar.gz` inputs use `latex`; local `.pdf` inputs use `pdf`. `--engine
{auto|arxiv-html|latex|pdf}` overrides selection. Every output records the engine used, and
fallback transitions are reported to the user with the reason.

## Consequences

- Positive: core reference-jump/math features get the most reliable available source per
  paper; recent arXiv papers work extremely well with no local toolchain; older papers and
  non-arXiv PDFs still work.
- Negative: three converters to build and test. Mitigated by the shared IR contract — the
  renderer/viewer and everything downstream is engine-agnostic, and each converter is
  independently issue-sized.
- The selection logic is a small explicit state machine (DESIGN.md §9) that must be unit
  tested; silent fallback is forbidden (must surface engine + reason in CLI output and in the
  document's provenance block).
