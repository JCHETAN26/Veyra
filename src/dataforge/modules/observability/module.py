"""Observability module implementation."""

from __future__ import annotations

from fastapi import APIRouter, Query

from dataforge.contracts.forecast import FailurePrediction, TrainingResult
from dataforge.contracts.health import DependencyHealth, HealthStatus
from dataforge.contracts.incident import Incident
from dataforge.core.db import session_scope
from dataforge.core.logging import get_logger
from dataforge.modules.metadata.incident_repository import IncidentRepository
from dataforge.modules.observability.service import ObservabilityService

logger = get_logger(__name__)


class ObservabilityModule:
    name = "observability"

    def __init__(self) -> None:
        self._service = ObservabilityService()

    @property
    def service(self) -> ObservabilityService:
        """Expose the service for in-process composition (the coordinator)."""
        return self._service

    def router(self) -> APIRouter:
        router = APIRouter()

        @router.get("/status", summary="Observability module status")
        async def status() -> dict[str, str]:
            return {"module": self.name, "status": "ready"}

        @router.post(
            "/runs/{run_id}/evaluate",
            summary="Run anomaly detection over a pipeline run",
            response_model=list[Incident],
        )
        async def evaluate(run_id: str) -> list[Incident]:
            return await self._service.evaluate_run(run_id)

        @router.get(
            "/incidents",
            summary="List open incidents",
            response_model=list[Incident],
        )
        async def list_open(
            limit: int = Query(default=50, ge=1, le=500),
        ) -> list[Incident]:
            async with session_scope() as session:
                return await IncidentRepository(session).list_open(limit=limit)

        @router.get(
            "/runs/{run_id}/incidents",
            summary="List incidents for a run",
            response_model=list[Incident],
        )
        async def list_for_run(run_id: str) -> list[Incident]:
            async with session_scope() as session:
                return await IncidentRepository(session).list_for_run(run_id)

        @router.post(
            "/forecaster/train",
            summary="Fit the failure forecaster from recent run history",
            response_model=TrainingResult,
        )
        async def train_forecaster(
            history_limit: int = Query(default=500, ge=30, le=5000),
        ) -> TrainingResult:
            return await self._service.train_forecaster(history_limit=history_limit)

        @router.get(
            "/forecaster/predict/{app_name}",
            summary="Predict P(next run of this pipeline fails)",
            response_model=FailurePrediction,
        )
        async def predict_failure(
            app_name: str,
            window_limit: int = Query(default=50, ge=2, le=500),
        ) -> FailurePrediction:
            return await self._service.predict_failure(app_name, window_limit=window_limit)

        return router

    async def startup(self) -> None:
        logger.info("module.startup", module=self.name)

    async def shutdown(self) -> None:
        logger.info("module.shutdown", module=self.name)

    async def health(self) -> list[DependencyHealth]:
        return [DependencyHealth(name="observability", status=HealthStatus.OK)]


module = ObservabilityModule()
