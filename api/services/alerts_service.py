"""Alertes de l'utilisateur : signaux qui ont change et dividendes proches.

Les alertes se deduisent des historiques (aucune table a remplir chaque
soir) : bascules de signal sur les ALERT_SESSIONS dernieres seances de
chaque titre, et date butoir d'un dividende a moins de DIVIDEND_ALERT_DAYS
jours pour les titres detenus. L'utilisateur ne garde qu'une date,
alerts_seen_on : ce qui est date de ce jour ou avant est lu.

Ces memes evenements serviront aux notifications push.
"""

from datetime import date

import pandas as pd

from core.engine import market_data
from core.engine.analysis import latest_sessions, next_dividend_cutoff

from api.services import market_service


# Seances examinees pour les bascules de signal : deux semaines de bourse
# (market_service.HISTORY_SESSIONS en garde une de plus, la reference).
ALERT_SESSIONS = market_service.HISTORY_SESSIONS - 1

# Dividende signale quand la date butoir d'achat est a ce nombre de jours
# ou moins.
DIVIDEND_ALERT_DAYS = 7


def _day(value):

    return pd.Timestamp(value).strftime("%Y-%m-%d")


def _events(preferences):
    """Evenements communs a tous les comptes aux memes reglages."""

    settings = market_service.user_settings(preferences)

    events = []

    for symbol, structure in market_data.get_structures().items():

        history = market_service.decision_history(symbol, preferences)

        if history:

            # Signal stabilise : une bascule annoncee est une vraie bascule,
            # pas un aller-retour d'une seance (cf. core.engine.stability).
            for (_, before, _, _), (session, after, _, _) in zip(history, history[1:]):

                if before["decision"] != after["decision"]:
                    events.append({
                        "kind": "signal",
                        "symbol": symbol,
                        "name": structure["name"],
                        "date": _day(session["Date"]),
                        "before": before["decision"],
                        "after": after["decision"]
                    })

        try:
            prepared = market_service.load_prepared(symbol, settings["adjust_dividends"])
        except (FileNotFoundError, ValueError):
            continue

        sessions = latest_sessions(prepared, count=1)

        if not sessions:
            continue

        last_date = pd.Timestamp(sessions[-1]["Date"])

        dividend = next_dividend_cutoff(structure["dividends"], last_date)

        if dividend and 0 <= dividend["days_left"] <= DIVIDEND_ALERT_DAYS:
            events.append({
                "kind": "dividend",
                "symbol": symbol,
                "name": structure["name"],
                "date": _day(last_date),
                "amount": dividend["amount"],
                "cutoff": _day(dividend["cutoff"]),
                "days_left": dividend["days_left"]
            })

    return events


def cached_events(preferences):

    return market_service.results_cache.get_or_compute(
        market_service.result_key("alerts", preferences),
        lambda: _events(preferences)
    )


def alerts(user):
    """Alertes du compte, les plus recentes d'abord, titres detenus en tete
    a date egale.

    - Dividendes : titres detenus seulement.
    - Signaux : favoris et titres detenus des que l'utilisateur en a ; tous
      les titres sinon (nouveau compte, rien encore de choisi)."""

    held = {position.symbol for position in user.positions}

    favorites = set(user.favorites or [])

    followed = held | favorites

    seen = user.alerts_seen_on.isoformat() if user.alerts_seen_on else None

    items = []

    for event in cached_events(user.preferences):

        if event["kind"] == "dividend" and event["symbol"] not in held:
            continue

        if event["kind"] == "signal" and followed and event["symbol"] not in followed:
            continue

        items.append({
            **event,
            "id": f'{event["kind"]}:{event["symbol"]}:{event["date"]}',
            "held": event["symbol"] in held,
            "favorite": event["symbol"] in favorites,
            "unread": seen is None or event["date"] > seen
        })

    items.sort(key=lambda item: (item["date"], item["held"]), reverse=True)

    return {
        "alerts": items,
        "unread": sum(1 for item in items if item["unread"])
    }


def mark_seen(db, user, today=None):
    """Toutes les alertes actuelles deviennent lues."""

    user.alerts_seen_on = today or date.today()

    db.commit()

    return alerts(user)
