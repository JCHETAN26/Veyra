"""Spark event-log parser.

Parses the JSON-lines event log emitted by Spark's EventLoggingListener
(``spark.eventLog.enabled=true``) into a canonical :class:`PipelineRun`.

Why anchor on this format: the event log is produced by the same JVM code on
OSS Spark and Databricks, so the schema is identical across both. By parsing
it here and normalizing into canonical telemetry, the same ingestion path
works locally today and against real Databricks later — the realism gap
becomes an adapter concern, not an architectural one.

The parser is intentionally tolerant: unknown event types are ignored and
missing optional fields fall back to defaults, because event logs vary across
Spark versions and may be truncated for in-flight applications.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any

from dataforge.contracts.telemetry import (
    FailureInfo,
    PipelineRun,
    RunMetrics,
    RunStatus,
    StageMetrics,
)
from dataforge.core.logging import get_logger

logger = get_logger(__name__)


def _epoch_ms_to_dt(value: Any) -> datetime | None:
    """Convert Spark's epoch-millis timestamp to an aware datetime."""
    if value is None or not isinstance(value, (int, float)):
        return None
    if value <= 0:
        return None
    return datetime.fromtimestamp(value / 1000.0, tz=UTC)


class _RunAccumulator:
    """Mutable state folded over the event stream, emitted as a PipelineRun."""

    def __init__(self) -> None:
        self.app_id: str | None = None
        self.app_name: str = ""
        self.spark_user: str | None = None
        self.started_at: datetime | None = None
        self.completed_at: datetime | None = None
        self.num_jobs = 0
        self.num_failed_tasks = 0
        self.num_tasks = 0
        self.executor_run_time_ms = 0
        self.shuffle_read_bytes = 0
        self.shuffle_write_bytes = 0
        self.memory_spilled_bytes = 0
        self.disk_spilled_bytes = 0
        self.job_failed = False
        self.stages: dict[tuple[int, int], StageMetrics] = {}
        self.failure: FailureInfo | None = None

    def handle(self, event: dict[str, Any]) -> None:
        event_type = event.get("Event", "")
        handler = _HANDLERS.get(event_type)
        if handler is not None:
            handler(self, event)

    # --- per-event handlers ---------------------------------------------
    def _on_app_start(self, event: dict[str, Any]) -> None:
        self.app_name = event.get("App Name", "")
        self.app_id = event.get("App ID")
        self.spark_user = event.get("User")
        self.started_at = _epoch_ms_to_dt(event.get("Timestamp"))

    def _on_app_end(self, event: dict[str, Any]) -> None:
        self.completed_at = _epoch_ms_to_dt(event.get("Timestamp"))

    def _on_job_start(self, event: dict[str, Any]) -> None:
        self.num_jobs += 1

    def _on_job_end(self, event: dict[str, Any]) -> None:
        result = event.get("Job Result", {})
        if result.get("Result") == "JobFailed":
            self.job_failed = True
            message = result.get("Exception", {}).get("Message", "")
            if self.failure is None and message:
                self.failure = FailureInfo(message=message)

    def _on_stage_completed(self, event: dict[str, Any]) -> None:
        info = event.get("Stage Info", {})
        stage_id = info.get("Stage ID")
        attempt_id = info.get("Stage Attempt ID", 0)
        if stage_id is None:
            return

        submission = _epoch_ms_to_dt(info.get("Submission Time"))
        completion = _epoch_ms_to_dt(info.get("Completion Time"))
        duration_ms: int | None = None
        if submission and completion:
            duration_ms = int((completion - submission).total_seconds() * 1000)

        failure_reason = info.get("Failure Reason")
        stage = StageMetrics(
            stage_id=stage_id,
            attempt_id=attempt_id,
            name=info.get("Stage Name", ""),
            num_tasks=info.get("Number of Tasks", 0),
            submission_time=submission,
            completion_time=completion,
            duration_ms=duration_ms,
            failure_reason=failure_reason,
        )
        self.stages[(stage_id, attempt_id)] = stage

        if failure_reason and self.failure is None:
            self.failure = FailureInfo(message=failure_reason, stage_id=stage_id)

    def _on_task_end(self, event: dict[str, Any]) -> None:
        self.num_tasks += 1
        stage_id = event.get("Stage ID")
        attempt_id = event.get("Stage Attempt ID", 0)

        metrics = event.get("Task Metrics") or {}
        self.executor_run_time_ms += metrics.get("Executor Run Time", 0) or 0
        self.memory_spilled_bytes += metrics.get("Memory Bytes Spilled", 0) or 0
        self.disk_spilled_bytes += metrics.get("Disk Bytes Spilled", 0) or 0
        shuffle_read = metrics.get("Shuffle Read Metrics") or {}
        shuffle_write = metrics.get("Shuffle Write Metrics") or {}
        self.shuffle_read_bytes += (shuffle_read.get("Remote Bytes Read", 0) or 0) + (
            shuffle_read.get("Local Bytes Read", 0) or 0
        )
        self.shuffle_write_bytes += shuffle_write.get("Shuffle Bytes Written", 0) or 0

        end_reason = event.get("Task End Reason", {})
        reason = end_reason.get("Reason", "")
        if reason and reason != "Success":
            self.num_failed_tasks += 1
            key = (stage_id, attempt_id)
            if stage_id is not None and key in self.stages:
                self.stages[key].num_failed_tasks += 1
            self._capture_task_failure(end_reason, stage_id, event.get("Task Info"))

    def _capture_task_failure(
        self,
        end_reason: dict[str, Any],
        stage_id: int | None,
        task_info: dict[str, Any] | None,
    ) -> None:
        if self.failure is not None and self.failure.stack_trace is not None:
            return  # keep the first failure that carried a stack trace

        class_name = end_reason.get("Class Name")
        description = end_reason.get("Description", "")
        stack = end_reason.get("Stack Trace")
        stack_str = _format_stack(stack) if stack else None
        task_id = task_info.get("Task ID") if task_info else None

        self.failure = FailureInfo(
            error_class=class_name,
            message=description or end_reason.get("Reason", ""),
            stack_trace=stack_str,
            stage_id=stage_id,
            task_id=task_id,
        )

    def build(self, run_id: str) -> PipelineRun:
        status = self._derive_status()
        duration_ms: int | None = None
        if self.started_at and self.completed_at:
            duration_ms = int((self.completed_at - self.started_at).total_seconds() * 1000)

        ordered_stages = [self.stages[key] for key in sorted(self.stages.keys())]
        metrics = RunMetrics(
            num_jobs=self.num_jobs,
            num_stages=len(ordered_stages),
            num_tasks=self.num_tasks,
            num_failed_tasks=self.num_failed_tasks,
            executor_run_time_ms=self.executor_run_time_ms,
            shuffle_read_bytes=self.shuffle_read_bytes,
            shuffle_write_bytes=self.shuffle_write_bytes,
            memory_spilled_bytes=self.memory_spilled_bytes,
            disk_spilled_bytes=self.disk_spilled_bytes,
        )

        return PipelineRun(
            run_id=run_id,
            app_name=self.app_name,
            source="spark-eventlog",
            spark_user=self.spark_user,
            status=status,
            started_at=self.started_at,
            completed_at=self.completed_at,
            duration_ms=duration_ms,
            metrics=metrics,
            stages=ordered_stages,
            failure=self.failure,
        )

    def _derive_status(self) -> RunStatus:
        if self.job_failed or self.failure is not None:
            return RunStatus.FAILED
        if self.completed_at is not None:
            return RunStatus.SUCCEEDED
        if self.started_at is not None:
            return RunStatus.RUNNING
        return RunStatus.UNKNOWN


def _format_stack(stack: Any) -> str | None:
    """Render Spark's structured stack-trace array into a string."""
    if isinstance(stack, str):
        return stack
    if not isinstance(stack, list):
        return None
    lines = []
    for frame in stack:
        if not isinstance(frame, dict):
            continue
        cls = frame.get("Declaring Class", "")
        method = frame.get("Method Name", "")
        file_name = frame.get("File Name", "")
        line = frame.get("Line Number", "")
        lines.append(f"  at {cls}.{method}({file_name}:{line})")
    return "\n".join(lines) if lines else None


# Dispatch table: event name -> bound-method-by-name on the accumulator.
_HANDLERS = {
    "SparkListenerApplicationStart": _RunAccumulator._on_app_start,
    "SparkListenerApplicationEnd": _RunAccumulator._on_app_end,
    "SparkListenerJobStart": _RunAccumulator._on_job_start,
    "SparkListenerJobEnd": _RunAccumulator._on_job_end,
    "SparkListenerStageCompleted": _RunAccumulator._on_stage_completed,
    "SparkListenerTaskEnd": _RunAccumulator._on_task_end,
}


def parse_events(events: Iterable[dict[str, Any]], *, run_id: str) -> PipelineRun:
    """Fold a sequence of parsed Spark events into a canonical PipelineRun."""
    acc = _RunAccumulator()
    for event in events:
        acc.handle(event)
    run = acc.build(run_id)
    logger.info(
        "ingestion.eventlog.parsed",
        run_id=run_id,
        status=run.status,
        num_stages=run.metrics.num_stages,
        num_failed_tasks=run.metrics.num_failed_tasks,
    )
    return run


def parse_event_log(content: str, *, run_id: str) -> PipelineRun:
    """Parse a raw event-log string (JSON lines) into a PipelineRun.

    Malformed lines are skipped with a warning rather than aborting the whole
    parse, since logs can be partially written for in-flight applications.
    """

    def _iter_lines() -> Iterable[dict[str, Any]]:
        for lineno, raw in enumerate(content.splitlines(), start=1):
            line = raw.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                logger.warning("ingestion.eventlog.bad_line", lineno=lineno)

    return parse_events(_iter_lines(), run_id=run_id)
