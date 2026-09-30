"""Tests du backtest des signaux techniques (services/backtest.py)."""

import numpy as np
import pandas as pd

from services.backtest import (
    SIGNAL_INDICATORS,
    replay_signals,
    summarize_scores,
    summarize_signals
)


def _trending_history(n=120):
    """Hausse reguliere : le cours reste au-dessus de ses moyennes mobiles
    et chaque seance est suivie d'une hausse."""

    return pd.DataFrame({
        "Date": pd.bdate_range("2024-01-01", periods=n),
        "Close": np.linspace(100, 200, n)
    })


def test_replay_reads_each_signal_from_the_engine():

    replayed = replay_signals({"X": _trending_history()})

    assert not replayed.empty
    assert set(SIGNAL_INDICATORS).issubset(replayed.columns)

    # Tendance haussiere continue : MM20, MM50 et momentum favorables.
    assert (replayed[["MM20", "MM50", "Momentum"]] == 1).all().all()
    assert (replayed["Future_Return_5"] > 0).all()

    # Horizon long : vide sur les dernieres seances, faute de recul.
    assert replayed["Future_Return_60"].isna().any()
    assert replayed["Future_Return_60"].notna().any()

    # Les 5 dernieres seances n'ont pas de futur : elles sont ecartees.
    assert replayed["Date"].max() < _trending_history()["Date"].iloc[-5]


def test_summaries_compare_each_signal_to_the_baseline():

    replayed = replay_signals({"X": _trending_history()})

    signals = summarize_signals(replayed)

    baseline = signals.iloc[0]

    assert baseline["Indicateur"] == "Toutes les séances"
    assert baseline["Séances"] == len(replayed)
    assert baseline["Hausse ensuite (%)"] == 100

    mm20 = signals[signals["Indicateur"] == "MM20"]

    assert mm20["Signal"].tolist() == ["favorable"]

    scores = summarize_scores(replayed)

    assert scores["Séances"].sum() == len(replayed)


def test_fees_are_deducted_and_long_horizons_use_fewer_sessions():

    replayed = replay_signals({"X": _trending_history()})

    short = summarize_signals(replayed, horizon=5, fee=2.0).iloc[0]

    long = summarize_signals(replayed, horizon=60, fee=2.0).iloc[0]

    assert short["Net de frais (%)"] == short["Variation moyenne (%)"] - 2.0

    assert long["Séances"] < short["Séances"]
    assert long["Variation moyenne (%)"] > short["Variation moyenne (%)"]
