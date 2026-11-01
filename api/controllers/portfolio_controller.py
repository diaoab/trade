from fastapi import Depends
from sqlalchemy.orm import Session

from api.config.db import get_db
from api.middlewares.auth import current_user
from api.models import User
from api.services import portfolio_service
from api.utils.response import created, ok
from api.validations.portfolio_validation import PositionIn


def get_portfolio(user: User = Depends(current_user)):
    return ok(portfolio_service.portfolio(user))


def add_position(
    body: PositionIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db)
):

    return created(
        portfolio_service.add_position(db, user, body.model_dump()),
        "Position ajoutée"
    )


def delete_position(
    position_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db)
):

    return ok(
        portfolio_service.delete_position(db, user, position_id),
        "Position supprimée"
    )
