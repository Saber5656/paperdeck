# Title

[W4] 28 Implement the LLM disk cache

## Summary

Implement `src/paperdeck/llm/cache.py`: content-addressed caching of LLM responses under
the cache tree, keyed by the full request identity, per DESIGN §14.5.

## Context

Makes re-runs free and quasi-deterministic (same input → same pipeline result without
network), and is the substrate for FakeLLM-independent development iteration.

## Scope

- `class LlmCache(cache: CacheManager, enabled: bool)` implementing issue 27's
  `LlmCacheLike` protocol.
- `key(model, messages, schema_name, schema_version) -> str` (sha256 of canonical JSON).
- `get(key, schema: type[BaseModel], schema_version: str) -> str | None` (validated
  response content or None), `put(key, response_content: str, usage: dict)`.
- Integration point in `LlmClient.complete` (`--no-llm-cache` semantics).

## Detailed Requirements

1. Canonical JSON for keying: `json.dumps(payload, sort_keys=True, separators=(",",":"),
   ensure_ascii=False)` over `{model, messages, schema_name, schema_version}` — messages
   include image data-URIs (so identical images hit).
2. Value file `llm/<model-sanitized>/<key>.json` with exactly the DESIGN §14.5 fields:
   `{"schema_name":…, "schema_version":…, "created_at":…, "response_content":…,
   "usage":…}` — **never** request headers, never the messages themselves (privacy:
   prompts contain paper text; the response content is enough for replay; the key alone
   links them). File mode 0600; directory naming via `CacheManager.llm_dir` (issue 09
   owns model-name sanitization).
3. `--no-llm-cache`: `get` disabled, `put` still active (DESIGN §6.1 flag table).
4. Cache hits: `get` validates the stored `response_content` against the passed schema
   (and compares `schema_version`) before returning; mismatch/parse failure → treat as
   miss, delete the stale file, log INFO `llm-cache-stale`.
5. Hit accounting: ledger callback receives `cache_hit=True` with usage zeroed and
   original usage attached as `usage_original` (report shows saved cost, issue 29/48).
6. (Model-name path sanitization is issue 09's `llm_dir` — not re-implemented here.)

## Acceptance Criteria

- Unit tests: identical logical requests hit (different key order in dicts still hits —
  canonicalization proven); any field change misses; stale-schema overwrite path;
  `--no-llm-cache` read-bypass/write-through; 0600 mode asserted.
- SEC-AC: value file for a call with `Authorization` header present contains neither the
  header nor the messages (file content scanned in test).
- Round-trip with `LlmClient` (MockTransport): second identical call performs zero
  transport requests.

## Validation

`uv run pytest tests/unit/test_llm_cache.py -q`

## Dependencies

01, 09, 27.

## Non-goals

Cost math (29); cache CLI (49 covers arxiv artifacts; llm cache clearing rides
`cache clear`).

## Design References

DESIGN §14.5, §8.5 (tree), §20.2 T8/T12.
