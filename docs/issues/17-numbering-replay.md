# Title

[W2] 17 Implement LaTeX numbering replay (counters)

## Summary

Implement `src/paperdeck/engines/latex/counters.py`: assign section/equation/figure/table
numbers by replaying LaTeX counter semantics over the mapped document in order, splitting
multi-row math environments, exactly per the normative algorithm in DESIGN §12.5.

## Context

Correct numbers are the backbone of reference jumps (`Eq. (3)` must point at the right
equation). pandoc does not do this; we own it (ADR-002).

## Scope

- `assign_numbers(mapped: MappedDoc, preamble: str) -> NumberedDoc` — mutates/rebuilds
  blocks with `number` fields set, splits multi-row `Equation` blocks, and returns
  `labels: dict[str, str]` (label → anchor id) built from `LabelDef` directives attached
  to blocks (issue 15 stored raw spans positionally; this issue associates a `LabelDef`
  with the nearest enclosing/preceding numberable block per LaTeX semantics).

## Detailed Requirements

1. Section numbering: counters (sec, subsec, subsubsec) with child reset; produce dotted
   strings `4`, `4.2`, `4.2.1`; unnumbered when the header came from `section*` (pandoc
   attr class `unnumbered`); `\appendix` directive (an `OtherTex` raw block) switches
   top-level to `A, B, …` (subsections `A.1`).
2. Equation environment handling — the mapped `Equation.latex` still contains the original
   environment body; classify via `MappedDoc.env_map` (issue 15) with delimiter detection
   as fallback: `equation` → 1 number; `align|gather|eqnarray|
   multline|flalign|alignat` → split on top-level `\\` (brace- and env-depth-aware; `\\`
   inside `\begin{cases}…\end{cases}` or nested envs/braces must not split) into one
   `Equation` per row, numbering rows without `\nonumber`/`\notag`; starred envs and
   `\[…\]`/`$$…$$` unnumbered; `split`/`aligned` inner envs never split (they are inside
   one number).
3. `\numberwithin{equation}{section}` (or `amsmath` `\numberwithin` in preamble) →
   equation numbers formatted `<sec>.<n>` and reset at each level-1 section.
4. `\label` binding: a `LabelDef` inside a row's latex binds to that row's Equation; in a
   figure/table caption → that Figure/Table; in section title raw span → the Section;
   loose in a paragraph → the enclosing Section (LaTeX `\label` after `\section`), with
   warning `label-loose`.
5. Figures/Tables: increment only for blocks with non-empty caption (DESIGN §12.5 #3).
6. Output invariant (DESIGN §12.5): every Equation's `latex` is the row content
   **without** the `\begin{env}`/`\end{env}` wrapper and without `\label{}` (moved to
   metadata), suitable for KaTeX display-mode rendering. Rows containing top-level
   alignment `&` are wrapped in `\begin{aligned}…\end{aligned}` (alignment preserved);
   rows without `&` are kept verbatim. `&` is never stripped.
7. Not replayed (explicit warnings when encountered as raw tex): `\setcounter`,
   `\addtocounter`, `\refstepcounter`, theorem environments (`theorem-like-unsupported`).

## Acceptance Criteria

- Golden fixtures: `equation` + `align` (3 rows, middle `\nonumber`) + `gather*` + `\[…\]`
  + `cases` inside align row (no split) + `split` inside equation → exact expected number
  sequence `(1) (2) (3) (4)`… as snapshot; `\numberwithin` fixture → `1.1, 1.2, 2.1`;
  appendix fixture → `A`, `A.1`.
- Label-binding tests for each binding rule (eq row, caption, section, loose).
- Row-splitting unit tests proving `\\` inside `cases`/braces does not split; a row with
  top-level `&` gets the `aligned` wrapper, a row without `&` stays verbatim.
- Figure/Table counter fixture: captionless figure does not increment; captioned
  figure/table sequence numbers `1, 2, …` asserted.
- Non-replayed constructs fixture: `\setcounter`, `\refstepcounter`, and a
  `theorem` environment each produce their documented warning codes.
- Property: total numbered equations == count of `(n)` produced; ids stable across two runs.

## Validation

`uv run pytest tests/unit/test_counters.py -q`

## Dependencies

01, 15, 16.

## Non-goals

Rendering `aligned` visuals (KaTeX's job); `\eqref` text formation (18); theorem numbering
(v2).

## Design References

DESIGN §12.5 (normative algorithm); §24 known-unknown 1.
