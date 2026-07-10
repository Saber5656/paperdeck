# Title

[W1] 11 Implement arXiv metadata client

## Summary

Implement metadata fetching in `src/paperdeck/input/arxiv.py`: query the arXiv Atom API for
one paper, parse it safely, cache it, and expose typed metadata per DESIGN §8.3.

## Context

Metadata resolves the latest version when the user omitted `vN`, and supplies
title/authors/abstract/links for `Document.meta`.

## Scope

- `ArxivClient(netgate: NetGate, cache: CacheManager)`.
- `metadata(arxiv_id: str, version: int | None) -> ArxivMeta` (cache-first).
- `ArxivMeta` frozen dataclass: `id`, `latest_version: int`, `resolved_version: int`,
  `title: str`, `authors: list[str]`, `abstract: str`, `updated: str`,
  `abs_url: str`, `doi: str | None`, `categories: list[str]`.

## Detailed Requirements

1. Endpoint: `GET https://export.arxiv.org/api/query?id_list=<id>` via
   `netgate.client("arxiv")` (id **without** version; version resolution from the entry's
   version list / id suffix). Raw Atom bytes cached as `meta.xml` (cache promoted to the
   resolved version dir via `cache.promote`).
2. XML parsing: stdlib `xml.etree.ElementTree` on bytes fetched; **before parsing** reject
   payloads containing `<!DOCTYPE` or `<!ENTITY` (case-insensitive scan) with
   `SecurityError("xml-dtd")` — Atom never needs DTDs.
3. Namespaces handled explicitly (`http://www.w3.org/2005/Atom`,
   `http://arxiv.org/schemas/atom`). Missing entry / `<title>Error</title>` entry →
   `InputError("arxiv-id-not-found")` with the id echoed (sanitized).
4. Whitespace-normalize title/abstract (collapse internal newlines).
5. `resolved_version` and cache interplay (deterministic rules):
   - version explicitly requested → cache-first for that version's `meta.xml`; miss →
     network fetch (validated ≤ latest known from the response, else `InputError`).
   - `version=None` + online → always fetch metadata (rate-limited) to resolve latest,
     then operate cache-first for artifacts of that version.
   - `version=None` + `--offline` → use the **highest version directory** present in the
     cache for this id; none → `FetchError("offline")` with hint to run
     `paperdeck fetch` first.
6. The three rules above are the complete offline/latest contract — no other guessing.

## Acceptance Criteria

- Unit tests with MockTransport + captured real Atom fixtures (one modern id, one
  old-style id, one not-found): field extraction exact; each of the three
  version/offline rules (explicit version cache-first; None+online always fetches;
  None+offline picks highest cached / errors when empty) with transport-call counts
  asserted.
- SEC-AC: Atom payload containing `<!DOCTYPE foo [<!ENTITY x SYSTEM "file:///etc/passwd">]>`
  → `SecurityError("xml-dtd")`, nothing cached.
- Rate limiting is *not* re-tested here (netgate's job), but client uses purpose "arxiv"
  (asserted via mock).

## Validation

`uv run pytest tests/unit/test_arxiv_metadata.py -q`

## Dependencies

01, 02, 08, 09.

## Non-goals

Artifact downloads (12); HTML availability probing (23).

## Design References

DESIGN §8.2–8.3; research/01.
