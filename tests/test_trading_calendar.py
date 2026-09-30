"""Tests du calendrier BRVM (services/trading_calendar.py)."""

import datetime

import pandas as pd

from services import trading_calendar
from services.trading_calendar import (
    computed_holidays,
    easter_sunday,
    previous_trading_day
)


def test_easter_sunday_matches_known_dates():

    assert easter_sunday(2024) == datetime.date(2024, 3, 31)
    assert easter_sunday(2025) == datetime.date(2025, 4, 20)
    assert easter_sunday(2026) == datetime.date(2026, 4, 5)


def test_computed_holidays_include_fixed_and_easter_based_days():

    holidays = computed_holidays(2025)

    assert holidays[datetime.date(2025, 8, 7)] == "Fête de l'indépendance"
    assert holidays[datetime.date(2025, 4, 21)] == "Lundi de Pâques"
    assert holidays[datetime.date(2025, 5, 29)] == "Ascension"
    assert holidays[datetime.date(2025, 6, 9)] == "Lundi de Pentecôte"


def test_previous_trading_day_skips_weekends_and_holidays():

    # Mardi 22/04/2025 : la veille est le lundi de Paques, puis le week-end.
    assert previous_trading_day("2025-04-22", []) == pd.Timestamp("2025-04-18")

    # Vendredi 02/05/2025 : le 1er mai est ferie.
    assert previous_trading_day("2025-05-02", []) == pd.Timestamp("2025-04-30")

    # Fete mobile saisie a la main.
    assert previous_trading_day(
        "2025-06-12", [datetime.date(2025, 6, 11)]
    ) == pd.Timestamp("2025-06-10")


def test_extra_holidays_round_trip(tmp_path, monkeypatch):

    monkeypatch.setattr(trading_calendar, "HOLIDAYS_PATH", tmp_path / "h.json")

    assert trading_calendar.load_extra_holidays() == []

    trading_calendar.save_extra_holidays(["2025-06-06", "2025-03-31", "x"])

    assert trading_calendar.load_extra_holidays() == [
        datetime.date(2025, 3, 31),
        datetime.date(2025, 6, 6)
    ]
