import httpx
import pytest

from paperdeck.errors import LlmError
from paperdeck.llm.client import LlmClient
from paperdeck.llm.schemas import PdfEquationLatexV1
from tests.unit.test_llm_client_local import Gate, settings


@pytest.mark.parametrize("status", [401, 403, 404, 429, 503])
def test_terminal_http_errors_have_a_stable_boundary_error(status, monkeypatch):
    calls = []
    monkeypatch.setattr("paperdeck.llm.client.time.sleep", lambda _: None)

    def fail(request):
        calls.append(request)
        return httpx.Response(status, text="private provider response")

    with pytest.raises(LlmError) as error:
        LlmClient(settings(), Gate(fail)).complete(
            "equation", [{"role": "user", "content": "x"}], PdfEquationLatexV1, max_tokens=20
        )
    assert error.value.code == "llm-transport"
    assert "private provider response" not in str(error.value)
    assert len(calls) == (3 if status in {429, 503} else 1)
