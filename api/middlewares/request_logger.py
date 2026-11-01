"""Journal des requetes entrantes et en-tetes de securite."""

import logging
import time

from starlette.middleware.base import BaseHTTPMiddleware

from api.middlewares.rate_limit import client_ip


logger = logging.getLogger("api.http")


SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Cross-Origin-Resource-Policy": "same-site",
    "X-Permitted-Cross-Domain-Policies": "none"
}


class RequestLoggerMiddleware(BaseHTTPMiddleware):

    async def dispatch(self, request, call_next):

        start = time.perf_counter()

        response = await call_next(request)

        for name, value in SECURITY_HEADERS.items():
            response.headers.setdefault(name, value)

        if request.url.path != "/health":

            duration = (time.perf_counter() - start) * 1000

            logger.info(
                f"{request.method} {request.url.path} {response.status_code} {duration:.0f} ms",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "duration_ms": round(duration),
                    "ip": client_ip(request)
                }
            )

        return response
