# Title

[W5] 44 Implement the theme toggle (auto/light/dark)

## Summary

Implement the `theme` viewer feature: a three-state theme control (`auto → light → dark`)
driving `data-theme` on `<html>`, persisted across documents, per DESIGN §16 (`theme` row)
and R10.

## Context

Long reading sessions need reliable theming; the CSS variables land in 47 — this issue
owns state and control.

## Scope

- `theme` IIFE: initial state resolution, cycle control, persistence, OS-change reaction;
  exposes `pd.theme.cycle()` for the `d` key (46).

## Detailed Requirements

1. State (DESIGN §16 `theme` row): persisted via `pd.store` global key `pd-theme` ∈
   {`auto`,`light`,`dark`} (missing/invalid → `auto`). Applied as
   `document.documentElement.dataset.theme` = **resolved** value `light|dark` (`auto`
   resolves via `matchMedia("(prefers-color-scheme: dark)")`), plus `dataset.themeMode`
   = raw mode (CSS keys off `data-theme` only; the mode attribute feeds the button
   label).
2. To avoid a flash of wrong theme, the state-resolution snippet runs as the FIRST
   statement of viewer.js, which issue 39 places before `katex.js`? — order is fixed as
   [katex, viewer] (DESIGN §15.4); therefore the renderer (38) additionally emits the
   one-line theme bootstrap as the leading statement of the *viewer.js* file itself is
   insufficient. Resolution: this issue moves theme bootstrap into a tiny third inline
   script emitted FIRST by issue 39 (bundle order becomes [theme-bootstrap, katex,
   viewer]); the bootstrap is 3 lines, lives as
   `render/assets/theme_bootstrap.js`, and is hashed like the others. (Coordinated
   change: 39's `scripts` list gains this file — update its manifest test.)
3. Control: `button#pd-theme-toggle` in the header cycles auto→light→dark→auto; label
   shows current mode (`Theme: auto`); `aria-live="polite"` announcement on change.
4. OS changes while in `auto`: `matchMedia` listener re-resolves live.
5. On `pd.store` unavailability: in-page state only (no error).

## Acceptance Criteria

- Playwright (chromium): default follows emulated OS dark (`data-theme="dark"`); cycling
  reaches all three modes with label updates; choice persists across reload; in `auto`,
  emulated scheme flip updates `data-theme` without reload; no flash: a load-time
  assertion that `data-theme` is set before first paint (evaluated via
  `document.documentElement.dataset.theme` at `domcontentloaded`).
- webkit smoke: cycle works.
- SEC-AC: the theme-bootstrap script is hashed like every other inline script — the CSP
  contains exactly three `sha256-` tokens matching the three inline scripts, and the
  self-containment validator (40) stays green on a theme-enabled fixture (bundle-order
  test updated in 39's suite within this PR).

## Validation

`uv run pytest tests/e2e/test_viewer_theme.py -q`

## Dependencies

39 (bundle order change), 41.

## Non-goals

Color values/contrast (47); per-document theme memory (global by design).

## Design References

DESIGN §16 (`theme`), §15.4 (script order); R10.
