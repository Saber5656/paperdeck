# Title

[W1] 07 Implement input resolver and output slug

## Summary

Implement `src/paperdeck/input/resolver.py`: classify the CLI `INPUT` argument into an
`InputSpec` per the DESIGN §8.1 grammar, and the output-slug function per §6.4.

## Context

First step of every conversion; the accepted-forms grammar is a user-facing contract and
must produce excellent error messages.

## Scope

- `InputSpec` frozen dataclass: `kind: Literal["arxiv","latex-local","pdf-local"]`,
  `arxiv_id: str | None`, `version: int | None`, `path: Path | None`,
  `archive: bool` (latex-local), `original: str`.
- `resolve(raw: str) -> InputSpec`.
- `output_slug(spec: InputSpec) -> str` per DESIGN §6.4.

## Detailed Requirements

1. Classification order exactly DESIGN §8.1 (local path first — an existing file named
   `2401.12345` is treated as a file; document this in the docstring).
2. Local suffix mapping: `.pdf`→pdf-local; `.tex`→latex-local(single);
   `.tar`, `.tar.gz`, `.tgz`, `.gz`→latex-local(archive). Other suffixes → `InputError`
   listing accepted forms. Path must exist and be a regular file (symlinks resolved;
   directories rejected in v1).
3. arXiv URL parsing: hosts {arxiv.org, www.arxiv.org, export.arxiv.org}; paths
   `/abs/<id>`, `/pdf/<id>`, `/pdf/<id>.pdf`, `/html/<id>`; query/fragment ignored;
   scheme http/https. Extracted `<id>` re-validated by the ID regexes.
4. ID regexes (compiled, anchored): new `^\d{4}\.\d{4,5}(v\d+)?$`; old
   `^[a-z][a-z-]*(\.[A-Z]{2})?/\d{7}(v\d+)?$`; optional case-insensitive `arXiv:` prefix
   stripped before matching. Normalization: `InputSpec.arxiv_id` stores the id **without**
   any `v<N>` suffix; the version is captured separately as `InputSpec.version: int | None`.
   The slug (`§6.4`) re-appends `v<N>` from `spec.version` when present.
5. Slug: `arxiv-<id>[v<N>]` with `/`→`-`; local: input basename without suffix; result
   always matches `^[A-Za-z0-9._-]+$` (unsafe chars → `-`).
6. Error message for unrecognized input lists one example of each accepted form.

## Acceptance Criteria

- Table-driven unit tests: ≥ 25 accept cases (all forms above incl. versioned old-style
  IDs) and ≥ 10 reject cases (bad host, bad scheme `ftp:`, directory path, `.docx`,
  malformed ids like `24010.1234`); `2401.12345v2` yields `arxiv_id="2401.12345"`,
  `version=2` (normalization asserted).
- Slug property test: output always regex-safe, deterministic.
- No network and no filesystem writes in this module (reads only for existence checks).

## Validation

`uv run pytest tests/unit/test_resolver.py -q`

## Dependencies

01, 02.

## Non-goals

Fetching (11–12), engine choice (26), overwrite handling (48).

## Design References

DESIGN §6.4, §8.1.
