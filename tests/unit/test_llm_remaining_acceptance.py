"""Explicit Issue 27-30 acceptance boundaries using local transports only."""

from __future__ import annotations

import json
import logging

import httpx
import pytest

from paperdeck.config import load_settings
from paperdeck.errors import LlmError
from paperdeck.llm.client import LlmClient
from paperdeck.llm.cost import estimate_pdf_run
from paperdeck.llm.schemas import PdfEquationLatexV1, PdfSegmentV1
from paperdeck.llm.schemas.models import PdfBibV1, PdfCiteMapV1
from tests.unit.test_llm_client_local import Gate, settings


def _valid_response(
    *, status: int = 200, content: str = '{"latex":"x","confidence":0.5}'
) -> httpx.Response:
    if status != 200:
        return httpx.Response(status, headers={"Retry-After": "7"})
    return httpx.Response(
        200,
        json={
            "choices": [{"message": {"content": content}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 4, "completion_tokens": 3},
        },
    )


def test_retry_after_waits_seven_seconds_before_success(monkeypatch: pytest.MonkeyPatch) -> None:
    responses = iter([_valid_response(status=429), _valid_response()])
    sleeps: list[float] = []
    monkeypatch.setattr("paperdeck.llm.client.time.sleep", sleeps.append)
    client = LlmClient(settings(), Gate(lambda _request: next(responses)))
    assert (
        client.complete(
            "equation", [{"role": "user", "content": "read"}], PdfEquationLatexV1, max_tokens=20
        ).latex
        == "x"
    )
    assert sleeps and sleeps[0] >= 7


def test_truncation_raises_stable_error_without_validation_retry() -> None:
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "{}"}, "finish_reason": "length"}],
                "usage": {"prompt_tokens": 4, "completion_tokens": 20},
            },
        )

    with pytest.raises(LlmError, match="truncated") as error:
        LlmClient(settings(retries=2), Gate(handler)).complete(
            "equation", [{"role": "user", "content": "read"}], PdfEquationLatexV1, max_tokens=20
        )
    assert error.value.code == "llm-truncated" and calls == 1


def test_invalid_json_exhaustion_calls_each_retry_and_records_usage() -> None:
    calls = 0
    usage: list[dict[str, object]] = []

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "not-json"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 2, "completion_tokens": 5},
            },
        )

    client = LlmClient(
        settings(retries=2), Gate(handler), on_usage=lambda _p, _m, item, _cache: usage.append(item)
    )
    with pytest.raises(LlmError, match="invalid JSON") as error:
        client.complete(
            "equation", [{"role": "user", "content": "read"}], PdfEquationLatexV1, max_tokens=20
        )
    assert error.value.code == "llm-invalid-json"
    assert calls == 3 and len(usage) == 3
    assert all(item["prompt_tokens"] == 2 for item in usage)


def test_verbose_call_and_cache_put_never_expose_key_or_messages(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    secret = "zz-verbose-secret-987654"  # noqa: S105 -- synthetic redaction fixture
    stored: list[tuple[str, str, dict[str, object]]] = []

    class SpyCache:
        def get(self, *_args: object) -> None:
            return None

        def put(self, key: str, response_content: str, usage: dict[str, object]) -> None:
            stored.append((key, response_content, usage))

    monkeypatch.setenv("OPENAI_API_KEY", secret)
    config = load_settings(None, {"llm.base_url": "http://localhost:11434/v1"})
    caplog.set_level(logging.INFO, logger="paperdeck.llm.client")
    LlmClient(config, Gate(lambda _request: _valid_response()), cache=SpyCache()).complete(
        "equation",
        [{"role": "user", "content": "private message"}],
        PdfEquationLatexV1,
        max_tokens=20,
    )
    text = caplog.text
    assert secret not in text and "private message" not in text
    stored_json = json.dumps(stored)
    assert stored and secret not in stored_json and "private message" not in stored_json
    assert all("Authorization" not in json.dumps(item) for item in stored)


def test_canonical_formula_pins_thirty_pages_and_forty_equations() -> None:
    config = load_settings(None, {})
    estimate = estimate_pdf_run(30, 40_000, 40, config)
    assert estimate.calls == 46
    assert estimate.tokens_in == 65_000
    assert estimate.tokens_out == 56_960


def test_each_schema_rejects_top_level_and_nested_extra_keys() -> None:
    canonical = {
        PdfSegmentV1: {"blocks": [], "section_order": []},
        PdfEquationLatexV1: {"latex": "x", "confidence": 0.5},
        PdfBibV1: {"entries": [{"text": "entry", "urls": []}]},
        PdfCiteMapV1: {"mappings": [{"marker": "(A 2020)", "entry_indices": []}]},
    }
    for model, payload in canonical.items():
        with pytest.raises(ValueError):
            model.model_validate({**payload, "unexpected": True})
    with pytest.raises(ValueError):
        PdfSegmentV1.model_validate(
            {"blocks": [{"id": "b", "role": "paragraph", "surprise": 1}], "section_order": []}
        )
    with pytest.raises(ValueError):
        PdfBibV1.model_validate({"entries": [{"text": "x", "urls": [], "surprise": 1}]})
