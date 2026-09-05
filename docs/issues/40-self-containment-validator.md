# Title

[W5] 40 Implement the CSP and self-containment validator

## Summary

Implement `src/paperdeck/render/validate.py`: the post-render check that the emitted HTML
provably loads zero external resources and carries the exact CSP, runnable in-pipeline and
as `python -m paperdeck.render.validate <file>`, per DESIGN §15.6.

## Context

This is the enforcement half of ADR-006 — turning "no external requests" from a promise
into a machine-checked property of every artifact (T5/T6 backstop).

## Scope

- `validate_html(html_text: str) -> list[Violation]` (`Violation{code, detail,
  element_excerpt ≤ 120 chars}`) — empty list = pass.
- `__main__` entry: prints violations, exit 0/9.
- Pipeline wiring point defined (issue 48 calls it; here: function + CLI).

## Detailed Requirements

Parse with BeautifulSoup (`html.parser`) and flag:

1. `external-resource`: any element attribute in {`src`, `srcset`, `poster`, `data`,
   `ping`, `background`} whose value has a scheme other than `data:` (or is
   protocol-relative `//…`); `href` on any element **except** `<a>`; `<a href>` with
   scheme outside {https, http, mailto, fragment-only} or missing
   `rel~="noopener"` when scheme is http(s).
2. `forbidden-element`: `<link>`, `<iframe>`, `<frame>`, `<object>`, `<embed>`, `<form>`,
   `<base>`, `<meta http-equiv="refresh">`, `<video>`/`<audio>`/`<source>`/`<track>`
   (v1 has no media).
3. `inline-handler`: any attribute name matching `^on[a-z]+`.
4. `style-url`: `url(` token inside `<style>` text or any `style=""` attribute whose
   argument is not `data:` (tokenizer handles whitespace/quotes: `url( 'x' )`).
5. `csp-missing` / `csp-mismatch`: exactly one
   `meta[http-equiv="Content-Security-Policy"]`; its content must equal the DESIGN §15.6
   template with the hash list matching sha256 of each inline `<script>` body present
   (recomputed here independently of issue 39); `script-src` may contain only
   `'sha256-…'` tokens.
6. `script-external` / `script-type`: `<script src>` forbidden; scripts must be bare or
   `type="application/json"` (the data island).
7. `svg-inline`: any `<svg>` element in the document (policy: images only via
   `img[src^=data:]`, DESIGN §10.5).
8. Excerpts sanitized (control chars stripped, length-capped) — violations are safe to
   print.

## Acceptance Criteria

- Red-fixture suite: one minimal HTML per violation code (≥ 12 fixtures); each fixture's
  expected code must be **present** in the result (co-occurring codes are acceptable —
  e.g. a `<script src>` fixture also fails CSP hashing); green fixture (a real rendered
  kitchen-sink output from issue 38+39) produces zero violations.
- Hash recomputation: tampering one script byte in the green fixture → `csp-mismatch`.
- CLI: exit 9 with violations printed one-per-line as `<code>: <detail>`; exit 0 on
  green (both asserted via subprocess).
- SEC-AC: `<img src="https://tracker.example/p.gif">`, `<a href="javascript:x">`,
  `<div onclick=…>`, protocol-relative `//cdn…` each caught.

## Validation

`uv run pytest tests/unit/test_selfcontain_validator.py -q`

## Dependencies

38, 39 (green fixture).

## Non-goals

Fixing violations (renderer's job); generic HTML sanitization (we validate our own
output, not arbitrary pages).

## Design References

DESIGN §15.6, §20.2 T5/T6; ADR-006.
