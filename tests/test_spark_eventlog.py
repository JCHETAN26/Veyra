"""Unit tests for the Spark event-log parser."""

from __future__ import annotations

from pathlib import Path

import pytest

from dataforge.contracts.telemetry import RunStatus
from dataforge.modules.ingestion.spark_eventlog import parse_event_log

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def success_log() -> str:
    return (FIXTURES / "spark_eventlog_success.jsonl").read_text()


@pytest.fixture
def failure_log() -> str:
    return (FIXTURES / "spark_eventlog_failure.jsonl").read_text()


def test_parses_successful_run(success_log: str) -> None:
    run = parse_event_log(success_log, run_id="run-success")

    assert run.run_id == "run-success"
    assert run.app_name == "nyc_taxi_etl"
    assert run.spark_user == "dataforge"
    assert run.status == RunStatus.SUCCEEDED
    assert run.failure is None
    assert run.duration_ms == 8000  # 1717000008000 - 1717000000000


def test_aggregates_metrics(success_log: str) -> None:
    run = parse_event_log(success_log, run_id="run-success")
    m = run.metrics

    assert m.num_jobs == 1
    assert m.num_stages == 2
    assert m.num_tasks == 3
    assert m.num_failed_tasks == 0
    # 2500 + 2600 + 1500
    assert m.executor_run_time_ms == 6600
    # remote+local across 3 tasks: (1048576+524288)*2 + (2097152+0)
    assert m.shuffle_read_bytes == 5242880
    assert m.shuffle_write_bytes == 4194304


def test_stages_ordered_and_named(success_log: str) -> None:
    run = parse_event_log(success_log, run_id="run-success")
    assert [s.stage_id for s in run.stages] == [0, 1]
    assert run.stages[0].name == "read parquet"
    assert run.stages[0].duration_ms == 3000


def test_parses_failed_run_with_stack_trace(failure_log: str) -> None:
    run = parse_event_log(failure_log, run_id="run-failure")

    assert run.status == RunStatus.FAILED
    assert run.metrics.num_failed_tasks == 1
    assert run.failure is not None
    assert run.failure.error_class == "java.lang.OutOfMemoryError"
    assert "Java heap space" in run.failure.message
    assert run.failure.stack_trace is not None
    assert "SortMergeJoinExec" in run.failure.stack_trace
    assert run.failure.stage_id == 0


def test_captures_spill_signals(failure_log: str) -> None:
    run = parse_event_log(failure_log, run_id="run-failure")
    # OOM run spilled to memory and disk — key RCA signal.
    assert run.metrics.memory_spilled_bytes > 0
    assert run.metrics.disk_spilled_bytes > 0


def test_tolerates_malformed_lines() -> None:
    log = "\n".join(
        [
            '{"Event":"SparkListenerApplicationStart","App Name":"x",'
            '"App ID":"a","Timestamp":1717000000000,"User":"u"}',
            "this is not json",
            '{"Event":"SparkListenerApplicationEnd","Timestamp":1717000001000}',
        ]
    )
    run = parse_event_log(log, run_id="run-partial")
    assert run.app_name == "x"
    assert run.status == RunStatus.SUCCEEDED


def test_in_flight_run_is_running() -> None:
    log = (
        '{"Event":"SparkListenerApplicationStart","App Name":"x","App ID":"a",'
        '"Timestamp":1717000000000,"User":"u"}\n'
        '{"Event":"SparkListenerJobStart","Job ID":0}'
    )
    run = parse_event_log(log, run_id="run-inflight")
    assert run.status == RunStatus.RUNNING
    assert run.completed_at is None
