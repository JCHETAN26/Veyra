"""Incident and anomaly contracts.

An Incident is the canonical unit the self-healing loop revolves around: the
observability module detects anomalies and raises incidents; RCA explains
them; RAG retrieves similar past ones; remediation proposes fixes. Keeping
these as shared contracts lets every downstream module reason over one shape.
"""

from __future__ import annotations

from datetime import datetime
from enum import IntEnum, StrEnum

from pydantic import BaseModel, Field


class Severity(IntEnum):
    """Ordered severity so detectors can be compared with max()."""

    INFO = 10
    LOW = 20
    MEDIUM = 30
    HIGH = 40
    CRITICAL = 50

    @property
    def label(self) -> str:
        return self.name.lower()


class AnomalyType(StrEnum):
    RUN_FAILURE = "run_failure"
    EXCESSIVE_SPILL = "excessive_spill"
    HIGH_FAILED_TASK_RATIO = "high_failed_task_ratio"
    LONG_DURATION = "long_duration"


class IncidentStatus(StrEnum):
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"


class AnomalySignal(BaseModel):
    """A single quantified observation that contributed to an incident."""

    name: str
    value: float
    threshold: float | None = None
    detail: str = ""


class Finding(BaseModel):
    """A detector's verdict for one anomaly type on one run.

    Findings are transient (not persisted directly); the service bundles them
    into an Incident.
    """

    anomaly_type: AnomalyType
    severity: Severity
    title: str
    description: str
    signals: list[AnomalySignal] = Field(default_factory=list)


class Incident(BaseModel):
    """A persisted operational incident raised for a pipeline run."""

    incident_id: str
    run_id: str
    anomaly_type: AnomalyType
    severity: Severity
    status: IncidentStatus = IncidentStatus.OPEN
    title: str
    description: str
    signals: list[AnomalySignal] = Field(default_factory=list)
    detected_at: datetime | None = None
