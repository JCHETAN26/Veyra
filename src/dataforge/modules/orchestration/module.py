"""Orchestration module implementation.

Exposes the approval-gated remediation workflow that closes the self-healing
loop: propose a fix from a run's root-cause analysis, let a human approve or
reject, then apply + safely re-run with a fallback chain and rollback.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from dataforge.contracts.health import DependencyHealth, HealthStatus
from dataforge.contracts.pipeline import PipelineReport
from dataforge.contracts.remediation_workflow import RemediationWorkflow
from dataforge.core.logging import get_logger
from dataforge.modules.ingestion import module as ingestion_module
from dataforge.modules.observability import module as observability_module
from dataforge.modules.orchestration.coordinator import PipelineCoordinator
from dataforge.modules.orchestration.service import OrchestrationService
from dataforge.modules.rag import module as rag_module
from dataforge.modules.remediation import module as remediation_module
from dataforge.modules.remediation.fixes import build_fix_generator

logger = get_logger(__name__)


class ApproveRequest(BaseModel):
    approver: str = Field(..., min_length=1, max_length=255)


class RejectRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=1000)


class ProcessEventLogRequest(BaseModel):
    run_id: str = Field(..., min_length=1, max_length=255)
    content: str = Field(..., description="Raw Spark event-log text (JSON lines).")


class OrchestrationModule:
    name = "orchestration"

    def __init__(self) -> None:
        # Fix generator is config-driven (null -> rule-based, anthropic/openai
        # /ollama -> LLM-backed with deterministic fallback).
        self._service = OrchestrationService(fix_generator=build_fix_generator())
        # Compose the loop from the other modules' service instances, so the
        # coordinator shares state (notably the RAG index) with the API paths.
        self._coordinator = PipelineCoordinator(
            ingestion=ingestion_module.service,
            observability=observability_module.service,
            remediation=remediation_module.service,
            rag=rag_module.service,
            orchestration=self._service,
        )

    @property
    def service(self) -> OrchestrationService:
        """Expose the service for in-process composition (the coordinator)."""
        return self._service

    def router(self) -> APIRouter:
        router = APIRouter()

        @router.get("/status", summary="Orchestration module status")
        async def status() -> dict[str, str]:
            return {"module": self.name, "status": "ready"}

        @router.post(
            "/process/event-log",
            summary="Run the full self-healing loop over a Spark event log",
            response_model=PipelineReport,
        )
        async def process_event_log(
            request: ProcessEventLogRequest,
        ) -> PipelineReport:
            return await self._coordinator.process_event_log(request.content, run_id=request.run_id)

        @router.post(
            "/runs/{run_id}/process",
            summary="Run the full self-healing loop over an ingested run",
            response_model=PipelineReport,
        )
        async def process_run(run_id: str) -> PipelineReport:
            return await self._coordinator.process_run(run_id)

        @router.post(
            "/runs/{run_id}/remediation",
            summary="Propose a remediation workflow for a run",
            response_model=RemediationWorkflow,
        )
        async def propose(run_id: str) -> RemediationWorkflow:
            return await self._service.propose(run_id)

        @router.post(
            "/runs/{run_id}/remediation/approve",
            summary="Approve and execute the remediation",
            response_model=RemediationWorkflow,
        )
        async def approve(run_id: str, request: ApproveRequest) -> RemediationWorkflow:
            return await self._service.approve(run_id, approver=request.approver)

        @router.post(
            "/runs/{run_id}/remediation/reject",
            summary="Reject the proposed remediation",
            response_model=RemediationWorkflow,
        )
        async def reject(run_id: str, request: RejectRequest) -> RemediationWorkflow:
            return await self._service.reject(run_id, reason=request.reason)

        @router.get(
            "/runs/{run_id}/remediation",
            summary="Get the remediation workflow for a run",
            response_model=RemediationWorkflow,
        )
        async def get_workflow(run_id: str) -> RemediationWorkflow:
            return await self._service.get_for_run(run_id)

        return router

    async def startup(self) -> None:
        logger.info("module.startup", module=self.name)

    async def shutdown(self) -> None:
        logger.info("module.shutdown", module=self.name)

    async def health(self) -> list[DependencyHealth]:
        return [DependencyHealth(name="orchestration", status=HealthStatus.OK)]


module = OrchestrationModule()
