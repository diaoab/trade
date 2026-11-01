"""Routes du back-office, toutes sous /admin et reservees aux admins
(jeton d'un compte admin, ou cle X-Admin-Key)."""

from fastapi import APIRouter, Depends

from api.middlewares.admin import require_admin
from api.middlewares.rate_limit import admin_rate_limit
from api.routes.admin import dashboard_route, data_route, payments_route, users_route


router = APIRouter(
    prefix="/admin",
    tags=["Administration"],
    dependencies=[admin_rate_limit, Depends(require_admin)]
)

for module in (dashboard_route, users_route, payments_route, data_route):
    router.include_router(module.router)
