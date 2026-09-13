"""Chargement du modele partage et prediction sur une seance."""

import json
import logging

import joblib
import numpy as np

from config import (
    MODEL_PATH,
    FEATURES_PATH,
    MODEL_METADATA_PATH,
    PROBA_REFERENCE_PATH
)


logger = logging.getLogger(__name__)


class ModelUnavailable(RuntimeError):
    """Le modele n'a pas encore ete entraine, ou n'est plus lisible."""


def load_model():

    if not MODEL_PATH.exists():

        raise ModelUnavailable(
            "Modele introuvable. Lance d'abord : python -m training.train"
        )

    try:

        return joblib.load(MODEL_PATH)

    except Exception as error:

        logger.exception("Echec du chargement du modele")

        raise ModelUnavailable(
            f"Modele illisible ({error}). Il a probablement ete enregistre "
            "avec d'autres versions de scikit-learn ou xgboost : "
            "relance python -m training.train"
        ) from error


def load_features():

    if not FEATURES_PATH.exists():

        raise ModelUnavailable(
            "Liste des variables introuvable. "
            "Lance d'abord : python -m training.train"
        )

    return joblib.load(FEATURES_PATH)


def load_probability_reference():
    """Renvoie la distribution (triee) des probabilites hors-echantillon
    calculees a l'entrainement, ou None si un modele plus ancien n'en a pas
    produit. Sert a situer une probabilite du jour par rapport a l'historique
    plutot que de la lire en valeur absolue."""

    if not PROBA_REFERENCE_PATH.exists():
        return None

    try:

        return joblib.load(PROBA_REFERENCE_PATH)

    except Exception:

        logger.exception("Echec du chargement de la distribution de reference")

        return None


def load_model_metadata():
    """Renvoie la fiche du modele (date d'entrainement, score de test...)
    ecrite par training.train, ou None si elle n'existe pas encore -- un
    modele deja entraine avant l'ajout de cette fiche, par exemple."""

    if not MODEL_METADATA_PATH.exists():
        return None

    with open(MODEL_METADATA_PATH, encoding="utf-8") as handle:
        return json.load(handle)


def predict_row(row, model=None, features=None):
    """Predit le sens du lendemain a partir d'une seance deja calculee.

    On travaille sur une ligne fournie par l'appelant, et non sur le
    DataFrame entier, pour que l'analyse technique et le modele portent avec
    certitude sur la meme seance.
    """

    model = model if model is not None else load_model()

    features = (
        features
        if features is not None
        else load_features()
    )

    missing = [
        feature
        for feature in features
        if feature not in row.index
    ]

    if missing:

        raise ModelUnavailable(
            "Variables absentes de la seance analysee : "
            + ", ".join(missing)
            + ". Le modele et les indicateurs ne sont plus synchronises : "
            "relance python -m training.train"
        )

    values = row[features]

    if values.isna().any():

        incomplete = (
            values[values.isna()]
            .index
            .tolist()
        )

        raise ModelUnavailable(
            "Seance incomplete, indicateurs manquants : "
            + ", ".join(incomplete)
        )

    X = values.to_frame().T.astype(float)

    prediction = model.predict(X)[0]

    probabilities = model.predict_proba(X)[0]

    probability_up = float(probabilities[1])

    result = {

        "prediction": int(prediction),

        "probability_down": float(probabilities[0]),

        "probability_up": probability_up
    }

    # Situe la probabilite du jour dans la distribution hors-echantillon
    # calculee a l'entrainement (cf. training.train), plutot que de la lire
    # en valeur absolue : le decision_engine s'en sert preferentiellement
    # (cle "ml_score"), et retombe sur probability_up*100 si elle est absente
    # (modele plus ancien, sans fichier de reference).
    reference = load_probability_reference()

    if reference is not None and len(reference) > 0:

        percentile = float(
            np.searchsorted(reference, probability_up, side="left")
            / len(reference)
            * 100
        )

        result["ml_percentile"] = percentile

        result["ml_score"] = percentile

    return result


def predict(df):
    """Predit sur la derniere seance exploitable d'un historique."""

    model = load_model()

    features = load_features()

    usable = df.dropna(subset=features)

    if usable.empty:

        raise ModelUnavailable(
            "Aucune seance ne dispose de tous les indicateurs necessaires."
        )

    return predict_row(
        usable.iloc[-1],
        model=model,
        features=features
    )
