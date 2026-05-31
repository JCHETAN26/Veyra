"""Event-dict factories.

Helpers that return a single Spark event as a dict, matching the schema the
EventLoggingListener writes. The functions are intentionally low-level —
scenarios compose them into ordered lists. Timestamps are explicit (caller
threads them) so scenarios stay deterministic.
"""

from __future__ import annotations

from typing import Any

# Base epoch for all simulated runs. Kept fixed (2024-05-31 ~midnight UTC)
# so successive runs of a scenario yield byte-identical event logs.
BASE_EPOCH_MS = 1_717_100_000_000

# Common byte sizes used by scenarios for readability.
MB = 1024 * 1024
GB = 1024 * MB


def app_start(*, app_name: str, app_id: str, user: str = "dataforge", ts_ms: int) -> dict[str, Any]:
    return {
        "Event": "SparkListenerApplicationStart",
        "App Name": app_name,
        "App ID": app_id,
        "Timestamp": ts_ms,
        "User": user,
    }


def app_end(*, ts_ms: int) -> dict[str, Any]:
    return {"Event": "SparkListenerApplicationEnd", "Timestamp": ts_ms}


def job_start(*, job_id: int, ts_ms: int) -> dict[str, Any]:
    return {
        "Event": "SparkListenerJobStart",
        "Job ID": job_id,
        "Submission Time": ts_ms,
    }


def job_end_success(*, job_id: int, ts_ms: int) -> dict[str, Any]:
    return {
        "Event": "SparkListenerJobEnd",
        "Job ID": job_id,
        "Completion Time": ts_ms,
        "Job Result": {"Result": "JobSucceeded"},
    }


def job_end_failed(*, job_id: int, ts_ms: int, message: str) -> dict[str, Any]:
    return {
        "Event": "SparkListenerJobEnd",
        "Job ID": job_id,
        "Completion Time": ts_ms,
        "Job Result": {
            "Result": "JobFailed",
            "Exception": {"Message": message},
        },
    }


def stage_completed(
    *,
    stage_id: int,
    name: str,
    num_tasks: int,
    start_ms: int,
    end_ms: int,
    attempt_id: int = 0,
    failure_reason: str | None = None,
) -> dict[str, Any]:
    info: dict[str, Any] = {
        "Stage ID": stage_id,
        "Stage Attempt ID": attempt_id,
        "Stage Name": name,
        "Number of Tasks": num_tasks,
        "Submission Time": start_ms,
        "Completion Time": end_ms,
    }
    if failure_reason:
        info["Failure Reason"] = failure_reason
    return {"Event": "SparkListenerStageCompleted", "Stage Info": info}


def task_success(
    *,
    stage_id: int,
    task_id: int,
    attempt_id: int = 0,
    runtime_ms: int = 1000,
    memory_spill: int = 0,
    disk_spill: int = 0,
    shuffle_read: int = 0,
    shuffle_write: int = 0,
) -> dict[str, Any]:
    return {
        "Event": "SparkListenerTaskEnd",
        "Stage ID": stage_id,
        "Stage Attempt ID": attempt_id,
        "Task Type": "ShuffleMapTask",
        "Task End Reason": {"Reason": "Success"},
        "Task Info": {"Task ID": task_id},
        "Task Metrics": _task_metrics(
            runtime_ms=runtime_ms,
            memory_spill=memory_spill,
            disk_spill=disk_spill,
            shuffle_read=shuffle_read,
            shuffle_write=shuffle_write,
        ),
    }


def task_transient_failure(
    *,
    stage_id: int,
    task_id: int,
    reason: str = "FetchFailed",
    attempt_id: int = 0,
    runtime_ms: int = 1000,
) -> dict[str, Any]:
    """A task end with a transient reason (FetchFailed, TaskKilled, Resubmitted).

    Increments the failed-task counter without setting a fatal failure on
    the run — matches Spark's "task retried successfully" path. Used by the
    flaky-executors scenario.
    """
    return {
        "Event": "SparkListenerTaskEnd",
        "Stage ID": stage_id,
        "Stage Attempt ID": attempt_id,
        "Task Type": "ShuffleMapTask",
        "Task End Reason": {"Reason": reason},
        "Task Info": {"Task ID": task_id},
        "Task Metrics": _task_metrics(
            runtime_ms=runtime_ms,
            memory_spill=0,
            disk_spill=0,
            shuffle_read=0,
            shuffle_write=0,
        ),
    }


def task_failure(
    *,
    stage_id: int,
    task_id: int,
    error_class: str,
    message: str,
    attempt_id: int = 0,
    runtime_ms: int = 1000,
    memory_spill: int = 0,
    disk_spill: int = 0,
    shuffle_read: int = 0,
    shuffle_write: int = 0,
    stack_frames: list[tuple[str, str, str, int]] | None = None,
) -> dict[str, Any]:
    """A task end with a structured ExceptionFailure reason."""
    frames = stack_frames or [
        (
            "org.apache.spark.sql.execution.joins.SortMergeJoinExec",
            "doExecute",
            "SortMergeJoinExec.scala",
            182,
        ),
        (
            "org.apache.spark.sql.execution.SparkPlan",
            "execute",
            "SparkPlan.scala",
            175,
        ),
    ]
    stack = [
        {
            "Declaring Class": cls,
            "Method Name": method,
            "File Name": fn,
            "Line Number": line,
        }
        for (cls, method, fn, line) in frames
    ]
    return {
        "Event": "SparkListenerTaskEnd",
        "Stage ID": stage_id,
        "Stage Attempt ID": attempt_id,
        "Task Type": "ShuffleMapTask",
        "Task End Reason": {
            "Reason": "ExceptionFailure",
            "Class Name": error_class,
            "Description": message,
            "Stack Trace": stack,
        },
        "Task Info": {"Task ID": task_id},
        "Task Metrics": _task_metrics(
            runtime_ms=runtime_ms,
            memory_spill=memory_spill,
            disk_spill=disk_spill,
            shuffle_read=shuffle_read,
            shuffle_write=shuffle_write,
        ),
    }


def _task_metrics(
    *,
    runtime_ms: int,
    memory_spill: int,
    disk_spill: int,
    shuffle_read: int,
    shuffle_write: int,
) -> dict[str, Any]:
    return {
        "Executor Run Time": runtime_ms,
        "Memory Bytes Spilled": memory_spill,
        "Disk Bytes Spilled": disk_spill,
        "Shuffle Read Metrics": {
            "Remote Bytes Read": shuffle_read,
            "Local Bytes Read": 0,
        },
        "Shuffle Write Metrics": {"Shuffle Bytes Written": shuffle_write},
    }
