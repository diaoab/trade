"""Tests du chargement/normalisation des historiques (services/market_data.py)."""

import pandas as pd
import pytest

from services.market_data import (
    _count_inversions,
    _swap_day_month,
    _to_numeric,
    normalize_columns,
    parse_dates,
    prepare_dataframe
)


# =========================================================
# NORMALISATION DES COLONNES
# =========================================================

def test_normalize_columns_recognizes_french_headers():

    df = pd.DataFrame(columns=["Séance", "Cloture", "Ouverture", "Variation %"])

    renamed, rename_map = normalize_columns(df)

    assert set(renamed.columns) == {"Date", "Close", "Open", "Variation"}
    assert rename_map["Séance"] == "Date"
    assert rename_map["Cloture"] == "Close"


def test_normalize_columns_keeps_first_match_on_duplicate_candidates():
    """Deux colonnes pourraient repondre au meme candidat ("close" et
    "cours") : la premiere rencontree l'emporte, l'autre n'est pas touchee."""

    df = pd.DataFrame(columns=["Close", "Cours"])

    renamed, rename_map = normalize_columns(df)

    assert rename_map == {"Close": "Close"}
    assert "Cours" in renamed.columns


# =========================================================
# NOMBRES AU FORMAT FRANCOPHONE
# =========================================================

def test_to_numeric_handles_thousands_separator_and_decimal_comma():

    series = pd.Series(["1 234,56", "2 000", "12,5%"])

    result = _to_numeric(series)

    assert result.tolist() == [1234.56, 2000.0, 12.5]


# =========================================================
# DETECTION DU JOUR/MOIS INVERSE
# =========================================================

def test_swap_day_month_exchanges_fields():

    assert _swap_day_month(pd.Timestamp(2023, 5, 2)) == pd.Timestamp(2023, 2, 5)


def test_swap_day_month_returns_nat_when_impossible():
    """Le 25 ne peut pas devenir un mois : l'echange doit echouer proprement."""

    assert pd.isna(_swap_day_month(pd.Timestamp(2023, 1, 25)))


def test_count_inversions_counts_backward_steps():

    ascending = pd.Series([
        pd.Timestamp(2023, 1, 1),
        pd.Timestamp(2023, 1, 2)
    ])

    descending = pd.Series([
        pd.Timestamp(2023, 5, 2),
        pd.Timestamp(2023, 2, 5)
    ])

    assert _count_inversions(ascending) == 0
    assert _count_inversions(descending) == 1


def test_parse_dates_swaps_when_it_removes_an_inversion():
    """Les deux dates, lues telles quelles, reculent dans le temps (mai puis
    fevrier) ; inversees jour/mois, elles avancent (fevrier puis mai). La
    lecture inversee doit etre retenue."""

    series = pd.Series([
        pd.Timestamp(2023, 5, 2),
        pd.Timestamp(2023, 2, 5)
    ])

    dates, info = parse_dates(series)

    assert info["day_month_swapped"] is True
    assert dates.tolist() == [
        pd.Timestamp(2023, 2, 5),
        pd.Timestamp(2023, 5, 2)
    ]


def test_parse_dates_keeps_raw_reading_when_already_chronological():

    series = pd.Series([
        pd.Timestamp(2023, 1, 1),
        pd.Timestamp(2023, 1, 2)
    ])

    dates, info = parse_dates(series)

    assert info["day_month_swapped"] is False
    assert dates.tolist() == series.tolist()


# =========================================================
# PIPELINE COMPLET
# =========================================================

def test_prepare_dataframe_requires_a_close_column():

    df = pd.DataFrame({"Date": [pd.Timestamp(2023, 1, 1)], "Volume": [100]})

    with pytest.raises(ValueError):
        prepare_dataframe(df)


def test_prepare_dataframe_sorts_and_deduplicates_by_date():

    df = pd.DataFrame({
        "Date": [
            pd.Timestamp(2023, 1, 3),
            pd.Timestamp(2023, 1, 1),
            pd.Timestamp(2023, 1, 3)
        ],
        "Close": ["100,0", "90,0", "101,0"]
    })

    prepared, report = prepare_dataframe(df)

    # Le doublon du 3 janvier garde sa derniere occurrence (101.0), et les
    # lignes sont triees chronologiquement.
    assert prepared["Date"].tolist() == [
        pd.Timestamp(2023, 1, 1),
        pd.Timestamp(2023, 1, 3)
    ]

    assert prepared["Close"].tolist() == [90.0, 101.0]

    assert report["rows_out"] == 2
