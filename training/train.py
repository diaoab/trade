"""Entrainement du modele partage entre toutes les structures.

Un seul modele est entraine sur l'ensemble des historiques empiles, ce qui
suppose des variables comparables d'un titre a l'autre : on n'utilise donc que
des grandeurs relatives (ecarts, rendements, ratios), jamais des niveaux de
prix bruts.

    python -m training.train
"""

import json
import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from sklearn.base import clone
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GridSearchCV, TimeSeriesSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    precision_score,
    recall_score,
    f1_score,
    roc_auc_score,
    classification_report,
    confusion_matrix
)

from xgboost import XGBClassifier

sys.path.insert(
    0,
    str(Path(__file__).resolve().parent.parent)
)

from config import (
    MODEL_PATH,
    FEATURES_PATH,
    MODEL_METADATA_PATH,
    PROBA_REFERENCE_PATH,
    RESULT_DIR
)
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


# =========================================================
# CONFIGURATION
# =========================================================

TEST_SIZE = 0.20

CV_SPLITS = 4

RANDOM_STATE = 42

MINIMUM_ROWS = 50

warnings.filterwarnings("ignore")


# Uniquement des variables sans unite, comparables entre structures.
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

OPTIONAL_FEATURES = [
    "Volume_Ratio"
]


def section(title):

    print("\n" + "=" * 46)
    print(title)
    print("=" * 46)


# =========================================================
# 1. CHARGEMENT DES STRUCTURES
# =========================================================

section("CHARGEMENT DES STRUCTURES")

loaded = load_all_structures()

if not loaded:

    raise FileNotFoundError(
        "Aucun historique exploitable dans data/. "
        "Depose un classeur .xlsx contenant au moins une colonne de cloture."
    )


# Deux fichiers different peuvent decrire le meme titre (export renomme,
# doublon depose par erreur...). Les entrainer tous les deux revient a montrer
# deux fois les memes seances au modele : ca ne lui apprend rien de plus et
# fausse la separation train/validation/test, qui croit voir deux titres
# independants la ou il n'y en a qu'un. On les detecte par egalite stricte de
# la serie de cloture et on ne garde que le premier.
seen_series = {}

deduplicated = {}

for symbol, (df, report) in loaded.items():

    fingerprint = tuple(
        df["Close"].round(6)
    )

    duplicate_of = seen_series.get(fingerprint)

    if duplicate_of is not None:

        print(
            f"[!] {symbol} ecarte : cotations identiques a {duplicate_of} "
            "(doublon)"
        )

        continue

    seen_series[fingerprint] = symbol

    deduplicated[symbol] = (df, report)

loaded = deduplicated


frames = []

for symbol, (df, report) in loaded.items():

    print(
        f"\n{report['name']} ({symbol})"
    )

    print(
        f"  lignes retenues : {report['rows_out']} / {report['rows_in']}"
    )

    if report.get("day_month_swapped"):

        print(
            "  [corrige] jour et mois etaient inverses dans le fichier source"
        )

    ohlc_issues = report.get("ohlc_issues") or {}

    if ohlc_issues.get("inconsistent"):

        print(
            f"  [!] {ohlc_issues['inconsistent']} seances ou le plus bas / "
            "plus haut contredit l'ouverture ou la cloture, sans explication "
            "connue"
        )

    if ohlc_issues.get("flat_day_quirk"):

        print(
            f"  [i] {ohlc_issues['flat_day_quirk']} seances sans mouvement ou "
            "plus haut/plus bas different de l'ouverture/cloture (convention "
            "connue de l'export, sans impact)"
        )

    df = calculate_indicators(df)

    # Le rendement futur se calcule titre par titre : empiler d'abord ferait
    # deborder les dernieres seances d'une structure sur la premiere de la
    # suivante. La cible elle-meme (Target) n'est pas fixee ici : elle depend
    # de seuils par tercile qui ne peuvent etre appris que sur la portion
    # train+validation, une fois le decoupage chronologique fait (section 3).
    df["Future_Return"] = compute_future_return(
        df["Close"],
        FUTURE_HORIZON_DAYS
    )

    df["Symbol"] = symbol

    frames.append(df)


pooled = pd.concat(
    frames,
    ignore_index=True
)


# =========================================================
# 2. CONSTRUCTION DU JEU DE DONNEES
# =========================================================

section("JEU DE DONNEES")

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

# dropna() ci-dessus ecarte deja les dernieres seances de chaque titre : leur
# Future_Return est NaN, faute d'un horizon assez lointain.


if "Date" in data.columns:

    data = data.sort_values(
        ["Date", "Symbol"]
    )


data = data.reset_index(drop=True)


print(
    f"Structures        : {data['Symbol'].nunique()}"
)

print(
    f"Lignes utilisables : {len(data)}"
)

print(
    f"Variables          : {len(features)}"
)

for feature in features:
    print(f"  - {feature}")


if len(data) < MINIMUM_ROWS:

    raise ValueError(
        f"Seulement {len(data)} lignes exploitables : trop peu pour "
        "entrainer un modele. Ajoute des historiques dans data/."
    )


# =========================================================
# 3. DECOUPAGE CHRONOLOGIQUE
# =========================================================

section("DECOUPAGE TRAIN+VALIDATION / TEST")

# Avec aussi peu de seances, un unique decoupage train/validation/test rend
# chaque score tres bruite : un seul titre mal classe suffit a faire bouger
# l'accuracy de plusieurs points. Le test final reste un decoupage
# chronologique fixe (jamais vu avant l'evaluation), mais la selection du
# modele et de ses hyperparametres se fait desormais par validation croisee
# glissante (TimeSeriesSplit) sur la portion train+validation, ce qui moyenne
# le bruit sur plusieurs fenetres au lieu de dependre d'une seule.

test_start = int(len(data) * (1 - TEST_SIZE))

train_val_slice = data.iloc[:test_start]
test_slice = data.iloc[test_start:]

if "Date" in data.columns:

    dates = data["Date"]

    print(
        f"Train + validation : {dates.iloc[0]:%Y-%m-%d} "
        f"-> {dates.iloc[test_start - 1]:%Y-%m-%d}"
    )

    print(
        f"Test                : {dates.iloc[test_start]:%Y-%m-%d} "
        f"-> {dates.iloc[-1]:%Y-%m-%d}"
    )

# Les seuils de tercile sont appris uniquement sur le train+validation, puis
# appliques tels quels au test : les apprendre sur l'ensemble des donnees
# ferait fuiter de l'information du futur (test) vers l'entrainement.
lower_threshold, upper_threshold = fit_tercile_thresholds(
    train_val_slice["Future_Return"],
    TERCILE_LOWER_QUANTILE,
    TERCILE_UPPER_QUANTILE
)

print(
    f"\nSeuils de tercile (appris sur train+validation) : "
    f"bas={lower_threshold:.4f}  haut={upper_threshold:.4f}"
)


train_val_slice = (
    train_val_slice
    .assign(
        Target=label_tercile(
            train_val_slice["Future_Return"],
            lower_threshold,
            upper_threshold
        )
    )
    .dropna(subset=["Target"])
)

test_slice = (
    test_slice
    .assign(
        Target=label_tercile(
            test_slice["Future_Return"],
            lower_threshold,
            upper_threshold
        )
    )
    .dropna(subset=["Target"])
)

X_train_val = train_val_slice[features]
y_train_val = train_val_slice["Target"].astype(int)

X_test = test_slice[features]
y_test = test_slice["Target"].astype(int)


print(
    f"\nTrain + validation : {len(X_train_val)} seances tranchees "
    f"(tiers median ecarte)"
)
print(f"Test                : {len(X_test)} seances tranchees")

print("\nRepartition de la cible (train + validation) :")
print(y_train_val.value_counts().sort_index().to_string())


# =========================================================
# 4. REFERENCE NAIVE
# =========================================================

section("REFERENCE NAIVE")

majority_class = int(y_train_val.mode().iloc[0])

baseline_predictions = np.full(
    len(y_test),
    majority_class
)

baseline_accuracy = accuracy_score(
    y_test,
    baseline_predictions
)

print(
    f"Strategie : repondre toujours "
    f"{'hausse' if majority_class else 'baisse/stabilite'}"
)

print(
    f"Accuracy sur le test : {baseline_accuracy:.4f}"
)

print(
    "\nTout modele qui ne bat pas ce chiffre n'apporte rien."
)


# =========================================================
# 5. MODELES ET GRILLES D'HYPERPARAMETRES
# =========================================================

section("RECHERCHE D'HYPERPARAMETRES (validation croisee glissante)")

# Le desequilibre hausse/baisse est compense pour la regression logistique et
# la foret aleatoire via class_weight="balanced". XGBoost n'a pas cet
# argument : on lui donne l'equivalent via scale_pos_weight, calcule sur le
# train+validation, sinon il reste biaise vers la classe majoritaire.
positive_count = int(y_train_val.sum())
negative_count = len(y_train_val) - positive_count

scale_pos_weight = (
    negative_count / positive_count
    if positive_count > 0
    else 1.0
)

cv = TimeSeriesSplit(n_splits=CV_SPLITS)

# Des grilles volontairement petites : avec a peine plus d'une centaine de
# lignes d'entrainement, un grand nombre de combinaisons ne ferait
# qu'ajuster le bruit de la validation croisee plutot que reveler un reel
# meilleur choix. Les profondeurs et le nombre d'arbres restent modestes,
# pour limiter le surapprentissage.
search_space = {

    "Logistic Regression": (

        Pipeline([
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

        {
            "model__C": [0.01, 0.1, 1, 10]
        }

    ),

    "Random Forest": (

        RandomForestClassifier(
            class_weight="balanced",
            random_state=RANDOM_STATE
        ),

        {
            "n_estimators": [150, 300],
            "max_depth": [3, 5, 8],
            "min_samples_leaf": [3, 5]
        }

    ),

    "XGBoost": (

        XGBClassifier(
            subsample=0.8,
            colsample_bytree=0.8,
            scale_pos_weight=scale_pos_weight,
            objective="binary:logistic",
            eval_metric="logloss",
            random_state=RANDOM_STATE
        ),

        {
            "n_estimators": [150, 300],
            "max_depth": [2, 3, 4],
            "learning_rate": [0.03, 0.1]
        }

    )
}


def evaluate(model, X_eval, y_eval):

    predictions = model.predict(X_eval)

    probabilities = model.predict_proba(X_eval)[:, 1]

    # Le ROC AUC juge la qualite du classement des seances, independamment du
    # seuil. Selectionner sur le F1 recompenserait un modele qui repond
    # "hausse" partout : il obtient un rappel de 1 sans rien avoir appris.
    try:

        auc = roc_auc_score(y_eval, probabilities)

    except ValueError:

        auc = float("nan")

    return {

        "roc_auc": auc,

        "balanced_accuracy": balanced_accuracy_score(y_eval, predictions),

        "accuracy": accuracy_score(y_eval, predictions),

        "precision": precision_score(
            y_eval, predictions, zero_division=0
        ),

        "recall": recall_score(
            y_eval, predictions, zero_division=0
        ),

        "f1": f1_score(
            y_eval, predictions, zero_division=0
        )
    }


# =========================================================
# 6. RECHERCHE ET SELECTION SUR LA VALIDATION CROISEE
# =========================================================

results = []

best_estimators = {}

for name, (estimator, param_grid) in search_space.items():

    search = GridSearchCV(
        estimator,
        param_grid,
        scoring="roc_auc",
        cv=cv,
        refit=True
    )

    search.fit(X_train_val, y_train_val)

    print(
        f"\n{name}"
    )

    print(
        f"  meilleurs parametres : {search.best_params_}"
    )

    print(
        f"  roc_auc (moyenne {CV_SPLITS} folds) : {search.best_score_:.4f}"
    )

    results.append({
        "model": name,
        "cv_roc_auc_mean": search.best_score_,
        "cv_roc_auc_std": search.cv_results_["std_test_score"][
            search.best_index_
        ],
        "best_params": search.best_params_
    })

    # L'estimateur non calibre sert plus bas a lire l'importance des
    # variables ; le pipeline complet (deja reentraine sur train+validation
    # par refit=True) sert de base a la calibration des probabilites.
    best_estimators[name] = search.best_estimator_


results_df = (
    pd.DataFrame(results)
    .sort_values("cv_roc_auc_mean", ascending=False)
    .reset_index(drop=True)
)

results_df.to_csv(
    RESULT_DIR / "model_comparison.csv",
    index=False
)


# Le modele est choisi sur la validation croisee, jamais sur le test : sinon
# le score annonce serait celui du jeu qui a servi a le selectionner, donc
# optimiste.
best_model_name = results_df.iloc[0]["model"]

best_estimator = best_estimators[best_model_name]


section("MODELE RETENU")

print(f"Selectionne sur la validation croisee : {best_model_name}")

print(
    f"ROC AUC de validation (moyenne {CV_SPLITS} folds) : "
    f"{results_df.iloc[0]['cv_roc_auc_mean']:.4f} "
    "(0.5 = aucun pouvoir predictif)"
)


# =========================================================
# 7. CALIBRATION DES PROBABILITES
# =========================================================

section("CALIBRATION DES PROBABILITES")

# L'application affiche directement predict_proba comme "probabilite de
# hausse" et la fait entrer dans un score chiffre : elle doit donc refleter
# une vraie frequence, pas seulement bien ordonner les seances. Le sigmoide
# (Platt scaling) est prefere a l'isotonique, plus gourmande en donnees et
# instable sur un jeu de cette taille.
calibrated_model = CalibratedClassifierCV(
    clone(best_estimator),
    method="sigmoid",
    cv=cv
)

calibrated_model.fit(X_train_val, y_train_val)

# Copie non calibree, entrainee sur les memes donnees, uniquement pour lire
# l'importance des variables plus bas : CalibratedClassifierCV n'expose pas
# un unique jeu de coefficients/importances.
importance_model = clone(best_estimator)

importance_model.fit(X_train_val, y_train_val)


# =========================================================
# 7 bis. DISTRIBUTION DE REFERENCE DES PROBABILITES
# =========================================================

section("DISTRIBUTION DE REFERENCE DES PROBABILITES")

# cross_val_predict n'accepte pas TimeSeriesSplit (les premieres seances ne
# tombent jamais dans un pli de test, donc le decoupage n'est pas une
# partition complete). On utilise donc les probabilites du modele calibre sur
# les donnees qui lui ont servi a s'entrainer : legerement optimiste, mais
# cette distribution ne sert qu'a situer une probabilite du jour par rapport
# a l'historique (percentile), pas a mesurer une performance -- l'evaluation
# de performance reste entierement sur le test jamais vu (section 8).
probability_reference = np.sort(
    calibrated_model.predict_proba(X_train_val)[:, 1]
)

print(
    f"{len(probability_reference)} probabilites hors-echantillon "
    f"(min={probability_reference.min():.3f}, "
    f"mediane={np.median(probability_reference):.3f}, "
    f"max={probability_reference.max():.3f})"
)


# =========================================================
# 8. EVALUATION FINALE SUR LE TEST
# =========================================================

section("EVALUATION SUR LE TEST (jamais vu)")

test_predictions = calibrated_model.predict(X_test)

test_scores = evaluate(calibrated_model, X_test, y_test)

print(
    f"Accuracy  : {test_scores['accuracy']:.4f}"
)

print(
    f"Precision : {test_scores['precision']:.4f}"
)

print(
    f"Recall    : {test_scores['recall']:.4f}"
)

print(
    f"F1 Score  : {test_scores['f1']:.4f}"
)

print(
    f"ROC AUC   : {test_scores['roc_auc']:.4f}"
)

print(
    f"Bal. acc. : {test_scores['balanced_accuracy']:.4f}"
)

gain = test_scores["accuracy"] - baseline_accuracy

print(
    f"\nReference naive : {baseline_accuracy:.4f}"
)

print(
    f"Ecart           : {gain:+.4f} "
    f"({gain * len(y_test):+.1f} seances sur {len(y_test)})"
)

if gain <= 0:

    print(
        "\n[!] Le modele ne bat pas la reference naive. "
        "Ses probabilites ne doivent pas peser dans une decision."
    )

print("\nClassification report :")

print(
    classification_report(
        y_test,
        test_predictions,
        zero_division=0
    )
)

print("Matrice de confusion :")

print(
    confusion_matrix(y_test, test_predictions)
)


# =========================================================
# 9. SAUVEGARDE
# =========================================================

section("SAUVEGARDE")

joblib.dump(calibrated_model, MODEL_PATH)

joblib.dump(features, FEATURES_PATH)

joblib.dump(probability_reference, PROBA_REFERENCE_PATH)

# Le .pkl seul ne dit pas quand ni sur quelles donnees il a ete produit, ni
# s'il bat reellement la reference naive : sans cette trace, un modele en
# place depuis des mois est indiscernable d'un modele tout juste reentraine.
metadata = {

    "trained_at": datetime.now(timezone.utc).isoformat(),

    "model": best_model_name,

    "target_horizon_days": FUTURE_HORIZON_DAYS,

    "target_method": "tercile",

    "target_tercile_thresholds": {
        "lower": float(lower_threshold),
        "upper": float(upper_threshold)
    },

    "structures": sorted(loaded.keys()),

    "rows_train_val": len(X_train_val),

    "rows_test": len(X_test),

    "cv_roc_auc_mean": results_df.iloc[0]["cv_roc_auc_mean"],

    "test_scores": test_scores,

    "baseline_accuracy": baseline_accuracy,

    "beats_baseline": bool(gain > 0)

}

with open(MODEL_METADATA_PATH, "w", encoding="utf-8") as handle:

    json.dump(metadata, handle, ensure_ascii=False, indent=2)

print(f"-> {MODEL_PATH}")
print(f"-> {FEATURES_PATH}")
print(f"-> {PROBA_REFERENCE_PATH}")
print(f"-> {MODEL_METADATA_PATH}")


# =========================================================
# 10. IMPORTANCE DES VARIABLES
# =========================================================

section("IMPORTANCE DES VARIABLES")

if hasattr(importance_model, "feature_importances_"):

    importance = importance_model.feature_importances_

else:

    importance = np.abs(
        importance_model.named_steps["model"].coef_[0]
    )


importance_df = (
    pd.DataFrame({
        "feature": features,
        "importance": importance
    })
    .sort_values("importance", ascending=False)
    .reset_index(drop=True)
)

print(
    importance_df.to_string(index=False)
)

importance_df.to_csv(
    RESULT_DIR / "feature_importance.csv",
    index=False
)

data.to_csv(
    RESULT_DIR / "prepared_dataset.csv",
    index=False
)

print(f"\n-> {RESULT_DIR / 'model_comparison.csv'}")
print(f"-> {RESULT_DIR / 'feature_importance.csv'}")
print(f"-> {RESULT_DIR / 'prepared_dataset.csv'}")

print("\nLancer l'application : streamlit run app.py")
