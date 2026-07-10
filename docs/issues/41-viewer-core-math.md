# Title

[W5] 41 Implement viewer core and lazy math rendering

## Summary

Create `src/paperdeck/render/assets/viewer.js` foundations: the `pd` core (store, docId,
data island, tiny DOM helpers) and the `math` feature — KaTeX rendering with viewport
laziness, macros injection, and error fallback, per DESIGN §16 (`math` row) and ADR-003.

## Context

First viewer issue: establishes the file's IIFE-per-feature structure (ADR-008) and the
math pipeline every popup/preview depends on.

## Scope

- `pd` core with fixed signatures (later viewer issues program against these):
  `pd.qs(sel, root = document) -> Element | null`;
  `pd.qsa(sel, root = document) -> Element[]` (real array);
  `pd.on(target, event, handler, opts?) -> void`;
  `pd.store = {get(key) -> string | null, set(key, value) -> void, remove(key) -> void}`
  — try/catch localStorage; every method silently no-ops/returns null when storage
  throws; `pd.data` (parsed `#pd-data` JSON island, `{}` on parse failure); `pd.docId`
  (string from `pd.data`).
- `math` IIFE: render `.pd-eq[data-latex]` (displayMode) and `.pd-math[data-latex]`
  (inline), plus `pd.math.renderInto(root)` API for the popup (42): renders every
  un-rendered math element **within `root`, including `root` itself** when it matches.
- Copy-latex button behavior for image equations (`.pd-copy-latex`).

## Detailed Requirements

1. ES2020, strict mode, zero globals except one `window.pd`; each feature an IIFE
   appended to the same file with a `// ---- feature: math ----` banner (ADR-008 layout).
2. Math rendering (DESIGN §16 `math` row): elements within the initial viewport render
   synchronously at DOMContentLoaded; everything else via one `IntersectionObserver`
   (`rootMargin: "200%"` — pre-renders the surrounding screens before they scroll in),
   unobserved after render. Each element:
   `katex.render(latex, el, {throwOnError: false, displayMode, macros: pd.data.macros,
   trust: false, strict: "ignore"})`; a thrown error (malformed despite
   throwOnError=false is possible for lexer errors) is caught → element gets class
   `pd-math-error` and shows the raw latex inside a `<code>` (textContent assignment
   only).
3. Rendered flag `data-pd-rendered="1"`; `renderInto(cloneRoot)` renders any un-rendered
   math inside a detached clone synchronously (popup path).
4. Copy button: `navigator.clipboard.writeText(btn.dataset.latex)` with fallback to a
   temporary textarea + `document.execCommand("copy")` (file:// clipboard quirks); after
   copy show a 2 s inline toast `Copied (unverified LaTeX)` (R5 wording).
5. No timers besides the toast timeout; no network APIs anywhere (fetch/XHR/WebSocket
   absent from the file — CI greps, issue 54).
6. JS budget for this issue: ≤ 150 lines (core + math), documented line-count check in
   review.

## Acceptance Criteria

- Playwright tests (chromium + webkit) on a rendered fixture from issues 38+39:
  above-fold equation rendered before any scroll (KaTeX DOM present); below-fold
  equation renders after scroll into view; broken latex fixture shows `.pd-math-error`
  with raw source visible; macros from `#pd-data` resolve (`\R` fixture renders);
  copy button writes clipboard (chromium permission granted) and toast appears.
- `pd.store` works on `file://` chromium and silently no-ops when storage throws
  (simulated via page context override).
- SEC-AC: a fixture equation with latex `\href{javascript:alert(1)}{x}` renders with
  **no** `<a>` element in the KaTeX output (`trust: false` proven), and a malformed-latex
  fallback displays via `textContent` only (no HTML interpretation — asserted by
  injecting `<img onerror>` into the latex string and finding zero `img` elements).
- Zero console errors on load (asserted).

## Validation

`uv run pytest tests/e2e/test_viewer_math.py -q` (Playwright marker)

## Dependencies

37, 38, 39 (fixture pages).

## Non-goals

Popups (42), ToC (43), theme (44), position (45), keys (46), styling (47).

## Design References

DESIGN §16 (`math`, core), §23 (first-paint budget); ADR-003, ADR-008; R5.
