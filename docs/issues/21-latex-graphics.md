# Title

[W2] 21 Implement LaTeX graphics resolution and conversion

## Summary

Implement `src/paperdeck/engines/latex/graphics.py`: resolve `\includegraphics` targets
inside the source tree, convert PDF figures to PNG via pypdfium2, validate rasters, and
emit IR `Asset`s with size caps, per DESIGN §12.9.

## Context

Figures are hover-preview targets; assets must be safe (magic-byte validated, path
confined) and budget-aware since everything embeds into one HTML file.

## Scope

- `resolve_graphics(doc, project: LatexProject, limits) -> tuple[dict[str, Asset],
  list[Warning]]` — fills `Figure.asset_id` for figures whose mapped image target (issue
  15 side map) resolves; unresolved figures keep placeholder rendering.
- `\graphicspath{{dir1}{dir2}}` honored (parsed from preamble by this module).

## Detailed Requirements

1. Resolution order per target name: exact name; then `+.pdf,.png,.jpg,.jpeg` in that
   order; search dirs = graphicspath dirs then project root; all candidate paths
   realpath-confined to project root (escape → `SecurityError("graphics-escape")`).
2. `.pdf` figure → pypdfium2 render page 1, scale chosen so long side == min(2000,
   natural long side at 144 dpi) px → PNG bytes. Multi-page figure PDFs: page 1 +
   warning `figure-pdf-multipage`.
3. `.png/.jpg/.jpeg` → magic-byte validation (reject mismatch:
   `SecurityError("asset-magic-mismatch")`); dimension probe (pure-Python header parse for
   PNG IHDR / JPEG SOF — no Pillow); if long side > 4096 px → **placeholder + warning**
   `figure-too-large` (no re-encoder in v1, DESIGN §12.9).
4. `.eps` (and any other extension) → placeholder + warning `figure-eps-unsupported` /
   `figure-format-unsupported`.
5. Per-asset size cap of 10 MB, measured mechanically as: for raster files, the file
   size on disk (no decode); for PDF-rendered figures, the produced PNG byte length.
   Exceeding → placeholder + warning `figure-oversize-bytes`. (Global budget enforcement
   stays in renderer §15.5.)
6. Asset ids: `asset-<n>` sequential; `origin.source_path` = project-relative path.
7. Placeholder contract: `Figure.asset_id=None`, `alt_text` set to
   `figure unavailable (<reason>)`; renderer already handles this (issue 38).

## Acceptance Criteria

- Fixtures: tree with pdf/png/jpg figures + graphicspath subdir + extensionless reference
  + eps + oversized png (header-crafted 8000×8000) → asset map snapshot with exact
  warnings; PDF page renders to PNG bytes (magic verified) with long side ≤ 2000.
- SEC-AC: `\includegraphics{../../../../etc/passwd}` → `SecurityError`; png-named file
  with PDF magic → `asset-magic-mismatch`.
- Header-parser unit tests: PNG IHDR and JPEG SOF dimensions on 6 crafted minimal files.

## Validation

`uv run pytest tests/unit/test_latex_graphics.py -q`

## Dependencies

02, 04, 05, 13, 15 (image target side map).

## Non-goals

Downscaling rasters (v2); EPS via ghostscript (v2); global embed budget (39).

## Design References

DESIGN §12.9, §15.5; ADR-005 (no Pillow decision context), ADR-007 §2.
