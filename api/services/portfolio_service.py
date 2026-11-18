"""Portefeuille d'un utilisateur, valorise au dernier cours connu.

Un achat se fait au cours actuel (dernier cours connu) et a la date du
jour : ni achat date dans le futur ou le passe, ni prix saisi a la main.
"""

import logging
from datetime import date

import pandas as pd

from core.engine import market_data
from core.engine.portfolio import value_position

from api.config import settings as app_settings
from api.errors.app_error import NotFoundError, PlanLimitError, ServiceUnavailableError
from api.models import Position
from api.services import market_service
from api.utils.format_user import plan_limits


logger = logging.getLogger(__name__)


def require_structure(symbol):

    if symbol not in market_data.get_structures():
        raise NotFoundError(f"Titre inconnu : {symbol}")


def _position_out(position, settings, structures):

    out = {
        "id": position.id,
        "symbol": position.symbol,
        "name": structures.get(position.symbol, {}).get("name", position.symbol),
        "quantity": position.quantity,
        "buy_price": position.buy_price,
        "buy_date": position.buy_date.isoformat(),
        "last_close": None,
        "last_date": None,
        "awaiting_quote": False,
        "valuation": None
    }

    if position.symbol not in structures:
        return out

    try:
        prepared = market_service.load_prepared(
            position.symbol,
            settings["adjust_dividends"]
        )
    except (FileNotFoundError, ValueError):
        return out

    quoted = prepared.get("Close_Raw", prepared["Close"])

    last_close = float(quoted.iloc[-1])

    last_date = prepared["Date"].iloc[-1]

    out["last_close"] = last_close

    out["last_date"] = pd.Timestamp(last_date).strftime("%Y-%m-%d")

    # Achat posterieur au dernier cours connu : aucun cours ne dit encore ce
    # que vaut la position, la chiffrer au cours d'avant l'achat donnerait un
    # resultat sans rapport avec la realite.
    # (Un achat fait au dernier cours, a la date du jour, reste valorise :
    # son cours d'achat est ce dernier cours.)
    if _awaiting(position.buy_date, last_date):
        out["awaiting_quote"] = True
        return out

    out["valuation"] = value_position(
        {
            "quantity": position.quantity,
            "buy_price": position.buy_price,
            "buy_date": position.buy_date.isoformat()
        },
        last_close,
        pd.Timestamp(last_date),
        structures[position.symbol]["dividends"],
        settings["round_trip_fee"]
    )

    return out


def _awaiting(buy_date, last_date):

    gap = (pd.Timestamp(buy_date) - pd.Timestamp(last_date)).days

    if gap <= 0:
        return False

    return app_settings.MAX_QUOTE_AGE_DAYS is not None and gap > app_settings.MAX_QUOTE_AGE_DAYS


def _is_stale(last_date, today):

    if app_settings.MAX_QUOTE_AGE_DAYS is None:
        return False

    return (pd.Timestamp(today) - pd.Timestamp(last_date)).days > app_settings.MAX_QUOTE_AGE_DAYS


def current_quote(symbol, settings, today=None):
    """(cours, date de seance) du dernier cours connu du titre. Si ce cours
    est trop ancien, relit d'abord les cours du jour (AUTO_REFRESH_QUOTES) ;
    ServiceUnavailableError s'il l'est toujours."""

    today = today or date.today()

    def last():
        prepared = market_service.load_prepared(symbol, settings["adjust_dividends"])
        quoted = prepared.get("Close_Raw", prepared["Close"])
        return float(quoted.iloc[-1]), pd.Timestamp(prepared["Date"].iloc[-1])

    price, day = last()

    missing = []

    if _is_stale(day, today) and app_settings.AUTO_REFRESH_QUOTES:

        from api.services import quotes_feed, sika_feed

        try:
            if quotes_feed.QUOTES_FEED_URL:
                quotes_feed.refresh()
            else:
                # Lecture partagee, au plus toutes les 10 minutes : des essais
                # d'achat repetes ne relisent pas la page a chaque fois.
                missing = sika_feed.refresh().get("missing", [])
            price, day = last()
        except Exception as error:  # flux indisponible : refus plus bas
            logger.warning("Cours du jour indisponibles : %s", error)

    if _is_stale(day, today):

        name = market_data.get_structures().get(symbol, {}).get("name", symbol)

        if name in missing:
            raise ServiceUnavailableError(
                f"{name} n'est pas coté sur Sika Finance : son cours du jour ne peut pas être récupéré "
                f"(dernier cours connu : {day.strftime('%d/%m/%Y')}). Achat impossible tant que son "
                "historique n'est pas mis à jour depuis le back-office."
            )

        raise ServiceUnavailableError(
            f"Le cours du jour de {name} n'est pas disponible (dernier cours : {day.strftime('%d/%m/%Y')}). "
            "Achat impossible pour l'instant, réessaie plus tard."
        )

    return price, day


def portfolio(user):

    settings = market_service.user_settings(user.preferences)

    structures = market_data.get_structures()

    positions = [
        _position_out(position, settings, structures)
        for position in user.positions
    ]

    valued = [p["valuation"] for p in positions if p["valuation"]]

    totals = {
        key: sum(v[key] for v in valued)
        for key in ("cost", "value", "dividends", "fees", "net")
    }

    totals["net_pct"] = totals["net"] / totals["cost"] * 100 if totals["cost"] else None

    # Seance la plus ancienne parmi les cours utilises : la valorisation
    # n'est pas plus recente que celle-ci.
    dates = [p["last_date"] for p in positions if p["valuation"]]

    totals["as_of"] = min(dates) if dates else None

    # Positions achetees apres le dernier cours : exclues des totaux.
    totals["awaiting_quote"] = sum(1 for p in positions if p["awaiting_quote"])

    return market_service.to_json({"positions": positions, "totals": totals})


def add_position(db, user, values, today=None):
    """Achat de values["quantity"] actions de values["symbol"] au cours
    actuel, a la date du jour (buy_price et buy_date recus sont ignores)."""

    require_structure(values["symbol"])

    limit = plan_limits(user)["positions"]

    if limit is not None and len(user.positions) >= limit:
        raise PlanLimitError(
            f"L'offre gratuite est limitée à {limit} lignes de portefeuille. "
            "Passe à l'offre Pro pour en ajouter davantage."
        )

    settings = market_service.user_settings(user.preferences)

    price, _ = current_quote(values["symbol"], settings, today)

    db.add(Position(
        user_id=user.id,
        symbol=values["symbol"],
        quantity=values["quantity"],
        buy_price=price,
        buy_date=today or date.today()
    ))

    db.commit()

    db.refresh(user)

    return portfolio(user)


def delete_position(db, user, position_id):

    position = db.get(Position, position_id)

    if position is None or position.user_id != user.id:
        raise NotFoundError("Position introuvable.")

    db.delete(position)

    db.commit()

    db.refresh(user)

    return portfolio(user)
