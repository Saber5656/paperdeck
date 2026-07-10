# Title

[W5] 46 Implement keyboard navigation and the help overlay

## Summary

Implement the `keys` viewer feature: the central key registry, the v1 binding set
(`j/k/t/d/Backspace/?/Escape`), and the shortcut help overlay, per DESIGN §16 (`keys`
row) and R10.

## Context

Final interactive feature; consolidates bindings exposed by earlier features
(`pd.toc.toggle`, `pd.theme.cycle`, back-stack pop) behind one guarded dispatcher.

## Scope

- `keys` IIFE: `pd.keys.register(key, description, handler)` registry + single keydown
  dispatcher; bindings; `?` overlay.

## Detailed Requirements

1. Dispatcher guards (DESIGN §16): ignore events with `ctrlKey/metaKey/altKey`; ignore
   when `event.target` is `input|textarea|select` or `isContentEditable`; ignore when
   composing (`event.isComposing`).
2. v1 bindings (registered here, delegating to feature APIs):
   `j` / `k` = scroll to next/previous section heading top (relative to current scroll;
   instant under reduced-motion, else smooth); `t` = `pd.toc.toggle()`; `d` =
   `pd.theme.cycle()`; `Backspace` = back-stack pop (42 exposes `pd.jump.back()`;
   refactor its internal listener to route through this registry — coordinated change);
   `?` (shift+/) = toggle help overlay; `Escape` = close overlay/popup (delegates to
   popup's existing handler; overlay handled here).
3. Help overlay `div#pd-help[role="dialog"][aria-modal="true"]`: table generated from the
   registry (key, description) — always in sync with actual bindings; focus trapped
   (Tab cycles inside), restored on close; close via `Escape`, `?`, or backdrop click.
4. `j/k` target list = section heading elements in document order (computed once,
   cached); from between-sections positions, `j` goes to the next heading strictly below
   `scrollY + 8`.
5. Registry rejects duplicate keys (throw at load — a broken build must fail loudly in
   e2e, not silently shadow bindings).

## Acceptance Criteria

- Playwright: `j` twice then `k` lands on the expected headings (scrollY compared to
  heading offsets); `t`/`d` trigger their features; `Backspace` pops a jump;
  `?` opens overlay listing exactly the registered bindings (row count == registry
  size), focus trapped (Tab ×N stays inside), `Escape` closes and restores focus;
  bindings inert while overlay open except `Escape`/`?`; modifier-guard: `Cmd+d`
  does not cycle theme (chromium `Meta`).
- Duplicate-registration unit-style test via page-injected script (throws).
- Zero console errors.

## Validation

`uv run pytest tests/e2e/test_viewer_keys.py -q`

## Dependencies

42, 43, 44.

## Non-goals

Vim-depth navigation (gg/G etc.), user-customizable bindings (v2).

## Design References

DESIGN §16 (`keys`, a11y); R10.
