"""Portefeuille d'un utilisateur, valorise au dernier cours connu."""

import pandas as pd

from core.engine import market_data
from core.engine.portfolio import value_position

from api.errors.app_error import NotFoundError
from api.models import Position
from api.services import market_service


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
    if pd.Timestamp(position.buy_date) > pd.Timestamp(last_date):
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


def add_position(db, user, values):

    require_structure(values["symbol"])

    db.add(Position(user_id=user.id, **values))

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
