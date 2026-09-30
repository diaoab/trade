"""Tests des aides d'analyse partagees entre les pages
(services/analysis.py)."""

import pandas as pd

from services.analysis import (
    next_dividend_cutoff,
    relative_performance,
    session_changes
)


def _history(start, end):
    """Cours passant lineairement de `start` a `end` sur 400 jours."""

    dates = pd.date_range("2024-01-01", periods=400, freq="D")

    return pd.DataFrame({
        "Date": dates,
        "Close": [
            start + (end - start) * index / 399
            for index in range(400)
        ]
    })


def test_relative_performance_compares_stock_and_benchmark():

    rows = relative_performance(
        _history(100, 200),
        _history(100, 120),
        pd.Timestamp("2025-02-03")
    )

    assert [row["period"] for row in rows] == ["1 mois", "3 mois", "1 an"]

    # Le titre monte plus vite que l'indice sur chaque periode.
    assert all(row["gap"] > 0 for row in rows)
    assert all(row["stock"] > row["benchmark"] > 0 for row in rows)


def test_relative_performance_skips_periods_without_history():

    rows = relative_performance(
        _history(100, 200),
        _history(100, 120),
        pd.Timestamp("2024-03-15")
    )

    # Deux mois et demi d'historique : seul "1 mois" est couvert.
    assert [row["period"] for row in rows] == ["1 mois"]


def test_next_dividend_cutoff_picks_the_first_upcoming_detachment():

    dividends = [
        {"ex_date": "2025-05-05", "amount": 10},
        {"ex_date": "2025-06-12", "amount": 20},
        {"ex_date": "2026-06-12", "amount": 30}
    ]

    upcoming = next_dividend_cutoff(dividends, pd.Timestamp("2025-06-06"))

    assert upcoming["amount"] == 20
    # Le 9 juin 2025 est le lundi de Pentecote : sans effet ici, la veille
    # du 12 est le mercredi 11.
    assert upcoming["cutoff"] == pd.Timestamp("2025-06-11")
    assert upcoming["days_left"] == 5

    assert next_dividend_cutoff(dividends, pd.Timestamp("2027-01-01")) is None


def test_session_changes_reports_only_what_changed():

    quiet = {"decision": "CONSERVER", "liquidity_warnings": []}

    assert session_changes({"RSI": 50}, {"RSI": 55}, quiet, quiet) == []

    changes = session_changes(
        {"RSI": 65},
        {"RSI": 75},
        quiet,
        {"decision": "ACHETER", "liquidity_warnings": ["x"]}
    )

    assert changes == [
        "le signal passe de CONSERVER à ACHETER",
        "le RSI entre en zone de surachat",
        "le titre devient peu liquide"
    ]

    # Deja en surachat la veille : ce n'est plus une nouvelle.
    assert session_changes({"RSI": 72}, {"RSI": 75}, quiet, quiet) == []
