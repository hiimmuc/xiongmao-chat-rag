from decimal import Decimal

from app.services.prompts import successful_history
from app.services.usage import estimate_cost


def test_decimal_cost_and_missing_usage():
    rate = {"input": "1", "output": "4", "cached_input": "0.5"}
    assert estimate_cost(1000, 100, 200, rate) == Decimal("0.0013")
    assert estimate_cost(None, 100, 0, rate) is None
    assert estimate_cost(100, 100, 0, {}) is None


def test_failed_turn_excluded_from_context():
    turns = [
        dict(user_text="one", content="yes", status="completed"),
        dict(user_text="failed", content="partial", status="failed"),
        dict(user_text="failed", content="retry answer", status="completed"),
    ]
    result = successful_history(turns)
    assert [m["content"] for m in result] == ["one", "yes", "failed", "retry answer"]
