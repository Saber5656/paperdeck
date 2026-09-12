"""OpenAI-compatible Chat Completions boundary with strict local validation."""
from __future__ import annotations

import base64
import json
import logging
import random
import time
from typing import Any, Callable, Protocol
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, ValidationError

from ..errors import ConfigError, LlmError
from .cache import request_key

log = logging.getLogger(__name__)


class LlmCacheLike(Protocol):
    def get(self, key: str, schema: type[BaseModel], schema_version: str) -> str | None: ...
    def put(self, key: str, response_content: str, usage: dict[str, Any]) -> None: ...


UsageHook = Callable[[str, str, dict[str, Any], bool], None]


def _schema_name(schema: type[BaseModel]) -> str:
    explicit = getattr(schema, "schema_name", None)
    if explicit:
        return str(explicit)
    name = schema.__name__.removesuffix("V1")
    out = []
    for i, char in enumerate(name):
        if char.isupper() and i:
            out.append("_")
        out.append(char.lower())
    return "".join(out)


class LlmClient:
    def __init__(self, settings: Any, netgate: Any, cache: LlmCacheLike | None = None, on_usage: UsageHook | None = None) -> None:
        self.settings = settings
        self.netgate = netgate
        self.cache = cache
        self.on_usage = on_usage
        self._compat_mode = False
        host = urlparse(str(settings.llm.base_url)).hostname or ""
        if not settings.resolve_api_key() and host not in {"localhost", "127.0.0.1", "::1"}:
            raise ConfigError("LLM API key is not configured", f"Set the environment variable {settings.llm.api_key_env}.")

    def _messages_with_images(self, messages: list[dict[str, Any]], images: list[bytes] | None) -> list[dict[str, Any]]:
        copied = [dict(m) for m in messages]
        if not images:
            return copied
        users = [m for m in copied if m.get("role") == "user"]
        if len(users) != 1:
            raise ValueError("images require exactly one user message")
        user = users[0]
        content = user.get("content", "")
        if isinstance(content, list):
            text = " ".join(str(p.get("text", "")) for p in content if isinstance(p, dict) and p.get("type") == "text")
        else:
            text = str(content)
        parts: list[dict[str, Any]] = [{"type": "text", "text": text}]
        parts.extend({"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(img).decode("ascii")}} for img in images)
        user["content"] = parts
        return copied

    def _body(self, model: str, messages: list[dict[str, Any]], schema: type[BaseModel], max_tokens: int, compat: bool) -> dict[str, Any]:
        schema_name = _schema_name(schema)
        if compat:
            instruction = "Return JSON matching this schema exactly: " + json.dumps(schema.model_json_schema(), separators=(",", ":"))
            modified = [dict(m) for m in messages]
            systems = [m for m in modified if m.get("role") == "system"]
            if systems:
                systems[0]["content"] = str(systems[0].get("content", "")) + "\n" + instruction
            else:
                modified.insert(0, {"role": "system", "content": instruction})
            return {"model": model, "messages": modified, "response_format": {"type": "json_object"}, "temperature": 0, "max_tokens": max_tokens}
        return {"model": model, "messages": messages, "response_format": {"type": "json_schema", "json_schema": {"name": schema_name, "schema": schema.model_json_schema(), "strict": True}}, "temperature": 0, "max_tokens": max_tokens}

    def _transport(self, body: dict[str, Any]) -> httpx.Response:
        last: Exception | None = None
        for attempt in range(3):
            try:
                with self.netgate.client("llm") as client:
                    response = client.post(str(self.settings.llm.base_url).rstrip("/") + "/chat/completions", json=body, headers=self._headers(), timeout=self.settings.llm.timeout_s)
                if response.status_code == 400:
                    return response
                if response.status_code == 429 or response.status_code >= 500:
                    retry_after = 0.0
                    try:
                        retry_after = float(response.headers.get("Retry-After", "0"))
                    except ValueError:
                        pass
                    if attempt < 2:
                        time.sleep(max(retry_after, (attempt + 1) ** 2 + random.random()))
                        continue
                response.raise_for_status()
                return response
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last = exc
                if attempt < 2:
                    time.sleep((attempt + 1) ** 2 + random.random())
                    continue
        raise LlmError("LLM transport failed", "Check the LLM endpoint and network connectivity.", "llm-transport") from last

    def _headers(self) -> dict[str, str]:
        key = self.settings.resolve_api_key()
        return {"Authorization": f"Bearer {key}"} if key else {}

    def complete(self, purpose: str, messages: list[dict[str, Any]], schema: type[BaseModel], *, model: str | None = None, images: list[bytes] | None = None, max_tokens: int) -> BaseModel:
        selected = model or self.settings.llm.model
        wire_messages = self._messages_with_images(messages, images)
        version = "v1"
        schema_name = _schema_name(schema)
        cache_key = request_key(selected, wire_messages, schema_name, version)
        if self.cache is not None:
            bind = getattr(self.cache, "bind_model", None)
            if bind:
                bind(cache_key, selected, schema_name, version)
            cached = self.cache.get(cache_key, schema, version)
            if cached is not None:
                try:
                    parsed = schema.model_validate(json.loads(cached))
                    if self.on_usage:
                        self.on_usage(purpose, selected, {"prompt_tokens": 0, "completion_tokens": 0}, True)
                    return parsed
                except (ValueError, TypeError, json.JSONDecodeError, ValidationError):
                    pass
        log.info("llm %s model=%s est_in=%dtok cache=miss", purpose, selected, sum(len(str(m.get("content", ""))) for m in wire_messages) // 4)
        current = [dict(m) for m in wire_messages]
        last_error = ""
        for validation_attempt in range(int(self.settings.llm.max_retries) + 1):
            body = self._body(selected, current, schema, max_tokens, self._compat_mode)
            response = self._transport(body)
            if response.status_code == 400 and not self._compat_mode:
                detail = response.text
                if "response_format" in detail.lower() or "json_schema" in detail.lower():
                    self._compat_mode = True
                    body = self._body(selected, current, schema, max_tokens, True)
                    response = self._transport(body)
            try:
                payload = response.json()
                choice = payload["choices"][0]
                if choice.get("finish_reason") == "length":
                    raise LlmError("LLM response was truncated", "Increase max_tokens and retry.", "llm-truncated")
                content = choice["message"]["content"]
                parsed_json = json.loads(content)
                validated = schema.model_validate(parsed_json)
            except LlmError:
                raise
            except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError, ValidationError) as exc:
                last_error = str(exc).replace("\n", " ")[:200]
                if validation_attempt < int(self.settings.llm.max_retries):
                    current.append({"role": "user", "content": f"Your previous reply failed validation: {last_error}. Reply with corrected JSON only."})
                    continue
                raise LlmError("LLM returned invalid JSON", "Retry the conversion or inspect the model response.", "llm-invalid-json") from exc
            usage = payload.get("usage") or {}
            if self.on_usage:
                self.on_usage(purpose, selected, usage, False)
            if self.cache is not None:
                self.cache.put(cache_key, content, usage)
            return validated
        raise LlmError("LLM returned invalid JSON", "Retry the conversion.", "llm-invalid-json")


__all__ = ["LlmCacheLike", "LlmClient", "UsageHook"]
