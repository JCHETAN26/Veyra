"""Unit tests for the deterministic anomaly detectors."""

from __future__ import annotations

from dataforge.contracts.incident import AnomalyType, Severity
from dataforge.contracts.telemetry import (
    FailureInfo,
    PipelineRun,
    RunMetrics,
    RunStatus,
)
from dataforge.modules.observability.detectors import (
    DetectorThresholds,
    run_detectors,
)


def _run(**overrides: object) -> PipelineRun:
    base: dict[str, object] = {
        "run_id": "r1",
        "app_name": "test_app",
        "status": RunStatus.SUCCEEDED,
        "metrics": RunMetrics(),
    }
    base.update(overrides)
    return PipelineRun(**base)  # type: ignore[arg-type]


def test_clean_run_produces_no_findings() -> None:
    run = _run(metrics=RunMetrics(num_tasks=100, num_failed_tasks=0))
    assert run_detectors(run) == []


def test_failed_run_is_high_severity() -> None:
    run = _run(status=RunStatus.FAILED)
    findings = run_detectors(run)
    failure = [f for f in findings if f.anomaly_type == AnomalyType.RUN_FAILURE]
    assert len(failure) == 1
    assert failure[0].severity == Severity.HIGH


def test_oom_failure_escalates_to_critical() -> None:
    run = _run(
        status=RunStatus.FAILED,
        failure=FailureInfo(error_class="java.lang.OutOfMemoryError", message="Java heap space"),
    )
    findings = run_detectors(run)
    failure = next(f for f in findings if f.anomaly_type == AnomalyType.RUN_FAILURE)
    assert failure.severity == Severity.CRITICAL
    assert any(s.name == "error_class" for s in failure.signals)


def test_excessive_spill_detected() -> None:
    run = _run(
        metrics=RunMetrics(
            num_tasks=10,
            memory_spilled_bytes=200 * 1024 * 1024,
            disk_spilled_bytes=200 * 1024 * 1024,
        )
    )
    findings = run_detectors(run)
    spill = [f for f in findings if f.anomaly_type == AnomalyType.EXCESSIVE_SPILL]
    assert len(spill) == 1
    assert spill[0].severity == Severity.MEDIUM


def test_spill_below_threshold_not_detected() -> None:
    run = _run(metrics=RunMetrics(num_tasks=10, memory_spilled_bytes=1024))
    findings = run_detectors(run)
    assert not any(f.anomaly_type == AnomalyType.EXCESSIVE_SPILL for f in findings)


def test_high_failed_task_ratio_detected() -> None:
    run = _run(metrics=RunMetrics(num_tasks=100, num_failed_tasks=20))
    findings = run_detectors(run)
    assert any(f.anomaly_type == AnomalyType.HIGH_FAILED_TASK_RATIO for f in findings)


def test_long_duration_detected() -> None:
    run = _run(duration_ms=45 * 60 * 1000)
    findings = run_detectors(run)
    assert any(f.anomaly_type == AnomalyType.LONG_DURATION for f in findings)


def test_detectors_are_deterministic() -> None:
    run = _run(
        status=RunStatus.FAILED,
        failure=FailureInfo(error_class="java.lang.OutOfMemoryError"),
        metrics=RunMetrics(
            num_tasks=50,
            num_failed_tasks=10,
            memory_spilled_bytes=512 * 1024 * 1024,
        ),
    )
    first = run_detectors(run)
    second = run_detectors(run)
    assert [f.model_dump() for f in first] == [f.model_dump() for f in second]


def test_custom_thresholds_respected() -> None:
    run = _run(metrics=RunMetrics(num_tasks=10, memory_spilled_bytes=1024))
    # Lower the spill threshold below the observed value.
    th = DetectorThresholds(spill_bytes=512)
    findings = run_detectors(run, th)
    assert any(f.anomaly_type == AnomalyType.EXCESSIVE_SPILL for f in findings)
