"""Failure profile.

A consolidated, embeddable view of a run's operational signature, assembled
from its canonical telemetry, incidents, and root-cause analysis. This is the
unit RAG indexes and queries, so similarity reflects operational likeness
(same error class, cause, anomaly mix) rather than prose overlap.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from dataforge.contracts.incident import Incident
from dataforge.contracts.rca import RootCauseAnalysis
from dataforge.contracts.telemetry import PipelineRun


class FailureProfile(BaseModel):
    """The indexed representation of a run's failure signature."""

    run_id: str
    app_name: str = ""
    category: str | None = None
    summary: str = ""
    severity: str | None = None
    anomaly_types: list[str] = Field(default_factory=list)
    error_class: str | None = None
    occurred_at: datetime | None = None
    #: Tokenized feature bag the embedder hashes. Order-independent in effect.
    tokens: list[str] = Field(default_factory=list)

    def to_text(self) -> str:
        """Human-readable rendering (useful for an LLM embedder later)."""
        parts = [
            f"app={self.app_name}",
            f"category={self.category or 'unknown'}",
            f"error={self.error_class or 'none'}",
            f"anomalies={','.join(sorted(self.anomaly_types)) or 'none'}",
            self.summary,
        ]
        return " | ".join(p for p in parts if p)


def build_profile(
    run: PipelineRun,
    incidents: list[Incident],
    analysis: RootCauseAnalysis | None,
) -> FailureProfile:
    """Assemble a FailureProfile from a run and its derived signals."""
    anomaly_types = sorted({i.anomaly_type.value for i in incidents})
    top_severity = (
        max(incidents, key=lambda i: int(i.severity)).severity.label if incidents else None
    )
    error_class = run.failure.error_class if run.failure else None
    category = analysis.category.value if analysis else None
    summary = analysis.summary if analysis else ""

    tokens = _build_tokens(
        app_name=run.app_name,
        error_class=error_class,
        category=category,
        anomaly_types=anomaly_types,
        status=run.status.value,
    )

    return FailureProfile(
        run_id=run.run_id,
        app_name=run.app_name,
        category=category,
        summary=summary,
        severity=top_severity,
        anomaly_types=anomaly_types,
        error_class=error_class,
        occurred_at=run.started_at,
        tokens=tokens,
    )


def build_profile_from_fields(
    *,
    run_id: str,
    app_name: str = "",
    category: str | None = None,
    summary: str = "",
    severity: str | None = None,
    anomaly_types: list[str] | None = None,
    error_class: str | None = None,
    occurred_at: datetime | None = None,
    status: str = "unknown",
) -> FailureProfile:
    """Build a FailureProfile directly from pre-extracted fields.

    Used by external-dataset loaders (postmortems, Loghub samples, ...) that
    don't have a synthetic PipelineRun to back the profile. Token weighting
    is identical to `build_profile`, so a profile assembled here ranks
    consistently against profiles assembled from real runs.
    """
    anomalies = anomaly_types or []
    tokens = _build_tokens(
        app_name=app_name,
        error_class=error_class,
        category=category,
        anomaly_types=anomalies,
        status=status,
    )
    return FailureProfile(
        run_id=run_id,
        app_name=app_name,
        category=category,
        summary=summary,
        severity=severity,
        anomaly_types=anomalies,
        error_class=error_class,
        occurred_at=occurred_at,
        tokens=tokens,
    )


def _build_tokens(
    *,
    app_name: str,
    error_class: str | None,
    category: str | None,
    anomaly_types: list[str],
    status: str,
) -> list[str]:
    """Build the weighted feature bag.

    Operationally salient features (error class, cause, anomalies) are repeated
    to weight them above incidental ones (app name), so OOM failures cluster by
    cause rather than by which app emitted them.
    """
    tokens: list[str] = [f"status:{status}"]
    if error_class:
        # Index both the full class and its short name for partial matches.
        tokens += [f"error:{error_class}"] * 3
        short = error_class.rsplit(".", 1)[-1]
        tokens += [f"errorname:{short}"] * 2
    if category:
        tokens += [f"cause:{category}"] * 3
    for anomaly in anomaly_types:
        tokens += [f"anomaly:{anomaly}"] * 2
    if app_name:
        tokens.append(f"app:{app_name}")
    return tokens
