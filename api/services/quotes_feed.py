"""Mise a jour automatique des cours a partir d'un flux de donnees.

Le flux est fourni par un prestataire autorise a redistribuer les cours de
la BRVM (a contractualiser) ; son adresse est QUOTES_FEED_URL. Format
attendu, en CSV ou en JSON (liste d'objets), une ligne par titre et par
seance :

    name,date,open,high,low,close,volume
    PALM CI,2026-10-27,8050,8105,8050,8100,4628

`name` designe le titre comme dans l'application ("PALM CI", "PALMCI" et
"palm_ci" sont reconnus). Les seances deja connues sont mises a jour, les
nouvelles ajoutees (cf. core.engine.market_data.save_uploaded_structure).

Lancer a la main : python -m api.jobs.refresh_market
"""

import io
import logging
import os

import httpx
import pandas as pd

from core.engine.market_data import match_structure_name, save_uploaded_structure


logger = logging.getLogger(__name__)

QUOTES_FEED_URL = os.environ.get("QUOTES_FEED_URL", "")

# En-tete d'authentification eventuel du prestataire, "Nom: valeur".
QUOTES_FEED_HEADER = os.environ.get("QUOTES_FEED_HEADER", "")

COLUMNS = {
    "date": "Date",
    "open": "Open",
    "high": "High",
    "low": "Low",
    "close": "Close",
    "volume": "Volume"
}


def parse_feed(content, content_type=""):
    """Lit le flux (octets) en DataFrame aux colonnes name + COLUMNS."""

    text = content.decode("utf-8-sig").strip()

    if "json" in content_type or text.startswith("["):
        feed = pd.DataFrame(pd.read_json(io.StringIO(text)))
    else:
        feed = pd.read_csv(io.StringIO(text))

    feed.columns = [str(column).strip().lower() for column in feed.columns]

    missing = {"name", "date", "close"} - set(feed.columns)

    if missing:
        raise ValueError("Colonnes absentes du flux : " + ", ".join(sorted(missing)))

    return feed


def apply_feed(feed):
    """Integre les lignes du flux aux historiques. Retourne un rapport par
    titre : {nom: {"symbol", "rows_added"} ou {"error"}}."""

    report = {}

    for name, rows in feed.groupby("name"):

        renamed = rows.rename(columns=COLUMNS)

        history = renamed[
            [column for column in COLUMNS.values() if column in renamed.columns]
        ]

        buffer = io.BytesIO()
        history.to_excel(buffer, index=False)
        buffer.seek(0)

        try:
            symbol, details = save_uploaded_structure(buffer, match_structure_name(str(name)))
            report[str(name)] = {"symbol": symbol, "rows_added": details["rows_added"]}
        except ValueError as error:
            logger.warning("Flux de cours, %s ignore : %s", name, error)
            report[str(name)] = {"error": str(error)}

    return report


def refresh(client=None):
    """Telecharge le flux et l'integre. Leve RuntimeError si aucun flux
    n'est configure."""

    if not QUOTES_FEED_URL:
        raise RuntimeError("QUOTES_FEED_URL n'est pas défini : aucun flux de cours configuré.")

    headers = {}

    if ":" in QUOTES_FEED_HEADER:
        key, value = QUOTES_FEED_HEADER.split(":", 1)
        headers[key.strip()] = value.strip()

    client = client or httpx.Client(timeout=60)

    response = client.get(QUOTES_FEED_URL, headers=headers)
    response.raise_for_status()

    return apply_feed(parse_feed(response.content, response.headers.get("content-type", "")))

