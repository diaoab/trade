from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from api.controllers import billing_controller as controller
from api.middlewares.rate_limit import (
    authenticated_rate_limit,
    mutation_rate_limit,
    payment_return_rate_limit
)


router = APIRouter(prefix="/billing", tags=["Abonnement"])

router.add_api_route("/offer", controller.offer, methods=["GET"])
router.add_api_route("/checkout", controller.checkout, methods=["POST"], dependencies=[mutation_rate_limit])
router.add_api_route("/confirm", controller.confirm, methods=["POST"], dependencies=[authenticated_rate_limit])

# Appeles par PayDunya (retour du client, notification) : sans jeton.
router.add_api_route("/return", controller.payment_return, methods=["GET"], response_class=HTMLResponse, dependencies=[payment_return_rate_limit])
router.add_api_route("/ipn", controller.ipn, methods=["POST"])
