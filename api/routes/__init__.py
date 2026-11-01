"""Toutes les routes metier, montees sous /trade/v1 (cf. api.main)."""

from fastapi import APIRouter

from api.routes import (
    account_route,
    admin_route,
    auth_route,
    billing_route,
    market_route,
    portfolio_route
)


api_router = APIRouter()

for module in (
    auth_route,
    account_route,
    market_route,
    portfolio_route,
    billing_route,
    admin_route
):
    api_router.include_router(module.router)
