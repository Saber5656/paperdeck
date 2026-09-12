import json

import httpx
import pytest

from paperdeck.config import PricingEntry, load_settings
from paperdeck.input.cache import CacheManager
from paperdeck.llm.cache import LlmCache, request_key
from paperdeck.llm.client import LlmClient
from paperdeck.llm.cost import CostEstimate, Ledger, estimate_pdf_run, format_estimate
from paperdeck.llm.schemas import PdfEquationLatexV1
from tests.unit.test_llm_client_local import Gate


def test_every_request_identity_field_affects_cache_key():
    request = ("local", [{"role": "user", "content": "text"}], "equation", "v1")
    original = request_key(*request)
    changes = [
        ("other", request[1], "equation", "v1"),
        ("local", [{"role": "user", "content": "changed"}], "equation", "v1"),
        ("local", request[1], "segment", "v1"),
        ("local", request[1], "equation", "v2"),
        ("local", [{"role": "user", "content": "data:image/png;base64,eA=="}], "equation", "v1"),
    ]
    assert len({request_key(*changed) for changed in changes} | {original}) == 6


def test_stale_schema_and_disabled_cache_write_through(tmp_path):
    manager = CacheManager(tmp_path / "paperdeck")
    cache = LlmCache(manager)
    key = request_key("local", [], "equation", "v1")
    cache.bind_model(key, "local")
    cache.put(key, '{"latex":"x","confidence":0.5}', {}, schema_version="v0")
    path = manager.llm_dir("local") / f"{key}.json"
    assert cache.get(key, PdfEquationLatexV1, "v1") is None
    assert not path.exists()
    cache.enabled = False
    cache.put(key, '{"latex":"y","confidence":0.6}', {})
    assert cache.get(key, PdfEquationLatexV1, "v1") is None
    cache.enabled = True
    assert json.loads(cache.get(key, PdfEquationLatexV1, "v1"))["latex"] == "y"


def test_real_client_cache_replay_has_no_transport_or_billable_usage(tmp_path):
    requests, usages = [], []
    settings = load_settings(None, {"llm.base_url": "http://localhost:11434/v1"})

    def handler(request):
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {"content": '{"latex":"x","confidence":0.5}'},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            },
        )

    cache = LlmCache(CacheManager(tmp_path / "paperdeck"))
    client = LlmClient(
        settings, Gate(handler), cache=cache, on_usage=lambda *args: usages.append(args)
    )
    messages = [{"role": "user", "content": "private paper text"}]
    first = client.complete("equation", messages, PdfEquationLatexV1, max_tokens=20)
    second = client.complete("equation", messages, PdfEquationLatexV1, max_tokens=20)
    assert first == second and len(requests) == 1 and usages[-1][-1] is True
    stored = next((tmp_path / "paperdeck").rglob("*.json")).read_text()
    assert "private paper text" not in stored and "Authorization" not in stored
    ledger = Ledger(settings)
    for item in usages:
        ledger.record(*item)
    assert ledger.cache_hits == 1 and ledger.token_count() == 15
    assert ledger.spent_usd() == pytest.approx(0.0001)
    assert ledger.records[-1]["usage_original"] == {"prompt_tokens": 10, "completion_tokens": 5}


def test_cost_estimate_uses_the_distinct_vision_model_price():
    settings = load_settings(None, {})
    settings = settings.model_copy(
        update={
            "llm": settings.llm.model_copy(
                update={
                    "vlm_model": "vision",
                    "pricing": {
                        settings.llm.model: PricingEntry(input_per_mtok=2, output_per_mtok=4),
                        "vision": PricingEntry(input_per_mtok=10, output_per_mtok=20),
                    },
                }
            )
        }
    )
    estimate = estimate_pdf_run(8, 4000, 2, settings)
    assert (estimate.calls, estimate.tokens_in, estimate.tokens_out) == (5, 5100, 4548)
    assert estimate.usd == pytest.approx((2500 * 2 + 2500 * 4 + 2600 * 10 + 2048 * 20) / 1e6)
    assert Ledger(settings).call_estimate("equation") == pytest.approx(0.03348)


def test_unknown_vision_price_keeps_estimate_unknown():
    settings = load_settings(None, {})
    settings = settings.model_copy(
        update={"llm": settings.llm.model_copy(update={"vlm_model": "unknown"})}
    )
    assert estimate_pdf_run(8, 4000, 2, settings).usd is None


def test_unknown_prices_are_never_reported_as_actual_dollars(caplog):
    ledger = Ledger(load_settings(None, {}))
    ledger.record("equation", "unpriced", {"prompt_tokens": 2_000_000}, False)
    assert ledger.spent_usd() is None
    assert "2,000,000" in caplog.text
    # Reservations still use conservative prices, including for unknown models.
    assert not ledger.remaining_allows(0.01)


def test_unknown_price_cache_hit_keeps_actual_zero():
    ledger = Ledger(load_settings(None, {}))
    ledger.record("equation", "unpriced", {"prompt_tokens": 2_000_000}, True)
    assert ledger.spent_usd() == pytest.approx(0)
    assert ledger.token_count() == 0


def test_confirmation_text_is_stable():
    estimate = CostEstimate(23, 310000, 45000, 0.42, ["rough estimate"], "example")
    assert format_estimate(estimate) == (
        "LLM cost estimate: ~$0.42 (23 calls, ~310k in / ~45k out tokens, model example)\n"
        "rough estimate\nProceed? [y/N]"
    )
