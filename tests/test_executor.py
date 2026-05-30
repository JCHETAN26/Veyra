"""Unit tests for the deterministic simulated rerun executor."""

from __future__ import annotations

import asyncio

from dataforge.contracts.remediation_workflow import FixAction
from dataforge.contracts.telemetry import (
    FailureInfo,
    PipelineRun,
    RunMetrics,
    RunStatus,
)
from dataforge.modules.orchestration.executor import SimulatedExecutor


def _oom_run() -> PipelineRun:
    return PipelineRun(
        run_id="r1",
        status=RunStatus.FAILED,
        failure=FailureInfo(error_class="java.lang.OutOfMemoryError"),
        metrics=RunMetrics(num_tasks=4, disk_spilled_bytes=500 * 1024 * 1024),
    )


def _rerun(run: PipelineRun, action: FixAction) -> bool:
    return asyncio.run(SimulatedExecutor().rerun(run, action)).succeeded


def test_broadcast_resolves_oom() -> None:
    assert _rerun(_oom_run(), FixAction(title="Broadcast the smaller side of the join"))


def test_shuffle_partitions_resolves_spill() -> None:
    assert _rerun(_oom_run(), FixAction(title="Increase shuffle partitions"))


def test_irrelevant_fix_does_not_resolve() -> None:
    assert not _rerun(_oom_run(), FixAction(title="Restart the cluster"))


def test_executor_is_deterministic() -> None:
    run = _oom_run()
    action = FixAction(title="Broadcast the smaller side of the join")
    a = asyncio.run(SimulatedExecutor().rerun(run, action))
    b = asyncio.run(SimulatedExecutor().rerun(run, action))
    assert a.succeeded == b.succeeded
    assert a.detail == b.detail
