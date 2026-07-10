# Title

[W3] 23 Implement arxiv-html fetch orchestration and quality gate

## Summary

Implement `src/paperdeck/engines/arxiv_html/fetch.py` and `quality.py`: obtain the official
HTML artifact (via issue 12), then decide whether it is good enough to convert, per DESIGN
§11.1–11.2.

## Context

The quality gate is what makes the three-engine fallback safe: bad LaTeXML output must
route papers to the `latex` engine instead of producing a broken reading experience.

## Scope

- `fetch_html(ctx) -> HtmlArtifact | None` — thin orchestration over
  `ArxivClient.html_page` (issue 12), returning the cached artifact when present. The
  page + same-host image fetching itself is issue 12's responsibility (DESIGN §11.1);
  this module adds only cache/offline decision-making and gate invocation.
- `assess(html_text: str) -> GateResult` where `GateResult = {ok: bool, reason:
  str | None, error_marker_count: int, text_kb: int}`.

## Detailed Requirements

1. Gate rejection conditions (any → `ok=False`, DESIGN §11.2):
   - `reason="html-stub"`: page matches the "HTML is not available"/conversion-pending
     stub patterns (substring list kept as module constants with comments);
   - `reason="html-no-content"`: zero elements with class `ltx_section` AND zero
     `ltx_para`;
   - `reason="html-missing-title"`: no `.ltx_title_document` with non-whitespace text;
   - `reason="html-low-quality"`: `error_marker_count > max(20, text_kb / 2)` where
     markers = elements whose `class` contains `ltx_ERROR` or `ltx_missing`, `text_kb` =
     `len(visible_text)/1024`.
2. Parsing via BeautifulSoup `html.parser`; the assessment must run on the raw fetched
   file without network.
3. Threshold constants live in `quality.py` with rationale comments; changing them is a
   code change by design (DESIGN §11.2) — no config keys.
4. Result feeds selection (26) verbatim as the reason code.
5. Log line at INFO: `arxiv-html gate: ok=<bool> markers=<n> size=<kb>KB`.

## Acceptance Criteria

- Fixture HTMLs (captured/synthesized, committed): healthy paper (passes); stub page;
  empty-body page; title-less page; page with 60 error markers on 40 KB text (fails
  low-quality); page with 5 markers on 200 KB (passes). Each yields the exact reason
  string.
- No transport calls in `assess` (pure function test).
- mypy strict.

## Validation

`uv run pytest tests/unit/test_html_quality.py -q`

## Dependencies

01, 09, 11, 12.

## Non-goals

Structure/content parsing (24–25); tuning thresholds against a live sample (DESIGN §24
unknown 2 — post-v1 activity).

## Design References

DESIGN §11.1–11.2, §9; research/01 (quality statistics).
