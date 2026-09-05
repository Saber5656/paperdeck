# Title

[W2] 18 Implement LaTeX reference and citation resolution

## Summary

Implement part 2 of `src/paperdeck/engines/latex/refs.py`: replace every raw-TeX
placeholder with resolved `RefLink`/`Cite`/`FootnoteRef` inlines (or clean degradation),
using the label map from issue 17 and bibliography keys from issue 20, per DESIGN §12.6.

## Context

Final pass that turns parsed directives into the clickable reference graph — the product's
core feature.

## Scope

- `resolve_references(doc: NumberedDoc, labels: dict[str,str],
  bib_index: dict[str, BibRef]) -> Document`-shaped result (still engine-internal):
  substitutes sentinels in inline streams, populates `Document.labels`, appends warnings.
  `BibRef` is the cross-issue type produced by issue 20:
  `@dataclass(frozen=True) class BibRef: anchor_id: str; number: str | None;
  label: str | None` (numeric styles carry `number`; natbib author-year styles carry
  `label`).

## Detailed Requirements

1. Sentinel substitution: walk all inline sequences; each placeholder maps to its
   `RawSpan` → directives (issue 16):
   - `LabelDef` → removed (already consumed by 17; leftover = `label-loose` warning).
   - `RefUse` → one `RefLink` per name. `kind` = target block type (`eq/fig/tab/sec/fn`).
     Display text: `ref`→`<number>`; `eqref`→`(<number>)`; `cref/Cref`→`<word> <number>`
     with word from kind (`eq., fig., table, section`; capitalized for `Cref`; any `~`
     in authored text becomes a plain space); `autoref` behaves as `Cref`. Multi-name
     `cref{a,b}` → `RefLink`s joined by `, ` with the word once, pluralized by appending
     `s` when >1 name (`figs. 2, 3`).
   - `CiteUse` → `Cite{bib_ids, text}`: keys resolved via `bib_index`; text rules:
     all resolved entries have `number` → `[3, 5]` joined form; entries with `label` →
     `(Smith et al., 2020; Li & Ma, 2021)` joined by `; `; mixed/missing → fall back to
     bracketed numbers where known and `?` otherwise. Pre/postnotes appended inside the
     bracket/parens (`[3, p. 5]`). Unresolved key → that key dropped from `bib_ids`,
     `?` in its text slot, warning `cite-unresolved:<key>`.
   - `FootnoteInline` → allocate `FootnoteDef` (body re-parsed through a minimal inline
     pass: plain text + `Math` via `$…$` detection; nested commands degrade to text) +
     `FootnoteRef`.
   - `OtherTex` → dropped, warning `raw-tex-dropped:<first-30-chars-sanitized>`; **never**
     emitted into visible text (ADR guarantee: no raw TeX in output).
2. Unresolvable `RefUse` name → inert `RefLink` (`target_id=""`, kind `unresolved` is NOT
   allowed — keep syntactic kind guess from style: `eqref`→eq, else `sec`) + warning
   code `unresolved-ref` with `where=<name>` (issue 06's shared code vocabulary);
   display text falls back to `??` exactly like LaTeX.
3. After substitution run `assert_no_sentinels(doc)` (from issue 15) — any survivor is a
   hard `ConversionError("sentinel-leak")`.
4. `Document.labels` = the issue-17 map verbatim.

## Acceptance Criteria

- Golden fixture: document with `\ref/\eqref/\cref` to eq/fig/tab/sec + `\citep`
  multi-key (numeric fixture) + a natbib label fixture (`(Smith et al., 2020)` text
  asserted) + `\footnote` + one broken `\ref{nope}` + one unrecognized raw command
  `\weirdcmd{x}` → snapshot IR with exact display texts `(3)`, `fig. 2`, `[1, 4]`, `??`,
  and exactly these warnings: `unresolved-ref` (where=nope), `cite-unresolved:<key>` (from
  a citep to a missing key), `raw-tex-dropped:\weirdcmd…`.
- Sentinel-leak test: artificially unmatched placeholder → `ConversionError`.
- SEC-AC: `OtherTex` containing `<script>alert(1)</script>` never appears in any IR text
  field (dropped path asserted).

## Validation

`uv run pytest tests/unit/test_latex_refs.py -q`

## Dependencies

01, 16, 17, 20.

## Non-goals

Rendering of links (38); PDF-engine citation heuristics (35).

## Design References

DESIGN §12.6, §10.3 (RefLink/Cite), §20.2 T5.
