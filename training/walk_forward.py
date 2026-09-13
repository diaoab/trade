"""Validation walk-forward du modele retenu par training.train.

training.train mesure la performance sur un seul decoupage train/test (une
seule fenetre temporelle) : un ROC AUC de 0.667 sur cette fenetre precise
pourrait etre un coup de chance plutot qu'un signal stable. Ce script reprend
la configuration du modele deja choisie (cf. results/model_comparison.csv) et
l'evalue sur plusieurs fenetres glissantes successives, pour verifier si la
performance se maintient dans le temps ou si elle varie fortement d'une
periode a l'autre.

Contrairement a training.train, il n'y a pas de nouvelle recherche
d'hyperparametres ici : le but est de tester la stabilite de la config deja
retenue, pas d'en chercher une meilleure -- ce qui rend chaque fenetre rapide
a evaluer.

    python -m training.walk_forward
"""

import ast
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

from sklearn.base import clone
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, roc_auc_score
from sklearn.model_selection import TimeSeriesSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from xgboost import XGBClassifier

sys.path.insert(
    0,
    str(Path(__file__).resolve().parent.parent)
)

from config import RESULT_DIR
from services.indicators import calculate_indicators
from services.market_data import load_all_structures
from services.targets import (
    FUTURE_HORIZON_DAYS,
    TERCILE_LOWER_QUANTILE,
    TERCILE_UPPER_QUANTILE,
    compute_future_return,
    fit_tercile_thresholds,
    label_tercile
)


warnings.filterwarnings("ignore")


N_WINDOWS = 6

CALIBRATION_CV_SPLITS = 3

RANDOM_STATE = 42

MINIMUM_WINDOW_ROWS = 30

# Meme liste que training.train : les deux doivent rester synchronises.
FEATURES = [
    "RSI",
    "Distance_MM20",
    "Distance_MM50",
    "MACD_Rel",
    "MACD_Hist_Rel",
    "Bollinger_Position",
    "Bollinger_Width",
    "Return_1D",
    "Return_5D",
    "Volatility_10D"
]

OPTIONAL_FEATURES = ["Volume_Ratio"]


# Reconstruit un estimateur "vierge" du meme type que ceux proposes par
# training.train ; ses hyperparametres sont ensuite fixes via set_params()
# avec les valeurs deja retenues dans results/model_comparison.csv.
ESTIMATOR_FACTORIES = {

    "Logistic Regression": lambda: Pipeline([
        ("scaler", StandardScaler()),
        (
            "model",
            LogisticRegression(
                max_iter=2000,
                class_weight="balanced",
                random_state=RANDOM_STATE
            )
        )
    ]),

    "Random Forest": lambda: RandomForestClassifier(
        class_weight="balanced",
        random_state=RANDOM_STATE
    ),

    "XGBoost": lambda: XGBClassifier(
        subsample=0.8,
        colsample_bytree=0.8,
        objective="binary:logistic",
        eval_metric="logloss",
        random_state=RANDOM_STATE
    )
}


def section(title):

    print("\n" + "=" * 46)
    print(title)
    print("=" * 46)


def build_chosen_estimator():
    """Relit le modele et les hyperparametres retenus par le dernier
    entrainement, pour tester leur stabilite plutot que d'en chercher de
    nouveaux."""

    comparison_path = RESULT_DIR / "model_comparison.csv"

    if not comparison_path.exists():

        raise FileNotFoundError(
            f"{comparison_path} introuvable. Lance d'abord : "
            "python -m training.train"
        )

    comparison = pd.read_csv(comparison_path)

    best_row = (
        comparison
        .sort_values("cv_roc_auc_mean", ascending=False)
        .iloc[0]
    )

    name = best_row["model"]

    params = ast.literal_eval(best_row["best_params"])

    estimator = ESTIMATOR_FACTORIES[name]()

    estimator.set_params(**params)

    return name, estimator


def build_dataset():
    """Reconstruit le meme jeu de donnees pooled que training.train (memes
    variables, meme deduplication), sans encore etiqueter la cible."""

    loaded = load_all_structures()

    if not loaded:

        raise FileNotFoundError(
            "Aucun historique exploitable dans data/."
        )

    # Meme deduplication par empreinte de cloture que training.train : deux
    # fichiers identiques ne doivent pas compter double.
    seen_series = {}
    deduplicated = {}

    for symbol, (df, report) in loaded.items():

        fingerprint = tuple(df["Close"].round(6))

        if fingerprint in seen_series:
            continue

        seen_series[fingerprint] = symbol
        deduplicated[symbol] = (df, report)

    frames = []

    for symbol, (df, _report) in deduplicated.items():

        df = calculate_indicators(df)

        df["Future_Return"] = compute_future_return(
            df["Close"],
            FUTURE_HORIZON_DAYS
        )

        df["Symbol"] = symbol

        frames.append(df)

    pooled = pd.concat(frames, ignore_index=True)

    features = list(FEATURES)

    for feature in OPTIONAL_FEATURES:

        if feature in pooled.columns:
            features.append(feature)

    columns = features + ["Future_Return", "Symbol"]

    if "Date" in pooled.columns:
        columns.append("Date")

    data = (
        pooled[columns]
        .replace([np.inf, -np.inf], np.nan)
        .dropna()
    )

    if "Date" in data.columns:

        data = data.sort_values(["Date", "Symbol"])

    return data.reset_index(drop=True), features


def evaluate_window(estimator, X_train, y_train, X_test, y_test):

    n_splits = min(
        CALIBRATION_CV_SPLITS,
        y_train.value_counts().min()
    )

    if n_splits < 2:
        return None

    calibrated = CalibratedClassifierCV(
        clone(estimator),
        method="sigmoid",
        cv=n_splits
    )

    calibrated.fit(X_train, y_train)

    predictions = calibrated.predict(X_test)
    probabilities = calibrated.predict_proba(X_test)[:, 1]

    majority_class = int(y_train.mode().iloc[0])

    baseline_accuracy = accuracy_score(
        y_test,
        np.full(len(y_test), majority_class)
    )

    try:
        auc = roc_auc_score(y_test, probabilities)
    except ValueError:
        auc = float("nan")

    accuracy = accuracy_score(y_test, predictions)

    return {
        "accuracy": accuracy,
        "baseline_accuracy": baseline_accuracy,
        "gain": accuracy - baseline_accuracy,
        "roc_auc": auc
    }


def main():

    section("CHARGEMENT")

    data, features = build_dataset()

    model_name, estimator = build_chosen_estimator()

    print(f"Modele teste : {model_name}")
    print(f"Lignes disponibles (avant decoupage par tercile) : {len(data)}")

    section(f"VALIDATION WALK-FORWARD ({N_WINDOWS} fenetres)")

    cv = TimeSeriesSplit(n_splits=N_WINDOWS)

    rows = []

    for window_index, (train_idx, test_idx) in enumerate(
        cv.split(data),
        start=1
    ):

        train_slice = data.iloc[train_idx]
        test_slice = data.iloc[test_idx]

        lower, upper = fit_tercile_thresholds(
            train_slice["Future_Return"],
            TERCILE_LOWER_QUANTILE,
            TERCILE_UPPER_QUANTILE
        )

        train_slice = (
            train_slice
            .assign(Target=label_tercile(
                train_slice["Future_Return"], lower, upper
            ))
            .dropna(subset=["Target"])
        )

        test_slice = (
            test_slice
            .assign(Target=label_tercile(
                test_slice["Future_Return"], lower, upper
            ))
            .dropna(subset=["Target"])
        )

        date_range = ""

        if "Date" in data.columns and not test_slice.empty:

            date_range = (
                f"{test_slice['Date'].iloc[0]:%Y-%m-%d} -> "
                f"{test_slice['Date'].iloc[-1]:%Y-%m-%d}"
            )

        if (
            len(train_slice) < MINIMUM_WINDOW_ROWS
            or len(test_slice) < MINIMUM_WINDOW_ROWS
            or train_slice["Target"].nunique() < 2
        ):

            print(
                f"Fenetre {window_index} [{date_range}] : "
                "ignoree (pas assez de seances tranchees)"
            )

            continue

        metrics = evaluate_window(
            estimator,
            train_slice[features],
            train_slice["Target"].astype(int),
            test_slice[features],
            test_slice["Target"].astype(int)
        )

        if metrics is None:

            print(
                f"Fenetre {window_index} [{date_range}] : "
                "ignoree (classe trop rare pour la calibration)"
            )

            continue

        metrics["window"] = window_index
        metrics["period"] = date_range
        metrics["n_train"] = len(train_slice)
        metrics["n_test"] = len(test_slice)

        rows.append(metrics)

        print(
            f"Fenetre {window_index} [{date_range}] : "
            f"accuracy={metrics['accuracy']:.3f} "
            f"(baseline {metrics['baseline_accuracy']:.3f}, "
            f"ecart {metrics['gain']:+.3f}) "
            f"roc_auc={metrics['roc_auc']:.3f} "
            f"n_test={metrics['n_test']}"
        )

    if not rows:

        print(
            "\nAucune fenetre exploitable : pas assez de donnees pour un "
            "walk-forward significatif."
        )

        return

    results_df = pd.DataFrame(rows)[
        ["window", "period", "n_train", "n_test",
         "accuracy", "baseline_accuracy", "gain", "roc_auc"]
    ]

    results_df.to_csv(RESULT_DIR / "walk_forward.csv", index=False)

    section("SYNTHESE")

    windows_beating_baseline = (results_df["gain"] > 0).sum()

    print(
        f"Fenetres ou le modele bat la reference naive : "
        f"{windows_beating_baseline} / {len(results_df)}"
    )

    print(
        f"ROC AUC   : moyenne={results_df['roc_auc'].mean():.3f}  "
        f"ecart-type={results_df['roc_auc'].std():.3f}  "
        f"min={results_df['roc_auc'].min():.3f}  "
        f"max={results_df['roc_auc'].max():.3f}"
    )

    print(
        f"Ecart accuracy vs baseline : "
        f"moyenne={results_df['gain'].mean():+.3f}  "
        f"ecart-type={results_df['gain'].std():.3f}"
    )

    if windows_beating_baseline < len(results_df):

        print(
            "\n[!] La performance varie selon la periode : le modele ne bat "
            "pas la reference naive sur toutes les fenetres. A interpreter "
            "comme une fourchette de performance realiste, pas comme le "
            "chiffre unique optimiste d'un seul decoupage."
        )

    print(f"\n-> {RESULT_DIR / 'walk_forward.csv'}")


if __name__ == "__main__":
    main()
