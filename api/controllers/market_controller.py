from fastapi import Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from core.engine import market_data

from api.config.db import get_db
from api.errors.app_error import ValidationError
from api.middlewares.auth import current_user
from api.models import User
from api.services import assistant_service, market_service
from api.services.portfolio_service import require_structure
from api.utils.response import ok, revalidated
from api.validations.market_validation import ChatIn


def structures(user: User = Depends(current_user)):

    return ok([
        {"symbol": symbol, "name": structure["name"]}
        for symbol, structure in market_data.get_structures().items()
    ])


def overview(request: Request, user: User = Depends(current_user)):

    key = market_service.result_key("market", user.preferences)

    return revalidated(
        request,
        key,
        lambda: market_service.market_overview(user.preferences, key)
    )


def analysis(symbol: str, request: Request, user: User = Depends(current_user)):

    require_structure(symbol)

    key = market_service.result_key("analysis", user.preferences, symbol)

    def compute():
        try:
            return market_service.analyse_structure(symbol, user.preferences, key)
        except ValueError as error:
            raise ValidationError(str(error))

    return revalidated(request, key, compute)


def assistant(
    symbol: str,
    body: ChatIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db)
):

    require_structure(symbol)

    answer = assistant_service.ask(
        db,
        user,
        symbol,
        [message.model_dump() for message in body.messages]
    )

    return ok(answer)


def assistant_stream(
    symbol: str,
    body: ChatIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db)
):
    """Meme demande que assistant, reponse en Server-Sent Events."""

    require_structure(symbol)

    events = assistant_service.ask_stream(
        db,
        user,
        symbol,
        [message.model_dump() for message in body.messages]
    )

    return StreamingResponse(
        events,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            # Nginx : transmettre chaque morceau tout de suite.
            "X-Accel-Buffering": "no"
        }
    )
