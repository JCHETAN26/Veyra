"""Metadata repository.

The typed persistence port for canonical telemetry. Other modules depend on
this interface (not the ORM) so the metadata module can change its storage
without breaking callers. Upserts are idempotent on run_id, which matters
because event-log ingestion may be replayed (build-plan §B idempotency).
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dataforge.contracts.telemetry import (
    FailureInfo,
    PipelineRun,
    RunMetrics,
    RunStatus,
    StageMetrics,
)
from dataforge.core.logging import get_logger
from dataforge.modules.metadata.models import PipelineRunRow, StageMetricsRow

logger = get_logger(__name__)


class MetadataRepository:
    """Async repository over pipeline-run telemetry."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert_run(self, run: PipelineRun) -> None:
        """Insert or replace a pipeline run (idempotent on run_id)."""
        existing = await self._session.get(PipelineRunRow, run.run_id)
        if existing is not None:
            await self._session.delete(existing)
            await self._session.flush()

        row = _run_to_row(run)
        self._session.add(row)
        await self._session.flush()
        logger.info(
            "metadata.run.upserted",
            run_id=run.run_id,
            status=run.status,
            num_stages=len(run.stages),
        )

    async def get_run(self, run_id: str) -> PipelineRun | None:
        row = await self._session.get(PipelineRunRow, run_id)
        if row is None:
            return None
        return _row_to_run(row)

    async def list_runs(self, *, limit: int = 50) -> list[PipelineRun]:
        stmt = select(PipelineRunRow).order_by(PipelineRunRow.ingested_at.desc()).limit(limit)
        result = await self._session.execute(stmt)
        return [_row_to_run(row) for row in result.scalars().all()]


def _run_to_row(run: PipelineRun) -> PipelineRunRow:
    m = run.metrics
    f = run.failure or FailureInfo()
    return PipelineRunRow(
        run_id=run.run_id,
        app_name=run.app_name,
        source=run.source,
        spark_user=run.spark_user,
        status=run.status.value,
        started_at=run.started_at,
        completed_at=run.completed_at,
        duration_ms=run.duration_ms,
        num_jobs=m.num_jobs,
        num_stages=m.num_stages,
        num_tasks=m.num_tasks,
        num_failed_tasks=m.num_failed_tasks,
        executor_run_time_ms=m.executor_run_time_ms,
        shuffle_read_bytes=m.shuffle_read_bytes,
        shuffle_write_bytes=m.shuffle_write_bytes,
        memory_spilled_bytes=m.memory_spilled_bytes,
        disk_spilled_bytes=m.disk_spilled_bytes,
        failure_error_class=f.error_class,
        failure_message=f.message or None,
        failure_stack_trace=f.stack_trace,
        failure_stage_id=f.stage_id,
        failure_task_id=f.task_id,
        stages=[_stage_to_row(s) for s in run.stages],
    )


def _stage_to_row(stage: StageMetrics) -> StageMetricsRow:
    return StageMetricsRow(
        stage_id=stage.stage_id,
        attempt_id=stage.attempt_id,
        name=stage.name,
        num_tasks=stage.num_tasks,
        num_failed_tasks=stage.num_failed_tasks,
        submission_time=stage.submission_time,
        completion_time=stage.completion_time,
        duration_ms=stage.duration_ms,
        failure_reason=stage.failure_reason,
    )


def _row_to_run(row: PipelineRunRow) -> PipelineRun:
    failure: FailureInfo | None = None
    if row.failure_error_class or row.failure_message or row.failure_stack_trace:
        failure = FailureInfo(
            error_class=row.failure_error_class,
            message=row.failure_message or "",
            stack_trace=row.failure_stack_trace,
            stage_id=row.failure_stage_id,
            task_id=row.failure_task_id,
        )

    return PipelineRun(
        run_id=row.run_id,
        app_name=row.app_name,
        source=row.source,
        spark_user=row.spark_user,
        status=RunStatus(row.status),
        started_at=row.started_at,
        completed_at=row.completed_at,
        duration_ms=row.duration_ms,
        metrics=RunMetrics(
            num_jobs=row.num_jobs,
            num_stages=row.num_stages,
            num_tasks=row.num_tasks,
            num_failed_tasks=row.num_failed_tasks,
            executor_run_time_ms=row.executor_run_time_ms,
            shuffle_read_bytes=row.shuffle_read_bytes,
            shuffle_write_bytes=row.shuffle_write_bytes,
            memory_spilled_bytes=row.memory_spilled_bytes,
            disk_spilled_bytes=row.disk_spilled_bytes,
        ),
        stages=[_row_to_stage(s) for s in row.stages],
        failure=failure,
    )


def _row_to_stage(row: StageMetricsRow) -> StageMetrics:
    return StageMetrics(
        stage_id=row.stage_id,
        attempt_id=row.attempt_id,
        name=row.name,
        num_tasks=row.num_tasks,
        num_failed_tasks=row.num_failed_tasks,
        submission_time=row.submission_time,
        completion_time=row.completion_time,
        duration_ms=row.duration_ms,
        failure_reason=row.failure_reason,
    )
