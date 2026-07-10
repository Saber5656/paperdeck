# ADR-008: Viewer is framework-free vanilla JS/CSS with no build toolchain; vendored assets are pinned and checksummed

- Status: Accepted
- Date: 2026-07-08
- Deciders: user (round 2: Python stack, viewer as vanilla JS/CSS), Fable (supply-chain design)

## Context

The viewer runs inside the generated HTML. Choices: a JS framework + bundler (adds a Node
toolchain to a Python project, plus supply-chain surface), vs. hand-written ES2020 vanilla JS
and plain CSS shipped as static package data.

## Decision

1. Viewer source lives at `src/paperdeck/render/assets/viewer.js` and `viewer.css` —
   hand-written, framework-free, no build step, no npm, no bundler, no transpiler. Target:
   current evergreen Chrome/Firefox/Safari (ES2020, IntersectionObserver, CSS custom
   properties). The renderer inlines these files verbatim.
2. Code organization inside the single JS file: one IIFE per feature (`popup`, `toc`,
   `theme`, `position`, `keys`) over a tiny shared core (`pd.on`, `pd.state`) — specified in
   DESIGN.md §16 so features remain independently implementable and testable.
3. Viewer logic is testable headlessly via Playwright (dev dependency only) against fixture
   documents.
4. Third-party frontend code is limited to KaTeX, vendored under
   `src/paperdeck/render/assets/vendor/katex/` by `scripts/vendor_katex.py`, which downloads
   a **pinned version over HTTPS from the official release artifact and verifies SHA-256
   checksums** recorded in `vendor/katex/MANIFEST.json`. Vendored files are committed; CI
   re-verifies checksums. No CDN references anywhere, ever (ADR-006).
5. No other runtime JS dependency may be added without a new ADR.

## Consequences

- Positive: zero Node.js in the toolchain; the whole frontend supply chain is one pinned,
  checksummed library; contributors need only Python; weak implementation agents get small,
  isolated JS features to build.
- Negative: no framework conveniences (state, components) — acceptable at this scale (~600
  lines of JS budgeted); manual cross-browser care (covered by Playwright smoke on chromium +
  webkit).
