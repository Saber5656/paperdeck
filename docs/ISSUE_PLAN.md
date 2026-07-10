# paperdeck — v1 Issue Plan

Status: Draft for review
Date: 2026-07-08
Canonical spec: [docs/DESIGN.md](DESIGN.md). Issue drafts: `docs/issues/NN-*.md`.
GitHub Issues are derived artifacts generated from the drafts; when they disagree, drafts win.

## 1. v1 completion statement

v1 is complete when **all 55 issues below are closed and validated**, which yields:

- `paperdeck convert <arxiv-id|url|.tex|.tar.gz|.pdf>` producing a single self-contained
  HTML file via three engines (`arxiv-html`, `latex`, `pdf`) with automatic fallback
  (DESIGN §9), engine provenance, and a machine-readable run report.
- A reading experience with reference jumps + back, hover previews, KaTeX math, ToC,
  light/dark themes, reading-position restore, and keyboard navigation (DESIGN §16).
- LLM usage (PDF engine only) through any OpenAI-compatible endpoint with strict schemas,
  disk cache, cost estimation, interactive confirmation, and a hard budget (DESIGN §14).
- The enforced self-containment/CSP invariant, the security controls T1–T12 (DESIGN §20)
  with SEC-AC tests, CI (lint/type/tests/license-gate/checksums), and release packaging to
  PyPI via Trusted Publishing.

Anything not covered by an issue below is out of v1 scope by definition (see §7, §8).

## 2. Implementation waves and recommended order

Execute in numeric order within a wave; waves may overlap only where the dependency table
allows. One issue = one PR.

| Wave | Theme | Issues |
|---|---|---|
| W0 | Foundations | 01 scaffolding, 02 errors, 03 logging, 04 config, 05 IR model, 06 anchors+validation+schema |
| W1 | Acquisition | 07 resolver, 08 netgate, 09 cache, 10 tarsafe, 11 arxiv-metadata, 12 arxiv-downloads |
| W2 | `latex` engine | 13 project, 14 pandoc-runner, 15 ast-map, 16 rawtex-parser, 17 counters, 18 refs, 19 macros, 20 bib, 21 graphics, 22 latex-assembly |
| W3 | `arxiv-html` engine + selection | 23 html-fetch+gate, 24 html-structure, 25 html-content, 26 engine-selection |
| W4 | LLM + `pdf` engine | 27 llm-client, 28 llm-cache, 29 llm-cost, 30 llm-schemas+prompts, 31 pdf-extract, 32 pdf-blocks, 33 pdf-segment, 34 pdf-equations, 35 pdf-citations, 36 pdf-assembly |
| W5 | Render + viewer | 37 katex-vendoring, 38 renderer-core, 39 asset-inlining, 40 selfcontain-validator, 41 viewer-core+math, 42 viewer-popup+back, 43 viewer-toc, 44 viewer-theme, 45 viewer-position, 46 viewer-keys, 47 viewer-css |
| W6 | CLI + E2E | 48 convert-command, 49 fetch+cache-commands, 50 doctor, 51 e2e-latex+viewer, 52 e2e-pdf+security-suite |
| W7 | Release | 53 oss-meta-docs, 54 ci-pipeline, 55 packaging-release |

Suggested parallel tracks after W0: {W1→W2}, {W4 LLM half: 27–30}, {W5: 37, 41–47 against
fixture IR} can proceed concurrently; W3, W6 join the tracks.

## 3. Dependency table

`⇐` = "depends on". Convention (normative for drafts too): the table lists **direct**
dependencies only; transitive dependencies are omitted; issue 01 (scaffolding) is an
implicit dependency of every issue and is never repeated. Each draft's Dependencies
section must match its table row verbatim.

| Issue | ⇐ Depends on |
|---|---|
| 02 errors | — |
| 03 logging | 02 |
| 04 config | 02 |
| 05 ir-model | 02 |
| 06 anchors+validate | 04, 05 |
| 07 resolver | 02 |
| 08 netgate | 02, 04 |
| 09 cache | 02, 04 |
| 10 tarsafe | 02, 04 |
| 11 arxiv-metadata | 02, 08, 09 |
| 12 arxiv-downloads | 08, 09, 10, 11 |
| 13 latex-project | 02, 10 |
| 14 pandoc-runner | 02 |
| 15 ast-map | 05, 06, 14 |
| 16 rawtex-parser | 02 |
| 17 counters | 15, 16 |
| 18 latex-refs | 16, 17, 20 |
| 19 macros | 13, 16 |
| 20 latex-bib | 05, 06, 13 |
| 21 graphics | 02, 04, 05, 13, 15 |
| 22 latex-assembly | 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21 |
| 23 html-fetch+gate | 09, 11, 12 |
| 24 html-structure | 05, 06, 23 |
| 25 html-content | 11, 23, 24 |
| 26 engine-selection | 02, 04, 07, 09 |
| 27 llm-client | 03, 04, 08 |
| 28 llm-cache | 09, 27 |
| 29 llm-cost | 02, 04, 27 |
| 30 llm-schemas+prompts | 02 |
| 31 pdf-extract | 02, 04 |
| 32 pdf-blocks | 31 |
| 33 pdf-segment | 27, 28, 30, 32 |
| 34 pdf-equations | 05, 27, 29, 30, 31, 33 |
| 35 pdf-citations | 05, 06, 27, 30, 33 |
| 36 pdf-assembly | 05, 06, 12, 29, 31, 32, 33, 34, 35 |
| 37 katex-vendoring | — |
| 38 renderer-core | 05, 06 |
| 39 asset-inlining | 37, 38 |
| 40 selfcontain-validator | 38, 39 |
| 41 viewer-core+math | 37, 38, 39 |
| 42 viewer-popup+back | 41 |
| 43 viewer-toc | 41, 42 |
| 44 viewer-theme | 39, 41 |
| 45 viewer-position | 41 |
| 46 viewer-keys | 42, 43, 44 |
| 47 viewer-css | 41 |
| 48 convert-command | 02, 03, 07, 26, 29, 38, 39, 40 |
| 49 fetch+cache-commands | 07, 09, 11, 12 |
| 50 doctor | 04, 08, 14, 37 |
| 51 e2e-latex+viewer | 22, 42, 43, 44, 45, 46, 48 |
| 52 e2e-pdf+security | 10, 30, 36, 40, 48 |
| 53 oss-meta-docs | — |
| 54 ci-pipeline | — (workflow grows with waves; its final gates require 06, 08, 37, 40, 41, 52 to have landed — see plan order) |
| 55 packaging-release | 54 |

## 4. Coverage table (DESIGN.md § → issues)

| DESIGN section | Issue(s) |
|---|---|
| §5.1 layout, engine protocol | 01 |
| §6.1 convert | 48 |
| §6.2–6.3 fetch/cache/doctor | 49, 50 |
| §6.4 slug | 07, 48 |
| §7 config | 04 |
| §8.1 resolver | 07 |
| §8.2–8.3 arXiv client | 11, 12 |
| §8.4 netgate | 08 |
| §8.5 cache | 09 |
| §8.6 tarsafe | 10 |
| §9 selection | 26 |
| §10 IR | 05, 06 |
| §11.1–11.2 html fetch/gate | 23 |
| §11.3 html structure | 24 |
| §11.4 html content | 25 |
| §12.1 project | 13 |
| §12.2 pandoc | 14 |
| §12.3 ast-map | 15 |
| §12.4 rawtex | 16 |
| §12.5 counters | 17 |
| §12.6 refs | 18 |
| §12.7 macros | 19 |
| §12.8 bib | 20 |
| §12.9 graphics | 21 |
| §12.10 assembly | 22 |
| §13.1 extract | 31 |
| §13.2 blocks | 32 |
| §13.3 segment | 33 |
| §13.4 equations | 34 |
| §13.5 citations | 35 |
| §13.6 assembly | 36 |
| §14.1–14.4 client | 27 |
| §14.5 cache | 28 |
| §14.6 cost | 29 |
| LLM schemas/prompts (§13.3–13.5) | 30 |
| §15.1–15.3 renderer | 38 |
| §15.4–15.5 assets/budgets | 39 (KaTeX supply: 37) |
| §15.6 CSP/validator | 40 |
| §16 viewer | 41–47 |
| §17 storage | 09 (cache), 04 (config) |
| §18 errors | 02 |
| §19 logging/report | 03, 48 |
| §20 security model | distributed SEC-ACs: 08, 10, 14, 27, 38, 40; suite: 52; disclosure: 53 |
| §21 testing | per-issue Validation + 51, 52, 54 |
| §22 packaging | 01, 55 |
| §23 budgets | 39, 41, 48 (report timings) |

Every DESIGN section maps to ≥1 issue; no v1 behavior lives only in prose.

## 5. Validation strategy (product level)

1. Per-issue: each issue's Validation section is executable (pytest selectors / commands);
   PRs must run them.
2. Integration gates: after W2 → golden IR snapshots for the latex corpus; after W3 →
   selection matrix tests (§9 table); after W4 → FakeLLM pdf-engine goldens; after W5 →
   self-containment validator green on all goldens + Playwright suite; after W6 → full
   `convert` E2E on fixtures incl. `--offline`, `--engine` forcing, cost-guard paths.
3. Security: SEC-AC tests (T1 tar attacks, T4 injection strings, T5/T6 validator, T8 log
   redaction) all land with their owning issues; issue 52 assembles them into one suite CI
   job; release blocked if absent.
4. Pre-release manual sweep: 10-paper checklist (DESIGN §21) executed and recorded in the
   release PR.
5. Coverage floor 85% enforced by CI (issue 54).

## 6. GitHub issue conventions

- Title: `[W<wave>] <NN> <short imperative title>` (English).
- Body: generated from the draft file verbatim + a footer link to the draft path.
- Labels: `enhancement` + `wave:W<N>` (labels created on demand); security-relevant issues
  additionally `security`.
- One issue per draft; drafts are the source of truth; edits flow draft → issue.

## 7. Deferred to v2 (explicitly out of scope)

Symbol-definition hover (LLM), LaTeXML-local backend, MathJax fallback, offline/local-ML
PDF path (GROBID/Nougat), Crossref/Semantic Scholar citation enrichment, `--dir` output,
annotations/highlights, library index page, PDF-parse process sandboxing, EPS via
ghostscript, Windows CI, theorem-environment numbering, inline math on the pdf engine.

## 8. Known unknowns that may create new issues

Tracked list mirrors DESIGN §24: (1) pandoc failure rate on old sources → possible
preamble-sanitizer issue; (2) LaTeXML HTML variance → mapping/gate tuning issue;
(3) VLM LaTeX quality threshold; (4) file:// storage matrix; (5) KaTeX coverage gaps;
(6) json_schema compat quirks per local server; (7) exotic PDF layouts; (8) pricing drift
at release. Discovery during implementation must produce a new draft in `docs/issues/`
before code, per the derived-artifact rule.
