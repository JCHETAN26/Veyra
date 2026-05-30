"""RAG module implementation.

Exposes operational retrieval: index a run's failure profile and find similar
past failures. The service (and its in-process index) is held for the module's
lifetime so the corpus persists across requests within the process.
"""

from __future__ import annotations

from fastapi import APIRouter, Query

from dataforge.contracts.health import DependencyHealth, HealthStatus
from dataforge.contracts.retrieval import RetrievalResult
from dataforge.core.logging import get_logger
from dataforge.modules.rag.embedder import build_embedder
from dataforge.modules.rag.profile import FailureProfile
from dataforge.modules.rag.service import RagService

logger = get_logger(__name__)


class RagModule:
    name = "rag"

    def __init__(self) -> None:
        # Embedder is settings-driven (hashing default, semantic via fastembed).
        self._service = RagService(embedder=build_embedder())

    @property
    def service(self) -> RagService:
        """Expose the service for in-process composition (the coordinator)."""
        return self._service

    def router(self) -> APIRouter:
        router = APIRouter()

        @router.get("/status", summary="RAG module status")
        async def status() -> dict[str, str]:
            return {"module": self.name, "status": "ready"}

        @router.post(
            "/runs/{run_id}/index",
            summary="Index a run's failure profile",
            response_model=RetrievalResult,
        )
        async def index(run_id: str) -> RetrievalResult:
            await self._service.index_run(run_id)
            # Echo current similar matches as immediate feedback.
            return await self._service.find_similar(run_id)

        @router.get(
            "/runs/{run_id}/similar",
            summary="Find past runs with a similar failure profile",
            response_model=RetrievalResult,
        )
        async def similar(
            run_id: str,
            limit: int = Query(default=5, ge=1, le=50),
            min_score: float = Query(default=0.1, ge=0.0, le=1.0),
        ) -> RetrievalResult:
            return await self._service.find_similar(run_id, limit=limit, min_score=min_score)

        @router.post(
            "/profiles/index",
            summary="Index a pre-built FailureProfile (used by dataset loaders)",
            response_model=FailureProfile,
        )
        async def index_profile(profile: FailureProfile) -> FailureProfile:
            return await self._service.index_profile(profile)

        return router

    async def startup(self) -> None:
        logger.info("module.startup", module=self.name)

    async def shutdown(self) -> None:
        logger.info("module.shutdown", module=self.name)

    async def health(self) -> list[DependencyHealth]:
        return [DependencyHealth(name="rag", status=HealthStatus.OK)]


module = RagModule()
