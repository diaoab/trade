"""Tests de la construction de la cible (services/targets.py)."""

import numpy as np
import pandas as pd

from services.targets import (
    compute_future_return,
    fit_tercile_thresholds,
    label_tercile
)


def test_compute_future_return_matches_manual_ratio():

    close = pd.Series([100.0, 101.0, 102.0, 103.0, 104.0, 110.0, 90.0])

    future_return = compute_future_return(close, horizon=2)

    assert future_return.iloc[0] == 102.0 / 100.0 - 1
    assert future_return.iloc[4] == 90.0 / 104.0 - 1


def test_compute_future_return_is_nan_for_trailing_rows():

    close = pd.Series([100.0, 101.0, 102.0, 103.0])

    future_return = compute_future_return(close, horizon=2)

    assert future_return.iloc[:2].notna().all()
    assert future_return.iloc[2:].isna().all()


def test_fit_tercile_thresholds_matches_manual_quantiles():

    values = pd.Series(range(1, 10))  # 1..9

    lower, upper = fit_tercile_thresholds(values, 1 / 3, 2 / 3)

    assert lower == values.quantile(1 / 3)
    assert upper == values.quantile(2 / 3)
    assert lower < upper


def test_label_tercile_splits_into_top_bottom_and_drops_middle():

    future_returns = pd.Series([-0.10, -0.09, -0.01, 0.00, 0.01, 0.09, 0.10])

    lower, upper = fit_tercile_thresholds(future_returns)

    labels = label_tercile(future_returns, lower, upper)

    top = future_returns[labels == 1]
    bottom = future_returns[labels == 0]
    middle = future_returns[labels.isna()]

    # Aucun chevauchement, et chaque valeur est classee quelque part.
    assert len(top) + len(bottom) + len(middle) == len(future_returns)
    assert (top >= upper).all()
    assert (bottom <= lower).all()


def test_label_tercile_propagates_nan_future_return_as_ambiguous():
    """Une seance sans lendemain assez lointain (Future_Return = NaN) ne doit
    satisfaire ni le seuil haut ni le seuil bas : elle est donc ecartee au
    meme titre que le tiers median, sans traitement special."""

    future_returns = pd.Series([-0.10, 0.10, np.nan])

    labels = label_tercile(future_returns, lower_threshold=-0.05, upper_threshold=0.05)

    assert labels.iloc[0] == 0
    assert labels.iloc[1] == 1
    assert pd.isna(labels.iloc[2])


def test_label_tercile_thresholds_are_inclusive_boundaries():

    future_returns = pd.Series([-0.05, 0.05])

    labels = label_tercile(future_returns, lower_threshold=-0.05, upper_threshold=0.05)

    assert labels.iloc[0] == 0
    assert labels.iloc[1] == 1
