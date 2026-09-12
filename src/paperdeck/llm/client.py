"""OpenAI-compatible Chat Completions boundary with strict local validation."""

from __future__ import annotations

import base64
import copy
import json
import logging
import secrets
import time
from collections.abc import Callable
from typing import Any, Protocol
from urllib.parse import urlparse

from pydantic import BaseModel, ValidationError

from ..errors import ConfigError, LlmError
from ..netgate import HttpResponse, TimeoutException, TransportError
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


def _strict_wire_schema(schema: type[BaseModel]) -> dict[str, Any]:
    """Make a Pydantic schema valid for the strict Chat Completions dialect.

    OpenAI's strict mode requires every object property to be listed in
    ``required``. Pydantic expresses optional values with a nullable ``anyOf``;
    retaining that shape makes the field required while allowing ``null``.
    """
    result = copy.deepcopy(schema.model_json_schema())

    def visit(node: Any) -> None:
        if not isinstance(node, dict):
            if isinstance(node, list):
                for item in node:
                    visit(item)
            return
        if node.get("type") == "object" or "properties" in node:
            props = node.get("properties", {})
            if isinstance(props, dict):
                node["required"] = list(props)
                node["additionalProperties"] = False
                for prop in props.values():
                    visit(prop)
        for key in ("$defs", "definitions", "items", "anyOf", "oneOf", "allOf"):
            visit(node.get(key))

    visit(result)
    return result


class LlmClient:
    def __init__(
        self,
        settings: Any,
        netgate: Any,
        cache: LlmCacheLike | None = None,
        on_usage: UsageHook | None = None,
    ) -> None:
        self.settings = settings
        self.netgate = netgate
        self.cache = cache
        self.on_usage = on_usage
        self._compat_mode = False
        host = urlparse(str(settings.llm.base_url)).hostname or ""
        if not settings.resolve_api_key() and host not in {"localhost", "127.0.0.1", "::1"}:
            raise ConfigError(
                "LLM API key is not configured",
                f"Set the environment variable {settings.llm.api_key_env}.",
            )

    def _messages_with_images(
        self, messages: list[dict[str, Any]], images: list[bytes] | None
    ) -> list[dict[str, Any]]:
        copied = copy.deepcopy(messages)
        if not images:
            return copied
        users = [m for m in copied if m.get("role") == "user"]
        if len(users) != 1:
            raise ValueError("images require exactly one user message")
        user = users[0]
        content = user.get("content", "")
        if isinstance(content, list):
            text = " ".join(
                str(p.get("text", ""))
                for p in content
                if isinstance(p, dict) and p.get("type") == "text"
            )
        else:
            text = str(content)
        parts: list[dict[str, Any]] = [{"type": "text", "text": text}]
        parts.extend(
            {
                "type": "image_url",
                "image_url": {
                    "url": "data:image/png;base64," + base64.b64encode(img).decode("ascii")
                },
            }
            for img in images
        )
        user["content"] = parts
        return copied

    def _body(
        self,
        model: str,
        messages: list[dict[str, Any]],
        schema: type[BaseModel],
        max_tokens: int,
        compat: bool,
    ) -> dict[str, Any]:
        schema_name = _schema_name(schema)
        if compat:
            instruction = "Return JSON matching this schema exactly: " + json.dumps(
                _strict_wire_schema(schema), separators=(",", ":")
            )
            modified = [dict(m) for m in messages]
            systems = [m for m in modified if m.get("role") == "system"]
            if systems:
                systems[0]["content"] = str(systems[0].get("content", "")) + "\n" + instruction
            else:
                modified.insert(0, {"role": "system", "content": instruction})
            return {
                "model": model,
                "messages": modified,
                "response_format": {"type": "json_object"},
                "temperature": 0,
                "max_tokens": max_tokens,
            }
        return {
            "model": model,
            "messages": messages,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": schema_name,
                    "schema": _strict_wire_schema(schema),
                    "strict": True,
                },
            },
            "temperature": 0,
            "max_tokens": max_tokens,
        }

    def _transport(self, body: dict[str, Any]) -> HttpResponse:
        last: Exception | None = None
        for attempt in range(3):
            try:
                client = self.netgate.client("llm")
                response = client.post(
                    str(self.settings.llm.base_url).rstrip("/") + "/chat/completions",
                    json=body,
                    headers=self._headers(),
                    timeout=self.settings.llm.timeout_s,
                )
                if response.status_code == 400:
                    return response  # type: ignore[no-any-return]
                if response.status_code == 429 or response.status_code >= 500:
                    retry_after = 0.0
                    try:
                        retry_after = float(response.headers.get("Retry-After", "0"))
                    except ValueError:
                        pass
                    if attempt < 2:
                        delay = (attempt + 1) ** 2 + secrets.SystemRandom().random()
                        time.sleep(max(retry_after, delay))
                        continue
                response.raise_for_status()
                return response  # type: ignore[no-any-return]
            except (TimeoutException, TransportError) as exc:
                last = exc
                if attempt < 2:
                    time.sleep((attempt + 1) ** 2 + secrets.SystemRandom().random())
                    continue
        raise LlmError(
            "LLM transport failed",
            "Check the LLM endpoint and network connectivity.",
            "llm-transport",
        ) from last

    def _headers(self) -> dict[str, str]:
        key = self.settings.resolve_api_key()
        return {"Authorization": f"Bearer {key}"} if key else {}

    def complete(
        self,
        purpose: str,
        messages: list[dict[str, Any]],
        schema: type[BaseModel],
        *,
        model: str | None = None,
        images: list[bytes] | None = None,
        max_tokens: int,
        ledger: Any = None,
    ) -> BaseModel:
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
                        self.on_usage(
                            purpose, selected, {"prompt_tokens": 0, "completion_tokens": 0}, True
                        )
                    return parsed
                except (ValueError, TypeError, json.JSONDecodeError, ValidationError):
                    pass
        log.info(
            "llm %s model=%s est_in=%dtok cache=miss",
            purpose,
            selected,
            sum(len(str(m.get("content", ""))) for m in wire_messages) // 4,
        )
        current = copy.deepcopy(wire_messages)
        last_error = ""
        for validation_attempt in range(int(self.settings.llm.max_retries) + 1):
            body = self._body(selected, current, schema, max_tokens, self._compat_mode)
            input_chars = sum(len(str(m.get("content", ""))) for m in current)
            image_tokens = len(images or []) * int(
                getattr(getattr(self.settings.llm, "estimate", None), "image_tokens_flat", 1100)
            )
            estimated_in = max(1, input_chars // 4 + image_tokens)
            # _transport itself has up to three HTTP retries. Reserve for all of
            # them so a retry can never bypass the hard cap.
            reservation = 0.0
            reservation_tokens = (estimated_in + max_tokens) * 3
            if ledger is not None:
                reservation = ledger.reserve_call(
                    selected, tokens_in=estimated_in * 3, tokens_out=max_tokens * 3
                )
            response = self._transport(body)
            if ledger is not None:
                ledger.release_call(reservation, tokens=reservation_tokens)
            # Account for this physical request before parsing or validating it:
            # malformed JSON and truncated replies are billable too. When a
            # provider omits usage, the conservative request estimate is used.
            estimated_usage = {
                "prompt_tokens": estimated_in,
                "completion_tokens": max_tokens,
                "estimated": True,
            }
            usage_for_record: dict[str, Any] = estimated_usage
            try:
                candidate = response.json()
                if isinstance(candidate, dict) and isinstance(candidate.get("usage"), dict):
                    candidate_usage = dict(candidate["usage"])
                    if candidate_usage.get("prompt_tokens") or candidate_usage.get(
                        "completion_tokens"
                    ):
                        usage_for_record = candidate_usage
            except (ValueError, TypeError):
                pass
            if self.on_usage:
                self.on_usage(purpose, selected, usage_for_record, False)
            if response.status_code == 400 and not self._compat_mode:
                detail = response.text
                if "response_format" in detail.lower() or "json_schema" in detail.lower():
                    self._compat_mode = True
                    body = self._body(selected, current, schema, max_tokens, True)
                    if ledger is not None:
                        reservation = ledger.reserve_call(
                            selected, tokens_in=estimated_in * 3, tokens_out=max_tokens * 3
                        )
                    response = self._transport(body)
                    if ledger is not None:
                        ledger.release_call(reservation, tokens=reservation_tokens)
                    usage_for_record = dict(estimated_usage)
                    try:
                        candidate = response.json()
                        if isinstance(candidate, dict) and isinstance(candidate.get("usage"), dict):
                            candidate_usage = dict(candidate["usage"])
                            if candidate_usage.get("prompt_tokens") or candidate_usage.get(
                                "completion_tokens"
                            ):
                                usage_for_record = candidate_usage
                    except (ValueError, TypeError):
                        pass
                    if self.on_usage:
                        self.on_usage(purpose, selected, usage_for_record, False)
            try:
                payload = response.json()
                choice = payload["choices"][0]
                if choice.get("finish_reason") == "length":
                    raise LlmError(
                        "LLM response was truncated",
                        "Increase max_tokens and retry.",
                        "llm-truncated",
                    )
                content = choice["message"]["content"]
                parsed_json = json.loads(content)
                validated = schema.model_validate(parsed_json)
            except LlmError:
                raise
            except (
                KeyError,
                IndexError,
                TypeError,
                ValueError,
                json.JSONDecodeError,
                ValidationError,
            ) as exc:
                last_error = str(exc).replace("\n", " ")[:200]
                if validation_attempt < int(self.settings.llm.max_retries):
                    current.append(
                        {
                            "role": "user",
                            "content": (
                                f"Your previous reply failed validation: {last_error}. "
                                "Reply with corrected JSON only."
                            ),
                        }
                    )
                    continue
                raise LlmError(
                    "LLM returned invalid JSON",
                    "Retry the conversion or inspect the model response.",
                    "llm-invalid-json",
                ) from exc
            if self.cache is not None:
                self.cache.put(cache_key, content, usage_for_record)
            return validated
        raise LlmError("LLM returned invalid JSON", "Retry the conversion.", "llm-invalid-json")


__all__ = ["LlmCacheLike", "LlmClient", "UsageHook"]
