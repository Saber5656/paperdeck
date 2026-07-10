# ADR-006: Single self-contained HTML output with an enforced no-external-request invariant

- Status: Accepted
- Date: 2026-07-08
- Deciders: user (round 2: single self-contained HTML), Fable (enforcement design)

## Context

One paper → one `.html` file, fully readable offline from `file://`, shareable as a single
artifact, importable into note tools. Readers must be able to trust that opening a converted
paper performs zero network activity (privacy: no tracking of what you read; security: no
remote content injection after the fact).

## Decision

1. Output is exactly one HTML file. All CSS/JS (viewer + KaTeX) is inlined; all fonts and
   images are `data:` URIs. No `--dir` mode in v1.
2. **Self-containment invariant**: the document must load zero external resources. Enforced
   in depth:
   - a `<meta http-equiv="Content-Security-Policy">` with
     `default-src 'none'; img-src data:; media-src data:; style-src 'unsafe-inline';
     script-src '<sha256 of each inline script>'; font-src data:; connect-src 'none';
     form-action 'none'; base-uri 'none'` (exact policy in DESIGN.md §15.6);
   - a post-render **validator** that parses the emitted HTML and fails the conversion if any
     element carries a fetchable external reference (`src`, `href` on `link`, `srcset`,
     `url()` in styles, etc.);
   - the only permitted external URLs are human-clickable `<a rel="noopener noreferrer">`
     links (bibliography DOIs/arXiv links, paper metadata) — navigation on explicit click is
     allowed, resource loading is not.
3. Size budget: warn above 25 MB, hard cap 50 MB (config-overridable); oversized images are
   downscaled/recompressed to fit (DESIGN.md §15.5).
4. Reading-position and theme persistence uses `localStorage` guarded by try/catch (file://
   storage varies by browser); persistence failure degrades silently to session-only.

## Consequences

- Positive: trivially portable and archivable output; a mechanically testable privacy/security
  guarantee ("no external requests" is a CI-verifiable property, not a promise).
- Negative: multi-MB files (fonts + figures); no asset dedup across papers. Accepted for v1;
  a `--dir` layout is a v2 idea.
