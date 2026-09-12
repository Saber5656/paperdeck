import json
from types import SimpleNamespace

import httpx
import pytest

from paperdeck.errors import CostLimitError
from paperdeck.llm.client import LlmClient
from paperdeck.llm.schemas import PdfEquationLatexV1, PdfSegmentV1


def settings(retries=1):
    return SimpleNamespace(
        llm=SimpleNamespace(
            base_url="http://localhost:11434/v1",
            model="local",
            vlm_model="local",
            max_retries=retries,
            timeout_s=3,
        ),
        resolve_api_key=lambda: None,
    )


class Gate:
    def __init__(self, handler):
        self.handler = handler

    def client(self, purpose):
        return httpx.Client(transport=httpx.MockTransport(self.handler))


def test_strict_json_and_image_parts() -> None:
    seen = []

    def handler(request):
        seen.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {"content": '{"latex":"x","confidence":0.5}'},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 2, "completion_tokens": 3},
            },
        )

    client = LlmClient(settings(), Gate(handler))
    result = client.complete(
        "equation",
        [{"role": "user", "content": "read"}],
        PdfEquationLatexV1,
        images=[b"png"],
        max_tokens=20,
    )
    assert result.latex == "x"
    assert seen[0]["response_format"]["type"] == "json_schema"
    assert seen[0]["messages"][0]["content"][1]["image_url"]["url"].startswith(
        "data:image/png;base64,"
    )


def test_image_requires_one_user_message() -> None:
    client = LlmClient(settings(), Gate(lambda request: httpx.Response(500)))
    with pytest.raises(ValueError):
        client.complete(
            "equation",
            [{"role": "system", "content": "x"}],
            PdfEquationLatexV1,
            images=[b"x"],
            max_tokens=20,
        )


def test_compatibility_fallback_sticks_after_schema_rejection() -> None:
    bodies = []

    def handler(request):
        body = json.loads(request.content)
        bodies.append(body)
        if len(bodies) == 1:
            return httpx.Response(400, text="response_format json_schema unsupported")
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {"content": '{"latex":"x","confidence":0.5}'},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {},
            },
        )

    client = LlmClient(settings(), Gate(handler))
    client.complete(
        "equation", [{"role": "user", "content": "read"}], PdfEquationLatexV1, max_tokens=20
    )
    client.complete(
        "equation", [{"role": "user", "content": "read2"}], PdfEquationLatexV1, max_tokens=20
    )
    assert bodies[0]["response_format"]["type"] == "json_schema"
    assert bodies[1]["response_format"]["type"] == "json_object"
    assert bodies[2]["response_format"]["type"] == "json_object"


def test_wire_schema_requires_optional_properties_as_nullable() -> None:
    client = LlmClient(settings(), Gate(lambda request: httpx.Response(500)))
    wire = client._body("local", [], PdfSegmentV1, 20, False)
    schema = wire["response_format"]["json_schema"]["schema"]
    assert set(schema["required"]) == set(schema["properties"])
    # Nullable values remain nullable, while their property is required.
    level_schema = schema["$defs"]["SegmentBlock"]["properties"]["level"]
    assert any(option.get("type") == "null" for option in level_schema["anyOf"])


def test_invalid_json_retry_is_recorded_before_validation() -> None:
    calls = 0
    usage: list[dict[str, object]] = []

    def handler(request):
        nonlocal calls
        calls += 1
        content = "not-json" if calls == 1 else '{"latex":"x","confidence":0.5}'
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": content}, "finish_reason": "stop"}]},
        )

    client = LlmClient(
        settings(retries=1), Gate(handler), on_usage=lambda p, m, u, c: usage.append(u)
    )
    result = client.complete(
        "equation", [{"role": "user", "content": "read"}], PdfEquationLatexV1, max_tokens=20
    )
    assert result.latex == "x"
    assert calls == 2
    assert len(usage) == 2
    assert all(int(item["completion_tokens"]) > 0 for item in usage)


def test_zero_cost_budget_rejects_before_transport() -> None:
    from paperdeck.config import load_settings
    from paperdeck.llm.cost import Ledger

    config = load_settings(
        None,
        {"llm.base_url": "http://localhost:11434/v1", "llm.max_cost_usd": "0"},
    )
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={})

    client = LlmClient(config, Gate(handler), on_usage=lambda *args: None)
    with pytest.raises(CostLimitError):
        client.complete(
            "equation", [{"role": "user", "content": "read"}], PdfEquationLatexV1,
            max_tokens=20, ledger=Ledger(config)
        )
    assert calls == 0
