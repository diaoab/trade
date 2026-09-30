"""Tests de l'assistant conversationnel (services/assistant_chat.py), sans
appel reseau : le client de l'API est remplace par un faux."""

from types import SimpleNamespace

import pandas as pd
import pytest

from services.assistant_chat import (
    MODEL,
    AssistantUnavailable,
    build_context,
    stream_answer
)


RESULT = {
    "decision": "VENDRE",
    "score": 30.7,
    "confidence": 38.6,
    "technical_score": 30.0,
    "ml_score": None,
    "risk_score": 90.0,
    "positive": 1,
    "negative": 3,
    "neutral": 2,
    "reasons": ["Le cours est inférieur à la MM20."],
    "liquidity_warnings": []
}


class FakeStream:

    def __init__(self, chunks, stop_reason):
        self.text_stream = iter(chunks)
        self._final = SimpleNamespace(
            stop_reason=stop_reason,
            content=[{"type": "text", "text": "".join(chunks)}]
        )

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_final_message(self):
        return self._final


class FakeClient:

    def __init__(self, chunks=("Bon", "jour"), stop_reason="end_turn"):
        self.calls = []
        self.beta = SimpleNamespace(
            messages=SimpleNamespace(stream=self._stream)
        )
        self._chunks = list(chunks)
        self._stop_reason = stop_reason

    def _stream(self, **kwargs):
        self.calls.append(kwargs)
        return FakeStream(self._chunks, self._stop_reason)


def _context():

    return build_context(
        "BIBI CI", pd.Timestamp("2025-12-31"), RESULT, None, None
    )


def test_context_carries_the_decision_the_reasons_and_raw_values():

    context = _context()

    assert "BIBI CI" in context
    assert "le signal est à la vente" in context
    assert '"score_global": 30.7' in context
    assert "Le cours est inférieur à la MM20." in context


def test_answer_is_streamed_and_appended_to_the_history():

    client = FakeClient()

    history = [{"role": "user", "content": "Pourquoi vendre ?"}]

    chunks = list(stream_answer(_context(), history, client=client))

    assert "".join(chunks) == "Bonjour"

    assert history[-1]["role"] == "assistant"
    assert len(history) == 2

    call = client.calls[0]

    assert call["model"] == MODEL
    assert call["system"].endswith(_context())
    assert call["messages"][0]["content"] == "Pourquoi vendre ?"


def test_refusal_is_reported_in_plain_words():

    client = FakeClient(chunks=(), stop_reason="refusal")

    history = [{"role": "user", "content": "?"}]

    answer = "".join(stream_answer(_context(), history, client=client))

    assert "ne peux pas répondre" in answer


def test_missing_key_gives_a_readable_message(monkeypatch):

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)

    with pytest.raises(AssistantUnavailable, match="ANTHROPIC_API_KEY"):

        list(stream_answer(_context(), [{"role": "user", "content": "?"}]))
