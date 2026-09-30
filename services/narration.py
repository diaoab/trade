"""Texte lu a voix haute par l'assistant de la page Analyse.

Le resume est assemble ici, a partir du resultat de
services.decision_engine.analyze, et non redige par un modele de langage :
l'assistant ne peut donc rien dire que le moteur n'ait calcule. Il est ecrit
pour l'oreille (nombres "sur 100", dates en toutes lettres) et renvoye
phrase par phrase, l'unite que la synthese vocale enchaine le mieux.
"""

import re


MONTHS = [
    "janvier",
    "février",
    "mars",
    "avril",
    "mai",
    "juin",
    "juillet",
    "août",
    "septembre",
    "octobre",
    "novembre",
    "décembre"
]

DECISION_PHRASES = {
    "ACHETER": "le signal est à l'achat",
    "CONSERVER": "le signal est de conserver",
    "VENDRE": "le signal est à la vente"
}


def _number(value):
    """58.0 -> "58", 58.4 -> "58,4" : virgule decimale, sans zero inutile."""

    return f"{round(float(value), 1):g}".replace(".", ",")


def _date(value):
    """Date en toutes lettres : "1er juin 2025", "12 juin 2025"."""

    day = "1er" if value.day == 1 else str(value.day)

    return f"{day} {MONTHS[value.month - 1]} {value.year}"


def _for_speech(reason):
    """Reecrit une raison du moteur, pensee pour l'ecran, de facon a ce que
    la synthese vocale la lise correctement : "57.0%" devient "57 pour
    cent", "64.2/100" devient "64,2 sur 100", "MM20" "moyenne mobile 20"."""

    text = re.sub(r"(\d+)\.0\b", r"\1", reason)
    text = re.sub(r"(\d+)\.(\d+)", r"\1,\2", text)
    text = re.sub(r"\s*%", " pour cent", text)
    text = re.sub(r"/100\b", " sur 100", text)
    text = re.sub(r"\bMM(\d+)", r"moyenne mobile \1", text)

    return text.replace("modèle ML", "modèle d'apprentissage")


def _count(count, singular, plural):

    return f"{count} {singular if count <= 1 else plural}"


def build_narration(
    structure_name,
    session_date,
    result,
    dividend=None
):
    """Renvoie la liste des phrases a lire.

    dividend, s'il est fourni, decrit le prochain detachement :
    {"cutoff": date butoir, "ex_date": date ex-dividende, "amount": montant,
    "days_left": jours entre la seance analysee et la date butoir}.
    """

    sentences = [
        f"Analyse de {structure_name}"
        + (
            f", séance du {_date(session_date)}."
            if session_date is not None
            else "."
        ),

        f"Sur cette séance, {DECISION_PHRASES[result['decision']]}.",

        f"Le score global est de {_number(result['score'])} sur 100, "
        f"avec une confiance de {_number(result['confidence'])} pour cent.",

        f"Dans le détail : analyse technique, "
        f"{_number(result['technical_score'])} sur 100. "
        + (
            f"Modèle d'apprentissage, {_number(result['ml_score'])} sur 100. "
            if result["ml_score"] is not None
            else ""
        )
        + (
            f"Risque, {_number(result['risk_score'])} sur 100."
            if result["risk_score"] is not None
            else "Le risque n'a pas été mesuré."
        ),

        "Côté signaux techniques : "
        + _count(result["positive"], "favorable", "favorables")
        + ", "
        + _count(result["negative"], "défavorable", "défavorables")
        + ", "
        + _count(result["neutral"], "neutre", "neutres")
        + ".",

        "Voici pourquoi."
    ]

    sentences.extend(
        _for_speech(reason)
        for reason in result["reasons"]
    )

    if result.get("liquidity_warnings"):

        sentences.append(
            "Attention, liquidité faible : "
            + " ".join(
                _for_speech(warning)
                for warning in result["liquidity_warnings"]
            )
            + " Les signaux techniques sont moins fiables sur un titre qui "
            "s'échange peu."
        )

    if dividend is not None and dividend["days_left"] >= 0:

        sentences.append(
            "Attention au dividende : la date butoir pour acheter avec droit "
            f"au dividende de {_number(dividend['amount'])} francs par action "
            f"est le {_date(dividend['cutoff'])}, "
            + (
                "c'est-à-dire la séance analysée."
                if dividend["days_left"] == 0
                else "dans "
                + _count(dividend["days_left"], "jour", "jours")
                + "."
            )
            + " Le titre détache son dividende le "
            f"{_date(dividend['ex_date'])}."
        )

    sentences.append(
        "Rappel : cette analyse est expérimentale et ne constitue pas une "
        "recommandation financière personnalisée."
    )

    return sentences
