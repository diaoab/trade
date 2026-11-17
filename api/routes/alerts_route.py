from fastapi import APIRouter

from api.controllers import alerts_controller as controller
from api.middlewares.rate_limit import authenticated_rate_limit


router = APIRouter(prefix="/alerts", tags=["Alertes"], dependencies=[authenticated_rate_limit])

router.add_api_route("", controller.get_alerts, methods=["GET"])
router.add_api_route("/seen", controller.mark_seen, methods=["POST"])
