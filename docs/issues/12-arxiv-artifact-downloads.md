# Title

[W1] 12 Implement arXiv artifact downloads (e-print, PDF, HTML page)

## Summary

Extend `src/paperdeck/input/arxiv.py` with cached, sniffed downloads of the three artifact
kinds — e-print source, PDF, and the official HTML page with its images — per DESIGN §8.3
and §11.1.

## Context

Engines consume these artifacts; download correctness (content sniffing, caps, cache
placement) determines what the selection state machine can offer.

## Scope

- `eprint(id, version) -> EprintArtifact` where kind ∈ {`tar-gz`,`tex`,`pdf-only`} and
  `path` points into cache (`source.tar.gz` / `source.tex` / `source.pdf`).
- `pdf(id, version) -> Path` (`paper.pdf`).
- `html_page(id, version) -> HtmlArtifact | None`, with the cross-issue contract
  (consumed by 23–25):
  `@dataclass(frozen=True) class HtmlArtifact: page_path: Path;
  asset_map: dict[str, str]  # original src → stored basename under html/assets/;
  skipped_images: list[str]; fetched_at: str`.

## Detailed Requirements

1. All transfers via `netgate.download` (caps + UA + rate limit inherited). Cache-first for
   every artifact; `--offline` + cached = success, + uncached = `FetchError("offline")`.
2. e-print URL `https://export.arxiv.org/e-print/<id>v<N>`; download to a temp file, then
   classify with `tarsafe.sniff_kind(tmp_path)` (never by Content-Type): `tar-gz|tar` →
   store as `source.tar.gz`; `gzip-single` → gunzip (bomb-safe, issue 10) to `source.tex`;
   `pdf` → `source.pdf` (kind `pdf-only`); `unknown` → `FetchError("eprint-unrecognized")`.
3. HTML host order: try `https://export.arxiv.org/html/<id>v<N>` first; on HTTP 404/405
   there, try `https://arxiv.org/html/<id>v<N>` (both hosts are already on the netgate
   allowlist; no allowlist exception is created — redirects remain confined to the
   allowlist by netgate). 404 at both → return `None` (not an error — feeds selection
   reason `html-unavailable`).
4. HTML image fetch: parse `index.html` for `<img src>`; fetch only same-host relative
   paths (resolve against page URL; anything absolute/cross-host is skipped and listed in
   `HtmlArtifact.skipped_images`); cap 200 images (DESIGN §11.1); each stored as
   `html/assets/<sha1-of-path><ext-from-magic-bytes>`; returned map `{original_src →
   stored_name}`.
5. Image responses validated by magic bytes (png/jpg/gif→reject gif with warning list,
   svg by `<svg` prefix after XML decl); non-image → skipped + listed.
6. Every artifact download logged at INFO with size; progress line per artifact (§19).

## Acceptance Criteria

- MockTransport tests: each e-print kind routes to the right cache file; pdf-only
  submission recognized; html 404→`None`; image allowlist (cross-host skipped), cap
  enforced, magic-byte rejection; offline behavior both branches; cache-hit performs zero
  transport calls.
- SEC-AC: `<img src="https://tracker.example/x.png">` in fetched HTML is skipped and
  recorded, never fetched (assert on transport call log).
- SEC-AC: image served with `Content-Type: image/png` but HTML payload is rejected by
  magic-byte check.

## Validation

`uv run pytest tests/unit/test_arxiv_downloads.py -q`

## Dependencies

08, 09, 10, 11.

## Non-goals

Quality gating and parsing of the HTML (23–25); tar extraction of the e-print (13 via 10).

## Design References

DESIGN §8.3, §11.1; research/01; ADR-007 §3.
