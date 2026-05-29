"""Request middleware: correlation IDs and access logging.

Every request gets a request_id and a correlation_id (propagated from an
inbound header when present). These are bound into the structlog contextvars
so all log lines for the request carry them, satisfying the mandatory log
fields in §25 of the build plan.
"""

from __future__ import annotations

import time
import uuid
from typing import TYPE_CHECKING

from starlette.middleware.base import BaseHTTPMiddleware

from dataforge.core.logging import (
    bind_contextvars,
    clear_contextvars,
    get_logger,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from starlette.requests import Request
    from starlette.responses import Response

logger = get_logger(__name__)

REQUEST_ID_HEADER = "x-request-id"
CORRELATION_ID_HEADER = "x-correlation-id"


class CorrelationMiddleware(BaseHTTPMiddleware):
    """Bind correlation context and emit a structured access log per request."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request_id = request.headers.get(REQUEST_ID_HEADER, str(uuid.uuid4()))
        correlation_id = request.headers.get(CORRELATION_ID_HEADER, request_id)

        clear_contextvars()
        bind_contextvars(request_id=request_id, correlation_id=correlation_id)

        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            duration_ms = (time.perf_counter() - start) * 1000
            logger.exception(
                "request.failed",
                method=request.method,
                path=request.url.path,
                duration_ms=round(duration_ms, 2),
            )
            raise

        duration_ms = (time.perf_counter() - start) * 1000
        response.headers[REQUEST_ID_HEADER] = request_id
        response.headers[CORRELATION_ID_HEADER] = correlation_id

        logger.info(
            "request.completed",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=round(duration_ms, 2),
        )
        return response
