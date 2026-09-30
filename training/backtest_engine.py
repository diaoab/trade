"""Backtest des signaux techniques sur tout l'historique de data/.

    python -m training.backtest_engine

Affiche, pour chaque indicateur du moteur de decision, ce que le cours a
fait dans les seances qui ont suivi un signal favorable, neutre ou
defavorable, et enregistre le tableau dans results/engine_backtest.csv.
Voir services/backtest.py pour la methode et ses limites.
"""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(
    0,
    str(Path(__file__).resolve().parent.parent)
)

from config import RESULT_DIR
from services.backtest import (
    HORIZON_SESSIONS,
    replay_signals,
    summarize_scores,
    summarize_signals
)
from services.market_data import load_all_structures


BACKTEST_PATH = RESULT_DIR / "engine_backtest.csv"


def main():

    histories = {
        symbol: history
        for symbol, (history, _) in load_all_structures().items()
    }

    if not histories:

        raise FileNotFoundError(
            "Aucun historique exploitable dans data/."
        )

    replayed = replay_signals(histories)

    signals = summarize_signals(replayed)

    scores = summarize_scores(replayed)

    pd.set_option("display.width", 200)
    pd.set_option("display.float_format", "{:.2f}".format)

    print(
        f"{len(replayed)} seances rejouees sur {len(histories)} titre(s), "
        f"variation mesuree a {HORIZON_SESSIONS} seances.\n"
    )

    print(signals.to_string(index=False))

    print()

    print(scores.to_string(index=False))

    signals.to_csv(BACKTEST_PATH, index=False)

    print(f"\n-> {BACKTEST_PATH}")


if __name__ == "__main__":
    main()
