"""Limites de debit, en memoire, par fenetre fixe.

Compteurs propres au processus : l'API tourne avec un seul worker uvicorn
(cf. Dockerfile). Avec plusieurs workers ou serveurs, il faudrait un
stockage partage (Redis).
"""

import threading
import time

from fastapi import Depends, Request
from starlette.middleware.base import BaseHTTPMiddleware

from api.config.security import (
    ADMIN_RATE_LIMIT,
    AUTH_RATE_LIMIT,
    AUTHENTICATED_RATE_LIMIT,
    GLOBAL_RATE_LIMIT,
    MUTATION_RATE_LIMIT,
    PAYMENT_RETURN_RATE_LIMIT
)
from api.errors.app_error import TooManyRequestsError
from api.middlewares.auth import current_user
from api.utils.response import fail


_limiters = []


class RateLimiter:

    def __init__(self, max_requests, window, message=None):

        self.max_requests = max_requests
        self.window = window
        self.message = message
        self._hits = {}
        self._lock = threading.Lock()

        _limiters.append(self)

    def hit(self, key):
        """Compte une requete ; renvoie le nombre de secondes a attendre si
        la limite est depassee, sinon None."""

        now = time.monotonic()

        with self._lock:

            # Purge des fenetres terminees, pour que la table ne grossisse pas.
            if len(self._hits) > 10_000:
                self._hits = {
                    k: v for k, v in self._hits.items() if now - v[0] < self.window
                }

            start, count = self._hits.get(key, (now, 0))

            if now - start >= self.window:
                start, count = now, 0

            count += 1

            self._hits[key] = (start, count)

            if count > self.max_requests:
                return int(self.window - (now - start)) + 1

        return None

    def reset(self):

        with self._lock:
            self._hits.clear()


def reset_all():
    """Remet tous les compteurs a zero (tests)."""

    for limiter in _limiters:
        limiter.reset()


def client_ip(request):
    return request.client.host if request.client else "inconnu"


def _check(limiter, key):

    retry_after = limiter.hit(key)

    if retry_after is not None:
        error = TooManyRequestsError(limiter.message)
        error.headers = {"Retry-After": str(retry_after)}
        raise error


def by_ip(limiter):
    """Dependance : limite par adresse IP (routes publiques)."""

    def dependency(request: Request):
        _check(limiter, client_ip(request))

    return dependency


def by_user(limiter):
    """Dependance : limite par compte (routes authentifiees)."""

    def dependency(user=Depends(current_user)):
        _check(limiter, user.id)

    return dependency


global_limiter = RateLimiter(**GLOBAL_RATE_LIMIT)

authenticated_limiter = RateLimiter(**AUTHENTICATED_RATE_LIMIT)

auth_limiter = RateLimiter(
    **AUTH_RATE_LIMIT,
    message="Trop de tentatives. Réessaie dans 15 minutes."
)

mutation_limiter = RateLimiter(**MUTATION_RATE_LIMIT)

# Retour de PayDunya : public et chaque appel interroge PayDunya, par IP.
payment_return_limiter = RateLimiter(**PAYMENT_RETURN_RATE_LIMIT)

admin_limiter = RateLimiter(
    **ADMIN_RATE_LIMIT,
    message="Trop de requêtes d'administration. Réessaie plus tard."
)


auth_rate_limit = Depends(by_ip(auth_limiter))

authenticated_rate_limit = Depends(by_user(authenticated_limiter))

mutation_rate_limit = Depends(by_user(mutation_limiter))

admin_rate_limit = Depends(by_ip(admin_limiter))

payment_return_rate_limit = Depends(by_ip(payment_return_limiter))


class GlobalRateLimitMiddleware(BaseHTTPMiddleware):
    """Filet de securite par IP sur toutes les routes, /health exclu
    (sonde Docker)."""

    async def dispatch(self, request, call_next):

        if request.url.path != "/health":

            retry_after = global_limiter.hit(client_ip(request))

            if retry_after is not None:
                return fail(
                    "Trop de requêtes. Réessaie dans 15 minutes.",
                    429,
                    headers={"Retry-After": str(retry_after)}
                )

        return await call_next(request)
