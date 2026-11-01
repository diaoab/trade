from fastapi import APIRouter

from api.controllers import portfolio_controller as controller
from api.middlewares.rate_limit import authenticated_rate_limit


router = APIRouter(prefix="/portfolio", tags=["Portefeuille"], dependencies=[authenticated_rate_limit])

router.add_api_route("", controller.get_portfolio, methods=["GET"])
router.add_api_route("/positions", controller.add_position, methods=["POST"], status_code=201)
router.add_api_route("/positions/{position_id}", controller.delete_position, methods=["DELETE"])
