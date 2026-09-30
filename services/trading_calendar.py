"""Jours de fermeture de la BRVM, pour situer la date butoir d'un dividende.

La BRVM, a Abidjan, suit les jours feries de Cote d'Ivoire. Deux familles :

- les fetes a date fixe et celles calees sur Paques, calculees ici ;
- les fetes musulmanes (lendemain de la Nuit du Destin, Ramadan, Tabaski,
  Maouloud), fixees chaque annee par decret d'apres l'observation de la
  lune : impossibles a calculer a l'avance, elles se saisissent dans la
  page Parametres et sont gardees dans data/holidays.json.
"""

import datetime
import json

import pandas as pd

from config import DATA_DIR


HOLIDAYS_PATH = DATA_DIR / "holidays.json"

# (mois, jour, nom)
FIXED_HOLIDAYS = [
    (1, 1, "Jour de l'an"),
    (5, 1, "Fête du travail"),
    (8, 7, "Fête de l'indépendance"),
    (8, 15, "Assomption"),
    (11, 1, "Toussaint"),
    (11, 15, "Journée nationale de la paix"),
    (12, 25, "Noël")
]

# (jours apres le dimanche de Paques, nom)
EASTER_HOLIDAYS = [
    (1, "Lundi de Pâques"),
    (39, "Ascension"),
    (50, "Lundi de Pentecôte")
]


def easter_sunday(year):
    """Dimanche de Paques (calendrier gregorien, algorithme de Meeus)."""

    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    g = (8 * b + 13) // 25
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 19 * l) // 433
    month = (h + l - 7 * m + 90) // 25
    day = (h + l - 7 * m + 33 * month + 19) % 32

    return datetime.date(year, month, day)


def computed_holidays(year):
    """Feries calculables de l'annee : {date: nom}."""

    holidays = {
        datetime.date(year, month, day): name
        for month, day, name in FIXED_HOLIDAYS
    }

    easter = easter_sunday(year)

    for offset, name in EASTER_HOLIDAYS:
        holidays[easter + datetime.timedelta(days=offset)] = name

    return holidays


def _clean_dates(values):

    dates = pd.to_datetime(list(values or []), errors="coerce")

    return sorted({date.date() for date in dates if not pd.isna(date)})


def load_extra_holidays():
    """Jours de fermeture saisis a la main (fetes mobiles), tries."""

    if not HOLIDAYS_PATH.exists():
        return []

    try:

        with open(HOLIDAYS_PATH, encoding="utf-8") as handle:
            return _clean_dates(json.load(handle))

    except (json.JSONDecodeError, OSError, TypeError):

        return []


def save_extra_holidays(dates):

    with open(HOLIDAYS_PATH, "w", encoding="utf-8") as handle:

        json.dump(
            [date.isoformat() for date in _clean_dates(dates)],
            handle,
            indent=2
        )


def is_trading_day(date, extra_holidays=()):

    return (
        date.weekday() < 5
        and date not in computed_holidays(date.year)
        and date not in extra_holidays
    )


def previous_trading_day(date, extra_holidays=None):
    """Derniere seance strictement avant `date`.

    extra_holidays=None relit data/holidays.json ; passer une liste permet
    de tester, ou de previsualiser une saisie pas encore enregistree.
    """

    if extra_holidays is None:
        extra_holidays = load_extra_holidays()

    extra_holidays = set(extra_holidays)

    day = pd.Timestamp(date).date() - datetime.timedelta(days=1)

    while not is_trading_day(day, extra_holidays):
        day -= datetime.timedelta(days=1)

    return pd.Timestamp(day)
