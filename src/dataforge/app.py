"""Application factory.

Assembles the modular monolith: configures logging + observability, mounts
each registered domain module under /api/v1/<name>, and wires lifecycle and
health endpoints. This is the only composition root.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from dataforge import __version__
from dataforge.contracts.health import HealthReport, HealthStatus
from dataforge.core.config import get_settings
from dataforge.core.db import dispose_engine
from dataforge.core.errors import DataForgeError, ErrorResponse
from dataforge.core.logging import configure_logging, get_logger
from dataforge.core.middleware import CorrelationMiddleware
from dataforge.core.observability import setup_metrics, setup_tracing
from dataforge.registry import MODULES

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from starlette.requests import Request

logger = get_logger(__name__)


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    logger.info("app.startup.begin", modules=[m.name for m in MODULES])
    for mod in MODULES:
        await mod.startup()
    logger.info("app.startup.complete")
    try:
        yield
    finally:
        logger.info("app.shutdown.begin")
        for mod in reversed(MODULES):
            await mod.shutdown()
        await dispose_engine()
        logger.info("app.shutdown.complete")


def create_app() -> FastAPI:
    configure_logging()

    app = FastAPI(
        title="DataForge AI",
        version=__version__,
        lifespan=_lifespan,
    )

    app.add_middleware(CorrelationMiddleware)
    setup_tracing(app)
    setup_metrics(app)

    _register_error_handlers(app)
    _register_health(app)

    for mod in MODULES:
        app.include_router(
            mod.router(),
            prefix=f"/api/v1/{mod.name}",
            tags=[mod.name],
        )

    return app


def _register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(DataForgeError)
    async def _handle_domain_error(request: Request, exc: DataForgeError) -> JSONResponse:
        correlation_id = request.headers.get("x-correlation-id")
        logger.warning("domain.error", code=exc.code, detail=exc.detail)
        body = ErrorResponse(error=exc.code, detail=exc.detail, correlation_id=correlation_id)
        return JSONResponse(status_code=exc.status_code, content=body.model_dump())


def _register_health(app: FastAPI) -> None:
    settings = get_settings()

    @app.get("/health/live", tags=["health"], summary="Liveness probe")
    async def live() -> dict[str, str]:
        return {"status": "ok"}

    @app.get(
        "/health/ready",
        tags=["health"],
        summary="Readiness probe",
        response_model=HealthReport,
    )
    async def ready() -> HealthReport:
        deps = []
        for mod in MODULES:
            deps.extend(await mod.health())

        overall = HealthStatus.OK
        if any(d.status == HealthStatus.DOWN for d in deps):
            overall = HealthStatus.DOWN
        elif any(d.status == HealthStatus.DEGRADED for d in deps):
            overall = HealthStatus.DEGRADED

        return HealthReport(
            status=overall,
            version=__version__,
            environment=settings.environment.value,
            dependencies=deps,
        )
