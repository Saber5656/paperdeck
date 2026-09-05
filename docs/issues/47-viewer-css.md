# Title

[W5] 47 Implement viewer CSS (layout, themes, components, print)

## Summary

Author `src/paperdeck/render/assets/viewer.css`: the complete stylesheet — reading
layout, light/dark theme variables, every `pd-*` component, responsive/narrow mode, and
print styles, per DESIGN §16 (CSS paragraph) and the DOM contract of issue 38.

## Context

All visual polish lives here; JS features toggle classes, CSS makes them real. This is
also where readability (the actual product value) is won.

## Scope

- One CSS file, no preprocessor (ADR-008), organized by banner comments:
  variables/reset/layout/header/toc/content/math/popup/back-chip/toast/help/bib/
  footnotes/print.

## Detailed Requirements

1. Theme variables on `:root[data-theme="light"]` and `[data-theme="dark"]`: bg, fg,
   muted-fg, accent, link, popup-bg, popup-border, flash, code-bg, error — every color in
   the file must come from a variable (reviewable greppable rule: raw hex only inside the
   variable blocks). Contrast: body text ≥ 7:1, muted ≥ 4.5:1 in both themes (values
   chosen accordingly and documented as comments).
2. Layout: content column `max-width: 46rem`, centered, generous line-height (1.65);
   fixed slim header (title ellipsized, toggle buttons right); ToC as left sidebar
   (`body.pd-toc-open` grid `minmax(16rem, 20rem) 1fr`), < 900 px = fixed slide-over +
   `::backdrop`-style overlay div; `scroll-margin-top` on all `[id]` targets = header
   height + 0.5rem.
3. Math: `.pd-eq` block spacing, `overflow-x: auto` with subtle scrollbar, number
   right-aligned via flex (`.pd-eq-number`); `.pd-math-error > code` amber-tinted;
   equation images `max-width: 100%` with dark-theme treatment
   `filter: invert(1) hue-rotate(180deg)` applied ONLY when `data-theme="dark"` AND the
   image is a pdf-engine equation/table crop (class `pd-img-crop` from renderer) —
   figures are never inverted.
4. Popup `#pd-popup`: elevated card (border + shadow variables), max-width
   `min(40rem, 90vw)`, max-height 45vh, inner scroll, small arrow omitted (simplicity),
   fade-in 120 ms (`prefers-reduced-motion: reduce` → no animation anywhere — global
   media query disabling transitions).
5. Components: `.pd-flash` (background pulse via keyframes on variable), Back chip
   (fixed, bottom-left, pill), toast (bottom-center), help dialog (centered card +
   dimmed backdrop), `.pd-ref` links (accent underline-on-hover), `.pd-ref-dead`
   (muted, dotted underline, `cursor: help`), `.pd-unhandled` (muted monospace block),
   copy-latex button (small ghost button + `unverified` badge styling per R5),
   collapsible provenance footer (`<details>`).
6. Print (`@media print`): hide header/toc/chips/toast/help/popup; full-width column;
   black-on-white regardless of theme; page-break avoidance inside `.pd-eq`, `figure`,
   `li`.
7. Tables: header row emphasis, row hairlines, horizontal scroll wrapper styling
   (`.pd-table-wrap`).
8. File budget ≤ 700 lines; no `!important` (grep rule) except a single documented
   reduced-motion override block.

## Acceptance Criteria

- Playwright visual assertions (not pixel snapshots): computed styles — content column
  ≤ 46rem; header fixed; dark toggle flips body background variable; popup constrained to
  45vh on an oversized target; `.pd-img-crop` filtered in dark only; figures unfiltered;
  reduced-motion emulation removes smooth scroll (jump is instant — scroll event count
  heuristic).
- Print: `page.emulate_media("print")` hides header/toc (display none asserted).
- Grep tests: no raw hex outside variable blocks; single `!important` block.
- SEC-AC: grep test asserting `viewer.css` contains **no** `url(` token other than
  `url(data:` (a stylesheet-introduced external fetch would breach ADR-006; the issue-40
  validator is the runtime backstop, this is the source-level gate).
- Manual review checklist attached to the PR: screenshots of light/dark/narrow/print on
  the kitchen-sink fixture (procedure documented in the PR template text of this issue).

## Validation

`uv run pytest tests/e2e/test_viewer_css.py -q`

## Dependencies

41 (fixtures + class contract; later viewer-feature issues styled here may land in
parallel — selectors are fixed by the DOM contract).

## Non-goals

Custom fonts (system stack only — keeps size down); user-configurable typography (v2).

## Design References

DESIGN §16 (CSS paragraph, a11y), §23 (size); ADR-008; R5 (unverified badge), R10.
