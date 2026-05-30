"""Remediation workflow repository.

Typed persistence port for RemediationWorkflow. One workflow per run (unique on
run_id). State and its full transition history are persisted on every change so
the workflow is resumable and auditable.
"""

from __future__ import annotations

import json

from sqlalchemy.ext.asyncio import AsyncSession

from dataforge.contracts.remediation_workflow import (
    FixProposal,
    RemediationWorkflow,
    WorkflowState,
    WorkflowTransition,
)
from dataforge.core.logging import get_logger
from dataforge.modules.metadata.models import RemediationWorkflowRow

logger = get_logger(__name__)


class WorkflowRepository:
    """Async repository over remediation workflows."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, workflow: RemediationWorkflow) -> None:
        """Insert or update a workflow (idempotent on workflow_id)."""
        existing = await self._session.get(RemediationWorkflowRow, workflow.workflow_id)
        if existing is None:
            self._session.add(_to_row(workflow))
        else:
            _apply(existing, workflow)
        await self._session.flush()
        logger.info(
            "workflow.saved",
            workflow_id=workflow.workflow_id,
            run_id=workflow.run_id,
            state=workflow.state,
        )

    async def get(self, workflow_id: str) -> RemediationWorkflow | None:
        row = await self._session.get(RemediationWorkflowRow, workflow_id)
        return _to_workflow(row) if row is not None else None

    async def get_for_run(self, run_id: str) -> RemediationWorkflow | None:
        # workflow_id is deterministic (wf-<run_id>).
        return await self.get(f"wf-{run_id}")


def _to_row(w: RemediationWorkflow) -> RemediationWorkflowRow:
    row = RemediationWorkflowRow(
        workflow_id=w.workflow_id,
        run_id=w.run_id,
        state=w.state.value,
        proposal_json=w.proposal.model_dump_json(),
        approver=w.approver,
        rejection_reason=w.rejection_reason,
        applied_action_index=w.applied_action_index,
        attempts=w.attempts,
        transitions_json=json.dumps([t.model_dump(mode="json") for t in w.transitions]),
    )
    if w.created_at is not None:
        row.created_at = w.created_at
    if w.updated_at is not None:
        row.updated_at = w.updated_at
    return row


def _apply(row: RemediationWorkflowRow, w: RemediationWorkflow) -> None:
    row.state = w.state.value
    row.proposal_json = w.proposal.model_dump_json()
    row.approver = w.approver
    row.rejection_reason = w.rejection_reason
    row.applied_action_index = w.applied_action_index
    row.attempts = w.attempts
    row.transitions_json = json.dumps([t.model_dump(mode="json") for t in w.transitions])
    if w.updated_at is not None:
        row.updated_at = w.updated_at


def _to_workflow(row: RemediationWorkflowRow) -> RemediationWorkflow:
    return RemediationWorkflow(
        workflow_id=row.workflow_id,
        run_id=row.run_id,
        state=WorkflowState(row.state),
        proposal=FixProposal.model_validate_json(row.proposal_json),
        approver=row.approver,
        rejection_reason=row.rejection_reason,
        applied_action_index=row.applied_action_index,
        attempts=row.attempts,
        transitions=[
            WorkflowTransition.model_validate(t) for t in json.loads(row.transitions_json or "[]")
        ],
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
