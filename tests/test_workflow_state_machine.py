"""Unit tests for the pure workflow state machine."""

from __future__ import annotations

import pytest

from dataforge.contracts.remediation_workflow import (
    FixAction,
    FixProposal,
    RemediationWorkflow,
    WorkflowState,
)
from dataforge.core.errors import ConflictError
from dataforge.modules.orchestration.workflow import transition


def _workflow() -> RemediationWorkflow:
    return RemediationWorkflow(
        workflow_id="wf-r1",
        run_id="r1",
        proposal=FixProposal(
            run_id="r1",
            cause_category="memory_pressure",
            actions=[FixAction(title="Broadcast join")],
        ),
    )


def test_happy_path_transitions() -> None:
    wf = _workflow()
    transition(wf, WorkflowState.APPROVED)
    transition(wf, WorkflowState.APPLYING)
    transition(wf, WorkflowState.RERUNNING)
    transition(wf, WorkflowState.RESOLVED)
    assert wf.state == WorkflowState.RESOLVED
    assert [t.to_state for t in wf.transitions] == [
        WorkflowState.APPROVED,
        WorkflowState.APPLYING,
        WorkflowState.RERUNNING,
        WorkflowState.RESOLVED,
    ]


def test_reject_from_pending() -> None:
    wf = _workflow()
    transition(wf, WorkflowState.REJECTED, note="not now")
    assert wf.state == WorkflowState.REJECTED
    assert wf.state.is_terminal


def test_rollback_path() -> None:
    wf = _workflow()
    transition(wf, WorkflowState.APPROVED)
    transition(wf, WorkflowState.APPLYING)
    transition(wf, WorkflowState.RERUNNING)
    transition(wf, WorkflowState.ROLLED_BACK)
    assert wf.state == WorkflowState.ROLLED_BACK


def test_illegal_transition_rejected() -> None:
    wf = _workflow()
    # Cannot jump straight to RERUNNING from PENDING_APPROVAL.
    with pytest.raises(ConflictError):
        transition(wf, WorkflowState.RERUNNING)


def test_cannot_transition_from_terminal() -> None:
    wf = _workflow()
    transition(wf, WorkflowState.REJECTED, note="done")
    with pytest.raises(ConflictError):
        transition(wf, WorkflowState.APPROVED)


def test_transitions_are_recorded_with_notes() -> None:
    wf = _workflow()
    transition(wf, WorkflowState.APPROVED, note="by alice")
    assert wf.transitions[-1].note == "by alice"
    assert wf.transitions[-1].from_state == WorkflowState.PENDING_APPROVAL
    assert wf.updated_at is not None
