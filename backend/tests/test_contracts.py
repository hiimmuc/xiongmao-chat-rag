from decimal import Decimal

import pytest

from app.services.ingestion import chunk_text, extract_text
from app.services.prompts import successful_history
from app.services.retrieval import retrieval_query
from app.services.usage import estimate_cost


def test_chunking_and_utf8():
    text = "Document evidence. " * 1200
    chunks = chunk_text(text, size=80, overlap=10)
    assert len(chunks) > 1
    assert all(len(c) > 0 for c in chunks)
    assert "Document" in chunks[0]


def test_reject_binary_and_scanned_pdf():
    with pytest.raises(ValueError):
        extract_text("payload.exe", b"hello")
    with pytest.raises(ValueError):
        extract_text("empty.txt", b"\x00\x01")


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


def test_retrieval_query_keeps_bounded_history_and_current_question():
    import tiktoken

    history = [{"role": "assistant", "content": "earlier evidence " * 5000}]
    query = retrieval_query("What does it mean?", history)
    assert query.endswith("Current question: What does it mean?")
    assert "earlier evidence" in query
    assert len(tiktoken.get_encoding("cl100k_base").encode(query)) < 1050
    assert retrieval_query("Question", []) == "Question"
