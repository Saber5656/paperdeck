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
