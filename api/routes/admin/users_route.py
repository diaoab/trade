from fastapi import APIRouter

from api.controllers.admin import users_controller as controller


router = APIRouter()

router.add_api_route("/users", controller.list_users, methods=["GET"])
router.add_api_route("/users/{user_id}", controller.get_user, methods=["GET"])
router.add_api_route("/users/{user_id}", controller.update_user, methods=["PATCH"])
router.add_api_route("/users/{user_id}/revoke-sessions", controller.revoke_sessions, methods=["POST"])
