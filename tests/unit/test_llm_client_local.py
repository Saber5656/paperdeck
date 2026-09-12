import json
from types import SimpleNamespace

import httpx
import pytest

from paperdeck.llm.client import LlmClient
from paperdeck.llm.schemas import PdfEquationLatexV1


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
