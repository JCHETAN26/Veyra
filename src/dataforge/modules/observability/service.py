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

from dataforge.contracts.forecast import FailurePrediction, TrainingResult
from dataforge.contracts.incident import Finding, Incident, IncidentStatus
from dataforge.core.config import get_settings
from dataforge.core.db import session_scope
from dataforge.core.errors import NotFoundError
from dataforge.core.logging import get_logger
from dataforge.modules.metadata.incident_repository import IncidentRepository
from dataforge.modules.metadata.repository import MetadataRepository
from dataforge.modules.observability.detectors import (
    DetectorThresholds,
    run_detectors,
)
from dataforge.modules.observability.forecaster import (
    FailureForecaster,
    ForecasterError,
)
from dataforge.modules.observability.ml import (
    MLDetector,
    build_ml_detectors,
    run_ml_detectors,
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

    def __init__(
        self,
        thresholds: DetectorThresholds | None = None,
        *,
        ml_detectors: list[MLDetector] | None = None,
        history_limit: int | None = None,
        forecaster: FailureForecaster | None = None,
    ) -> None:
        self._thresholds = thresholds or DetectorThresholds()
        cfg = get_settings()
        # ML detectors are an injection point. When None (production), build
        # from settings — disabled by default, so the deterministic path is
        # unchanged. Tests pass a pre-built list to skip the dep gate.
        self._ml_detectors: list[MLDetector] = (
            ml_detectors if ml_detectors is not None else build_ml_detectors(cfg)
        )
        self._history_limit = (
            history_limit if history_limit is not None else cfg.ml_detector_history_limit
        )
        # Forecaster is per-process state, lazily fit. Held here rather than
        # in a module-level singleton so tests can inject a pre-fit instance.
        self._forecaster = forecaster or FailureForecaster()

    async def evaluate_run(self, run_id: str) -> list[Incident]:
        """Detect anomalies for a run and persist one incident per anomaly.

        Idempotent: re-evaluating the same run updates existing incidents
        rather than duplicating them. When ML detectors are enabled, the
        recent run history is fetched once and shared across them so the
        DB cost is a single query regardless of how many detectors run.
        """
        async with session_scope() as session:
            repo = MetadataRepository(session)
            run = await repo.get_run(run_id)
            if run is None:
                raise NotFoundError(f"run '{run_id}' not found")

            findings = run_detectors(run, self._thresholds)
            if self._ml_detectors:
                history = await repo.list_runs(limit=self._history_limit)
                # Exclude the run under evaluation so it doesn't bias its own
                # baseline. The baseline is "everything before this run."
                history = [h for h in history if h.run_id != run.run_id]
                findings.extend(
                    run_ml_detectors(
                        run,
                        history,
                        self._ml_detectors,
                        thresholds=self._thresholds,
                    )
                )

            detected_at = datetime.now(UTC)
            incidents = [_finding_to_incident(run_id, f, detected_at) for f in findings]

            incident_repo = IncidentRepository(session)
            for incident in incidents:
                await incident_repo.upsert(incident)

        logger.info(
            "observability.evaluated",
            run_id=run_id,
            num_incidents=len(incidents),
            num_ml_detectors=len(self._ml_detectors),
            status=run.status,
        )
        return incidents

    # ------------------------------------------------------------------
    # Failure forecasting
    # ------------------------------------------------------------------

    async def train_forecaster(self, *, history_limit: int = 500) -> TrainingResult:
        """Fit the failure forecaster from recent run history.

        Idempotent: calling repeatedly retrains the model. Returns the
        per-feature importances for caller introspection.
        """
        async with session_scope() as session:
            history = await MetadataRepository(session).list_runs(limit=history_limit)
        return self._forecaster.fit(history)

    async def predict_failure(self, app_name: str, *, window_limit: int = 50) -> FailurePrediction:
        """Predict the probability the next run of `app_name` will fail.

        Loads recent runs of that pipeline (most-recent first) and feeds the
        chronologically-ordered window into the trained forecaster.
        """
        async with session_scope() as session:
            history = await MetadataRepository(session).list_runs(limit=window_limit)
        relevant = [r for r in history if r.app_name == app_name]
        if len(relevant) < 2:
            raise ForecasterError(
                f"too few recent runs for pipeline '{app_name}': "
                f"have {len(relevant)}, need >= 2."
            )
        # list_runs returns most-recent first; predict expects oldest first.
        relevant.reverse()
        return self._forecaster.predict(relevant)
