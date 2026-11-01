"""Assistant conversationnel sur l'analyse d'un titre (API Claude)."""

from datetime import datetime, timezone

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError

from api.services.engine.assistant_chat import AssistantUnavailable, build_context, stream_answer

from api.errors.app_error import ServiceUnavailableError, TooManyRequestsError, ValidationError
from api.models import AssistantUsage
from api.services import account_service, market_service


# Garde-fous sur la conversation envoyee par l'app : le cout d'un appel a
# l'assistant croit avec la longueur de l'historique.
MAX_MESSAGES = 20

MAX_CHARS = 2000


def _clean_history(messages):

    messages = messages[-MAX_MESSAGES:]

    if (
        not messages
        or messages[-1]["role"] != "user"
        or any(message["role"] not in ("user", "assistant") for message in messages)
        or any(len(message["content"]) > MAX_CHARS for message in messages)
    ):
        raise ValidationError("Conversation invalide ou message trop long.")

    # L'API attend une conversation qui commence par l'utilisateur.
    while messages and messages[0]["role"] != "user":
        messages = messages[1:]

    return messages


def ask(db, user, symbol, messages):
    """Repond a la derniere question de `messages` ; l'app garde la
    conversation et la renvoie a chaque question (texte seul)."""

    history = _clean_history(messages)

    try:
        raw = market_service.analyse_raw(symbol, user.preferences)
    except ValueError as error:
        raise ValidationError(str(error))

    context = build_context(
        raw["structure"]["name"],
        raw["session_date"],
        raw["result"],
        raw["ml_result"],
        raw["dividend"],
        (raw["model_metadata"] or {}).get("target_horizon_days")
    )

    # La question est decomptee avant l'appel, en une requete
    # conditionnelle : deux questions envoyees en meme temps ne peuvent pas
    # depasser la limite (chaque appel a l'API Claude est facture).
    day = _reserve(db, user)

    try:
        answer = "".join(stream_answer(context, history))
    except Exception as error:
        _release(db, user, day)
        if isinstance(error, AssistantUnavailable):
            raise ServiceUnavailableError(str(error))
        raise

    return {"answer": answer, "assistant": account_service.assistant_quota(db, user)}


def _reserve(db, user):
    """Decompte une question du quota du jour ; TooManyRequestsError si la
    limite est atteinte. Retourne le jour decompte."""

    day = datetime.now(timezone.utc).date()

    limit = account_service.assistant_quota(db, user)["limit"]

    if account_service.usage_row(db, user) is None:
        try:
            db.add(AssistantUsage(user_id=user.id, day=day, count=0))
            db.commit()
        except IntegrityError:
            # Ligne creee entre-temps par une requete concurrente.
            db.rollback()

    reserved = db.execute(
        update(AssistantUsage)
        .where(
            AssistantUsage.user_id == user.id,
            AssistantUsage.day == day,
            AssistantUsage.count < limit
        )
        .values(count=AssistantUsage.count + 1),
        execution_options={"synchronize_session": False}
    ).rowcount

    db.commit()

    if not reserved:
        raise TooManyRequestsError(
            f"Limite de {limit} questions par jour atteinte "
            f"pour l'offre {user.effective_plan}."
        )

    return day


def _release(db, user, day):
    """Rend la question decomptee quand l'assistant n'a pas pu repondre."""

    db.execute(
        update(AssistantUsage)
        .where(
            AssistantUsage.user_id == user.id,
            AssistantUsage.day == day,
            AssistantUsage.count > 0
        )
        .values(count=AssistantUsage.count - 1),
        execution_options={"synchronize_session": False}
    )

    db.commit()
