"""Tests du portefeuille (services/portfolio.py)."""

import pandas as pd
import pytest

from services import portfolio


def test_positions_round_trip_and_invalid_lines_are_dropped(
    tmp_path,
    monkeypatch
):

    monkeypatch.setattr(portfolio, "PORTFOLIO_PATH", tmp_path / "p.json")

    assert portfolio.load_positions() == []

    portfolio.save_positions([
        {"symbol": "B", "quantity": 10, "buy_price": 100, "buy_date": "2025-03-01"},
        {"symbol": "A", "quantity": 5, "buy_price": 200, "buy_date": "2025-01-15"},
        {"symbol": "C", "quantity": 0, "buy_price": 100, "buy_date": "2025-01-15"},
        {"symbol": "D", "quantity": 1, "buy_price": 100, "buy_date": "pas une date"},
    ])

    positions = portfolio.load_positions()

    assert [position["symbol"] for position in positions] == ["A", "B"]


def test_value_position_counts_only_dividends_detached_after_the_purchase():

    position = {
        "symbol": "A",
        "quantity": 10,
        "buy_price": 1000.0,
        "buy_date": "2025-03-10"
    }

    dividends = [
        {"ex_date": "2025-03-10", "amount": 50},   # jour de l'achat : non
        {"ex_date": "2025-06-02", "amount": 80},   # encaisse
        {"ex_date": "2026-06-02", "amount": 90}    # a venir : non
    ]

    valued = portfolio.value_position(
        position,
        last_close=1100.0,
        last_date=pd.Timestamp("2025-12-31"),
        dividends=dividends,
        fee=2.0
    )

    assert valued["cost"] == 10000
    assert valued["gain"] == 1000
    assert valued["dividends"] == 800
    assert valued["fees"] == 200
    assert valued["net"] == 1600
    assert valued["net_pct"] == pytest.approx(16.0)
