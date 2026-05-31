"""Orchestration service — the remediation workflow driver.

Closes the self-healing loop: build a fix proposal from a run's root-cause
analysis, gate it behind human approval, then apply + safely re-run with a
fallback chain and rollback on exhaustion.

Persists state at every step (resumable, auditable) and drives reruns through
the RerunExecutor interface (simulated locally; real Spark/Temporal later).
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from dataforge.contracts.incident import IncidentStatus
from dataforge.contracts.remediation_workflow import (
    RemediationWorkflow,
    WorkflowState,
)
from dataforge.contracts.retrieval import SimilarIncident
from dataforge.core.db import session_scope
from dataforge.core.errors import ConflictError, NotFoundError
from dataforge.core.logging import get_logger
from dataforge.modules.metadata.incident_repository import IncidentRepository
from dataforge.modules.metadata.rca_repository import RcaRepository
from dataforge.modules.metadata.repository import MetadataRepository
from dataforge.modules.metadata.workflow_repository import WorkflowRepository
from dataforge.modules.orchestration.executor import (
    RerunExecutor,
    SimulatedExecutor,
)
from dataforge.modules.orchestration.workflow import transition
from dataforge.modules.remediation.fixes import (
    FixGenerator,
    RuleBasedFixGenerator,
)

logger = get_logger(__name__)


class OrchestrationService:
    """Drives approval-gated, fallback-aware remediation workflows."""

    def __init__(
        self,
        executor: RerunExecutor | None = None,
        fix_generator: FixGenerator | None = None,
    ) -> None:
        self._executor: RerunExecutor = executor or SimulatedExecutor()
        self._fix_generator: FixGenerator = fix_generator or RuleBasedFixGenerator()

    @property
    def fix_generator(self) -> FixGenerator:
        """Expose the generator so the module can late-bind LLM deps into it."""
        return self._fix_generator

    async def propose(
        self,
        run_id: str,
        *,
        similar: list[SimilarIncident] | None = None,
    ) -> RemediationWorkflow:
        """Create a remediation workflow (PENDING_APPROVAL) from a run's RCA.

        Idempotent: re-proposing returns the existing workflow rather than
        resetting an in-flight or completed one.
        """
        async with session_scope() as session:
            run = await MetadataRepository(session).get_run(run_id)
            if run is None:
                raise NotFoundError(f"run '{run_id}' not found")

            wf_repo = WorkflowRepository(session)
            existing = await wf_repo.get_for_run(run_id)
            if existing is not None:
                return existing

            analysis = await RcaRepository(session).get_for_run(run_id)
            if analysis is None:
                raise ConflictError(f"run '{run_id}' has no root-cause analysis; analyze first")

            proposal = await self._fix_generator.generate(run, analysis, similar=similar)
            if not proposal.actions:
                raise ConflictError(f"run '{run_id}' has no actionable fix to propose")

            now = datetime.now(UTC)
            workflow = RemediationWorkflow(
                workflow_id=f"wf-{run_id}",
                run_id=run_id,
                state=WorkflowState.PENDING_APPROVAL,
                proposal=proposal,
                created_at=now,
                updated_at=now,
            )
            await wf_repo.save(workflow)

        logger.info(
            "orchestration.proposed",
            run_id=run_id,
            num_actions=len(proposal.actions),
            cause=proposal.cause_category,
        )
        return workflow

    async def reject(self, run_id: str, *, reason: str) -> RemediationWorkflow:
        async with session_scope() as session:
            wf_repo = WorkflowRepository(session)
            workflow = await self._require_workflow(wf_repo, run_id)
            transition(workflow, WorkflowState.REJECTED, note=reason)
            workflow.rejection_reason = reason
            await wf_repo.save(workflow)
        logger.info("orchestration.rejected", run_id=run_id, reason=reason)
        return workflow

    async def approve(self, run_id: str, *, approver: str) -> RemediationWorkflow:
        """Approve the proposal and execute the fix/rerun fallback chain.

        Runs synchronously through APPROVED -> APPLYING -> RERUNNING and then to
        a terminal RESOLVED or ROLLED_BACK, persisting at each step.
        """
        async with session_scope() as session:
            wf_repo = WorkflowRepository(session)
            workflow = await self._require_workflow(wf_repo, run_id)
            run = await MetadataRepository(session).get_run(run_id)
            if run is None:
                raise NotFoundError(f"run '{run_id}' not found")

            transition(workflow, WorkflowState.APPROVED, note=f"by {approver}")
            workflow.approver = approver
            await wf_repo.save(workflow)

            transition(workflow, WorkflowState.APPLYING)
            await wf_repo.save(workflow)

            transition(workflow, WorkflowState.RERUNNING)
            await wf_repo.save(workflow)

            # Fallback chain: try actions in order until one resolves the run.
            resolved_index: int | None = None
            for index, action in enumerate(workflow.proposal.actions):
                workflow.attempts += 1
                outcome = await self._executor.rerun(run, action)
                if outcome.succeeded:
                    resolved_index = index
                    break

            if resolved_index is not None:
                workflow.applied_action_index = resolved_index
                transition(
                    workflow,
                    WorkflowState.RESOLVED,
                    note=(
                        f"resolved by action #{resolved_index}: "
                        f"{workflow.proposal.actions[resolved_index].title}"
                    ),
                )
                await self._resolve_incidents(session, run_id)
            else:
                transition(
                    workflow,
                    WorkflowState.ROLLED_BACK,
                    note="all proposed fixes failed; rolled back",
                )
            await wf_repo.save(workflow)

        logger.info(
            "orchestration.executed",
            run_id=run_id,
            state=workflow.state,
            attempts=workflow.attempts,
            applied_action_index=workflow.applied_action_index,
        )
        return workflow

    async def get_for_run(self, run_id: str) -> RemediationWorkflow:
        async with session_scope() as session:
            workflow = await WorkflowRepository(session).get_for_run(run_id)
        if workflow is None:
            raise NotFoundError(f"no workflow for run '{run_id}'")
        return workflow

    async def _require_workflow(
        self, wf_repo: WorkflowRepository, run_id: str
    ) -> RemediationWorkflow:
        workflow = await wf_repo.get_for_run(run_id)
        if workflow is None:
            raise NotFoundError(f"no workflow for run '{run_id}'")
        return workflow

    async def _resolve_incidents(self, session: AsyncSession, run_id: str) -> None:
        """Mark the run's incidents resolved once a fix succeeds."""
        await IncidentRepository(session).set_status_for_run(run_id, IncidentStatus.RESOLVED)
