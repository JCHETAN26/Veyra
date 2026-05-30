"""Pipeline processing report.

The consolidated result of running the full self-healing loop over a single
run: ingest -> detect -> explain -> recall -> propose (stopping at the human
approval gate). One object that shows what happened at every stage, so a
caller gets the whole picture from a single request.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from dataforge.contracts.incident import Incident
from dataforge.contracts.rca import RootCauseAnalysis
from dataforge.contracts.remediation_workflow import RemediationWorkflow
from dataforge.contracts.retrieval import SimilarIncident
from dataforge.contracts.telemetry import PipelineRun


class PipelineOutcome(StrEnum):
    """High-level outcome of processing a run through the loop."""

    HEALTHY = "healthy"  # no incidents detected
    NEEDS_APPROVAL = "needs_approval"  # remediation proposed, awaiting human
    NO_ACTIONABLE_FIX = "no_actionable_fix"  # anomalous but no auto-fix available


class PipelineReport(BaseModel):
    """End-to-end result of processing one run."""

    run_id: str
    outcome: PipelineOutcome
    run: PipelineRun
    incidents: list[Incident] = Field(default_factory=list)
    analysis: RootCauseAnalysis | None = None
    similar_incidents: list[SimilarIncident] = Field(default_factory=list)
    workflow: RemediationWorkflow | None = None
