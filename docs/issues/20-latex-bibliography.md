# Title

[W2] 20 Implement LaTeX bibliography parsing (.bbl / thebibliography / .bib)

## Summary

Implement `src/paperdeck/engines/latex/bib.py`: produce `BibEntry` IR nodes plus a
key→anchor map from `.bbl` files, inline `thebibliography` environments, or `.bib` files,
per DESIGN §12.8.

## Context

Citations resolve against these entries; arXiv sources nearly always ship a compiled
`.bbl`, so that path is primary.

## Scope

- `parse_bibliography(project: LatexProject, alloc: AnchorAllocator) ->
  tuple[list[BibEntry], dict[str, BibRef], list[Warning]]` — entries, and the
  `bib_index` consumed by issue 18 (`BibRef{anchor_id, number: str | None,
  label: str | None}`; the dataclass is defined here and imported by 18).
- Internal: `parse_bbl(text)`, `parse_bibtex(text)` (tolerant), entry-text LaTeX-lite
  cleaner.

## Detailed Requirements

1. Source priority: (a) `.bbl` file(s) in project root (if several, the one matching main
   file stem, else concatenate in name order + warning); (b) `thebibliography` environment
   in the flattened source; (c) `.bib` file(s). First non-empty source wins; record which
   in provenance-bound warning `bib-source:<kind>`.
2. `.bbl`/`thebibliography` parsing: split on `\bibitem`; each item:
   `\bibitem[label]{key}` or `\bibitem{key}`. Numbering per DESIGN §12.8: without
   `[label]`, `BibEntry.number` = 1-based position and `label=None`; with `[label]`
   (natbib author-year), `BibEntry.label` = the cleaned label text, `number=None`
   (the rendered list then shows labels, not numbers). `BibRef` mirrors these fields. Entry body cleaned by LaTeX-lite rules:
   `\emph{x}/\textit{x}` → `Emph`; `\textbf` → `Strong`; `\url{u}`/`\href{u}{t}` →
   `ExtLink` (scheme-filtered; invalid → text); `~` → space; `\&`→`&`, `\%`→`%`, `--`→en
   dash; `{...}` braces unwrapped; any remaining `\command` (with optional group) dropped
   with per-entry warning `bib-tex-dropped` (max 1 warning per entry); `$...$` spans →
   `Math` inline.
3. `.bib` parsing (fallback only): tolerant field scanner for entry types
   `article|inproceedings|book|misc|*` reading `author,title,year,journal,booktitle,doi,
   url,eprint`; format text `Authors. Title. Venue, Year.` (skip missing parts); `doi` →
   `ExtLink https://doi.org/<doi>`; `eprint` (arXiv id shape) → `ExtLink
   https://arxiv.org/abs/<eprint>`; unparseable entries skipped + warning
   `bib-entry-skipped:<key>`.
4. Keys must be unique; duplicates keep first + warning `bib-key-duplicate:<key>`.
5. Entry count cap 2 000 (warning + truncate beyond).

## Acceptance Criteria

- Fixtures: real-shaped `.bbl` (numeric style, 5 entries with `\emph`, `\url`, math in a
  title); natbib `.bbl` with `[Smith et al.(2020)]` labels; inline `thebibliography`;
  `.bib` with 4 types + one broken entry → golden IR snapshots incl. key maps and
  warnings.
- Priority test: project containing both `.bbl` and `.bib` uses `.bbl`.
- SEC-AC: `\href{javascript:alert(1)}{x}` in an entry degrades to plain text + warning
  (scheme filter proven).

## Validation

`uv run pytest tests/unit/test_latex_bib.py -q`

## Dependencies

05, 06, 13.

## Non-goals

Fetching metadata for entries (v2 Crossref); citation marker parsing (18); PDF-engine bib
(35).

## Design References

DESIGN §12.8, §10 (BibEntry), §20.2 T5.
