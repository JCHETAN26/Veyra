"""MLDetector protocol + aggregator.

Distinct from the rule-based `Detector` protocol because ML detectors are
inherently history-aware: their notion of "anomalous" only makes sense
relative to a baseline of past runs. Keeping them on a separate protocol
makes the dispatch explicit at the service boundary and lets us evolve
the contract (e.g. per-pipeline history slicing) without disrupting the
deterministic detectors.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from dataforge.contracts.incident import Finding
from dataforge.contracts.telemetry import PipelineRun
from dataforge.core.errors import DataForgeError
from dataforge.core.logging import get_logger
from dataforge.modules.observability.detectors import DetectorThresholds

logger = get_logger(__name__)


class MLDetectorError(DataForgeError):
    """An ML detector is misconfigured (missing dep, unknown kind, ...)."""

    code = "ml_detector_error"
    status_code = 500


@runtime_checkable
class MLDetector(Protocol):
    """A history-aware anomaly detector."""

    name: str
    requires_history: int  # minimum history size to run; smaller -> skip

    def detect(
        self,
        run: PipelineRun,
        history: list[PipelineRun],
        thresholds: DetectorThresholds,
    ) -> Finding | None:
        """Return a Finding if the run looks anomalous against `history`."""
        ...


def run_ml_detectors(
    run: PipelineRun,
    history: list[PipelineRun],
    detectors: list[MLDetector],
    *,
    thresholds: DetectorThresholds | None = None,
) -> list[Finding]:
    """Run every ML detector that has enough history. Errors are isolated.

    A single misbehaving ML detector must not take down the rest of the
    pipeline. If one raises, we log and continue — the deterministic rule-
    based detectors still produced findings, and the loop progresses.
    """
    th = thresholds or DetectorThresholds()
    findings: list[Finding] = []
    for d in detectors:
        if len(history) < d.requires_history:
            logger.info(
                "ml_detector.skipped_insufficient_history",
                detector=d.name,
                have=len(history),
                need=d.requires_history,
            )
            continue
        try:
            finding = d.detect(run, history, th)
        except Exception as exc:  # noqa: BLE001 - ML detectors must not fail loud
            logger.warning(
                "ml_detector.errored",
                detector=d.name,
                error=str(exc),
                error_class=type(exc).__name__,
            )
            continue
        if finding is not None:
            findings.append(finding)
    return findings
