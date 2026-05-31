"""Chaos scenarios.

Each scenario builds a list of Spark events that, when parsed by the
ingestion pipeline, produces a PipelineRun whose detectors land in a
distinct RCA category. They share the same parameter surface (`run_id`,
`app_name`, `num_tasks`) so the CLI can drive them uniformly.

Scenario coverage maps 1:1 to the analyzer taxonomy:

  - healthy             -> no incidents
  - oom_join            -> memory_pressure
  - data_skew           -> data_skew
  - flaky_executors     -> transient_failure
  - long_duration       -> performance_regression
  - schema_drift        -> dependency_failure (ClassCastException)
  - dependency_failure  -> dependency_failure (SocketTimeoutException)

Deterministic in every byte: re-running the same scenario with the same
inputs produces identical JSONL. That property is what makes the demo
recordable and the tests stable.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from dataforge.simulator.events import (
    BASE_EPOCH_MS,
    GB,
    MB,
    app_end,
    app_start,
    job_end_failed,
    job_end_success,
    job_start,
    stage_completed,
    task_failure,
    task_success,
    task_transient_failure,
)


@dataclass
class Scenario:
    """A named, parameterized chaos scenario."""

    name: str
    description: str
    build: Callable[..., list[dict[str, Any]]]


def events_to_jsonl(events: list[dict[str, Any]]) -> str:
    """Render a scenario's events as a Spark-compatible JSON-lines string."""
    return "\n".join(json.dumps(e, separators=(",", ":")) for e in events) + "\n"


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------


def healthy(
    *,
    run_id: str,
    app_name: str = "nightly_etl",
    num_tasks: int = 8,
) -> list[dict[str, Any]]:
    """Baseline: a clean ETL run with two stages and no anomalies."""
    t = BASE_EPOCH_MS
    half = max(num_tasks // 2, 1)
    events: list[dict[str, Any]] = []
    events.append(app_start(app_name=app_name, app_id=f"app-{run_id}", ts_ms=t))
    events.append(job_start(job_id=0, ts_ms=t + 1_000))
    events.append(
        stage_completed(
            stage_id=0,
            name="read_input",
            num_tasks=half,
            start_ms=t + 1_000,
            end_ms=t + 3_000,
        )
    )
    for i in range(half):
        events.append(task_success(stage_id=0, task_id=i, runtime_ms=1_800, shuffle_read=8 * MB))
    events.append(
        stage_completed(
            stage_id=1,
            name="write_output",
            num_tasks=num_tasks - half,
            start_ms=t + 3_000,
            end_ms=t + 5_000,
        )
    )
    for i in range(num_tasks - half):
        events.append(
            task_success(
                stage_id=1,
                task_id=half + i,
                runtime_ms=1_800,
                shuffle_write=8 * MB,
            )
        )
    events.append(job_end_success(job_id=0, ts_ms=t + 5_000))
    events.append(app_end(ts_ms=t + 5_500))
    return events


def oom_join(
    *,
    run_id: str,
    app_name: str = "finance_aggregator",
    num_tasks: int = 10,
) -> list[dict[str, Any]]:
    """OOM during a skewed join. Detector trio: run_failure + excessive_spill."""
    t = BASE_EPOCH_MS
    events: list[dict[str, Any]] = []
    events.append(app_start(app_name=app_name, app_id=f"app-{run_id}", ts_ms=t))
    events.append(job_start(job_id=0, ts_ms=t + 1_000))

    fail_reason = (
        "Task 1 in stage 0.0 failed 4 times, most recent failure: "
        "java.lang.OutOfMemoryError: Java heap space"
    )
    events.append(
        stage_completed(
            stage_id=0,
            name="join orders with customers",
            num_tasks=num_tasks,
            start_ms=t + 1_000,
            end_ms=t + 5_000,
            failure_reason=fail_reason,
        )
    )
    # First task survives but spills heavily — the skewed partition warning.
    events.append(
        task_success(
            stage_id=0,
            task_id=0,
            runtime_ms=3_500,
            memory_spill=300 * MB,
            disk_spill=400 * MB,
            shuffle_read=512 * MB,
        )
    )
    # The OOM-killed task.
    events.append(
        task_failure(
            stage_id=0,
            task_id=1,
            error_class="java.lang.OutOfMemoryError",
            message="Java heap space",
            runtime_ms=4_200,
            memory_spill=400 * MB,
            disk_spill=600 * MB,
            shuffle_read=512 * MB,
        )
    )
    # Remaining tasks didn't run because the stage failed.
    for i in range(2, num_tasks):
        events.append(
            task_success(
                stage_id=0,
                task_id=i,
                runtime_ms=200,
                memory_spill=0,
                disk_spill=0,
            )
        )
    events.append(job_end_failed(job_id=0, ts_ms=t + 5_000, message=fail_reason))
    events.append(app_end(ts_ms=t + 5_500))
    return events


def data_skew(
    *,
    run_id: str,
    app_name: str = "sales_rollup",
    num_tasks: int = 20,
) -> list[dict[str, Any]]:
    """Heavy spill without OOM. Detector: excessive_spill -> data_skew RCA."""
    t = BASE_EPOCH_MS
    events: list[dict[str, Any]] = []
    events.append(app_start(app_name=app_name, app_id=f"app-{run_id}", ts_ms=t))
    events.append(job_start(job_id=0, ts_ms=t + 1_000))
    events.append(
        stage_completed(
            stage_id=0,
            name="groupBy region rollup",
            num_tasks=num_tasks,
            start_ms=t + 1_000,
            end_ms=t + 8_000,
        )
    )
    # One hot task soaks 1 GiB of spill; the rest are normal.
    events.append(
        task_success(
            stage_id=0,
            task_id=0,
            runtime_ms=7_000,
            memory_spill=512 * MB,
            disk_spill=512 * MB,
            shuffle_read=1 * GB,
        )
    )
    for i in range(1, num_tasks):
        events.append(
            task_success(
                stage_id=0,
                task_id=i,
                runtime_ms=1_200,
                shuffle_read=16 * MB,
            )
        )
    events.append(job_end_success(job_id=0, ts_ms=t + 8_000))
    events.append(app_end(ts_ms=t + 8_500))
    return events


def flaky_executors(
    *,
    run_id: str,
    app_name: str = "batch_ingest",
    num_tasks: int = 100,
) -> list[dict[str, Any]]:
    """High failed-task ratio but the job eventually succeeds (retry path).

    Triggers HIGH_FAILED_TASK_RATIO -> transient_failure category.
    """
    t = BASE_EPOCH_MS
    events: list[dict[str, Any]] = []
    events.append(app_start(app_name=app_name, app_id=f"app-{run_id}", ts_ms=t))
    events.append(job_start(job_id=0, ts_ms=t + 1_000))
    events.append(
        stage_completed(
            stage_id=0,
            name="ingest partitions",
            num_tasks=num_tasks,
            start_ms=t + 1_000,
            end_ms=t + 7_000,
        )
    )
    # ~20% of tasks failed transiently before eventual retry success.
    failure_count = max(num_tasks // 5, 1)
    for i in range(failure_count):
        events.append(
            task_transient_failure(
                stage_id=0,
                task_id=i,
                reason="FetchFailed",
                runtime_ms=900,
            )
        )
    for i in range(failure_count, num_tasks):
        events.append(
            task_success(
                stage_id=0,
                task_id=i,
                runtime_ms=900,
                shuffle_write=4 * MB,
            )
        )
    events.append(job_end_success(job_id=0, ts_ms=t + 7_000))
    events.append(app_end(ts_ms=t + 7_500))
    return events


def long_duration(
    *,
    run_id: str,
    app_name: str = "ml_feature_etl",
    num_tasks: int = 50,
) -> list[dict[str, Any]]:
    """Run takes >30 minutes. Triggers LONG_DURATION -> performance_regression."""
    t = BASE_EPOCH_MS
    forty_min_ms = 40 * 60 * 1000
    events: list[dict[str, Any]] = []
    events.append(app_start(app_name=app_name, app_id=f"app-{run_id}", ts_ms=t))
    events.append(job_start(job_id=0, ts_ms=t + 1_000))
    events.append(
        stage_completed(
            stage_id=0,
            name="feature compute",
            num_tasks=num_tasks,
            start_ms=t + 1_000,
            end_ms=t + forty_min_ms,
        )
    )
    for i in range(num_tasks):
        events.append(
            task_success(
                stage_id=0,
                task_id=i,
                runtime_ms=forty_min_ms // num_tasks,
                shuffle_read=64 * MB,
            )
        )
    events.append(job_end_success(job_id=0, ts_ms=t + forty_min_ms))
    events.append(app_end(ts_ms=t + forty_min_ms + 500))
    return events


def schema_drift(
    *,
    run_id: str,
    app_name: str = "customer_cdc",
    num_tasks: int = 10,
) -> list[dict[str, Any]]:
    """ClassCastException from a column type changing upstream. Job fails."""
    t = BASE_EPOCH_MS
    events: list[dict[str, Any]] = []
    events.append(app_start(app_name=app_name, app_id=f"app-{run_id}", ts_ms=t))
    events.append(job_start(job_id=0, ts_ms=t + 1_000))
    fail_reason = (
        "Task 3 in stage 0.0 failed 4 times, most recent failure: "
        "java.lang.ClassCastException: java.lang.String cannot be cast to "
        "java.lang.Long"
    )
    events.append(
        stage_completed(
            stage_id=0,
            name="cdc apply",
            num_tasks=num_tasks,
            start_ms=t + 1_000,
            end_ms=t + 4_000,
            failure_reason=fail_reason,
        )
    )
    for i in range(3):
        events.append(task_success(stage_id=0, task_id=i, runtime_ms=900))
    events.append(
        task_failure(
            stage_id=0,
            task_id=3,
            error_class="java.lang.ClassCastException",
            message="java.lang.String cannot be cast to java.lang.Long at column customer_id",
            runtime_ms=1_100,
            stack_frames=[
                (
                    "org.apache.spark.sql.catalyst.expressions.Cast",
                    "eval",
                    "Cast.scala",
                    1024,
                ),
                (
                    "org.apache.spark.sql.execution.WholeStageCodegenExec",
                    "doExecute",
                    "WholeStageCodegenExec.scala",
                    719,
                ),
            ],
        )
    )
    events.append(job_end_failed(job_id=0, ts_ms=t + 4_000, message=fail_reason))
    events.append(app_end(ts_ms=t + 4_500))
    return events


def dependency_failure(
    *,
    run_id: str,
    app_name: str = "s3_ingest",
    num_tasks: int = 10,
) -> list[dict[str, Any]]:
    """Upstream S3 timeouts. Job fails with SocketTimeoutException."""
    t = BASE_EPOCH_MS
    events: list[dict[str, Any]] = []
    events.append(app_start(app_name=app_name, app_id=f"app-{run_id}", ts_ms=t))
    events.append(job_start(job_id=0, ts_ms=t + 1_000))
    fail_reason = (
        "Task 0 in stage 0.0 failed 4 times, most recent failure: "
        "java.net.SocketTimeoutException: Read timed out on s3://prod-events/"
    )
    events.append(
        stage_completed(
            stage_id=0,
            name="read s3 events",
            num_tasks=num_tasks,
            start_ms=t + 1_000,
            end_ms=t + 5_000,
            failure_reason=fail_reason,
        )
    )
    events.append(
        task_failure(
            stage_id=0,
            task_id=0,
            error_class="java.net.SocketTimeoutException",
            message="Read timed out on s3://prod-events/2026-05-30/part-0001.json",
            runtime_ms=30_000,
            stack_frames=[
                (
                    "org.apache.hadoop.fs.s3a.S3AInputStream",
                    "read",
                    "S3AInputStream.java",
                    412,
                ),
            ],
        )
    )
    for i in range(1, num_tasks):
        events.append(task_success(stage_id=0, task_id=i, runtime_ms=600))
    events.append(job_end_failed(job_id=0, ts_ms=t + 5_000, message=fail_reason))
    events.append(app_end(ts_ms=t + 5_500))
    return events


# ---------------------------------------------------------------------------
# Registry + dispatcher
# ---------------------------------------------------------------------------


SCENARIOS: dict[str, Scenario] = {
    "healthy": Scenario(
        name="healthy",
        description="Baseline successful run; no anomalies, no incidents.",
        build=healthy,
    ),
    "oom_join": Scenario(
        name="oom_join",
        description=("OOM in a join stage; RCA expected to land on memory_pressure."),
        build=oom_join,
    ),
    "data_skew": Scenario(
        name="data_skew",
        description=("Heavy spill from a hot partition; succeeds but RCA expected on data_skew."),
        build=data_skew,
    ),
    "flaky_executors": Scenario(
        name="flaky_executors",
        description=("Many task failures but retry succeeds; RCA expected on transient_failure."),
        build=flaky_executors,
    ),
    "long_duration": Scenario(
        name="long_duration",
        description=("Run far exceeds expected duration; RCA expected on performance_regression."),
        build=long_duration,
    ),
    "schema_drift": Scenario(
        name="schema_drift",
        description=("ClassCastException from upstream schema change; failure mode common in CDC."),
        build=schema_drift,
    ),
    "dependency_failure": Scenario(
        name="dependency_failure",
        description=("Upstream S3 timeouts; job fails with SocketTimeoutException."),
        build=dependency_failure,
    ),
}


def build_scenario(
    name: str,
    *,
    run_id: str,
    app_name: str | None = None,
    num_tasks: int | None = None,
) -> list[dict[str, Any]]:
    """Look up a scenario by name and invoke its builder.

    Raises KeyError on an unknown scenario; the CLI translates that into a
    helpful "did you mean ..." style message.
    """
    scenario = SCENARIOS[name]
    kwargs: dict[str, Any] = {"run_id": run_id}
    if app_name is not None:
        kwargs["app_name"] = app_name
    if num_tasks is not None:
        kwargs["num_tasks"] = num_tasks
    return scenario.build(**kwargs)
