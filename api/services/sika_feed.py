"""Cours du jour lus sur la page publique "cotations de A a Z" de Sika
Finance (https://www.sikafinance.com/marches/aaz).

Source par defaut quand aucun flux de prestataire n'est configure
(QUOTES_FEED_URL vide, cf. quotes_feed). La page donne, pour chaque action
de la BRVM : ouverture, plus haut, plus bas, volume et dernier cours de la
seance en cours (ou de la derniere seance close). Elle n'est pas datee : la
seance est deduite du calendrier de la BRVM (cf. session_date).

Seuls les titres deja suivis par l'application sont mis a jour : une seule
seance ne suffit pas a analyser un nouveau titre.

Avant une mise en production, verifier avec Sika Finance les conditions de
reutilisation de ces cours.
"""

import datetime
import html
import logging
import re
import threading
import time
from html.parser import HTMLParser

import pandas as pd

from core.engine import market_data
from core.engine.trading_calendar import is_trading_day, load_extra_holidays, previous_trading_day


logger = logging.getLogger(__name__)

SIKA_URL = "https://www.sikafinance.com/marches/aaz"

# Ouverture de la BRVM (heure d'Abidjan = UTC) : avant, la page affiche
# encore la seance precedente.
MARKET_OPEN_UTC = datetime.time(9, 0)

# Intervalle minimal entre deux lectures de la page, pour tout le serveur.
MIN_INTERVAL_SECONDS = 10 * 60

# Colonnes du tableau des actions, dans l'ordre de la page.
STOCK_COLUMNS = ["name", "open", "high", "low", "volume", "volume_xof", "close", "variation"]

_lock = threading.Lock()
_last = {"at": 0.0, "report": None}


class _TableParser(HTMLParser):
    """Texte des cellules de chaque tableau de la page."""

    def __init__(self):
        super().__init__()
        self.tables = []
        self._row = None
        self._cell = None
        self._depth = 0

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self._depth += 1
            self.tables.append([])
        elif tag == "tr" and self._depth:
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = []

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._cell is not None:
            self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if self._row:
                self.tables[-1].append(self._row)
            self._row = None
        elif tag == "table" and self._depth:
            self._depth -= 1

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)


def _number(text):
    """ "45 758 880" -> 45758880.0 ; "" ou "-" -> None."""

    cleaned = re.sub(r"[^\d,.\-]", "", html.unescape(text).replace("\xa0", "")).replace(",", ".")

    try:
        return float(cleaned)
    except ValueError:
        return None


def parse_page(content):
    """Actions de la page : DataFrame name, open, high, low, volume, close."""

    parser = _TableParser()
    parser.feed(content if isinstance(content, str) else content.decode("utf-8", "replace"))

    for table in parser.tables:

        header = [cell.lower() for cell in table[0]] if table else []

        if not header or "volume (titres)" not in header:
            continue

        rows = []

        for cells in table[1:]:

            if len(cells) < len(STOCK_COLUMNS):
                continue

            values = dict(zip(STOCK_COLUMNS, cells))
            close = _number(values["close"])

            if not values["name"] or not close:
                continue

            rows.append({
                "name": values["name"],
                "open": _number(values["open"]) or close,
                "high": _number(values["high"]) or close,
                "low": _number(values["low"]) or close,
                "volume": _number(values["volume"]) or 0,
                "close": close
            })

        return pd.DataFrame(rows, columns=["name", "open", "high", "low", "volume", "close"])

    raise ValueError("Tableau des actions introuvable sur la page Sika Finance.")


def session_date(now=None, extra_holidays=None):
    """Seance dont la page affiche les cours : aujourd'hui si c'est un jour
    de bourse et que la seance a ouvert, sinon la seance precedente."""

    now = now or datetime.datetime.now(datetime.timezone.utc)

    if extra_holidays is None:
        extra_holidays = load_extra_holidays()

    today = now.date()

    if is_trading_day(today, set(extra_holidays)) and now.time() >= MARKET_OPEN_UTC:
        return pd.Timestamp(today)

    return previous_trading_day(today, extra_holidays)


def known_rows(page, day):
    """Lignes de la page qui correspondent a un titre suivi, au format du
    flux (cf. quotes_feed.apply_feed) ; et noms des titres suivis absents
    de la page."""

    structures = market_data.get_structures()

    wanted = {
        market_data._name_key(structure["name"]): structure["name"]
        for structure in structures.values()
    }
    wanted.update({
        market_data._name_key(symbol): structure["name"]
        for symbol, structure in structures.items()
    })
    wanted.update({
        market_data._name_key(alias): structure["name"]
        for structure in structures.values()
        for alias in structure.get("aliases", [])
    })

    rows = []
    found = set()

    for record in page.to_dict("records"):

        name = wanted.get(market_data._name_key(record["name"]))

        if name is None or name in found:
            continue

        found.add(name)
        rows.append({**record, "name": name, "date": day.strftime("%Y-%m-%d")})

    missing = sorted({structure["name"] for structure in structures.values()} - found)

    return pd.DataFrame(rows, columns=["name", "date", "open", "high", "low", "close", "volume"]), missing


def fetch(client=None):
    """Telecharge la page (octets)."""

    import httpx

    client = client or httpx.Client(timeout=30, follow_redirects=True)

    response = client.get(SIKA_URL, headers={"User-Agent": "Mozilla/5.0 (compatible; trade-app)"})
    response.raise_for_status()

    return response.content


def refresh(client=None, now=None, force=False):
    """Lit la page et integre les cours des titres suivis. Rapport :
    {"source", "date", "structures": {nom: {...}}, "missing": [...]}.

    Une lecture de moins de MIN_INTERVAL_SECONDS rend le rapport precedent
    (sauf force=True)."""

    from api.services.quotes_feed import apply_feed

    with _lock:

        if not force and _last["report"] and time.monotonic() - _last["at"] < MIN_INTERVAL_SECONDS:
            return {**_last["report"], "cached": True}

        page = parse_page(fetch(client))
        day = session_date(now)
        rows, missing = known_rows(page, day)

        report = {
            "source": "sikafinance",
            "date": day.strftime("%Y-%m-%d"),
            "structures": apply_feed(rows) if len(rows) else {},
            "missing": missing
        }

        _last.update(at=time.monotonic(), report=report)

        logger.info("Cours Sika Finance du %s : %s", report["date"], report["structures"])

        return {**report, "cached": False}
