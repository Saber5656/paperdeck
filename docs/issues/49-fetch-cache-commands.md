# Title

[W6] 49 Implement the `fetch` and `cache` commands

## Summary

Implement `paperdeck fetch` (download artifacts into cache without converting) and
`paperdeck cache path|ls|clear`, per DESIGN §6.2–6.3.

## Context

Supports offline workflows (`fetch` on a connected machine, `convert --offline` later)
and cache hygiene.

## Scope

- `fetch ARXIV_ID [--kind source|pdf|html|all]` (default `all`).
- `cache path`, `cache ls`, `cache clear [ARXIV_ID] [--yes]`.

## Detailed Requirements

1. `fetch`: input restricted to arXiv ids/URLs (resolver kind `arxiv`; local path →
   `UsageError`). Per kind: `source` → `eprint()`, `pdf` → `pdf()`, `html` →
   `html_page()` (12). `all` fetches the three best-effort: missing HTML is reported
   (`html: not available`) but exits 0; network errors on an explicitly requested single
   kind exit 4. Prints one line per artifact: `<kind>: <cache-path>` (or status).
   Metadata always fetched first (version resolution).
2. `cache path`: prints the cache root (one line, stdout).
3. `cache ls`: table (plain text, aligned): `ID  VERSION  KINDS  SIZE` using
   `CacheManager.entries()`; sizes human-readable (KiB/MiB); llm cache summarized as one
   final row `llm-cache  -  <n> entries  <size>`.
4. `cache clear`: with id → that entry; without → everything incl. llm cache; requires
   confirmation (`click.confirm`) unless `--yes`; prints freed bytes. Non-TTY without
   `--yes` → decline (exit 2 usage hint).
5. All commands honor `--offline` where meaningful (`fetch` under offline → exit 4
   `offline`).
6. Stdout discipline: parseable output only (paths/table); progress to stderr.

## Acceptance Criteria

- E2E with MockTransport-backed client injected via test seam: `fetch --kind all` on a
  fixture id populates the exact cache layout of §8.5; missing-html tolerance; single-kind
  network failure exit 4; repeated fetch = cache hits (zero transport calls second time).
- `cache ls` golden output on a seeded cache (byte-exact fixture comparison);
  `clear <id>` removes only that entry; `clear --yes` empties root (guard from issue 09
  still enforced); freed-bytes line matches.
- Non-TTY clear without `--yes` declines safely (subprocess).
- SEC-AC: `paperdeck fetch '../../etc/passwd'` and other non-arXiv inputs are rejected
  by the resolver grammar with exit 2/3 and zero network calls; fetched artifacts land
  only under the cache root (no user-controllable path component beyond the validated
  id — asserted on the produced tree).

## Validation

`uv run pytest tests/e2e/test_fetch_cache_commands.py -q`

## Dependencies

07, 09, 11, 12.

## Non-goals

Converting (48); cache eviction policies/TTL (v2).

## Design References

DESIGN §6.2–6.3, §8.5.
