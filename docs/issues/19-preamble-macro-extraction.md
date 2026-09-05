# Title

[W2] 19 Implement preamble macro extraction for KaTeX

## Summary

Implement `src/paperdeck/engines/latex/macros.py`: extract user macro definitions from the
preamble slice into `Document.macros` (name → KaTeX-compatible definition), per DESIGN
§12.7.

## Context

Papers define shorthand (`\newcommand{\R}{\mathbb{R}}`) used throughout their math; KaTeX
renders those only if the definitions are shipped with the document (ADR-003).

## Scope

- `extract_macros(preamble: str) -> tuple[dict[str, str], list[Warning]]`.

## Detailed Requirements

1. Recognized forms (using `read_group` from issue 16):
   - `\newcommand{\name}[n]{body}` / `\newcommand*{...}` / `\renewcommand` /
     `\providecommand` — optional-arg default values (`[n][default]`) are **not**
     supported → skip + warning `macro-optional-arg:<name>`.
   - `\def\name{body}` (only parameterless or `#1..#9` parameter text of the simple form
     `\def\name#1#2{body}`).
   - `\DeclareMathOperator{\name}{text}` → `\operatorname{text}`;
     starred variant → `\operatorname*{text}`.
2. Output dict key includes the backslash (`"\\R"`) matching KaTeX `macros` convention;
   body passed through verbatim (KaTeX interprets `#1…#9`).
3. Skip with a warning (never guess): definitions whose body contains `\if`, `\csname`,
   `\expandafter`, `\futurelet`, `\catcode`, `@` in the macro name (internal macros), or
   nested definitions.
3b. Redefinition precedence (complete rule set): `\providecommand` on an existing name →
   ignored silently (LaTeX semantics); `\renewcommand` → overwrites silently;
   `\newcommand`/`\def` on an existing name → overwrites + warning
   `macro-redefined:<name>`.
4. Caps: max 500 macros, max body length 2 000 chars (skip + warning beyond).
5. Comments already stripped by issue 13 — this module assumes comment-free preamble
   (document in docstring).
6. Pure function; deterministic ordering (dict in definition order).

## Acceptance Criteria

- Table-driven tests: each recognized form incl. arg counts, operator (both variants),
  each precedence rule in 3b (three cases), each skip trigger, caps.
- Round-trip test: a fixture preamble of 12 mixed definitions → expected exact dict.
- Property: extractor never raises on arbitrary preamble text.

## Validation

`uv run pytest tests/unit/test_macros.py -q`

## Dependencies

01, 13, 16 (shared brace scanner).

## Non-goals

Expanding macros ourselves (KaTeX's job); math-mode validation of bodies.

## Design References

DESIGN §12.7; ADR-003; research/04 (KaTeX macros facts).
