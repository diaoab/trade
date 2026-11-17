from fastapi import Depends
from sqlalchemy.orm import Session

from api.config.db import get_db
from api.middlewares.auth import current_user
from api.models import User
from api.services import alerts_service
from api.utils.response import ok


def get_alerts(user: User = Depends(current_user)):
    return ok(alerts_service.alerts(user))


def mark_seen(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return ok(alerts_service.mark_seen(db, user), "Alertes lues")
