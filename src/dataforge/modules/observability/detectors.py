"""Anomaly detectors.

Each detector is a deterministic pure function: (PipelineRun, thresholds) ->
Finding | None. No I/O, no randomness, no clock reads — so the same run always
yields the same findings, which is required for reproducible incidents and
testable remediation (build-plan §6 Rule 7, §17).

Detectors are intentionally simple and explainable for the MVP. The ML-based
detectors (anomaly models, cost forecasting) layer in later behind this same
Finding contract.
"""

from __future__ import annotations

from collections.abc import Callable

from pydantic import BaseModel, Field

from dataforge.contracts.incident import (
    AnomalySignal,
    AnomalyType,
    Finding,
    Severity,
)
from dataforge.contracts.telemetry import PipelineRun, RunStatus


class DetectorThresholds(BaseModel):
    """Tunable thresholds for the rule-based detectors."""

    # Fraction of total tasks that failed to flag as anomalous.
    failed_task_ratio: float = Field(default=0.05, ge=0.0, le=1.0)
    # Total spill (memory + disk) in bytes above which a run is flagged.
    spill_bytes: int = Field(default=256 * 1024 * 1024, ge=0)  # 256 MiB
    # Run duration in milliseconds above which a run is flagged.
    long_duration_ms: int = Field(default=30 * 60 * 1000, ge=0)  # 30 min


Detector = Callable[[PipelineRun, DetectorThresholds], Finding | None]


def detect_run_failure(run: PipelineRun, _thresholds: DetectorThresholds) -> Finding | None:
    """A failed run is always an incident; severity escalates on a known cause."""
    if run.status != RunStatus.FAILED:
        return None

    severity = Severity.HIGH
    signals: list[AnomalySignal] = []
    description = f"Pipeline run '{run.app_name}' failed."

    if run.failure is not None:
        if run.failure.error_class:
            signals.append(
                AnomalySignal(
                    name="error_class",
                    value=1.0,
                    detail=run.failure.error_class,
                )
            )
            description = (
                f"Pipeline run '{run.app_name}' failed with "
                f"{run.failure.error_class}: {run.failure.message[:200]}"
            )
        # An OOM is a more severe, well-understood class -> CRITICAL.
        if run.failure.error_class and "OutOfMemory" in run.failure.error_class:
            severity = Severity.CRITICAL

    return Finding(
        anomaly_type=AnomalyType.RUN_FAILURE,
        severity=severity,
        title="Pipeline run failed",
        description=description,
        signals=signals,
    )


def detect_excessive_spill(run: PipelineRun, thresholds: DetectorThresholds) -> Finding | None:
    """Large memory/disk spill signals memory pressure / skew."""
    total_spill = run.metrics.memory_spilled_bytes + run.metrics.disk_spilled_bytes
    if total_spill <= thresholds.spill_bytes:
        return None

    return Finding(
        anomaly_type=AnomalyType.EXCESSIVE_SPILL,
        severity=Severity.MEDIUM,
        title="Excessive spill to memory/disk",
        description=(
            f"Run spilled {total_spill:,} bytes "
            f"(threshold {thresholds.spill_bytes:,}), indicating memory "
            "pressure or data skew."
        ),
        signals=[
            AnomalySignal(
                name="total_spill_bytes",
                value=float(total_spill),
                threshold=float(thresholds.spill_bytes),
            ),
            AnomalySignal(
                name="memory_spilled_bytes",
                value=float(run.metrics.memory_spilled_bytes),
            ),
            AnomalySignal(
                name="disk_spilled_bytes",
                value=float(run.metrics.disk_spilled_bytes),
            ),
        ],
    )


def detect_high_failed_task_ratio(
    run: PipelineRun, thresholds: DetectorThresholds
) -> Finding | None:
    """A high failed-task ratio signals flaky/unstable execution."""
    total = run.metrics.num_tasks
    if total <= 0:
        return None
    ratio = run.metrics.num_failed_tasks / total
    if ratio <= thresholds.failed_task_ratio:
        return None

    return Finding(
        anomaly_type=AnomalyType.HIGH_FAILED_TASK_RATIO,
        severity=Severity.MEDIUM,
        title="High failed-task ratio",
        description=(
            f"{run.metrics.num_failed_tasks}/{total} tasks failed "
            f"({ratio:.0%}), above the {thresholds.failed_task_ratio:.0%} "
            "threshold."
        ),
        signals=[
            AnomalySignal(
                name="failed_task_ratio",
                value=round(ratio, 4),
                threshold=thresholds.failed_task_ratio,
            )
        ],
    )


def detect_long_duration(run: PipelineRun, thresholds: DetectorThresholds) -> Finding | None:
    """An unusually long run may indicate a regression or resource starvation."""
    if run.duration_ms is None or run.duration_ms <= thresholds.long_duration_ms:
        return None

    return Finding(
        anomaly_type=AnomalyType.LONG_DURATION,
        severity=Severity.LOW,
        title="Long run duration",
        description=(
            f"Run took {run.duration_ms:,} ms, above the "
            f"{thresholds.long_duration_ms:,} ms threshold."
        ),
        signals=[
            AnomalySignal(
                name="duration_ms",
                value=float(run.duration_ms),
                threshold=float(thresholds.long_duration_ms),
            )
        ],
    )


# Registry of active detectors, evaluated in order.
DETECTORS: list[Detector] = [
    detect_run_failure,
    detect_excessive_spill,
    detect_high_failed_task_ratio,
    detect_long_duration,
]


def run_detectors(run: PipelineRun, thresholds: DetectorThresholds | None = None) -> list[Finding]:
    """Run all detectors over a pipeline run, returning the findings that fired."""
    th = thresholds or DetectorThresholds()
    findings: list[Finding] = []
    for detector in DETECTORS:
        finding = detector(run, th)
        if finding is not None:
            findings.append(finding)
    return findings
