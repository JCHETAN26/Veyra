"""Observability module implementation (skeleton)."""

from __future__ import annotations

from fastapi import APIRouter

from dataforge.contracts.health import DependencyHealth, HealthStatus
from dataforge.core.logging import get_logger

logger = get_logger(__name__)


class ObservabilityModule:
    name = "observability"

    def router(self) -> APIRouter:
        router = APIRouter()

        @router.get("/status", summary="Observability module status")
        async def status() -> dict[str, str]:
            return {"module": self.name, "status": "scaffolded"}

        return router

    async def startup(self) -> None:
        logger.info("module.startup", module=self.name)

    async def shutdown(self) -> None:
        logger.info("module.shutdown", module=self.name)

    async def health(self) -> list[DependencyHealth]:
        return [DependencyHealth(name="observability", status=HealthStatus.OK)]


module = ObservabilityModule()
