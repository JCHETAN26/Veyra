"""Remediation workflow engine — a pure state machine.

Encapsulates the transition rules of the self-healing workflow with no I/O, so
the control flow is deterministic and unit-testable. The service layer wires in
persistence (WorkflowRepository) and side effects (RerunExecutor); this module
only decides *what state comes next and why*.

Allowed transitions:

    pending_approval ─approve─► approved ─apply─► applying ─► rerunning
    pending_approval ─reject──► rejected (terminal)
    rerunning ─success─► resolved (terminal)
    rerunning ─exhausted fallbacks─► rolled_back (terminal)
"""

from __future__ import annotations

from datetime import UTC, datetime

from dataforge.contracts.remediation_workflow import (
    RemediationWorkflow,
    WorkflowState,
    WorkflowTransition,
)
from dataforge.core.errors import ConflictError

# Valid state graph; any transition not listed here is rejected.
_ALLOWED: dict[WorkflowState, set[WorkflowState]] = {
    WorkflowState.PENDING_APPROVAL: {
        WorkflowState.APPROVED,
        WorkflowState.REJECTED,
    },
    WorkflowState.APPROVED: {WorkflowState.APPLYING},
    WorkflowState.APPLYING: {WorkflowState.RERUNNING},
    WorkflowState.RERUNNING: {
        WorkflowState.RESOLVED,
        WorkflowState.ROLLED_BACK,
    },
}


def _now() -> datetime:
    return datetime.now(UTC)


def transition(
    workflow: RemediationWorkflow, to_state: WorkflowState, *, note: str = ""
) -> RemediationWorkflow:
    """Move a workflow to a new state, validating and recording the change.

    Raises ConflictError if the transition is not allowed from the current
    state (so out-of-order API calls fail loudly rather than corrupt state).
    """
    current = workflow.state
    if current.is_terminal:
        raise ConflictError(f"workflow {workflow.workflow_id} is terminal ({current})")
    if to_state not in _ALLOWED.get(current, set()):
        raise ConflictError(
            f"illegal transition {current} -> {to_state} " f"for workflow {workflow.workflow_id}"
        )

    now = _now()
    workflow.transitions.append(
        WorkflowTransition(from_state=current, to_state=to_state, at=now, note=note)
    )
    workflow.state = to_state
    workflow.updated_at = now
    return workflow
