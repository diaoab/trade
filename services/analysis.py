"""Analyse complete d'une seance : modele ML + moteur de decision.

Partage entre la page Analyse et la page Marche, pour qu'un meme titre
recoive exactement la meme decision des deux cotes.
"""

from services.decision_engine import analyze
from services.predictor import ModelUnavailable, predict_row


def analyse_session(row, selected_parameters, weights, model_metadata):
    """Retourne (resultat du moteur, resultat ML ou None, poids appliques).

    - Modele absent ou illisible : l'analyse se fait sans lui (ml_result
      vaut None), le moteur sait conclure sur la seule base technique.
    - Modele qui ne bat pas la reference naive : il n'a pas montre qu'il
      prevoyait quoi que ce soit. Le laisser peser dans le score reviendrait
      a y melanger du bruit ; son poids est mis a zero et sa probabilite
      reste disponible a titre indicatif.
    """

    try:

        ml_result = predict_row(row)

    except ModelUnavailable:

        ml_result = None

    if model_metadata is not None and not model_metadata["beats_baseline"]:

        weights = {**weights, "Machine Learning": 0}

    result = analyze(
        row,
        ml_result,
        selected_parameters,
        weights
    )

    return result, ml_result, weights
