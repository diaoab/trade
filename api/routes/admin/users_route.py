from fastapi import APIRouter

from api.controllers.admin import users_controller as controller


router = APIRouter()

# Chemins fixes avant /users/{user_id}, qui les capterait sinon.
router.add_api_route("/users", controller.list_users, methods=["GET"])
router.add_api_route("/users/export", controller.export_users, methods=["GET"])
router.add_api_route("/users/admins", controller.create_admin, methods=["POST"])
router.add_api_route("/users/{user_id}", controller.get_user, methods=["GET"])
router.add_api_route("/users/{user_id}", controller.update_user, methods=["PATCH"])
router.add_api_route("/users/{user_id}", controller.delete_user, methods=["DELETE"])
router.add_api_route("/users/{user_id}/activate", controller.activate_user, methods=["POST"])
router.add_api_route("/users/{user_id}/deactivate", controller.deactivate_user, methods=["POST"])
router.add_api_route("/users/{user_id}/revoke-sessions", controller.revoke_sessions, methods=["POST"])
