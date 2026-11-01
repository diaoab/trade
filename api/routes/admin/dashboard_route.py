from fastapi import APIRouter

from api.controllers.admin import dashboard_controller as controller


router = APIRouter()

router.add_api_route("/stats", controller.stats, methods=["GET"])
