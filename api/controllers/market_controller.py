from fastapi import Depends
from sqlalchemy.orm import Session

from core.engine import market_data

from api.config.db import get_db
from api.errors.app_error import ValidationError
from api.middlewares.auth import current_user
from api.models import User
from api.services import assistant_service, market_service
from api.services.portfolio_service import require_structure
from api.utils.response import ok
from api.validations.market_validation import ChatIn


def structures(user: User = Depends(current_user)):

    return ok([
        {"symbol": symbol, "name": structure["name"]}
        for symbol, structure in market_data.get_structures().items()
    ])


def overview(user: User = Depends(current_user)):
    return ok(market_service.market_overview(user.preferences))


def analysis(symbol: str, user: User = Depends(current_user)):

    require_structure(symbol)

    try:
        result = market_service.analyse_structure(symbol, user.preferences)
    except ValueError as error:
        raise ValidationError(str(error))

    return ok(result)


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
