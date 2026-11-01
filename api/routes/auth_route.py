from fastapi import APIRouter

from api.controllers import auth_controller as controller
from api.middlewares.rate_limit import auth_rate_limit, mutation_rate_limit


router = APIRouter(prefix="/auth", tags=["Authentification"])

router.add_api_route("/register", controller.register, methods=["POST"], status_code=201, dependencies=[auth_rate_limit])
router.add_api_route("/login", controller.login, methods=["POST"], dependencies=[auth_rate_limit])
router.add_api_route("/refresh", controller.refresh, methods=["POST"], dependencies=[auth_rate_limit])
router.add_api_route("/logout", controller.logout, methods=["POST"])
router.add_api_route("/password", controller.change_password, methods=["PUT"], dependencies=[mutation_rate_limit])
