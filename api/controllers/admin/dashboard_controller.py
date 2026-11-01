from fastapi import Depends
from sqlalchemy.orm import Session

from api.config.db import get_db
from api.services.admin import dashboard_service
from api.utils.response import ok


def stats(db: Session = Depends(get_db)):

    return ok(dashboard_service.stats(db), "Indicateurs récupérés")
