"""End-to-end tests for the chaos simulator.

Each scenario is verified by:
  1. parsing it through the real ingestion event-log parser,
  2. running it through the real detectors,
  3. running it through the rule-based RCA analyzer,
and asserting the resulting RootCauseAnalysis lands in the expected
category. This makes the simulator a regression test for the detector +
analyzer stack as much as a demo-driver.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from dataforge.contracts.incident import AnomalyType, Incident, IncidentStatus
from dataforge.contracts.rca import CauseCategory
from dataforge.contracts.telemetry import RunStatus
from dataforge.modules.ingestion.spark_eventlog import parse_event_log
from dataforge.modules.observability.detectors import run_detectors
from dataforge.modules.remediation.rca import RuleBasedAnalyzer
from dataforge.simulator import SCENARIOS, build_scenario, events_to_jsonl
from dataforge.simulator.cli import run as cli_run


def _ingest(content: str, *, run_id: str) -> tuple[object, list[Incident]]:
    run = parse_event_log(content, run_id=run_id)
    findings = run_detectors(run)
    incidents = [
        Incident(
            incident_id=f"inc-{i}",
            run_id=run_id,
            anomaly_type=f.anomaly_type,
            severity=f.severity,
            status=IncidentStatus.OPEN,
            title=f.title,
            description=f.description,
            signals=f.signals,
        )
        for i, f in enumerate(findings)
    ]
    return run, incidents


def _analyze(run: object, incidents: list[Incident]) -> CauseCategory:
    analysis = asyncio.run(RuleBasedAnalyzer().analyze(run, incidents))  # type: ignore[arg-type]
    return analysis.category


# --- JSONL round-trip ------------------------------------------------------


def test_events_to_jsonl_is_one_event_per_line() -> None:
    events = build_scenario("healthy", run_id="r")
    content = events_to_jsonl(events)
    lines = [line for line in content.splitlines() if line.strip()]
    assert len(lines) == len(events)
    for line in lines:
        json.loads(line)


# --- Scenario behavior -----------------------------------------------------


def test_healthy_run_parses_clean_and_raises_no_incidents() -> None:
    content = events_to_jsonl(build_scenario("healthy", run_id="sim-healthy"))
    run, incidents = _ingest(content, run_id="sim-healthy")
    assert run.status == RunStatus.SUCCEEDED  # type: ignore[attr-defined]
    assert run.failure is None  # type: ignore[attr-defined]
    assert incidents == []


def test_oom_join_lands_in_memory_pressure() -> None:
    content = events_to_jsonl(build_scenario("oom_join", run_id="sim-oom"))
    run, incidents = _ingest(content, run_id="sim-oom")
    assert run.status == RunStatus.FAILED  # type: ignore[attr-defined]
    assert "OutOfMemory" in (run.failure.error_class or "")  # type: ignore[attr-defined]

    types = {i.anomaly_type for i in incidents}
    assert AnomalyType.RUN_FAILURE in types
    assert AnomalyType.EXCESSIVE_SPILL in types
    assert _analyze(run, incidents) == CauseCategory.MEMORY_PRESSURE


def test_data_skew_lands_in_data_skew() -> None:
    content = events_to_jsonl(build_scenario("data_skew", run_id="sim-skew"))
    run, incidents = _ingest(content, run_id="sim-skew")
    assert run.status == RunStatus.SUCCEEDED  # type: ignore[attr-defined]
    types = {i.anomaly_type for i in incidents}
    assert AnomalyType.EXCESSIVE_SPILL in types
    assert _analyze(run, incidents) == CauseCategory.DATA_SKEW


def test_flaky_executors_lands_in_transient_failure() -> None:
    content = events_to_jsonl(build_scenario("flaky_executors", run_id="sim-flaky"))
    run, incidents = _ingest(content, run_id="sim-flaky")
    assert run.status == RunStatus.SUCCEEDED  # type: ignore[attr-defined]
    types = {i.anomaly_type for i in incidents}
    assert AnomalyType.HIGH_FAILED_TASK_RATIO in types
    assert _analyze(run, incidents) == CauseCategory.TRANSIENT_FAILURE


def test_long_duration_lands_in_performance_regression() -> None:
    content = events_to_jsonl(build_scenario("long_duration", run_id="sim-slow"))
    run, incidents = _ingest(content, run_id="sim-slow")
    assert run.status == RunStatus.SUCCEEDED  # type: ignore[attr-defined]
    assert run.duration_ms is not None and run.duration_ms >= 30 * 60 * 1000  # type: ignore[attr-defined]
    types = {i.anomaly_type for i in incidents}
    assert AnomalyType.LONG_DURATION in types
    assert _analyze(run, incidents) == CauseCategory.PERFORMANCE_REGRESSION


def test_schema_drift_is_failed_run_with_classcast_error() -> None:
    content = events_to_jsonl(build_scenario("schema_drift", run_id="sim-drift"))
    run, incidents = _ingest(content, run_id="sim-drift")
    assert run.status == RunStatus.FAILED  # type: ignore[attr-defined]
    assert "ClassCastException" in (run.failure.error_class or "")  # type: ignore[attr-defined]
    assert any(i.anomaly_type == AnomalyType.RUN_FAILURE for i in incidents)


def test_dependency_failure_is_failed_run_with_socket_timeout() -> None:
    content = events_to_jsonl(build_scenario("dependency_failure", run_id="sim-dep"))
    run, incidents = _ingest(content, run_id="sim-dep")
    assert run.status == RunStatus.FAILED  # type: ignore[attr-defined]
    assert "SocketTimeout" in (run.failure.error_class or "")  # type: ignore[attr-defined]
    assert any(i.anomaly_type == AnomalyType.RUN_FAILURE for i in incidents)


# --- Determinism -----------------------------------------------------------


def test_scenarios_are_deterministic() -> None:
    """Re-running the same scenario must produce byte-identical JSONL."""
    for name in SCENARIOS:
        a = events_to_jsonl(build_scenario(name, run_id="r-fixed"))
        b = events_to_jsonl(build_scenario(name, run_id="r-fixed"))
        assert a == b, f"scenario {name} is not deterministic"


def test_build_scenario_raises_on_unknown_name() -> None:
    with pytest.raises(KeyError):
        build_scenario("does_not_exist", run_id="r")


# --- CLI -------------------------------------------------------------------


def test_cli_list_prints_all_scenarios(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = cli_run(["--list"])
    assert exit_code == 0
    out = capsys.readouterr().out
    for name in SCENARIOS:
        assert name in out


def test_cli_emits_jsonl_to_stdout(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = cli_run(["--scenario", "data_skew", "--run-id", "cli-test-1"])
    assert exit_code == 0
    out = capsys.readouterr().out
    lines = [line for line in out.splitlines() if line.strip()]
    assert len(lines) > 5
    for line in lines:
        json.loads(line)


def test_cli_writes_to_file(tmp_path) -> None:  # type: ignore[no-untyped-def]
    out_path = tmp_path / "out.jsonl"
    exit_code = cli_run(
        [
            "--scenario",
            "oom_join",
            "--run-id",
            "cli-test-2",
            "--output",
            str(out_path),
        ]
    )
    assert exit_code == 0
    content = out_path.read_text()
    # File parses through the real ingestion path end-to-end.
    run = parse_event_log(content, run_id="cli-test-2")
    assert run.status == RunStatus.FAILED


def test_cli_rejects_unknown_scenario(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        cli_run(["--scenario", "bogus", "--run-id", "x"])
    err = capsys.readouterr().err
    assert "unknown scenario" in err


def test_cli_requires_scenario_and_run_id(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        cli_run([])
    err = capsys.readouterr().err
    assert "--scenario" in err
