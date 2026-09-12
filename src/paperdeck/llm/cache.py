"""Content addressed, privacy-preserving cache for validated LLM responses."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

log = logging.getLogger(__name__)


def request_key(
    model: str, messages: list[dict[str, Any]], schema_name: str, schema_version: str
) -> str:
    payload = {
        "model": model,
        "messages": messages,
        "schema_name": schema_name,
        "schema_version": schema_version,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(raw).hexdigest()


key = request_key


class LlmCache:
    def __init__(self, cache: Any, enabled: bool = True) -> None:
        self.cache = cache
        self.enabled = enabled
        self._identity_by_key: dict[str, tuple[str, str, str]] = {}

    def bind_model(
        self, cache_key: str, model: str, schema_name: str = "", schema_version: str = "v1"
    ) -> None:
        self._identity_by_key[cache_key] = (model, schema_name, schema_version)

    def _path(self, cache_key: str, model: str | None = None) -> Path:
        name = model or "unknown"
        directory = Path(self.cache.llm_dir(name))
        directory.mkdir(parents=True, exist_ok=True)
        try:
            directory.chmod(0o700)
        except OSError:
            pass
        return directory / f"{cache_key}.json"

    def get(
        self,
        cache_key: str,
        schema: type[BaseModel],
        schema_version: str,
        *,
        model: str | None = None,
    ) -> str | None:
        if not self.enabled:
            return None
        identity = self._identity_by_key.get(cache_key)
        model = model or (identity[0] if identity else None)
        path = self._path(cache_key, model)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if payload.get("schema_version") != schema_version:
                raise ValueError("schema version mismatch")
            content = payload["response_content"]
            schema.model_validate(json.loads(content))
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError, ValidationError):
            if path.exists():
                try:
                    path.unlink()
                except OSError:
                    pass
            log.info("llm-cache-stale key=%s", cache_key)
            return None
        return str(content)

    def put(
        self,
        cache_key: str,
        response_content: str,
        usage: dict[str, Any],
        *,
        model: str | None = None,
        schema_name: str = "",
        schema_version: str = "v1",
    ) -> None:
        identity = self._identity_by_key.get(cache_key)
        model = model or (identity[0] if identity else None)
        if identity:
            schema_name = schema_name or identity[1]
            schema_version = schema_version or identity[2]
        path = self._path(cache_key, model)
        payload = {
            "schema_name": schema_name,
            "schema_version": schema_version,
            "created_at": datetime.now(UTC).isoformat(),
            "response_content": response_content,
            "usage": usage,
        }
        directory = path.parent
        fd, temp_name = tempfile.mkstemp(prefix=f".{cache_key}.", suffix=".tmp", dir=directory)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                stream.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(temp_name, 0o600)
            os.replace(temp_name, path)
        finally:
            try:
                os.unlink(temp_name)
            except FileNotFoundError:
                pass


__all__ = ["LlmCache", "request_key", "key"]
