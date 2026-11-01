from fastapi import APIRouter

from api.controllers.admin import data_controller as controller


router = APIRouter()

router.add_api_route("/structures", controller.list_structures, methods=["GET"])
router.add_api_route("/structures", controller.upload_structure, methods=["POST"])
router.add_api_route("/refresh", controller.refresh, methods=["POST"])
router.add_api_route("/retrain", controller.retrain, methods=["POST"])
router.add_api_route("/model", controller.model_status, methods=["GET"])
