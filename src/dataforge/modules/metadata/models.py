"""Metadata ORM models.

Persistence representation of canonical telemetry. The metadata module owns
these tables; other modules read/write only through MetadataRepository so the
storage schema stays an internal detail of this module.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from dataforge.core.db import Base


class PipelineRunRow(Base):
    __tablename__ = "pipeline_runs"

    run_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    app_name: Mapped[str] = mapped_column(String(512), default="")
    source: Mapped[str] = mapped_column(String(64), default="spark-eventlog")
    spark_user: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="unknown", index=True)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    # Run-level aggregate metrics (flattened from RunMetrics).
    num_jobs: Mapped[int] = mapped_column(Integer, default=0)
    num_stages: Mapped[int] = mapped_column(Integer, default=0)
    num_tasks: Mapped[int] = mapped_column(Integer, default=0)
    num_failed_tasks: Mapped[int] = mapped_column(Integer, default=0)
    executor_run_time_ms: Mapped[int] = mapped_column(BigInteger, default=0)
    shuffle_read_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    shuffle_write_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    memory_spilled_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    disk_spilled_bytes: Mapped[int] = mapped_column(BigInteger, default=0)

    # First/primary failure (flattened from FailureInfo).
    failure_error_class: Mapped[str | None] = mapped_column(String(512), nullable=True)
    failure_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    failure_stack_trace: Mapped[str | None] = mapped_column(Text, nullable=True)
    failure_stage_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    failure_task_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    stages: Mapped[list[StageMetricsRow]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    __table_args__ = (Index("ix_pipeline_runs_started_at", "started_at"),)


class StageMetricsRow(Base):
    __tablename__ = "stage_metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("pipeline_runs.run_id", ondelete="CASCADE"), index=True
    )
    stage_id: Mapped[int] = mapped_column(Integer)
    attempt_id: Mapped[int] = mapped_column(Integer, default=0)
    name: Mapped[str] = mapped_column(String(512), default="")
    num_tasks: Mapped[int] = mapped_column(Integer, default=0)
    num_failed_tasks: Mapped[int] = mapped_column(Integer, default=0)
    submission_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completion_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    run: Mapped[PipelineRunRow] = relationship(back_populates="stages")


class IncidentRow(Base):
    __tablename__ = "incidents"

    incident_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("pipeline_runs.run_id", ondelete="CASCADE"), index=True
    )
    anomaly_type: Mapped[str] = mapped_column(String(64), index=True)
    severity: Mapped[int] = mapped_column(Integer, index=True)
    status: Mapped[str] = mapped_column(String(32), default="open", index=True)
    title: Mapped[str] = mapped_column(String(512), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    # Signals serialized as JSON; small and read whole, so no separate table.
    signals_json: Mapped[str] = mapped_column(Text, default="[]")
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    __table_args__ = (Index("ix_incidents_run_anomaly", "run_id", "anomaly_type", unique=True),)
