"""Remediation workflow contracts.

The remediation workflow is the closing arc of the self-healing loop
(build-plan steps 7-9): turn a root-cause analysis into a concrete fix
proposal, gate it behind human approval, then apply + safely re-run with
retry/fallback and rollback.

The workflow is a persisted state machine so execution is deterministic,
resumable, and auditable (build-plan §3E: deterministic execution, state
persistence, retries, human approval checkpoints, rollback support).
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class WorkflowState(StrEnum):
    """States of a remediation workflow.

    Happy path: PENDING_APPROVAL -> APPROVED -> APPLYING -> RERUNNING -> RESOLVED
    Reject:     PENDING_APPROVAL -> REJECTED
    Failure:    ... -> RERUNNING -> (fallback) ... -> ROLLED_BACK
    """

    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    APPLYING = "applying"
    RERUNNING = "rerunning"
    RESOLVED = "resolved"
    ROLLED_BACK = "rolled_back"

    @property
    def is_terminal(self) -> bool:
        return self in {
            WorkflowState.RESOLVED,
            WorkflowState.REJECTED,
            WorkflowState.ROLLED_BACK,
        }


class FixAction(BaseModel):
    """One candidate fix the workflow can apply, derived from an RCA action."""

    title: str
    detail: str = ""
    kind: str = "spark_conf"  # spark_conf | code_change | rerun


class FixProposal(BaseModel):
    """An ordered set of candidate fixes proposed for a failed run.

    Actions are ordered by preference; the workflow tries them in sequence
    (the fallback chain) until one yields a successful rerun.
    """

    run_id: str
    cause_category: str
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    actions: list[FixAction] = Field(default_factory=list)


class WorkflowTransition(BaseModel):
    """A single state transition, recorded for the audit trail."""

    from_state: WorkflowState
    to_state: WorkflowState
    at: datetime
    note: str = ""


class RemediationWorkflow(BaseModel):
    """A persisted, auditable remediation workflow for one run."""

    workflow_id: str
    run_id: str
    state: WorkflowState = WorkflowState.PENDING_APPROVAL
    proposal: FixProposal
    approver: str | None = None
    rejection_reason: str | None = None
    #: The action (by index) that resolved the run, if any.
    applied_action_index: int | None = None
    attempts: int = 0
    transitions: list[WorkflowTransition] = Field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None
