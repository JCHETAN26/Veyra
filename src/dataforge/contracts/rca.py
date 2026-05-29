"""Root-cause analysis contracts.

A RootCauseAnalysis is the bridge between detection (incidents) and
remediation (fixes): given a failed/anomalous run and the incidents raised
for it, it explains *why* in structured, plain language and proposes actions.

It is produced behind the RootCauseAnalyzer interface, so a deterministic
rule-based analyzer (MVP) and an LLM-backed analyzer (later) are
interchangeable without touching callers.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class CauseCategory(StrEnum):
    """Coarse root-cause taxonomy the analyzers classify into."""

    MEMORY_PRESSURE = "memory_pressure"
    DATA_SKEW = "data_skew"
    TRANSIENT_FAILURE = "transient_failure"
    PERFORMANCE_REGRESSION = "performance_regression"
    DEPENDENCY_FAILURE = "dependency_failure"
    UNKNOWN = "unknown"


class RecommendedAction(BaseModel):
    """A concrete, human-reviewable action proposed by the analysis."""

    title: str
    detail: str = ""
    # A coarse hint at how this could be applied later by remediation.
    kind: str = "manual"  # e.g. manual | spark_conf | code_change | rerun


class RootCauseAnalysis(BaseModel):
    """Structured explanation of why a run failed or behaved anomalously."""

    analysis_id: str
    run_id: str
    category: CauseCategory
    summary: str
    explanation: str
    contributing_factors: list[str] = Field(default_factory=list)
    recommended_actions: list[RecommendedAction] = Field(default_factory=list)
    # Confidence in [0, 1]; deterministic per analyzer rule for the MVP.
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    incident_ids: list[str] = Field(default_factory=list)
    analyzer: str = "rule-based-v1"
    created_at: datetime | None = None
