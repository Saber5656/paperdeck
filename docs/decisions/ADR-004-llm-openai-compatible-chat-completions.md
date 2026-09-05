# ADR-004: LLM access via OpenAI-compatible Chat Completions with strict JSON schemas

- Status: Accepted
- Date: 2026-07-08
- Deciders: user (round 2: "OpenAI-compatible API"), Fable (protocol/library choice), informed by docs/research/03

## Context

The `pdf` engine requires an LLM (text structuring) and a VLM (equation → LaTeX best-effort).
User decision: default to OpenAI with `base_url`/`model` swappable to any OpenAI-compatible
server (Ollama, vLLM, OpenRouter, …). The product must never depend on a Claude provider
(task constraint) and must keep secrets handling simple and safe.

## Decision

1. Protocol surface: **`POST {base_url}/chat/completions`** — the most widely cloned
   OpenAI-compatible endpoint. The OpenAI Responses API is not used (poorly cloned by
   compatible servers).
2. HTTP client: **`httpx`** (BSD-3) with a request shape fully owned by paperdeck. The
   `openai` SDK is not a dependency (avoids SDK/API drift and keeps the tree small).
3. Structured output: every call sends `response_format: {"type":"json_schema", ...,
   "strict": true}` derived from versioned JSON Schemas stored in the package. On servers
   rejecting `json_schema`, retry once with `{"type":"json_object"}` + schema embedded in the
   prompt. **All** responses are locally validated against the schema regardless of server
   claims; invalid → bounded retries with error feedback, then hard failure.
4. Defaults (config, never hard-coded): `base_url=https://api.openai.com/v1`,
   `model=gpt-5.6-terra`, `vlm_model=gpt-5.6-terra` (verified current lineup 2026-07-08;
   pricing table is config data because model names/prices drift).
5. API key: read from env var (default `OPENAI_API_KEY`, name configurable via
   `api_key_env`). Keys are never written to config by paperdeck, never logged, never
   embedded in outputs or caches; the cache stores request/response bodies only.
6. Cost accounting: token usage from every response is accumulated; a pre-flight estimator +
   `max_cost_usd` guard aborts before spending beyond budget (DESIGN.md §14.6).
7. Disk cache keyed by `(model, prompt_hash, schema_version)` makes re-runs free and
   quasi-deterministic.

## Consequences

- Positive: provider freedom incl. fully-local inference; minimal deps; schema-constrained
  outputs shrink the prompt-injection blast radius (ADR-007) and make weak-model retries
  mechanical.
- Negative: we own retry/backoff/error taxonomy ourselves (issue-sized, testable against a
  local fake server); features exclusive to the Responses API are unavailable (none needed
  for v1).
