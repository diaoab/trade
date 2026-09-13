"""Construction de la cible d'entrainement : rendement futur et tercile.

Extrait de training/train.py pour etre testable independamment -- importer
training.train execute tout le pipeline d'entrainement (chargement des
donnees, recherche d'hyperparametres...), ce qui est trop lent et trop
dependant de l'environnement pour des tests unitaires.
"""

import numpy as np
import pandas as pd


# La cible est le rendement a 5 jours plutot qu'au lendemain : moins bruite,
# et surtout on ne retient que les seances au rendement futur clairement
# tranche (tiers superieur = 1, tiers inferieur = 0), en ecartant le tiers
# median, ambigu par construction. Les deux classes retenues sont alors
# naturellement equilibrees (~50/50), contrairement au binaire hausse/baisse
# du lendemain qui etait desequilibre (~70/30) et rendait le modele biaise
# vers "jamais de hausse".
FUTURE_HORIZON_DAYS = 5

TERCILE_LOWER_QUANTILE = 1 / 3
TERCILE_UPPER_QUANTILE = 2 / 3


def compute_future_return(close, horizon=FUTURE_HORIZON_DAYS):
    """Rendement entre la seance courante et `horizon` seances plus tard.

    Les dernieres `horizon` valeurs de la serie n'ont pas de futur assez
    lointain : leur rendement vaut NaN.
    """

    return (
        close.shift(-horizon)
        / close
        - 1
    )


def fit_tercile_thresholds(
    future_returns,
    lower_quantile=TERCILE_LOWER_QUANTILE,
    upper_quantile=TERCILE_UPPER_QUANTILE
):
    """Calcule les deux seuils qui delimitent les tiers inferieur/superieur.

    A appeler uniquement sur la portion train (+validation) : apprendre ces
    seuils sur le test ferait fuiter de l'information du futur vers
    l'entrainement.
    """

    lower_threshold, upper_threshold = future_returns.quantile(
        [lower_quantile, upper_quantile]
    )

    return float(lower_threshold), float(upper_threshold)


def label_tercile(future_returns, lower_threshold, upper_threshold):
    """Etiquette 1 le tiers superieur, 0 le tiers inferieur, NaN le tiers
    median (ambigu) -- a ecarter du jeu d'entrainement/test avec dropna().

    Un rendement futur NaN (derniere seance d'une serie, cf.
    compute_future_return) ne satisfait ni l'une ni l'autre condition et
    devient donc naturellement NaN ici aussi, sans traitement special.
    """

    labels = pd.Series(np.nan, index=future_returns.index)

    labels[future_returns >= upper_threshold] = 1

    labels[future_returns <= lower_threshold] = 0

    return labels
