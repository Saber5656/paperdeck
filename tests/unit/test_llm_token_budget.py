import pytest

from paperdeck.config import load_settings
from paperdeck.errors import CostLimitError
from paperdeck.llm.cost import Ledger


def test_unknown_price_token_reservations_cannot_exceed_two_million():
    config = load_settings(None, {"llm.max_cost_usd": 1000})
    ledger = Ledger(config)
    first = ledger.reserve_call("unpriced", tokens_in=1_999_990, tokens_out=0)
    with pytest.raises(CostLimitError, match="token"):
        ledger.reserve_call("unpriced", tokens_in=10, tokens_out=1)
    ledger.release_call(first, tokens=1_999_990)
    assert ledger.reserve_call("unpriced", tokens_in=10, tokens_out=1) > 0
