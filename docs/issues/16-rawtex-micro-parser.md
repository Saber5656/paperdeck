# Title

[W2] 16 Implement the raw-TeX micro-parser

## Summary

Implement part 1 of `src/paperdeck/engines/latex/refs.py`: a small tolerant parser that
recognizes the fixed command set (`\label`, `\ref`, `\eqref`, `\cref`/`\Cref`,
`\autoref`, `\cite` variants, `\footnote`) inside raw TeX strings, per DESIGN §12.4.

## Context

pandoc leaves commands it cannot model as `RawInline (tex)`; issue 15 collects them as
`RawSpan`s. This parser turns each span into typed directives that issues 17–18 consume.

## Scope

- `parse_raw_tex(tex: str) -> list[TexDirective]` where every `TexDirective` variant
  carries `span: tuple[int, int]` (start/end offsets into the input) plus its fields:
  `LabelDef{name}`, `RefUse{style: "ref"|"eqref"|"cref"|"Cref"|"autoref", names:
  list[str]}`, `CiteUse{style: "cite"|"citep"|"citet"|"citealp"|"citealt"|"citeauthor"|
  "citeyear", keys: list[str], prenote?: str, postnote?: str}`,
  `FootnoteInline{tex_body: str, truncated: bool}`, `OtherTex{tex}` (unrecognized
  remainder).
- Balanced-brace scanning utility `read_group(s, i) -> (content, next_i)` (also consumed
  by issue 19).

## Detailed Requirements

1. Recognized grammar (regex + brace scanner; whitespace-tolerant):
   `\label{name}`; `\ref{a}` / `\ref{a,b}`; `\eqref{a}`; `\cref{a,b}` and `\Cref`;
   `\autoref{a}`; cite family with optional `[pre][post]` arguments:
   `\cite[p. 3]{k1,k2}`, `\citep[e.g.][p. 5]{k}` (one bracket = postnote, two =
   prenote+postnote, natbib semantics); `\footnote{...}` with balanced braces (nested
   braces and escaped `\{` handled; body over 10 000 chars → truncated to the cap with
   `FootnoteInline.truncated=True`).
2. A span may contain several directives plus loose text; loose text is returned as
   `OtherTex` fragments in positional order (issue 18 decides to drop them with warnings).
3. Never raises on malformed input: unterminated groups produce `OtherTex` for the
   remainder; the parser must be total.
4. Label/key charset: accept `[A-Za-z0-9_:.+/-]+`; anything else in a name → treat whole
   command as `OtherTex` (avoids garbage anchors).
5. Pure module: no IR imports, no logging; fully property-testable.

## Acceptance Criteria

- Table-driven tests ≥ 40 cases covering every style, comma lists, pre/postnotes, nested
  braces in footnotes, escaped braces, unterminated input, mixed text+commands ordering,
  10 KB footnote truncation.
- Fuzz-ish property test: for random byte strings (seeded), parser returns without
  exception, `span`s are non-overlapping, in ascending order, and their union covers the
  entire input exactly.
- mypy strict; zero dependencies beyond stdlib.

## Validation

`uv run pytest tests/unit/test_rawtex_parser.py -q`

## Dependencies

01, 02.

## Non-goals

Resolving names to anchors (18); counter semantics (17); macro definitions (19 — different
command set).

## Design References

DESIGN §12.4; ADR-002 (own the resolution layer).
