# Title

[W5] 39 Implement asset inlining, CSP hashing, and size budgets

## Summary

Implement `src/paperdeck/render/assets.py`: build the `AssetsBundle` (inline CSS/JS with
KaTeX fonts as data-URIs, CSP script hashes) and enforce the embed size budgets with
ordered asset dropping, per DESIGN §15.4–15.5.

## Context

Realizes the single-file guarantee mechanically: everything the page needs is embedded
here, and nothing else survives to the output.

## Scope

- `build_bundle(doc: Document, settings) -> AssetsBundle` =
  `{style_text, scripts: [{text, sha256_b64}], csp_value, image_srcs: dict[asset_id,
  data_uri], dropped: [DroppedAsset], total_embedded_bytes}`.
- Budget enforcement + drop ordering.

## Detailed Requirements

1. Style: `viewer.css` + `katex.min.css` with every `url(fonts/…woff2)` rewritten to
   `data:font/woff2;base64,…` from vendored files; non-woff2 `url()` refs stripped;
   verify vendored checksums first via `verify_vendored` (37) → mismatch =
   `SecurityError("vendor-checksum")`.
2. Scripts: `[katex.min.js, viewer.js]` in that order; each hashed
   `sha256-<base64(digest)>` for CSP.
3. CSP string exactly per DESIGN §15.6 with the script hash list substituted.
4. Document assets: every `Asset.data_b64` → `data:<mime>;base64,<data>`; total embedded
   bytes tracked (decoded sizes).
5. Budgets (DESIGN §15.5): warn > `embed_warn_mb`; over `embed_hard_max_mb` → drop
   assets in order: figure images largest-first, then table images; equation images are
   **never** dropped (pdf-engine ground truth), fonts/JS/CSS never dropped; each drop
   recorded (`DroppedAsset{id, bytes, reason}`) and the corresponding node renders its
   placeholder (renderer consumes `image_srcs` absence); still over after all droppable
   → `ConversionError("output-too-large")`.
6. Deterministic ordering of hashes and drops.

## Acceptance Criteria

- Unit tests: font URL rewrite covers every `url()` in the committed katex.css (count
  asserted > 0, none left); hash values verified against `hashlib` recomputation; CSP
  string matches DESIGN §15.6 template byte-exactly for a 2-script bundle.
- Budget tests with synthetic assets: warn boundary; drop order (fig > tab, largest
  first, equations retained); hard failure when undroppable.
- SEC-AC: flipped byte in vendored katex.min.js → `SecurityError("vendor-checksum")`.
- Determinism: two builds byte-identical.

## Validation

`uv run pytest tests/unit/test_render_assets.py -q`

## Dependencies

01, 37, 38 (bundle consumer contract).

## Non-goals

HTML-level validation (40); recompressing images (v2).

## Design References

DESIGN §15.4–15.5, §15.6 (CSP), §23 budgets; ADR-006; ADR-008.
