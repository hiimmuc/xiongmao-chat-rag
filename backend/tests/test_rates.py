import json
from decimal import Decimal
from pathlib import Path

from app.services.usage import estimate_cost


def test_every_configured_rate_is_complete_and_prices_a_call():
    rates = json.loads((Path(__file__).parents[1] / "app" / "services" / "rates.json").read_text())
    assert rates
    for model, rate in rates.items():
        assert {"input", "output", "source", "verified_at"} <= rate.keys(), model
    gpt = rates["openai-default"]
    # 1,000 input (200 cached) and 500 output tokens at $0.40 / $0.10 cached / $1.60 per million.
    assert estimate_cost(1000, 500, 200, gpt) == Decimal("0.000320") + Decimal("0.000020") + Decimal(
        "0.000800"
    )
