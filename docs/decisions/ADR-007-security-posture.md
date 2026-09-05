# ADR-007: Security posture — untrusted inputs, no code execution, allowlisted network

- Status: Accepted
- Date: 2026-07-08
- Deciders: Fable (security architecture); release posture confirmed by task instructions (public OSS)

## Context

paperdeck consumes untrusted files (PDFs, tarballs, TeX from the internet), talks to the
network, calls an LLM whose output is influenced by untrusted paper content, and emits HTML
that will be opened in the user's browser. Each boundary needs explicit rules that
implementation agents cannot skip.

## Decision

Core principles, binding for every issue:

1. **Never execute document-derived code.** No TeX compilation ever (`latex`, `pdflatex`,
   shell-escape are banned — TeX is Turing-complete with filesystem access). pandoc is a
   parser, not an executor, and runs as a hardened subprocess (no shell, arg list only,
   timeout, output cap, cwd = extraction dir). LLM output is data, never evaluated.
2. **Archive extraction is confined.** Tar members are validated before extraction: reject
   absolute paths, `..` traversal, symlinks/hardlinks pointing outside the extraction root,
   device/FIFO entries; enforce per-file and total size caps and a member-count cap
   (zip/tar-bomb defense). Same confinement applies to `\input` flattening.
3. **Network allowlist.** The fetch phase may contact only `export.arxiv.org` / `arxiv.org`;
   the LLM phase only the configured `base_url` host. Any other host is a hard error. TLS
   verification always on; redirects followed only within the same allowlisted host set;
   response size caps enforced while streaming. `--offline` disables all network and must be
   respected by every module (single network gate in one module).
4. **LLM output is untrusted input.** Paper text can carry prompt injection; therefore LLM
   calls use strict JSON schemas, responses are locally schema-validated, string fields are
   length-capped, and everything is HTML-escaped at render time. LLM output can never
   introduce URLs that get auto-loaded (ADR-006 validator is the backstop) and never
   influences file paths, shell args, or config.
5. **Secrets.** API keys come from env vars; never logged (a redaction filter masks
   `sk-`-like tokens in all log/error paths), never cached, never embedded in HTML output.
6. **Output is treated as a publication.** Renderer escapes all IR text; the only raw HTML
   sink is KaTeX's DOM rendering with `trust: false`. CSP + self-containment validator per
   ADR-006. Generated HTML never embeds absolute local paths beyond the user-chosen output
   name (privacy).
7. **Filesystem hygiene.** Cache/config under XDG dirs; config file permission check (warn
   if group/world-readable when it contains an inline key — which paperdeck itself never
   writes); temp dirs via `tempfile` with 0700; no world-writable artifacts.
8. **Parser risk containment (documented residual risk).** pypdfium2 parses untrusted PDFs
   in-process; PDFium is a hardened, widely-fuzzed engine, and wheels are updated via
   Dependabot. Subprocess isolation of PDF parsing is a **v2 idea**, recorded as a residual
   risk in SECURITY.md; v1 ships size caps (default 200 MB input, config-overridable) and
   page-count caps (default 500) as blast-radius limits.

Threat model, abuse cases, and per-boundary requirements are elaborated in DESIGN.md §20 and
enforced through security acceptance criteria inside individual issues (grep-able tag:
`SEC-AC`).

## Consequences

- Positive: every trust boundary has a named owner module and testable rules; "no TeX
  execution" removes the single worst risk class of this domain entirely.
- Negative: no sandboxing of PDF parsing in v1 (accepted, documented); allowlists add
  friction for exotic setups (mitigated by config override for the LLM host only).
