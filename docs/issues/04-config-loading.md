# Title

[W0] 04 Implement configuration loading and validation

## Summary

Implement `src/paperdeck/config.py`: a frozen pydantic `Settings` model materializing the
TOML schema of DESIGN §7 with precedence CLI > env > file > defaults, strict unknown-key
rejection, and actionable validation errors.

## Context

Every subsystem (netgate, LLM, limits, output budgets) reads from `Settings`. Strictness
here prevents silent misconfiguration (typo'd key silently ignored) and centralizes secret
handling rules.

## Scope

- `Settings` (nested models: `LlmSettings`, `PricingEntry`, `EstimateSettings`,
  `FetchSettings`, `LimitsSettings`, `OutputSettings`) — all frozen.
- `load_settings(config_path: Path | None, cli_overrides: Mapping[str, object])
  -> Settings`. `cli_overrides` keys are a **closed set** of dotted paths:
  `offline`, `llm.base_url`, `llm.model`, `llm.vlm_model`, `llm.max_cost_usd`,
  `llm.cache`; an unknown key is a programming error (raise `ValueError`, not
  `ConfigError` — it can only come from our own CLI code).
- Env-var override table per DESIGN §7.

## Detailed Requirements

1. Defaults exactly as the DESIGN §7 TOML listing (including the two default pricing
   entries and `schema_version = 1`).
2. File location: `platformdirs.user_config_path("paperdeck") / "config.toml"`, overridden
   by `--config` / `PAPERDECK_CONFIG`. Missing file → defaults. Present file: parse with
   stdlib `tomllib`; `schema_version != 1` → `ConfigError` with upgrade hint.
3. Unknown keys anywhere → `ConfigError` naming the full key path
   (`llm.modle: unknown key — did you mean "model"?` — closest-match suggestion via
   `difflib.get_close_matches`).
4. Env overrides (exact set, all optional): `PAPERDECK_OFFLINE=1`,
   `PAPERDECK_LLM_BASE_URL`, `PAPERDECK_LLM_MODEL`, `PAPERDECK_LLM_VLM_MODEL`,
   `PAPERDECK_MAX_COST_USD`. Applied after file, before CLI overrides.
5. Validation rules (explicit ranges — violations raise `ConfigError` listing every
   failure, not just the first): `llm.base_url` http(s) URL; `llm.timeout_s` 1..600;
   `llm.max_retries` 0..10; `llm.max_cost_usd` ≥ 0; pricing values ≥ 0;
   `estimate.chars_per_token` 0.5..20; `estimate.image_tokens_flat` 0..100000;
   `fetch.timeout_s` 1..600; `fetch.max_download_mb` 1..2048; `limits.max_pdf_pages`
   1..10000; `limits.max_input_mb` 1..2048; `limits.max_archive_members` 1..100000;
   `limits.max_archive_total_mb` 1..4096; `limits.embed_warn_mb` 1..1024;
   `limits.embed_hard_max_mb` ≥ `embed_warn_mb` and ≤ 1024; `output.default_dir`
   non-empty string.
6. Secret rule: `Settings` stores only `api_key_env` (the *name*). A method
   `resolve_api_key() -> str | None` reads the env var at call time; `Settings.__repr__`
   and `model_dump` must never include a resolved key (it is never stored).
7. `offline: bool` field present on `Settings` (from env/CLI only; not a file key).

## Acceptance Criteria

- Unit tests: defaults; file+env+CLI precedence (each layer overriding the previous);
  unknown-key suggestion; multi-error aggregation; schema_version guard; URL/range rules.
- SEC-AC: `repr(settings)` and `settings.model_dump_json()` never contain the value of the
  key env var (test sets one).
- mypy strict passes; `Settings` is hashable/frozen.

## Validation

`uv run pytest tests/unit/test_config.py -q`

## Dependencies

01, 02.

## Non-goals

`doctor` checks (50); netgate enforcement (08); cost math (29).

## Design References

DESIGN §7, §17, §20.2 T8; ADR-004 (defaults), ADR-007 §5.
