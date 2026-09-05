# Title

[W4] 27 Implement the LLM client (Chat Completions, strict JSON, retries)

## Summary

Implement `src/paperdeck/llm/client.py`: the OpenAI-compatible Chat Completions client
with strict JSON-schema responses, compat fallback, validation-driven retries, backoff,
and redaction-safe logging, per DESIGN §14.1–14.4.

## Context

The single LLM boundary (ADR-004). Everything the pdf engine asks of a model flows through
this class; its correctness and its security posture (T4, T8) are product-critical.

## Scope

- `class LlmClient:` built from `Settings` + `NetGate` + `cache: LlmCacheLike | None`
  + `on_usage: UsageHook | None`. This issue defines the two protocols so there is no
  dependency on later issues:
  `class LlmCacheLike(Protocol): def get(key, schema, schema_version) -> str | None;
  def put(key, response_content: str, usage: dict) -> None`
  (issue 28 implements it); `UsageHook = Callable[[str purpose, str model, dict usage,
  bool cache_hit], None]` (issue 29's Ledger provides one). Both default to None (no-op).
- `complete(purpose: str, messages: list[dict], schema: type[BaseModel], *, model:
  str | None = None, images: list[bytes] | None = None, max_tokens: int) -> BaseModel`.

## Detailed Requirements

1. Request per DESIGN §14.1: `POST {base_url}/chat/completions` via
   `netgate.client("llm")`; body `{model, messages, response_format:{type:"json_schema",
   json_schema:{name:<schema-name>, schema:<model_json_schema>, strict:true}},
   temperature:0, max_tokens}`. Message-shape rule for images: `complete()` requires
   exactly one user message; its `content` is converted to parts form
   `[{"type":"text","text":…}, {"type":"image_url","image_url":{"url":"data:image/png;
   base64,…"}}, …]` with images appended after the text part in the given order
   (violating the one-user-message precondition is a programming error → `ValueError`).
   Auth header from `settings.resolve_api_key()`; missing key → `ConfigError` **at
   client construction** (fail fast, DESIGN §14.1) unless base_url host is localhost.
2. Compat fallback per DESIGN §14.2: on HTTP 400 whose body mentions `response_format` or
   `json_schema` (case-insensitive), retry once with `{"type":"json_object"}` + one-line
   schema instruction appended to the system message; then set `self._compat_mode=True`
   for subsequent calls.
3. Validation loop per DESIGN §14.3: parse `choices[0].message.content` → JSON →
   `schema.model_validate`; on failure re-ask up to `settings.llm.max_retries` times,
   appending `Your previous reply failed validation: <first error, ≤200 chars>. Reply
   with corrected JSON only.`; exhausted → `LlmError("llm-invalid-json")`.
4. Transport retries: 429/5xx/timeouts → backoff 1s/4s/9s (+ full jitter, honoring
   `Retry-After` when larger), max 3 transport attempts per logical call;
   then `LlmError("llm-transport")`.
5. `finish_reason == "length"` → `LlmError("llm-truncated")` with hint to raise
   max_tokens (no silent truncation).
6. Usage: every response's `usage` object passed to `on_usage(purpose, model, usage,
   cache_hit)`; cache integration points: `cache.get` before transport,
   `cache.put(key, response_content, usage)` after successful validation — the put
   payload is exactly `(key, content, usage)`, never headers or messages.
7. Logging per DESIGN §14.4: INFO line `llm <purpose> model=<m> est_in=<n>tok cache=miss`;
   content only at `-vv` through the issue-03 redaction filter.
8. Timeouts from `settings.llm.timeout_s` per request.

## Acceptance Criteria

- MockTransport tests: happy path returns validated model; strict→compat fallback fires
  exactly once and sticks; validation-retry loop (bad JSON then good) succeeds with 2
  calls; exhaustion raises `llm-invalid-json`; 429 with `Retry-After: 7` waits ≥7s (mock
  clock); truncation raises; images become data-URI parts (request body asserted).
- SEC-AC: captured `-vv` logs of a full call never contain the API key (env set in test);
  a spy `LlmCacheLike` asserts its `put` input contains no `Authorization` value and no
  message content.
- Construction without key + non-localhost base_url → `ConfigError`;
  `http://localhost:11434` without key constructs fine.
- One-user-message precondition violation raises `ValueError`.

## Validation

`uv run pytest tests/unit/test_llm_client.py -q`

## Dependencies

03, 04, 08.

## Non-goals

Disk cache behavior (28), pricing math (29), prompt content (30, 33–35).

## Design References

DESIGN §14.1–14.4, §20.2 T4/T8; ADR-004; research/03.
