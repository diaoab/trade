from fastapi import APIRouter

from api.controllers.admin import payments_controller as controller


router = APIRouter()

router.add_api_route("/payments", controller.list_payments, methods=["GET"])
