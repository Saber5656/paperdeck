# Title

[W1] 08 Implement the network gate (allowlist, offline mode, rate limiter)

## Summary

Implement `src/paperdeck/netgate.py`: the single module through which every HTTP request
flows, enforcing host allowlists, TLS, redirect policy, offline mode, response-size caps,
and the arXiv rate limit, per DESIGN §8.4.

## Context

This is the T7 (SSRF/unexpected hosts) control and the only place `httpx` clients are
constructed. Everything network-touching (arxiv client, LLM client, doctor) builds on it.

## Scope

- `class NetGate:` constructed from `Settings` (`offline`, `fetch.timeout_s`,
  `fetch.max_download_mb`, `llm.base_url`).
- `client(purpose: Literal["arxiv","llm"]) -> httpx.Client` returning configured clients.
- `download(url, dest: Path, purpose) -> Path` streaming helper with cap enforcement.
- `RateLimiter` (min-interval, process-wide via module-level lock).

## Detailed Requirements

1. Allowlists per DESIGN §8.4 table: arxiv = {export.arxiv.org, arxiv.org, www.arxiv.org};
   llm = exactly the host(:port) of `settings.llm.base_url`. Enforced via an
   `httpx.BaseTransport` wrapper that checks `request.url.host` (covers redirects too) and
   raises `SecurityError("host-not-allowed")` — not just by constructing base URLs.
2. Redirects: arxiv client `follow_redirects=True` but each hop re-checked by the
   transport wrapper; llm client `follow_redirects=False`.
3. Offline: when `settings.offline`, any `send` raises `FetchError("offline")` with hint
   `remove --offline or use cached artifacts` (code path exists so callers need no
   special-casing).
4. Rate limiter: arxiv transport sleeps so consecutive requests are ≥ 3.0 s apart
   (monotonic clock; thread-safe; first request immediate). Single connection enforced
   via `httpx.Limits(max_connections=1)` on the arxiv client. llm purpose: no local
   limit.
5. `download()`: streams to `dest.tmp` then renames; aborts with `FetchError("size-cap")`
   once `fetch.max_download_mb` bytes exceeded (measured on the wire, not Content-Length).
   The `User-Agent: paperdeck/<version> (+https://github.com/Saber5656/paperdeck)` header
   is set at **client construction** for the arxiv purpose, so every request (not just
   downloads) carries it.
5b. LLM response cap: the llm transport wrapper aborts any response exceeding 20 MB
   (streamed count) with `FetchError("size-cap")` — DESIGN §8.4 table.
6. TLS verification always on (never expose an insecure toggle). HTTP (non-S) URLs are
   upgraded to HTTPS for the arxiv purpose; llm base_url may be plain http **only when
   host is localhost/127.0.0.1/::1** (local inference servers), else `ConfigError`.
7. CI guard (delivered here as a test): grep test asserting `httpx.` appears only in
   `netgate.py` and tests.

## Acceptance Criteria

- Unit tests with `httpx.MockTransport`: allowlist blocks disallowed host (incl. a redirect
  hop to an off-list host); offline raises before any transport call; rate limiter enforces
  ≥ 3 s between two arxiv sends (mock clock); download size cap aborts mid-stream and
  leaves no partial `dest`; llm 20 MB response cap aborts; UA header present on a plain
  arxiv GET (not only `download()`); arxiv client limits `max_connections=1`.
- SEC-AC: redirect from `export.arxiv.org` → `evil.example.com` raises
  `SecurityError("host-not-allowed")`.
- SEC-AC: `http://api.example.com` as llm base_url → `ConfigError`; `http://localhost:11434`
  accepted.
- Grep test green.

## Validation

`uv run pytest tests/unit/test_netgate.py -q`

## Dependencies

01, 02, 04.

## Non-goals

arXiv endpoint knowledge (11–12); LLM request semantics (27).

## Design References

DESIGN §8.4, §20.2 T6/T7; ADR-007 §3.
