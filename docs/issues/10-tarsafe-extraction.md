# Title

[W1] 10 Implement safe archive extraction (tarsafe)

## Summary

Implement `src/paperdeck/input/tarsafe.py`: hardened extraction of tar/tar.gz/tgz archives
and gzip single files with the full T1 defense set of DESIGN §8.6 (traversal, link escape,
special members, bombs).

## Context

arXiv e-prints are attacker-controllable archives; this module is the primary input-side
security boundary (DESIGN §20.2 T1) and is also reused for local archive inputs.

## Scope

- `extract_tar(src: Path, dest: Path, limits: LimitsSettings) -> list[Path]`.
- `gunzip_file(src: Path, dest: Path, max_mb: int) -> Path` (single-member gzip, bomb-safe).
- `sniff_kind(path: Path) -> Literal["tar-gz","tar","gzip-single","pdf","tex","unknown"]`
  by magic bytes: `%PDF-` → pdf; ustar magic at offset 257 → tar; `\x1f\x8b` → decompress
  at most 1024 bytes (bounded peek) and re-check for the ustar magic at offset 257 of the
  decompressed prefix → `tar-gz`, else `gzip-single`; printable-text heuristic containing
  `\documentclass`/`\begin` → tex; else unknown.

## Detailed Requirements

1. Member validation before any write, per member: reject absolute names, names containing
   `..` path segments, names with NUL or backslash; reject `LNKTYPE`/`SYMTYPE` members whose
   resolved target (via `os.path.realpath` against dest) escapes `dest`; reject
   char/block/FIFO members. Rejection raises `SecurityError` with exactly one of the codes
   `tar-path-invalid` (absolute/`..`/NUL/backslash), `tar-link-escape` (sym/hardlink
   escape), `tar-special-member` (char/block/FIFO), naming the member (sanitized,
   ≤120 chars) and aborting the whole extraction (no partial results left — extraction
   happens into a fresh temp subdir moved into place on success).
2. Caps enforced while streaming (not from headers): member count >
   `limits.max_archive_members` → `SecurityError("archive-too-many-members")`;
   per-member or cumulative decompressed bytes > `limits.max_archive_total_mb` →
   `SecurityError("archive-bomb")`.
3. Permissions normalized: files 0644, dirs 0755, exec bits dropped.
4. Use `tarfile` with `filter="data"` (Python ≥3.12 semantics) **plus** the explicit checks
   above (defense in depth; do not rely on the filter alone — required checks must exist in
   our code and be unit-tested).
5. `gunzip_file` decompresses in 1 MiB chunks aborting past cap; output to tmp+rename.
6. No extraction of nested archives (a `.tar.gz` member inside is left as a file).

## Acceptance Criteria

- Attack-fixture tests (fixtures built programmatically in the test, not committed
  binaries): absolute path member; `../../x` member; symlink→`/etc` then file through it;
  hardlink escape; FIFO member; 10⁶-member header bomb (synthesized headers); 100:1
  compression bomb — each raises the specified `SecurityError` code and leaves `dest`
  absent/empty.
- Happy path: representative arXiv-like tree (nested dirs, .tex/.bbl/figures) extracts with
  normalized permissions and correct file list.
- SEC-AC: after any failure, no file exists outside the temp dir and no partial dest.

## Validation

`uv run pytest tests/unit/test_tarsafe.py -q`

## Dependencies

01, 02, 04.

## Non-goals

Deciding *what* to extract (13); e-print sniff-based routing (12 uses `sniff_kind`).

## Design References

DESIGN §8.6, §20.2 T1; ADR-007 §2.
