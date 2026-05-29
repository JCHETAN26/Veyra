"""Metadata module implementation."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import text

from dataforge.contracts.health import DependencyHealth, HealthStatus
from dataforge.contracts.telemetry import PipelineRun
from dataforge.core.db import Base, get_engine, session_scope
from dataforge.core.logging import get_logger
from dataforge.modules.metadata import models  # noqa: F401 - register ORM tables
from dataforge.modules.metadata.repository import MetadataRepository

logger = get_logger(__name__)


class MetadataModule:
    name = "metadata"

    def router(self) -> APIRouter:
        router = APIRouter()

        @router.get("/status", summary="Metadata module status")
        async def status() -> dict[str, str]:
            return {"module": self.name, "status": "ready"}

        @router.get(
            "/runs",
            summary="List recent pipeline runs",
            response_model=list[PipelineRun],
        )
        async def list_runs(
            limit: int = Query(default=50, ge=1, le=500),
        ) -> list[PipelineRun]:
            async with session_scope() as session:
                return await MetadataRepository(session).list_runs(limit=limit)

        @router.get(
            "/runs/{run_id}",
            summary="Get a pipeline run by id",
            response_model=PipelineRun,
        )
        async def get_run(run_id: str) -> PipelineRun:
            async with session_scope() as session:
                run = await MetadataRepository(session).get_run(run_id)
            if run is None:
                raise HTTPException(status_code=404, detail="run not found")
            return run

        return router

    async def startup(self) -> None:
        """Create tables if absent.

        For the MVP we use create_all for fast local iteration; Alembic
        migrations (already a dependency) take over before any deployed env.

        Boots in degraded mode if the DB is unreachable rather than
        crash-looping: liveness stays up, readiness reports postgres DOWN
        until it recovers (build-plan: reliability over features).
        """
        try:
            engine = get_engine()
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            logger.info("module.startup", module=self.name, schema="ensured")
        except Exception as exc:  # noqa: BLE001 - degrade, don't crash
            logger.warning(
                "metadata.startup.db_unavailable",
                module=self.name,
                error=str(exc),
            )

    async def shutdown(self) -> None:
        logger.info("module.shutdown", module=self.name)

    async def health(self) -> list[DependencyHealth]:
        try:
            async with session_scope() as session:
                await session.execute(text("SELECT 1"))
            return [DependencyHealth(name="postgres", status=HealthStatus.OK)]
        except Exception as exc:  # noqa: BLE001 - report any failure as degraded
            logger.warning("metadata.health.db_unreachable", error=str(exc))
            return [
                DependencyHealth(
                    name="postgres",
                    status=HealthStatus.DOWN,
                    detail="database unreachable",
                )
            ]


module = MetadataModule()
