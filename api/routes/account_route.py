from fastapi import APIRouter

from api.controllers import account_controller as controller
from api.middlewares.rate_limit import authenticated_rate_limit, mutation_rate_limit


router = APIRouter(prefix="/account", tags=["Compte"], dependencies=[authenticated_rate_limit])

router.add_api_route("/me", controller.me, methods=["GET"])
router.add_api_route("/me", controller.delete_account, methods=["DELETE"], dependencies=[mutation_rate_limit])
router.add_api_route("/preferences", controller.get_preferences, methods=["GET"])
router.add_api_route("/preferences", controller.update_preferences, methods=["PUT"])
