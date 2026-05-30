"""Orchestration module implementation.

Exposes the approval-gated remediation workflow that closes the self-healing
loop: propose a fix from a run's root-cause analysis, let a human approve or
reject, then apply + safely re-run with a fallback chain and rollback.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from dataforge.contracts.health import DependencyHealth, HealthStatus
from dataforge.contracts.remediation_workflow import RemediationWorkflow
from dataforge.core.logging import get_logger
from dataforge.modules.orchestration.service import OrchestrationService

logger = get_logger(__name__)


class ApproveRequest(BaseModel):
    approver: str = Field(..., min_length=1, max_length=255)


class RejectRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=1000)


class OrchestrationModule:
    name = "orchestration"

    def __init__(self) -> None:
        self._service = OrchestrationService()

    def router(self) -> APIRouter:
        router = APIRouter()

        @router.get("/status", summary="Orchestration module status")
        async def status() -> dict[str, str]:
            return {"module": self.name, "status": "ready"}

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
