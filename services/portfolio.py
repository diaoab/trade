"""Portefeuille de l'utilisateur : les lignes qu'il detient reellement.

Sans lui, l'application ne sait pas si un signal VENDRE concerne un titre
detenu ou non. Les positions sont saisies a la main dans la page
Portefeuille et gardees dans data/portfolio.json (donnees personnelles,
hors depot git).
"""

import json

import pandas as pd

from config import DATA_DIR


PORTFOLIO_PATH = DATA_DIR / "portfolio.json"


def clean_positions(entries):
    """Ramene une saisie a une liste triee de positions valides :
    {"symbol", "quantity", "buy_price", "buy_date": "AAAA-MM-JJ"}."""

    positions = []

    for entry in entries or []:

        quantity = pd.to_numeric(entry.get("quantity"), errors="coerce")

        buy_price = pd.to_numeric(entry.get("buy_price"), errors="coerce")

        buy_date = pd.to_datetime(entry.get("buy_date"), errors="coerce")

        if (
            not entry.get("symbol")
            or pd.isna(quantity)
            or pd.isna(buy_price)
            or pd.isna(buy_date)
            or quantity <= 0
            or buy_price <= 0
        ):
            continue

        positions.append({
            "symbol": str(entry["symbol"]),
            "quantity": float(quantity),
            "buy_price": float(buy_price),
            "buy_date": buy_date.strftime("%Y-%m-%d")
        })

    return sorted(
        positions,
        key=lambda position: (position["buy_date"], position["symbol"])
    )


def load_positions():

    if not PORTFOLIO_PATH.exists():
        return []

    try:

        with open(PORTFOLIO_PATH, encoding="utf-8") as handle:
            return clean_positions(json.load(handle))

    except (json.JSONDecodeError, OSError, AttributeError, TypeError):

        return []


def save_positions(positions):

    with open(PORTFOLIO_PATH, "w", encoding="utf-8") as handle:

        json.dump(
            clean_positions(positions),
            handle,
            ensure_ascii=False,
            indent=2
        )


def value_position(position, last_close, last_date, dividends, fee):
    """Chiffre une position a la derniere seance connue.

    last_close : dernier cours REELLEMENT cote (non ajuste des dividendes).
    dividends : dividendes du titre ({"ex_date", "amount"}). fee : frais
    d'un aller-retour en pourcentage.

    - dividendes encaisses : ceux detaches apres l'achat et jusqu'a la
      derniere seance ; un titre achete le jour du detachement ou apres n'y
      a pas droit.
    - resultat net : plus-value latente + dividendes - frais. Les frais
      sont estimes sur le montant investi (l'aller-retour complet, vente
      comprise), pour donner ce qu'il resterait en vendant aujourd'hui.
    """

    cost = position["quantity"] * position["buy_price"]

    value = position["quantity"] * last_close

    buy_date = pd.Timestamp(position["buy_date"])

    received = sum(
        dividend["amount"] * position["quantity"]
        for dividend in dividends
        if buy_date < pd.Timestamp(dividend["ex_date"]) <= last_date
    )

    fees = cost * fee / 100

    net = value - cost + received - fees

    return {
        "cost": cost,
        "value": value,
        "gain": value - cost,
        "gain_pct": (value / cost - 1) * 100,
        "dividends": received,
        "fees": fees,
        "net": net,
        "net_pct": net / cost * 100
    }
