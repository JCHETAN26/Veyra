"""Ingestion module implementation."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from dataforge.contracts.health import DependencyHealth, HealthStatus
from dataforge.contracts.telemetry import PipelineRun
from dataforge.core.logging import get_logger
from dataforge.modules.ingestion.service import IngestionService

logger = get_logger(__name__)


class IngestEventLogRequest(BaseModel):
    """Request body for ingesting a raw Spark event log (JSON lines)."""

    run_id: str = Field(..., min_length=1, max_length=255)
    content: str = Field(..., description="Raw Spark event-log text (JSON lines).")


class IngestionModule:
    name = "ingestion"

    def __init__(self) -> None:
        self._service = IngestionService()

    @property
    def service(self) -> IngestionService:
        """Expose the service for in-process composition (the coordinator)."""
        return self._service

    def router(self) -> APIRouter:
        router = APIRouter()

        @router.get("/status", summary="Ingestion module status")
        async def status() -> dict[str, str]:
            return {"module": self.name, "status": "ready"}

        @router.post(
            "/event-logs",
            summary="Ingest a Spark event log",
            response_model=PipelineRun,
        )
        async def ingest_event_log(
            request: IngestEventLogRequest,
        ) -> PipelineRun:
            return await self._service.ingest_event_log(request.content, run_id=request.run_id)

        return router

    async def startup(self) -> None:
        logger.info("module.startup", module=self.name)

    async def shutdown(self) -> None:
        logger.info("module.shutdown", module=self.name)

    async def health(self) -> list[DependencyHealth]:
        return [DependencyHealth(name="ingestion", status=HealthStatus.OK)]


module = IngestionModule()
