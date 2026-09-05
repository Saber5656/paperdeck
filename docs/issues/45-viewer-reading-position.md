# Title

[W5] 45 Implement reading-position save and restore

## Summary

Implement the `position` viewer feature: continuously persist the reading position per
document and restore it on reopen with an unobtrusive toast, per DESIGN §16 (`position`
row) and R10.

## Context

Papers are read across multiple sittings; losing one's place in a 40-page paper is the
frustration this feature removes. Storage on `file://` is best-effort (known unknown 4).

## Scope

- `position` IIFE: tracking, persistence, restore + toast; exposes
  `pd.position.goTop()` for the toast action and tests.

## Detailed Requirements

1. Tracking (DESIGN §16 `position` row): on scroll (debounced 500 ms) find the topmost
   block element whose top is within the upper third of the viewport (candidates:
   elements with ids — sections, paragraphs, equations, figures); save
   `{anchor: id, offset: elementTop − scrollY, at: Date.now()}` where `elementTop =
   el.getBoundingClientRect().top + scrollY` at save time, via `pd.store` key
   `pd-pos:<pd.docId>`.
2. Restore on load only when: no `location.hash`, stored anchor exists in the DOM, and
   the restore target `currentElementTop − offset` > 1.5 × viewport height (restoring to
   near-top is noise). Restore after math settle (rAF ×2) via
   `scrollTo(0, currentElementTop − offset)` (instant, no smooth), then toast.
3. Toast `div#pd-toast[role="status"]`: `Resumed — press T to go to top` (wording fixed,
   DESIGN §16); auto-hide 4 s; `T` (this feature listens directly while toast visible;
   global key registry arrives in 46) or click hides + `goTop()` scrolls to 0 and clears
   the saved position.
4. Saving is skipped entirely (feature silent) when `pd.store` is a no-op.
5. Stored value validated on read (JSON shape `{anchor: str, offset: number, at:
   number}` + anchor regex `^[a-z]+-\d+$`); invalid → discard silently.
6. `beforeunload` flush of the pending debounce.

## Acceptance Criteria

- Playwright (chromium, `file://`): scroll to mid-document → reload → viewport restored
  within ±1 viewport-third of the anchor + toast visible then auto-hides; pressing `T`
  while visible goes to top and a subsequent reload does NOT restore; deep-link
  `#eq-2` reload does not restore (hash precedence); storage-disabled context → no toast,
  no errors.
- Debounce: rapid scroll produces ≤ 3 writes over 2 s (store spy).
- `beforeunload` flush: scroll then immediate reload persists the latest position (the
  pending debounced write is not lost — restore lands at the final scroll position).
- Stored-garbage injection (invalid JSON, alien anchor) → clean load, value replaced on
  next scroll.

## Validation

`uv run pytest tests/e2e/test_viewer_position.py -q`

## Dependencies

41.

## Non-goals

Cross-device sync; scroll percentage fallback when ids missing (ids always exist by IR
construction); key registry integration beyond the toast-local `T` (46).

## Design References

DESIGN §16 (`position`), §24 unknown 4; R10.
