# Research: PDF extraction stack and LLM/VLM facts

Date: 2026-07-08 (verified via web on this date)
Status: informs ADR-004 (LLM access), DESIGN.md §13–14

## PDF extraction library

**pypdfium2** (Python bindings to PDFium, Chromium's PDF engine):

- License: dual **Apache-2.0 OR BSD-3-Clause** — satisfies the permissive-only dependency
  policy (ADR-005). PyMuPDF is excluded (AGPL-3.0).
- Capabilities verified: character-level bounding boxes (`get_charbox`), bounded/full text
  extraction, page rendering to bitmaps (PIL interop) at arbitrary scale — covers all three
  PDF-engine needs: text+layout input for the LLM, equation-region cropping, and figure
  extraction.
- Maintained bindings with prebuilt wheels for macOS/Linux/Windows (no compiler needed).

Alternatives considered: `pdfplumber`/`pdfminer.six` (MIT; good text+layout, **no rendering**
— would force a second library for crops), `pypdf` (BSD; no layout geometry, no rendering).
pypdfium2 alone covers everything → fewer deps.

## Local ML document-AI tools (not adopted)

| Tool | Why not |
|---|---|
| Nougat (Meta) | Local transformer OCR for academic PDFs; heavyweight local ML runtime (GPU-oriented), model download, and quality ceiling below current hosted VLMs; contradicts the "LLM-API-first" decision |
| marker | PDF→Markdown pipeline with restrictive/commercial licensing terms for parts of the stack; also a heavy local ML runtime |
| GROBID | Java service, excellent for reference/metadata extraction, but adds a JVM service dependency; the LLM engine covers this need in v1 |

These stay documented as v2 candidates for an offline PDF path.

## LLM facts (OpenAI, verified 2026-07-08)

Current OpenAI API lineup (official model page):

| Model ID | Positioning | Price (in/out per MTok) | Vision | Context |
|---|---|---|---|---|
| `gpt-5.6-sol` | Frontier, complex work | $5 / $30 | yes | 1.05M |
| `gpt-5.6-terra` | Balanced intelligence/cost | $2.50 / $15 | yes | 1.05M |
| `gpt-5.6-luna` | Cost-sensitive, high volume | $1 / $6 | yes | 1.05M |

- All current models accept text+image input and support strict JSON ("structured outputs").
- **Default model for paperdeck: `gpt-5.6-terra`** for both text structuring and equation VLM
  reads; `gpt-5.6-luna` documented as the budget alternative. Defaults live in config, never
  hard-coded in call sites.
- Pricing table must be config data (`[llm.pricing]`), because prices and model names change
  faster than releases; the cost estimator reads config, not constants.

## OpenAI-compatible surface

To honor the "OpenAI-compatible endpoint" decision (swap `base_url`/`model` to use Ollama,
vLLM, OpenRouter, etc.), paperdeck targets the **Chat Completions API**
(`POST {base_url}/chat/completions`) with `response_format: {type: "json_schema", strict}` —
the most widely cloned surface. The newer OpenAI Responses API is NOT used: compatible servers
clone it far less consistently. Implementation uses plain `httpx` (BSD-3) rather than the
`openai` SDK to keep the request shape fully under our control and the dependency tree small.
Fallback behavior when a server rejects `json_schema` (older compatibles): retry with
`response_format: {type: "json_object"}` + schema-in-prompt + local JSON-Schema validation.

## Impact on paperdeck design

1. Single extraction dependency: `pypdfium2` (text, char boxes, page/figure/equation
   rendering).
2. LLM client is a thin `httpx` wrapper over Chat Completions with strict-JSON enforcement,
   retries, timeouts, cost accounting, and local schema validation as a backstop.
3. Defaults: `base_url=https://api.openai.com/v1`, `model=gpt-5.6-terra`; all overridable.
4. Every LLM interaction must be reproducible-ish: request/response cached on disk keyed by
   `(model, prompt_hash, schema_version)` so re-runs are free and deterministic.

## Sources

- [pypdfium2 project (license, capabilities)](https://github.com/pypdfium2-team/pypdfium2)
- [pypdfium2 char bounding boxes discussion](https://github.com/pypdfium2-team/pypdfium2/issues/204)
- [OpenAI API models (official)](https://developers.openai.com/api/docs/models)
- [OpenAI model release notes](https://help.openai.com/en/articles/9624314-model-release-notes)
