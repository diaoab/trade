"""Assistant conversationnel de la page Analyse (API Claude).

Repond aux questions de l'utilisateur sur l'analyse affichee. Il ne calcule
rien lui-meme : il recoit le resultat du moteur de decision (scores, raisons,
dividende, liquidite) et l'explique. Contrairement a l'assistant vocal
(services.avatar), il passe par un service externe payant et demande une cle
d'API ; sans elle, le reste de l'application fonctionne a l'identique.

    export ANTHROPIC_API_KEY=...   (avant de lancer l'application)
"""

import json

from services.narration import build_narration


MODEL = "claude-opus-5-5"

# Bascule automatique sur un autre modele si celui-ci decline une requete
# (parametre "fallbacks" de l'API, en beta).
FALLBACK_BETA = "server-side-fallback-2026-07-01"

# Questions-reponses courtes sur des donnees fournies : le niveau d'effort
# le plus bas suffit et limite le cout de chaque reponse.
EFFORT = "low"

MAX_TOKENS = 16000

SYSTEM_PROMPT = """\
Tu es l'assistant d'une application expérimentale d'analyse de titres cotés \
à la BRVM. L'utilisateur vient de lancer une analyse et te pose des questions \
sur son résultat. Il n'est pas forcément familier de l'analyse technique : \
explique simplement, en français, en quelques phrases, sans tableau ni titre.

Tout ce que tu sais de cette analyse figure ci-dessous. Appuie-toi \
uniquement sur ces éléments pour parler du titre : si la réponse ne s'y \
trouve pas (actualité de la société, résultats financiers, cours futurs, \
autres titres), dis-le plutôt que de le supposer. Tu peux en revanche \
expliquer librement les notions générales (ce qu'est un RSI, une date \
ex-dividende, la liquidité).

L'application ne connaît ni le portefeuille ni la situation de \
l'utilisateur, et ses signaux sont expérimentaux : le modèle et le moteur \
de décision ont un pouvoir prédictif faible. Présente donc la décision \
comme le signal produit par l'application, avec ses limites, et non comme \
un conseil d'achat ou de vente personnalisé. Si l'utilisateur demande ce \
qu'il doit faire de son argent, explique ce que le signal dit et ne dit \
pas, et laisse-lui la décision.

Résultat de l'analyse :
"""


class AssistantUnavailable(RuntimeError):
    """L'assistant ne peut pas repondre : paquet absent, cle manquante ou
    refusee, service injoignable. Le message est destine a l'utilisateur."""


def build_context(structure_name, session_date, result, ml_result, dividend):
    """Texte decrivant l'analyse, place dans le prompt systeme.

    Reprend le resume lu par l'assistant vocal, suivi des valeurs brutes :
    le modele peut ainsi citer un chiffre exact sans le reconstituer.
    """

    summary = " ".join(
        build_narration(structure_name, session_date, result, dividend)
    )

    details = {
        "decision": result["decision"],
        "score_global": result["score"],
        "confiance": result["confidence"],
        "score_technique": result["technical_score"],
        "score_modele_ml": result["ml_score"],
        "score_risque": result["risk_score"],
        "probabilite_ml_forte_performance_5_seances": (
            ml_result["probability_up"]
            if ml_result is not None
            else None
        ),
        "signaux_favorables": int(result["positive"]),
        "signaux_defavorables": int(result["negative"]),
        "signaux_neutres": int(result["neutral"]),
        "raisons": result["reasons"],
        "alertes_liquidite": result.get("liquidity_warnings", [])
    }

    return (
        summary
        + "\n\nValeurs brutes :\n"
        + json.dumps(details, ensure_ascii=False, indent=2, sort_keys=True)
    )


def stream_answer(context, history, client=None):
    """Genere la reponse a la derniere question de `history`, morceau par
    morceau (a passer a st.write_stream).

    history : messages au format de l'API, le dernier etant la question. La
    reponse complete y est ajoutee a la fin de la generation, avec tous ses
    blocs (et pas seulement le texte) : l'API en a besoin tels quels au tour
    suivant.

    Leve AssistantUnavailable avec un message lisible en cas d'echec.
    """

    try:
        import anthropic
    except ImportError as error:
        raise AssistantUnavailable(
            "Le paquet `anthropic` n'est pas installé : "
            "`python -m pip install -r requirements.txt`."
        ) from error

    try:

        if client is None:
            client = anthropic.Anthropic()

        with client.beta.messages.stream(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT + context,
            messages=history,
            output_config={"effort": EFFORT},
            betas=[FALLBACK_BETA],
            fallbacks="default"
        ) as stream:

            for text in stream.text_stream:
                yield text

            final = stream.get_final_message()

    except (anthropic.AuthenticationError, TypeError) as error:

        # TypeError : le SDK le leve a l'envoi quand aucune cle n'est
        # configuree.
        raise AssistantUnavailable(
            "Clé d'API absente ou refusée. Définis la variable "
            "d'environnement `ANTHROPIC_API_KEY` avant de lancer "
            "l'application."
        ) from error

    except anthropic.RateLimitError as error:

        raise AssistantUnavailable(
            "Trop de requêtes pour l'instant : réessaie dans une minute."
        ) from error

    except anthropic.APIStatusError as error:

        raise AssistantUnavailable(
            f"Le service a répondu par une erreur ({error.status_code}) : "
            f"{error.message}"
        ) from error

    except anthropic.APIConnectionError as error:

        raise AssistantUnavailable(
            "Service injoignable : vérifie la connexion internet."
        ) from error

    if final.stop_reason == "refusal":

        yield "Je ne peux pas répondre à cette question."

    elif final.stop_reason == "max_tokens":

        yield " […réponse interrompue, trop longue.]"

    history.append({"role": "assistant", "content": final.content})
