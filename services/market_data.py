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
from services.trading_calendar import previous_trading_day


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

            "path": path,

            "dividends": clean_dividends(entry.get("dividends", []))
        }

    return structures


def register_structure(symbol, name):
    """Associe un nom lisible a un symbole et le memorise pour les prochaines
    sessions."""

    registry = _read_registry()

    # On ne touche qu'au nom : reimporter un classeur ne doit pas effacer
    # les dividendes deja saisis pour ce titre.
    registry[symbol] = {**registry.get(symbol, {}), "name": name}

    _write_registry(registry)


# =========================================================
# DIVIDENDES
# =========================================================
#
# Le jour du detachement (date ex-dividende), le cours baisse mecaniquement
# du montant du dividende : ce n'est pas une vraie baisse, l'actionnaire a
# touche la difference. Laissee telle quelle, cette marche d'escalier est lue
# par les indicateurs comme un signal de vente (MACD qui plonge, cours qui
# sort de la bande basse de Bollinger, RSI en survente). On la neutralise en
# recalant l'historique anterieur au detachement.

PRICE_COLUMNS = [
    "Close",
    "Open",
    "High",
    "Low"
]


def clean_dividends(entries):
    """Ramene une saisie de dividendes a une liste triee de
    {"ex_date": "AAAA-MM-JJ", "amount": float}, en ecartant les lignes
    incompletes ou invalides (date illisible, montant nul ou negatif)."""

    cleaned = {}

    for entry in entries or []:

        ex_date = pd.to_datetime(
            entry.get("ex_date"),
            errors="coerce"
        )

        amount = pd.to_numeric(
            entry.get("amount"),
            errors="coerce"
        )

        if pd.isna(ex_date) or pd.isna(amount) or amount <= 0:
            continue

        # Une seule ligne par date : la derniere saisie l'emporte.
        cleaned[ex_date.strftime("%Y-%m-%d")] = float(amount)

    return [
        {"ex_date": ex_date, "amount": amount}
        for ex_date, amount in sorted(cleaned.items())
    ]


def set_dividends(symbol, dividends):
    """Enregistre les dividendes d'un titre dans le registre."""

    registry = _read_registry()

    entry = dict(registry.get(symbol, {}))

    entry["dividends"] = clean_dividends(dividends)

    registry[symbol] = entry

    _write_registry(registry)


def cutoff_date(ex_date, extra_holidays=None):
    """Date butoir : derniere seance avant la date ex-dividende, donc
    dernier jour ou acheter le titre donne encore droit au dividende.

    Saute les week-ends et les jours feries de la BRVM (cf.
    services.trading_calendar) ; les fetes mobiles ne sont prises en compte
    que si elles ont ete saisies dans Parametres.
    """

    return previous_trading_day(ex_date, extra_holidays)


def adjust_for_dividends(df, dividends):
    """Recale les cours anterieurs a chaque detachement deja survenu.

    Ajustement proportionnel, la convention des cours "ajustes" : tout ce
    qui precede la date ex-dividende est multiplie par
    1 - dividende / derniere cloture avant detachement. Les seances
    posterieures au dernier detachement ne bougent pas, donc le cours du
    jour reste le cours reellement cote.

    Retourne le DataFrame (avec le cours d'origine conserve dans Close_Raw
    des qu'un ajustement a eu lieu) et la liste des dividendes appliques.
    Un detachement a venir, ou anterieur au debut de l'historique, n'a rien
    a corriger et est ignore.
    """

    applied = []

    if "Date" not in df.columns or df.empty:
        return df, applied

    price_columns = [
        column
        for column in PRICE_COLUMNS
        if column in df.columns
    ]

    adjusted = df.copy()

    adjusted[price_columns] = adjusted[price_columns].astype(float)

    raw_close = df["Close"].astype(float)

    for dividend in clean_dividends(dividends):

        before = df["Date"] < pd.Timestamp(dividend["ex_date"])

        if not before.any() or before.all():
            continue

        factor = 1 - dividend["amount"] / raw_close[before].iloc[-1]

        # Dividende superieur ou egal au cours : saisie manifestement
        # erronee, on ne detruit pas l'historique pour autant.
        if factor <= 0:
            continue

        adjusted.loc[before, price_columns] *= factor

        applied.append(dividend)

    if not applied:
        return df, applied

    adjusted["Close_Raw"] = raw_close

    return adjusted, applied


def load_structure(symbol, with_report=False, adjust_dividends=True):
    """Charge l'historique d'un titre, normalise et trie chronologiquement.

    Par defaut les cours sont ajustes des dividendes enregistres pour ce
    titre (cf. adjust_for_dividends) ; adjust_dividends=False rend les
    cours bruts du fichier.
    """

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

    report["dividends_applied"] = []

    if adjust_dividends:

        df, report["dividends_applied"] = adjust_for_dividends(
            df,
            structures[symbol]["dividends"]
        )

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


def _name_key(name):
    """Forme de comparaison d'un nom : lettres et chiffres seuls, en
    majuscules. "Palm CI", "PALM_CI" et "palmci" donnent "PALMCI"."""

    return re.sub(r"[^A-Z0-9]+", "", _normalize_label(name).upper())


def match_structure_name(name):
    """Renvoie le nom de la structure existante que `name` designe, ou
    `name` tel quel s'il n'en designe aucune.

    Evite qu'un export nomme "PALMCI.xlsx" cree un doublon de la structure
    "PALM CI" au lieu de completer son historique.
    """

    key = _name_key(name)

    for symbol, structure in get_structures().items():

        if key in (_name_key(structure["name"]), _name_key(symbol)):
            return structure["name"]

    return name


def save_uploaded_structure(uploaded_file, name):
    """Valide puis enregistre un classeur depose depuis l'application.

    Le fichier n'est ecrit dans data/ que si prepare_dataframe() a reussi a
    l'interpreter, pour qu'un export mal forme ne pollue pas le catalogue.
    Si une structure porte deja ce nom, ses seances sont completees par
    celles du nouveau fichier (rapport : "updated", "rows_added").
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

    report["rows_added"] = len(df)

    report["updated"] = path.exists()

    if report["updated"] and "Date" in df.columns:

        # Meme nom qu'une structure existante : on complete son historique
        # au lieu de l'ecraser. Un export recent ne couvre souvent que les
        # dernieres seances ; le reimporter ne doit pas faire perdre les
        # annees deja en base. Sur une seance presente des deux cotes, le
        # nouveau fichier l'emporte (cours corrige par le fournisseur).
        existing, _ = prepare_dataframe(
            pd.read_excel(path)
        )

        if "Date" in existing.columns:

            report["rows_added"] = int(
                (~df["Date"].isin(existing["Date"])).sum()
            )

            df = (
                pd.concat([existing, df], ignore_index=True)
                .drop_duplicates(subset=["Date"], keep="last")
                .sort_values("Date")
                .reset_index(drop=True)
            )

            report["rows_out"] = len(df)

    df.to_excel(path, index=False)

    symbol = _symbol_from_path(path)

    register_structure(symbol, name.strip())

    report["symbol"] = symbol

    report["name"] = name.strip()

    return symbol, report
