"""Unit tests for the rule-based root-cause analyzer."""

from __future__ import annotations

from dataforge.contracts.incident import (
    AnomalyType,
    Incident,
    IncidentStatus,
    Severity,
)
from dataforge.contracts.rca import CauseCategory
from dataforge.contracts.telemetry import (
    FailureInfo,
    PipelineRun,
    RunMetrics,
    RunStatus,
)
from dataforge.modules.remediation.rca import RuleBasedAnalyzer


def _run(**overrides: object) -> PipelineRun:
    base: dict[str, object] = {
        "run_id": "r1",
        "app_name": "app",
        "status": RunStatus.SUCCEEDED,
        "metrics": RunMetrics(),
    }
    base.update(overrides)
    return PipelineRun(**base)  # type: ignore[arg-type]


def _incident(anomaly: AnomalyType, severity: Severity = Severity.MEDIUM) -> Incident:
    return Incident(
        incident_id=f"inc-{anomaly.value}",
        run_id="r1",
        anomaly_type=anomaly,
        severity=severity,
        status=IncidentStatus.OPEN,
        title=anomaly.value,
        description="",
    )


async def test_oom_classified_as_memory_pressure() -> None:
    run = _run(
        status=RunStatus.FAILED,
        failure=FailureInfo(error_class="java.lang.OutOfMemoryError", message="Java heap space"),
        metrics=RunMetrics(
            num_tasks=10,
            memory_spilled_bytes=300 * 1024 * 1024,
            disk_spilled_bytes=300 * 1024 * 1024,
        ),
    )
    incidents = [
        _incident(AnomalyType.RUN_FAILURE, Severity.CRITICAL),
        _incident(AnomalyType.EXCESSIVE_SPILL),
    ]
    analysis = await RuleBasedAnalyzer().analyze(run, incidents)

    assert analysis.category == CauseCategory.MEMORY_PRESSURE
    assert analysis.confidence >= 0.8
    assert analysis.recommended_actions
    assert any(a.kind == "spark_conf" for a in analysis.recommended_actions)
    assert set(analysis.incident_ids) == {i.incident_id for i in incidents}


async def test_heavy_spill_without_failure_is_skew() -> None:
    run = _run(
        status=RunStatus.SUCCEEDED,
        metrics=RunMetrics(
            num_tasks=20,
            memory_spilled_bytes=400 * 1024 * 1024,
        ),
    )
    incidents = [_incident(AnomalyType.EXCESSIVE_SPILL)]
    analysis = await RuleBasedAnalyzer().analyze(run, incidents)
    assert analysis.category == CauseCategory.DATA_SKEW


async def test_flaky_tasks_on_success_is_transient() -> None:
    run = _run(
        status=RunStatus.SUCCEEDED,
        metrics=RunMetrics(num_tasks=100, num_failed_tasks=20),
    )
    incidents = [_incident(AnomalyType.HIGH_FAILED_TASK_RATIO)]
    analysis = await RuleBasedAnalyzer().analyze(run, incidents)
    assert analysis.category == CauseCategory.TRANSIENT_FAILURE


async def test_long_duration_is_performance_regression() -> None:
    run = _run(status=RunStatus.SUCCEEDED, duration_ms=45 * 60 * 1000)
    incidents = [_incident(AnomalyType.LONG_DURATION)]
    analysis = await RuleBasedAnalyzer().analyze(run, incidents)
    assert analysis.category == CauseCategory.PERFORMANCE_REGRESSION


async def test_unmatched_failure_is_unknown_low_confidence() -> None:
    run = _run(
        status=RunStatus.FAILED,
        failure=FailureInfo(message="some unrecognized error"),
    )
    incidents = [_incident(AnomalyType.RUN_FAILURE, Severity.HIGH)]
    analysis = await RuleBasedAnalyzer().analyze(run, incidents)
    assert analysis.category == CauseCategory.UNKNOWN
    assert analysis.confidence < 0.5
    assert analysis.recommended_actions  # still suggests manual triage


async def test_clean_run_yields_no_cause() -> None:
    run = _run(status=RunStatus.SUCCEEDED, metrics=RunMetrics(num_tasks=10))
    analysis = await RuleBasedAnalyzer().analyze(run, [])
    assert analysis.category == CauseCategory.UNKNOWN
    assert analysis.confidence == 0.0


async def test_oom_takes_precedence_over_spill_rule() -> None:
    # Both OOM and spill present: most-specific (OOM) rule must win.
    run = _run(
        status=RunStatus.FAILED,
        failure=FailureInfo(error_class="java.lang.OutOfMemoryError"),
        metrics=RunMetrics(num_tasks=10, disk_spilled_bytes=500 * 1024 * 1024),
    )
    incidents = [
        _incident(AnomalyType.RUN_FAILURE, Severity.CRITICAL),
        _incident(AnomalyType.EXCESSIVE_SPILL),
    ]
    analysis = await RuleBasedAnalyzer().analyze(run, incidents)
    assert analysis.category == CauseCategory.MEMORY_PRESSURE


async def test_analyzer_is_deterministic() -> None:
    run = _run(
        status=RunStatus.FAILED,
        failure=FailureInfo(error_class="java.lang.OutOfMemoryError"),
        metrics=RunMetrics(num_tasks=10, memory_spilled_bytes=512 * 1024 * 1024),
    )
    incidents = [_incident(AnomalyType.EXCESSIVE_SPILL)]
    a = await RuleBasedAnalyzer().analyze(run, incidents)
    b = await RuleBasedAnalyzer().analyze(run, incidents)
    assert a.model_dump() == b.model_dump()
