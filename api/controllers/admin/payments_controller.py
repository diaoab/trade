from fastapi import Depends
from sqlalchemy.orm import Session

from api.config.db import get_db
from api.services.admin import payments_service
from api.utils.response import ok


def list_payments(
    page: int = 1,
    limit: int = 20,
    status: str = "",
    db: Session = Depends(get_db)
):

    return ok(payments_service.list_payments(db, page, limit, status), "Paiements récupérés")
