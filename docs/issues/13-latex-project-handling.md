# Title

[W2] 13 Implement LaTeX project handling (main-tex detection, input flattening)

## Summary

Implement `src/paperdeck/engines/latex/project.py`: pick the main `.tex` file from an
extracted source tree, flatten `\input`/`\include` with path confinement, strip comments,
and slice out the preamble, per DESIGN §12.1.

## Context

pandoc receives one flattened file; wrong main-file choice or unsafe include resolution
breaks or compromises the whole latex engine.

## Scope

- `prepare(source: Path) -> LatexProject` where source is a dir (extracted archive) or a
  single `.tex`; `LatexProject` = `{root: Path, main: Path, flattened: Path
  (main.flat.tex in a temp workdir), preamble: str, warnings: list[Warning]}`.

## Detailed Requirements

1. Main detection (dir case), in order per DESIGN §12.1: (a) unique `.tex` containing
   `\documentclass` → it; (b) several → prefer basename in {`main`,`paper`,`ms`,`arxiv`}
   (that order); (c) still ambiguous → the candidate with the **largest transitive count
   of `\input`/`\include`-reachable `.tex` files**; (d) tie → largest file size +
   warning `main-tex-ambiguous`. Zero candidates → `ConversionError("no-main-tex")`.
   Single-file input: that file is the main; `root` = its parent directory.
2. Comment stripping before include-scan: remove unescaped `%` to EOL, except inside
   `verbatim`/`lstlisting`/`filecontents` environments (line-based state machine; `\%`
   preserved).
3. Flattening: replace `\input{x}` / `\include{x}` (+ optional `.tex` suffix) with file
   contents wrapped in `% >>> x` / `% <<< x` markers; include paths resolve **relative to
   `root`** (LaTeX semantics — not relative to the including file), confined to `root`
   (reject via realpath check → `SecurityError("include-escape")`); missing file → leave
   command, add warning `missing-include`; recursion depth cap 20 and cycle set →
   `ConversionError("include-cycle")`.
4. `\include` additionally inserts `\clearpage`-equivalent paragraph break marker (plain
   blank line) — layout fidelity is irrelevant, structure is not.
5. Preamble = flattened text before the first `\begin{document}` (missing →
   `ConversionError("no-begin-document")`).
6. All reads latin-1-fallback decoding (arXiv sources are usually UTF-8, sometimes
   legacy 8-bit; try utf-8 then latin-1, record warning on fallback).

## Acceptance Criteria

- Fixture tests: single-file project (root = parent dir asserted); multi-file with
  nested `\input`; `\include` (blank-line insertion asserted); ambiguous mains resolved
  per priority list (each branch a-d covered); missing include leaves the command and
  emits `missing-include`; source without `\begin{document}` →
  `ConversionError("no-begin-document")`; comment stripping incl. `\%` and verbatim
  protection; utf-8 + latin-1 fixtures (fallback warning asserted).
- SEC-AC: `\input{../../etc/passwd}` and `\input{/abs/path}` raise
  `SecurityError("include-escape")`; symlinked include escaping root likewise.
- Cycle fixture (`a` includes `b` includes `a`) raises `include-cycle`.

## Validation

`uv run pytest tests/unit/test_latex_project.py -q`

## Dependencies

01, 02, 10.

## Non-goals

pandoc invocation (14); macro extraction (19 — consumes `preamble`).

## Design References

DESIGN §12.1; ADR-002; ADR-007 §2.
