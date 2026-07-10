# Title

[W5] 43 Implement the ToC sidebar with scroll-spy

## Summary

Implement the `toc` viewer feature: wire the server-rendered `#pd-toc` sidebar with
current-section highlighting, collapsing, toggle behavior, and narrow-viewport slide-over,
per DESIGN §16 (`toc` row) and R10.

## Context

Long papers need constant orientation; the ToC is rendered by issue 38 — this issue adds
all behavior.

## Scope

- `toc` IIFE: scroll-spy, collapse/expand, toggle button + `t` key hook point (key
  binding itself registered by 46 through `pd.keys.register` — this issue exposes
  `pd.toc.toggle()`), narrow-viewport mode.

## Detailed Requirements

1. Scroll-spy: one `IntersectionObserver` over section heading elements
   (`rootMargin: "-10% 0px -80% 0px"` — a heading in the top band is "current"); the
   matching `#pd-toc a` gets class `pd-current` (previous removed); current item scrolled
   into view within the sidebar (`block:"nearest"`).
2. Collapsing: a ToC entry of level ≥ 3 is hidden unless **it is the current section
   itself or** its ancestor chain contains the current section; a per-node disclosure
   caret (`<button aria-expanded>`, created by this JS — not by the renderer) allows
   manual pinning open (state not persisted).
3. Toggle: `button#pd-toc-toggle` is emitted by the renderer in the fixed header (issue
   38's DOM contract already includes the header button slots); `pd.toc.toggle()`
   adds/removes `pd-toc-open` on `<body>`; state persisted via `pd.store` key `pd-toc`
   (`"open"|"closed"`), default open ≥ 900 px viewport, closed below.
4. Narrow mode (< 900 px, CSS-driven via the same body class, 47): sidebar becomes a
   slide-over; the backdrop element `div#pd-toc-backdrop` is created by this JS on
   demand; clicking backdrop or any ToC link closes it.
5. ToC links reuse the jump machinery: clicking pushes the back stack (delegated —
   dispatch through the same handler as `.pd-ref` by giving ToC anchors class
   `pd-ref pd-toc-link`; renderer change coordinated in 38's DOM contract, already
   specified there).
6. No layout thrash: spy updates batched via `requestAnimationFrame`.

## Acceptance Criteria

- Playwright: scrolling through the fixture highlights successive ToC entries (≥ 3
  transitions asserted); deep level-3 entries hidden until their parent is current;
  caret expands a branch; toggle hides/shows sidebar and persists across reload
  (chromium); at 800 px viewport the sidebar overlays and closes on link click; ToC
  click jumps and Back returns (stack integration).
- a11y: sidebar is `nav[aria-label="Table of contents"]`; carets expose
  `aria-expanded`; toggle is a `<button>` with `aria-controls`.
- Scroll-spy batching: class updates occur at most once per animation frame (rAF spy
  counts ≤ frames during a scripted continuous scroll).
- Zero console errors.

## Validation

`uv run pytest tests/e2e/test_viewer_toc.py -q`

## Dependencies

41, 42 (jump integration).

## Non-goals

Key binding registration (46); styling specifics beyond the body-class contract (47);
figure/table list panels (v2).

## Design References

DESIGN §16 (`toc`, a11y), §15.2 (server-rendered nav); R10.
