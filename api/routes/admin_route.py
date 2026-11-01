from fastapi import APIRouter, Depends

from api.controllers import admin_controller as controller
from api.middlewares.admin import require_admin
from api.middlewares.rate_limit import admin_rate_limit


router = APIRouter(
    prefix="/admin",
    tags=["Administration"],
    dependencies=[admin_rate_limit, Depends(require_admin)]
)

router.add_api_route("/structures", controller.upload_structure, methods=["POST"])
router.add_api_route("/refresh", controller.refresh, methods=["POST"])
router.add_api_route("/retrain", controller.retrain, methods=["POST"])
