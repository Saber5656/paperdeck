# Title

[W5] 42 Implement hover previews and jump/back navigation

## Summary

Implement the `popup` and `jump/back` viewer features: hover/focus previews cloning the
reference target, click-to-jump with highlight, and the viewer-managed back stack with
floating Back chip, per DESIGN §16 (`popup`, `jump/back` rows) — the product's core
interaction (R6).

## Context

This is the headline feature: previews without losing position, jumps that always come
back.

## Scope

- `popup` IIFE: show/hide lifecycle, positioning, clone rendering, a11y wiring.
- `jump` IIFE: click handling on `.pd-ref`, back stack, Back chip, hash-on-load,
  target flash highlight.

## Detailed Requirements

1. Popup show: `mouseenter` on `a.pd-ref[href^="#"]` starts a 150 ms timer; on fire,
   clone the target element — `document.getElementById(link.hash.slice(1))` (the
   leading `#` must be stripped) — strip the clone's `id` and all `id`s inside
   (dup prevention), `pd.math.renderInto(clone)` (41), insert into the single reusable
   `div#pd-popup[role="tooltip"]`, position near the link (above when bottom half of
   viewport, below otherwise; clamp horizontally 8 px margins; max-height 45vh with
   internal scroll).
2. Popup hide: `mouseleave` of both link and popup after 300 ms grace (moving into the
   popup keeps it open); `Escape` hides immediately; scroll/resize reposition or hide.
3. Keyboard parity: `focusin` on a ref shows the popup (no delay), `focusout`/`Escape`
   hides; while open, the link gets `aria-describedby="pd-popup"`.
4. Refs inside a popup clone are inert (clone pass removes `href` — CSS shows them
   plain, 47).
5. Special targets: bib entries clone the `<li>`; sections clone only the heading
   element (`h2..h6`), not the whole section subtree (size); figure clones include
   caption; dead refs (`span.pd-ref-dead`) never popup.
6. Jump: click on `.pd-ref` → `preventDefault`; push `{y: scrollY}` (stack cap 50);
   smooth-scroll target into view (`scroll-margin-top` handles the offset, 47);
   target gets class `pd-flash` for 1.2 s (removed on animationend). Respect
   `prefers-reduced-motion` (`behavior: auto`).
7. Back: fixed-position chip `button#pd-back` visible when stack non-empty, label
   `← Back (n)`; click or `Backspace` (when not in input/textarea — none exist, but guard
   anyway per DESIGN §16 keys rule) pops and restores `scrollY` (instant).
8. On load with `location.hash`: jump (no stack push) after math render settles
   (`requestAnimationFrame` ×2).
9. History API untouched (DESIGN §16 decision).

## Acceptance Criteria

- Playwright (chromium + webkit): hover eq-ref → popup contains rendered KaTeX clone;
  moving into popup keeps it; leave hides after grace; focus via Tab shows popup
  (a11y attrs asserted); click ref scrolls (viewport moved) + flash class seen; Back chip
  appears with count, restores exact scrollY; 3-jump chain pops LIFO; Backspace works;
  Escape closes popup; dead ref does nothing; `#eq-2` deep link lands on target.
- Popup positioning: link near viewport bottom → popup above (bounding boxes asserted).
- Zero console errors throughout.

## Validation

`uv run pytest tests/e2e/test_viewer_popup_back.py -q`

## Dependencies

41.

## Non-goals

ToC/theme/position/keys beyond Backspace (43–46); pinned/persistent popups (v2).

## Design References

DESIGN §16 (`popup`, `jump/back`, a11y), §15.3; R6.
