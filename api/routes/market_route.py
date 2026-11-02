from fastapi import APIRouter

from api.controllers import market_controller as controller
from api.middlewares.rate_limit import authenticated_rate_limit


router = APIRouter(tags=["Marché et analyse"], dependencies=[authenticated_rate_limit])

router.add_api_route("/market", controller.overview, methods=["GET"])
router.add_api_route("/structures", controller.structures, methods=["GET"])
router.add_api_route("/structures/{symbol}/analysis", controller.analysis, methods=["GET"])
router.add_api_route("/structures/{symbol}/assistant", controller.assistant, methods=["POST"])
router.add_api_route("/structures/{symbol}/assistant/stream", controller.assistant_stream, methods=["POST"])
