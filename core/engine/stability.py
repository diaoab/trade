"""Stabilisation du signal : score lisse et marge autour des seuils.

Le score brut d'une seance avance par paliers (un indicateur qui change de
sens deplace le score de 8 a 12 points) : sur 3 ans, le signal brut
changeait environ 60 fois par an et par titre, souvent pour revenir des le
lendemain. Un utilisateur a qui l'on dit d'acheter, puis de vendre, puis
d'acheter a nouveau perd confiance.

Deux protections, simulees sur 3 ans de BIBI CI, PALM CI et TOTAL CI :

- le score affiche est une moyenne mobile exponentielle du score brut
  (SMOOTHING_ALPHA) : un pic d'une seance ne suffit plus a franchir un
  seuil ;
- pour quitter la zone du signal en cours, le score lisse doit depasser le
  seuil d'au moins DECISION_MARGIN points (hysteresis).

Resultat de la simulation : environ 17 changements par an au lieu de 60, et
une rentabilite moyenne a 20 seances apres un signal Achat de +2,4 % (contre
+1,8 % pour le signal brut). Echantillon court et sur 3 titres seulement :
a reverifier quand toute la cote sera chargee.
"""

from core.engine.decision_engine import (
    CONFIDENCE_MAX,
    CONFIDENCE_MIN,
    DECISION_BUY_THRESHOLD,
    DECISION_HOLD_THRESHOLD
)


SMOOTHING_ALPHA = 0.3

DECISION_MARGIN = 3

# Seances calculees avant celles que l'on affiche : le poids de la plus
# ancienne dans la moyenne lissee tombe alors sous 0,1 % (0,7 ** 20).
WARMUP_SESSIONS = 20


def _decision(score, current):
    """Zone du score lisse, la marge jouant en faveur du signal en cours."""

    if current is None:
        hold, buy = DECISION_HOLD_THRESHOLD, DECISION_BUY_THRESHOLD
    else:
        hold = DECISION_HOLD_THRESHOLD - DECISION_MARGIN if current in ("CONSERVER", "ACHETER") else DECISION_HOLD_THRESHOLD + DECISION_MARGIN
        buy = DECISION_BUY_THRESHOLD - DECISION_MARGIN if current == "ACHETER" else DECISION_BUY_THRESHOLD + DECISION_MARGIN

    if score >= buy:
        return "ACHETER"

    if score >= hold:
        return "CONSERVER"

    return "VENDRE"


def _confidence(score):
    """Meme regle que decision_engine : ecart a la neutralite (50)."""

    return round(min(CONFIDENCE_MAX, max(CONFIDENCE_MIN, abs(score - 50) * 2)), 1)


def stabilize(results):
    """Resultats du moteur, de la seance la plus ancienne a la plus recente,
    avec le signal stabilise.

    Chaque resultat garde son detail et recoit :
    - score : score lisse, celui qui fonde la decision ;
    - session_score / session_decision : score et decision bruts de la
      seance ;
    - decision et confidence recalculees sur le score lisse.
    """

    stable = []

    smoothed = None

    decision = None

    for result in results:

        raw = result["score"]

        smoothed = raw if smoothed is None else SMOOTHING_ALPHA * raw + (1 - SMOOTHING_ALPHA) * smoothed

        decision = _decision(smoothed, decision)

        stable.append({
            **result,
            "session_score": raw,
            "session_decision": result["decision"],
            "score": round(smoothed, 2),
            "decision": decision,
            "confidence": _confidence(smoothed)
        })

    return stable
