"""Orchestration module implementation (skeleton)."""

from __future__ import annotations

from fastapi import APIRouter

from dataforge.contracts.health import DependencyHealth, HealthStatus
from dataforge.core.logging import get_logger

logger = get_logger(__name__)


class OrchestrationModule:
    name = "orchestration"

    def router(self) -> APIRouter:
        router = APIRouter()

        @router.get("/status", summary="Orchestration module status")
        async def status() -> dict[str, str]:
            return {"module": self.name, "status": "scaffolded"}

        return router

    async def startup(self) -> None:
        logger.info("module.startup", module=self.name)

    async def shutdown(self) -> None:
        logger.info("module.shutdown", module=self.name)

    async def health(self) -> list[DependencyHealth]:
        # TODO: probe Temporal + Redis once the workflow runtime is wired.
        return [DependencyHealth(name="orchestration", status=HealthStatus.OK)]


module = OrchestrationModule()
