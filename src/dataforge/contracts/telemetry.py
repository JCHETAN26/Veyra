"""Canonical operational telemetry contracts.

These models are DataForge's *internal* representation of a pipeline
execution. They are deliberately decoupled from any source-specific wire
format (Spark event logs, Databricks Jobs API, etc.). Source adapters
normalize raw signals into these types, so the rest of the platform —
observability, RCA, RAG, remediation — reasons over one stable schema
regardless of where the telemetry came from.

This is the seam that keeps the platform portable: swapping local Spark for
real Databricks is an adapter change, not a domain change.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class RunStatus(StrEnum):
    """Terminal or in-flight status of a pipeline run."""

    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    UNKNOWN = "unknown"


class FailureInfo(BaseModel):
    """Normalized description of the first/primary failure in a run.

    Stack traces are identical across OSS Spark and Databricks because the
    same JVM code raises them, which makes this a portable RCA signal.
    """

    error_class: str | None = None
    message: str = ""
    stack_trace: str | None = None
    stage_id: int | None = None
    task_id: int | None = None


class StageMetrics(BaseModel):
    """Per-stage execution metrics, aggregated from task-level events."""

    stage_id: int
    attempt_id: int = 0
    name: str = ""
    num_tasks: int = 0
    num_failed_tasks: int = 0
    submission_time: datetime | None = None
    completion_time: datetime | None = None
    duration_ms: int | None = None
    failure_reason: str | None = None


class RunMetrics(BaseModel):
    """Run-level aggregate metrics rolled up from stages/tasks."""

    num_jobs: int = 0
    num_stages: int = 0
    num_tasks: int = 0
    num_failed_tasks: int = 0
    executor_run_time_ms: int = 0
    shuffle_read_bytes: int = 0
    shuffle_write_bytes: int = 0
    memory_spilled_bytes: int = 0
    disk_spilled_bytes: int = 0


class PipelineRun(BaseModel):
    """Canonical representation of a single pipeline (Spark application) run."""

    run_id: str
    app_name: str = ""
    source: str = "spark-eventlog"
    spark_user: str | None = None
    status: RunStatus = RunStatus.UNKNOWN
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_ms: int | None = None
    metrics: RunMetrics = Field(default_factory=RunMetrics)
    stages: list[StageMetrics] = Field(default_factory=list)
    failure: FailureInfo | None = None
