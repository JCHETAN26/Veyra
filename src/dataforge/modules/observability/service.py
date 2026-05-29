"""Observability service.

Evaluates a persisted pipeline run with the deterministic detectors and raises
incidents. This is the entry point of the self-healing loop: ingestion lands a
run, observability detects anomalies and opens an incident, which RCA / RAG /
remediation then act on.

Depends on metadata only through repository ports (read runs, write incidents),
preserving the module boundary.
"""

from __future__ import annotations

from datetime import UTC, datetime

from dataforge.contracts.incident import Finding, Incident, IncidentStatus
from dataforge.core.db import session_scope
from dataforge.core.errors import NotFoundError
from dataforge.core.logging import get_logger
from dataforge.modules.metadata.incident_repository import IncidentRepository
from dataforge.modules.metadata.repository import MetadataRepository
from dataforge.modules.observability.detectors import (
    DetectorThresholds,
    run_detectors,
)

logger = get_logger(__name__)


def _incident_id(run_id: str, anomaly_type: str) -> str:
    """Deterministic incident id so re-detection is idempotent."""
    return f"inc-{run_id}-{anomaly_type}"


def _finding_to_incident(run_id: str, finding: Finding, detected_at: datetime) -> Incident:
    return Incident(
        incident_id=_incident_id(run_id, finding.anomaly_type.value),
        run_id=run_id,
        anomaly_type=finding.anomaly_type,
        severity=finding.severity,
        status=IncidentStatus.OPEN,
        title=finding.title,
        description=finding.description,
        signals=finding.signals,
        detected_at=detected_at,
    )


class ObservabilityService:
    """Runs anomaly detection over pipeline runs and raises incidents."""

    def __init__(self, thresholds: DetectorThresholds | None = None) -> None:
        self._thresholds = thresholds or DetectorThresholds()

    async def evaluate_run(self, run_id: str) -> list[Incident]:
        """Detect anomalies for a run and persist one incident per anomaly.

        Idempotent: re-evaluating the same run updates existing incidents
        rather than duplicating them.
        """
        async with session_scope() as session:
            run = await MetadataRepository(session).get_run(run_id)
            if run is None:
                raise NotFoundError(f"run '{run_id}' not found")

            findings = run_detectors(run, self._thresholds)
            detected_at = datetime.now(UTC)
            incidents = [_finding_to_incident(run_id, f, detected_at) for f in findings]

            incident_repo = IncidentRepository(session)
            for incident in incidents:
                await incident_repo.upsert(incident)

        logger.info(
            "observability.evaluated",
            run_id=run_id,
            num_incidents=len(incidents),
            status=run.status,
        )
        return incidents
