"""Remediation module implementation.

Currently exposes the root-cause analysis layer (build-plan §4: "Spark failure
analysis"). Fix-proposal generation and the approval-gated safe rerun build on
this next.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from dataforge.contracts.health import DependencyHealth, HealthStatus
from dataforge.contracts.rca import RootCauseAnalysis
from dataforge.core.db import session_scope
from dataforge.core.logging import get_logger
from dataforge.modules.metadata.rca_repository import RcaRepository
from dataforge.modules.remediation.rca import LLMAnalyzer, build_analyzer
from dataforge.modules.remediation.service import RemediationService

logger = get_logger(__name__)


class RemediationModule:
    name = "remediation"

    def __init__(self) -> None:
        # Analyzer choice is config-driven: null provider -> rule-based,
        # anthropic/openai/ollama -> LLMAnalyzer. The RAG service is attached
        # later in startup() so both modules can be constructed independently.
        self._service = RemediationService(analyzer=build_analyzer())

    @property
    def service(self) -> RemediationService:
        """Expose the service for in-process composition (the coordinator)."""
        return self._service

    def router(self) -> APIRouter:
        router = APIRouter()

        @router.get("/status", summary="Remediation module status")
        async def status() -> dict[str, str]:
            return {"module": self.name, "status": "ready"}

        @router.post(
            "/runs/{run_id}/analyze",
            summary="Run root-cause analysis for a pipeline run",
            response_model=RootCauseAnalysis,
        )
        async def analyze(run_id: str) -> RootCauseAnalysis:
            return await self._service.analyze_run(run_id)

        @router.get(
            "/runs/{run_id}/analysis",
            summary="Get the stored root-cause analysis for a run",
            response_model=RootCauseAnalysis,
        )
        async def get_analysis(run_id: str) -> RootCauseAnalysis:
            async with session_scope() as session:
                analysis = await RcaRepository(session).get_for_run(run_id)
            if analysis is None:
                raise HTTPException(status_code=404, detail="analysis not found")
            return analysis

        return router

    async def startup(self) -> None:
        # Late-bind the RAG service into the LLM analyzer so it can fetch
        # similar past incidents. Done here (rather than at construction) so
        # we don't depend on rag module's import-time state.
        analyzer = self._service.analyzer
        if isinstance(analyzer, LLMAnalyzer):
            from dataforge.modules.rag import module as rag_module_instance

            analyzer.attach_rag(rag_module_instance.service)
            logger.info("remediation.llm_analyzer_attached_rag", analyzer=analyzer.name)
        logger.info("module.startup", module=self.name)

    async def shutdown(self) -> None:
        logger.info("module.shutdown", module=self.name)

    async def health(self) -> list[DependencyHealth]:
        return [DependencyHealth(name="remediation", status=HealthStatus.OK)]


module = RemediationModule()
