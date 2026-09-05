# Title

[W5] 37 Implement the KaTeX vendoring script and asset manifest

## Summary

Implement `scripts/vendor_katex.py` and commit the vendored KaTeX assets under
`src/paperdeck/render/assets/vendor/katex/` with a SHA-256 `MANIFEST.json`, per ADR-008
and DESIGN §15.4.

## Context

KaTeX is the only third-party frontend code; pinning + checksumming it is the T9
supply-chain control, re-verified at render time and in CI.

## Scope

- `scripts/vendor_katex.py` (stdlib-only: urllib over HTTPS, hashlib, zipfile/tarfile).
- Vendored files: `katex.min.js`, `katex.min.css`, `fonts/*.woff2` (woff2 only), KaTeX
  `LICENSE`.
- `MANIFEST.json`: `{"version": "<pinned>", "source_url": …, "files": {relpath: sha256},
  "generated_by": "scripts/vendor_katex.py"}`.
- A pytest verifying on-disk files against the manifest.

## Detailed Requirements

1. Pinned version as a constant at the top of the script (`KATEX_VERSION = "<latest
   stable at implementation time>"` — implementer fills from katex.org releases and
   records it in the PR description). Download the official release tarball from the
   KaTeX GitHub release URL over HTTPS; verify against `EXPECTED_ARCHIVE_SHA256`.
   Bootstrap procedure for that constant (documented in the script docstring, executed
   in the vendoring PR): download the archive, compute its sha256, **cross-check against
   the npm registry integrity field** (`npm view katex@<version> dist.integrity` /
   `dist.tarball` shasum — two independent distribution channels must agree), then
   record the constant. Version bumps repeat the same two-channel check.
2. Extract only the needed files (allowlist), stripping everything else (no auto-render
   extension — the viewer calls `katex.render` directly, issue 41); reject archive
   members outside the allowlist paths (reuse tarsafe rules if archive is tar).
3. Write files + regenerate `MANIFEST.json` (sorted keys, 2-space indent, trailing
   newline).
4. Idempotent: re-run with same version → zero diff.
5. `paperdeck.render.assets` (issue 39) and `doctor` (50) verify manifest at runtime;
   this issue ships the verification helper
   `verify_vendored(root) -> list[str]` (mismatched relpaths).
6. Committed assets in this PR: run the script once and commit the result (reviewable
   sizes; woff2 set is ~20 files).

## Acceptance Criteria

- `python scripts/vendor_katex.py` from a clean tree (network) reproduces the committed
  files byte-exactly (documented as the review procedure; CI does offline verification
  only).
- pytest: `verify_vendored` green on the tree; red when a byte is flipped (temp copy).
- SEC-AC: script refuses (exception) on archive-sha mismatch and on out-of-allowlist
  member names.
- KaTeX `LICENSE` present in the vendored dir (ADR-005 §4).

## Validation

`uv run pytest tests/unit/test_vendor_manifest.py -q`

## Dependencies

— (may optionally reuse the tarsafe member-validation helper when extracting the
release archive).

## Non-goals

Font subsetting (v2 size optimization); auto-render extension; CDN anything.

## Design References

ADR-008; DESIGN §15.4, §20.2 T9; research/04.
