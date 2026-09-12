import httpx

from paperdeck.input.cache import CacheManager
from paperdeck.llm.cache import LlmCache
from paperdeck.llm.client import LlmClient
from paperdeck.llm.schemas import PdfEquationLatexV1
from tests.unit.test_llm_client_local import Gate, settings


def test_provider_changes_do_not_replay_another_endpoint_cache(tmp_path):
    cache = LlmCache(CacheManager(tmp_path / "paperdeck"))
    calls = []

    def respond(request):
        calls.append(str(request.url))
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {"content": '{"latex":"x","confidence":0.5}'},
                        "finish_reason": "stop",
                    }
                ]
            },
        )

    for base in [
        "http://localhost:1111/v1",
        "http://localhost:2222/v1",
        "http://localhost:1111/v1/",
    ]:
        config = settings()
        config.llm.base_url = base
        LlmClient(config, Gate(respond), cache=cache).complete(
            "equation", [{"role": "user", "content": "x"}], PdfEquationLatexV1, max_tokens=20
        )
    assert len(calls) == 2
