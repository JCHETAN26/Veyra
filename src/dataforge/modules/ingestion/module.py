"""Ingestion module implementation (skeleton)."""

from __future__ import annotations

from fastapi import APIRouter

from dataforge.contracts.health import DependencyHealth, HealthStatus
from dataforge.core.logging import get_logger

logger = get_logger(__name__)


class IngestionModule:
    name = "ingestion"

    def router(self) -> APIRouter:
        router = APIRouter()

        @router.get("/status", summary="Ingestion module status")
        async def status() -> dict[str, str]:
            return {"module": self.name, "status": "scaffolded"}

        return router

    async def startup(self) -> None:
        logger.info("module.startup", module=self.name)

    async def shutdown(self) -> None:
        logger.info("module.shutdown", module=self.name)

    async def health(self) -> list[DependencyHealth]:
        # TODO: probe Redpanda consumer + Bronze writer once wired.
        return [DependencyHealth(name="ingestion", status=HealthStatus.OK)]


module = IngestionModule()
