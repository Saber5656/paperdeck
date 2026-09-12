from types import SimpleNamespace

import pytest

from paperdeck.errors import CostLimitError
from paperdeck.llm.cost import Ledger, estimate_pdf_run, format_estimate


def settings(model="gpt-5.6-terra", limit=1.5):
    pricing = {model: SimpleNamespace(input_per_mtok=2.5, output_per_mtok=15.0)}
    return SimpleNamespace(
        llm=SimpleNamespace(
            model=model,
            max_cost_usd=limit,
            pricing=pricing,
            estimate=SimpleNamespace(chars_per_token=4, image_tokens_flat=1100),
        )
    )


def test_estimate_and_ledger_budget() -> None:
    est = estimate_pdf_run(30, 40000, 4, settings())
    assert est.calls == 4 + 4 + 2
    assert "±50%" in format_estimate(est)
    ledger = Ledger(settings(limit=0.001))
    ledger.record(
        "segment", "gpt-5.6-terra", {"prompt_tokens": 1000, "completion_tokens": 1000}, False
    )
    with pytest.raises(CostLimitError):
        ledger.check_budget(0.001)


def test_ledger_reservation_rejects_zero_budget_before_request() -> None:
    ledger = Ledger(settings(limit=0.0))
    with pytest.raises(CostLimitError):
        ledger.reserve_call("gpt-5.6-terra", tokens_in=100, tokens_out=20)


def test_ledger_records_unknown_usage_with_estimate() -> None:
    ledger = Ledger(settings(limit=1.5))
    ledger.record(
        "segment",
        "gpt-5.6-terra",
        {"estimated": True, "prompt_tokens": 100, "completion_tokens": 20},
        False,
    )
    assert ledger.token_count() == 120


def test_midrun_budget_cap_is_checked_before_second_physical_call() -> None:
    ledger = Ledger(settings(limit=0.00002))
    reservation = ledger.reserve_call("gpt-5.6-terra", tokens_in=1, tokens_out=1)
    ledger.release_call(reservation, tokens=2)
    ledger.record("first", "gpt-5.6-terra", {"prompt_tokens": 100, "completion_tokens": 100}, False)
    with pytest.raises(CostLimitError):
        ledger.reserve_call("gpt-5.6-terra", tokens_in=1000, tokens_out=1000)
