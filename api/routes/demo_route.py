from fastapi import APIRouter

from api.controllers import demo_controller as controller
from api.middlewares.rate_limit import demo_rate_limit


# Publiques (sans jeton), limitees par adresse IP.
router = APIRouter(prefix="/demo", tags=["Démo sans compte"], dependencies=[demo_rate_limit])

router.add_api_route("/market", controller.overview, methods=["GET"])
router.add_api_route("/structures/{symbol}/analysis", controller.analysis, methods=["GET"])
