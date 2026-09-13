"""Chargement et normalisation des historiques de cotation BRVM.

Ce module est la seule porte d'entree des donnees : l'application Streamlit
et le script d'entrainement passent tous les deux par ici, pour qu'un titre
soit lu exactement de la meme facon des deux cotes.
"""

import datetime
import json
import logging
import re
import unicodedata

import pandas as pd

from config import DATA_DIR, REGISTRY_PATH, REQUIRED_COLUMNS


logger = logging.getLogger(__name__)


# =========================================================
# DETECTION DES COLONNES
# =========================================================

COLUMN_CANDIDATES = {

    "Date": [
        "date",
        "seance"
    ],

    "Close": [
        "close",
        "cloture",
        "closing price",
        "prix cloture",
        "dernier",
        "cours"
    ],

    "Open": [
        "open",
        "ouverture"
    ],

    "High": [
        "high",
        "plus haut",
        "plushaut"
    ],

    "Low": [
        "low",
        "plus bas",
        "plusbas"
    ],

    "Volume": [
        "volume",
        "volume titres",
        "titres echanges"
    ],

    "Variation": [
        "variation %",
        "variation%",
        "variation",
        "var %"
    ]
}


def _normalize_label(label):
    """Reduit un nom de colonne a une forme comparable : sans accent, sans
    ponctuation, en minuscules. "Cloture" et "CLOTURE" deviennent "cloture".
    """

    text = unicodedata.normalize(
        "NFKD",
        str(label)
    )

    text = "".join(
        char
        for char in text
        if not unicodedata.combining(char)
    )

    text = text.lower().strip()

    text = re.sub(
        r"[\s_]+",
        " ",
        text
    )

    return text


def normalize_columns(df):
    """Renomme les colonnes vers le vocabulaire interne (Date, Close, ...).

    Retourne le DataFrame renomme et la correspondance appliquee, utile pour
    montrer a l'utilisateur ce qui a ete reconnu dans son fichier.
    """

    lookup = {
        _normalize_label(column): column
        for column in df.columns
    }

    rename_map = {}

    for target, candidates in COLUMN_CANDIDATES.items():

        for candidate in candidates:

            source = lookup.get(candidate)

            if source is not None and source not in rename_map:

                rename_map[source] = target

                break

    return df.rename(columns=rename_map), rename_map


# =========================================================
# DATES
# =========================================================

DATE_TYPES = (
    pd.Timestamp,
    datetime.datetime,
    datetime.date
)


def _swap_day_month(value):
    """Echange jour et mois d'une date, ou renvoie NaT si le resultat n'existe
    pas (un 25 ne peut pas devenir un mois)."""

    try:

        return pd.Timestamp(
            year=value.year,
            month=value.day,
            day=value.month
        )

    except ValueError:

        return pd.NaT


def _parse_text_date(value):

    return pd.to_datetime(
        value,
        dayfirst=False,
        errors="coerce"
    )


def _count_inversions(series):
    """Nombre de fois ou la serie recule dans le temps."""

    valid = series.dropna()

    if len(valid) < 2:
        return 0

    return int(
        (valid.diff().dropna() < pd.Timedelta(0)).sum()
    )


def parse_dates(series):
    """Reconstruit une colonne de dates fiable a partir d'un export Excel.

    Excel decide cellule par cellule, selon sa locale, si "1/3/2023" est le
    1er mars ou le 3 janvier. Sur les exports BRVM, cela convertit en date
    reelle toutes les seances dont le jour est <= 12 -- en inversant jour et
    mois -- et laisse les autres en texte. Le tri chronologique se retrouve
    alors fausse sans qu'aucune erreur ne soit levee.

    On construit donc les deux lectures possibles et on garde celle qui rend
    la serie chronologique, un export de cotations etant toujours ordonne.
    En cas d'egalite on conserve la lecture brute, pour ne rien casser sur un
    fichier deja correct.
    """

    has_datetime_cell = series.map(
        lambda value: isinstance(value, DATE_TYPES)
    ).any()

    as_read = series.map(
        lambda value: pd.Timestamp(value)
        if isinstance(value, DATE_TYPES)
        else _parse_text_date(value)
    )

    swapped = series.map(
        lambda value: _swap_day_month(pd.Timestamp(value))
        if isinstance(value, DATE_TYPES)
        else _parse_text_date(value)
    )

    as_read_inversions = _count_inversions(as_read)
    swapped_inversions = _count_inversions(swapped)

    day_month_swapped = bool(
        has_datetime_cell
        and swapped_inversions < as_read_inversions
        and swapped.isna().sum() <= as_read.isna().sum()
    )

    dates = swapped if day_month_swapped else as_read

    info = {

        "day_month_swapped": day_month_swapped,

        "inversions": (
            swapped_inversions
            if day_month_swapped
            else as_read_inversions
        ),

        "unparsed": int(dates.isna().sum())
    }

    return dates, info


# =========================================================
# NETTOYAGE
# =========================================================

NUMERIC_COLUMNS = [
    "Close",
    "Open",
    "High",
    "Low",
    "Volume",
    "Variation"
]


def _to_numeric(series):
    """Convertit une colonne en nombre en tolerant les separateurs de milliers,
    les virgules decimales et les pourcentages des exports francophones."""

    # object couvre les colonnes texte "classiques" issues d'openpyxl -- y
    # compris quand elles melangent cellules numeriques et cellules texte
    # (cas frequent sur les exports BRVM). is_string_dtype seul ne suffit
    # pas : sur une colonne object au contenu mixte, pandas le renvoie a
    # False (il exige un contenu uniformement textuel), ce qui laisserait
    # passer les cellules texte telles quelles vers to_numeric. pandas >= 3.0
    # peut aussi renvoyer un dtype "str" natif pour une colonne purement
    # textuelle : is_object_dtype seul ne le couvrirait pas. Il faut les deux.
    if (
        pd.api.types.is_object_dtype(series)
        or pd.api.types.is_string_dtype(series)
    ):

        series = (
            series
            .astype(str)
            .str.replace(r"[\s  ]", "", regex=True)
            .str.replace("%", "", regex=False)
            .str.replace(",", ".", regex=False)
        )

    return pd.to_numeric(
        series,
        errors="coerce"
    )


def prepare_dataframe(df):
    """Applique la chaine complete : colonnes, dates, types, tri, nettoyage.

    Retourne le DataFrame pret a l'emploi et un rapport decrivant ce qui a ete
    reconnu, corrige ou ecarte.
    """

    df, rename_map = normalize_columns(df)

    missing = [
        column
        for column in REQUIRED_COLUMNS
        if column not in df.columns
    ]

    if missing:

        raise ValueError(
            "Colonne introuvable : "
            + ", ".join(missing)
            + ". Le fichier doit contenir au minimum un prix de cloture "
            "(colonne Close ou Cloture)."
        )

    report = {
        "columns": rename_map,
        "rows_in": len(df)
    }

    if "Date" in df.columns:

        dates, date_info = parse_dates(df["Date"])

        df["Date"] = dates

        report.update(date_info)

        df = (
            df
            .dropna(subset=["Date"])
            .sort_values("Date")
            .drop_duplicates(subset=["Date"], keep="last")
        )

    else:

        report["day_month_swapped"] = False

        report["no_date_column"] = True

    for column in NUMERIC_COLUMNS:

        if column in df.columns:

            df[column] = _to_numeric(df[column])

    df = (
        df
        .dropna(subset=["Close"])
        .reset_index(drop=True)
    )

    report["rows_out"] = len(df)

    report["dropped"] = report["rows_in"] - report["rows_out"]

    report["ohlc_issues"] = _check_ohlc(df)

    return df, report


def _check_ohlc(df):
    """Repere les seances dont le plus bas / plus haut contredit l'ouverture ou
    la cloture, en separant deux cas tres differents :

    - une convention recurrente des exports BRVM sur les seances sans
      mouvement (Ouverture == Cloture) : Plus haut et Plus bas y sont
      identiques entre eux mais superieurs aux deux, comme si le
      fournisseur reportait un autre cours (ex. la limite haute autorisee)
      plutot que la fourchette reellement traitee. Verifie sur les trois
      historiques actuellement en base (AGL, BOA, Coris Bank) : ce motif
      explique 100 % des incoherences, jamais dans l'autre sens (le plus
      haut n'est jamais inferieur a l'ouverture/cloture).
    - tout le reste, qui serait une vraie incoherence (plus bas superieur au
      plus haut, ou fourchette qui ne contient pas l'ouverture/cloture sur
      une seance ou le cours a bouge) et meriterait de verifier le fichier
      source.

    Dans les deux cas, High/Low ne sont pas utilises par les indicateurs
    (services.indicators ne s'appuie que sur Close et Volume) : la
    distinction sert seulement a ne pas alarmer l'utilisateur pour un motif
    connu et inoffensif, tout en gardant un vrai signal d'alerte pour le
    reste."""

    if not {"Open", "Close", "High", "Low"}.issubset(df.columns):
        return {"flat_day_quirk": 0, "inconsistent": 0}

    body_low = df[["Open", "Close"]].min(axis=1)
    body_high = df[["Open", "Close"]].max(axis=1)

    contradicts = (
        (df["Low"] > body_low)
        | (df["High"] < body_high)
        | (df["Low"] > df["High"])
    )

    flat_day_quirk = (
        contradicts
        & (df["Open"] == df["Close"])
        & (df["High"] == df["Low"])
        & (df["High"] > df["Open"])
    )

    return {
        "flat_day_quirk": int(flat_day_quirk.sum()),
        "inconsistent": int((contradicts & ~flat_day_quirk).sum())
    }


# =========================================================
# REGISTRE DES STRUCTURES
# =========================================================

def _read_registry():

    if not REGISTRY_PATH.exists():
        return {}

    try:

        with open(REGISTRY_PATH, encoding="utf-8") as handle:
            return json.load(handle)

    except (json.JSONDecodeError, OSError):

        return {}


def _write_registry(registry):

    with open(REGISTRY_PATH, "w", encoding="utf-8") as handle:

        json.dump(
            registry,
            handle,
            ensure_ascii=False,
            indent=2,
            sort_keys=True
        )


def _symbol_from_path(path):

    return re.sub(
        r"[^A-Z0-9]+",
        "_",
        path.stem.upper()
    ).strip("_")


def get_structures():
    """Recense les titres disponibles dans data/.

    Retourne {symbole: {"name": ..., "path": Path}}. Le nom lisible vient de
    data/structures.json quand il existe, sinon du nom de fichier.
    """

    registry = _read_registry()

    structures = {}

    for path in sorted(DATA_DIR.glob("*.xlsx")):

        # Fichiers verrous laisses par Excel quand le classeur est ouvert.
        if path.name.startswith("~$"):
            continue

        symbol = _symbol_from_path(path)

        entry = registry.get(symbol, {})

        structures[symbol] = {

            "name": entry.get("name", path.stem),

            "path": path
        }

    return structures


def register_structure(symbol, name):
    """Associe un nom lisible a un symbole et le memorise pour les prochaines
    sessions."""

    registry = _read_registry()

    registry[symbol] = {"name": name}

    _write_registry(registry)


def load_structure(symbol, with_report=False):
    """Charge l'historique d'un titre, normalise et trie chronologiquement."""

    structures = get_structures()

    if symbol not in structures:

        raise FileNotFoundError(
            f"Aucun historique trouve pour {symbol} dans {DATA_DIR}."
        )

    path = structures[symbol]["path"]

    df, report = prepare_dataframe(
        pd.read_excel(path)
    )

    report["symbol"] = symbol

    report["name"] = structures[symbol]["name"]

    if with_report:
        return df, report

    return df


def load_all_structures():
    """Charge tous les titres disponibles, pour l'entrainement du modele
    partage. Retourne {symbole: (DataFrame, rapport)}."""

    loaded = {}

    for symbol in get_structures():

        try:

            loaded[symbol] = load_structure(
                symbol,
                with_report=True
            )

        except (ValueError, OSError) as error:

            logger.warning(
                "%s ignore a l'entrainement : %s",
                symbol,
                error
            )

    return loaded


def save_uploaded_structure(uploaded_file, name):
    """Valide puis enregistre un classeur depose depuis l'application.

    Le fichier n'est ecrit dans data/ que si prepare_dataframe() a reussi a
    l'interpreter, pour qu'un export mal forme ne pollue pas le catalogue.
    """

    df, report = prepare_dataframe(
        pd.read_excel(uploaded_file)
    )

    filename = re.sub(
        r"[^A-Za-z0-9]+",
        "_",
        name.strip()
    ).strip("_")

    if not filename:

        raise ValueError(
            "Le nom de la structure ne peut pas etre vide."
        )

    path = DATA_DIR / f"{filename}.xlsx"

    df.to_excel(path, index=False)

    symbol = _symbol_from_path(path)

    register_structure(symbol, name.strip())

    report["symbol"] = symbol

    report["name"] = name.strip()

    return symbol, report
