"""Strict TOML, environment and CLI configuration loading."""

from __future__ import annotations

import difflib
import os
import tomllib
from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path
from typing import Any, NoReturn, TypeVar
from urllib.parse import urlparse

from platformdirs import user_config_path
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .errors import ConfigError


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


_T = TypeVar("_T")


class FrozenDict(dict[str, _T]):
    """A JSON-serializable mapping that rejects all in-place mutation."""

    @staticmethod
    def _immutable() -> NoReturn:
        raise TypeError("configuration mappings are immutable")

    def __setitem__(self, key: str, value: _T) -> None:
        self._immutable()

    def __delitem__(self, key: str) -> None:
        self._immutable()

    def clear(self) -> None:
        self._immutable()

    def pop(self, key: str, default: _T | None = None) -> _T | None:  # type: ignore[override]
        self._immutable()

    def popitem(self) -> tuple[str, _T]:
        self._immutable()

    def setdefault(self, key: str, default: _T | None = None) -> _T | None:  # type: ignore[override]
        self._immutable()

    def update(self, other: dict[str, _T] | None = None, **kwargs: _T) -> None:  # type: ignore[override]
        self._immutable()

    def __ior__(self, other: object) -> NoReturn:  # type: ignore[misc]
        self._immutable()


class PricingEntry(FrozenModel):
    input_per_mtok: float = Field(ge=0)
    output_per_mtok: float = Field(ge=0)


class EstimateSettings(FrozenModel):
    image_tokens_flat: int = Field(ge=0, le=100000)
    chars_per_token: float = Field(ge=0.5, le=20)


class LlmSettings(FrozenModel):
    base_url: str
    model: str
    vlm_model: str
    api_key_env: str
    timeout_s: int = Field(ge=1, le=600)
    max_retries: int = Field(ge=0, le=10)
    max_cost_usd: float = Field(ge=0)
    cache: bool
    pricing: dict[str, PricingEntry]
    estimate: EstimateSettings

    @field_validator("pricing", mode="after")
    @classmethod
    def freeze_pricing(cls, value: dict[str, PricingEntry]) -> dict[str, PricingEntry]:
        return FrozenDict(value)

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("base_url must be an http(s) URL")
        return value


class FetchSettings(FrozenModel):
    timeout_s: int = Field(ge=1, le=600)
    max_download_mb: int = Field(ge=1, le=2048)


class LimitsSettings(FrozenModel):
    max_pdf_pages: int = Field(default=500, ge=1, le=10000)
    max_input_mb: int = Field(default=200, ge=1, le=2048)
    max_archive_members: int = Field(default=2000, ge=1, le=100000)
    max_archive_total_mb: int = Field(default=500, ge=1, le=4096)
    embed_warn_mb: int = Field(default=25, ge=1, le=1024)
    embed_hard_max_mb: int = Field(default=50, ge=1, le=1024)

    @model_validator(mode="after")
    def hard_limit_not_below_warning(self) -> LimitsSettings:
        if self.embed_hard_max_mb < self.embed_warn_mb:
            raise ValueError("embed_hard_max_mb must be >= embed_warn_mb")
        return self


class OutputSettings(FrozenModel):
    default_dir: str

    @field_validator("default_dir")
    @classmethod
    def validate_default_dir(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("default_dir must be non-empty")
        return value


class Settings(FrozenModel):
    schema_version: int = 1
    llm: LlmSettings
    fetch: FetchSettings
    limits: LimitsSettings
    output: OutputSettings
    offline: bool = False

    def resolve_api_key(self) -> str | None:
        return os.environ.get(self.llm.api_key_env)

    def __hash__(self) -> int:
        """Hash the canonical public representation, including nested mappings."""
        return hash(self.model_dump_json())


_DEFAULTS: dict[str, Any] = {
    "schema_version": 1,
    "llm": {
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-5.6-terra",
        "vlm_model": "gpt-5.6-terra",
        "api_key_env": "OPENAI_API_KEY",
        "timeout_s": 120,
        "max_retries": 3,
        "max_cost_usd": 1.50,
        "cache": True,
        "pricing": {
            "gpt-5.6-terra": {"input_per_mtok": 2.50, "output_per_mtok": 15.00},
            "gpt-5.6-luna": {"input_per_mtok": 1.00, "output_per_mtok": 6.00},
        },
        "estimate": {"image_tokens_flat": 1100, "chars_per_token": 4.0},
    },
    "fetch": {"timeout_s": 60, "max_download_mb": 200},
    "limits": {
        "max_pdf_pages": 500,
        "max_input_mb": 200,
        "max_archive_members": 2000,
        "max_archive_total_mb": 500,
        "embed_warn_mb": 25,
        "embed_hard_max_mb": 50,
    },
    "output": {"default_dir": "."},
    "offline": False,
}

_KNOWN = {
    "schema_version",
    "llm",
    "fetch",
    "limits",
    "output",
}
_KNOWN_NESTED = {
    "llm": {
        "base_url",
        "model",
        "vlm_model",
        "api_key_env",
        "timeout_s",
        "max_retries",
        "max_cost_usd",
        "cache",
        "pricing",
        "estimate",
    },
    "fetch": {"timeout_s", "max_download_mb"},
    "limits": {
        "max_pdf_pages",
        "max_input_mb",
        "max_archive_members",
        "max_archive_total_mb",
        "embed_warn_mb",
        "embed_hard_max_mb",
    },
    "output": {"default_dir"},
    "estimate": {"image_tokens_flat", "chars_per_token"},
    "llm.estimate": {"image_tokens_flat", "chars_per_token"},
}
_CLI_KEYS = {
    "offline",
    "llm.base_url",
    "llm.model",
    "llm.vlm_model",
    "llm.max_cost_usd",
    "llm.cache",
}


def _config_error(message: str, hint: str = "Fix the configuration and try again.") -> ConfigError:
    return ConfigError(message, hint)


def _check_unknown(data: Mapping[str, Any], prefix: str = "") -> None:
    allowed = _KNOWN if not prefix else _KNOWN_NESTED.get(prefix, set())
    for key, value in data.items():
        if key not in allowed:
            siblings = sorted(allowed)
            suggestion = difflib.get_close_matches(key, siblings, n=1)
            suffix = f' — did you mean "{suggestion[0]}"?' if suggestion else ""
            raise _config_error(f"{prefix + '.' if prefix else ''}{key}: unknown key{suffix}")
        if isinstance(value, Mapping) and key not in {"pricing"}:
            _check_unknown(value, f"{prefix + '.' if prefix else ''}{key}")
        if key == "pricing" and isinstance(value, Mapping):
            for model, entry in value.items():
                if not isinstance(entry, Mapping):
                    raise _config_error(f"llm.pricing.{model}: expected a table")
                for field in entry:
                    if field not in {"input_per_mtok", "output_per_mtok"}:
                        raise _config_error(f"llm.pricing.{model}.{field}: unknown key")


def _merge(base: dict[str, Any], overlay: Mapping[str, Any]) -> None:
    for key, value in overlay.items():
        base_value = base.get(key)
        if isinstance(value, Mapping) and isinstance(base_value, dict):
            _merge(base_value, value)
        else:
            base[key] = value


def _load_file(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as stream:
            loaded = tomllib.load(stream)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise _config_error(f"cannot read config {path}: {exc}") from exc
    _check_unknown(loaded)
    if loaded.get("schema_version", 1) != 1:
        raise _config_error(
            "schema_version must be 1", "Upgrade the config file to schema_version = 1."
        )
    return loaded


def _validation_error(exc: Exception) -> ConfigError:
    details = str(exc)
    return _config_error(f"invalid configuration: {details}")


def load_settings(config_path: Path | None, cli_overrides: Mapping[str, object]) -> Settings:
    """Load settings with CLI > environment > TOML > defaults precedence."""
    unknown_cli = set(cli_overrides) - _CLI_KEYS
    if unknown_cli:
        raise ValueError(f"unknown CLI override: {sorted(unknown_cli)[0]}")
    selected = config_path
    if selected is None:
        env_path = os.environ.get("PAPERDECK_CONFIG")
        selected = (
            Path(env_path) if env_path else Path(user_config_path("paperdeck")) / "config.toml"
        )
    values = {
        "schema_version": 1,
        "llm": deepcopy(_DEFAULTS["llm"]),
        "fetch": dict(_DEFAULTS["fetch"]),
        "limits": dict(_DEFAULTS["limits"]),
        "output": dict(_DEFAULTS["output"]),
        "offline": False,
    }
    if selected.exists():
        _merge(values, _load_file(selected))
    if os.environ.get("PAPERDECK_OFFLINE") == "1":
        values["offline"] = True
    env_map = {
        "PAPERDECK_LLM_BASE_URL": "llm.base_url",
        "PAPERDECK_LLM_MODEL": "llm.model",
        "PAPERDECK_LLM_VLM_MODEL": "llm.vlm_model",
        "PAPERDECK_MAX_COST_USD": "llm.max_cost_usd",
    }
    for env_name, dotted in env_map.items():
        if env_name in os.environ:
            value: object = os.environ[env_name]
            if dotted == "llm.max_cost_usd":
                try:
                    value = float(str(value))
                except ValueError as exc:
                    raise _config_error(f"{env_name} must be a number") from exc
            section, field = dotted.split(".")
            values[section][field] = value
    for dotted, value in cli_overrides.items():
        if dotted == "offline":
            values["offline"] = value
        else:
            section, field = dotted.split(".")
            values[section][field] = value
    try:
        return Settings.model_validate(values)
    except Exception as exc:
        raise _validation_error(exc) from exc
