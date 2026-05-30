"""Rerun executors.

The RerunExecutor interface re-runs a pipeline after a fix is applied and
reports the outcome. The MVP ships a deterministic simulator: it decides
success/failure from the fix action + run signature with no I/O and no
randomness, so the workflow's fallback chain and the tests are fully
reproducible.

A real executor (submit to a local Spark cluster, or drive a Temporal
activity that does) implements the same interface later — the workflow logic
does not change.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from dataforge.contracts.remediation_workflow import FixAction
from dataforge.contracts.telemetry import PipelineRun
from dataforge.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class RerunOutcome:
    """Result of attempting a rerun with a given fix action."""

    succeeded: bool
    detail: str


@runtime_checkable
class RerunExecutor(Protocol):
    name: str

    async def rerun(self, run: PipelineRun, action: FixAction) -> RerunOutcome:
        """Apply the fix action and re-run the pipeline; report the outcome."""
        ...


class SimulatedExecutor:
    """Deterministic rerun simulator for the local/zero-cost MVP.

    Heuristic, but principled: each fix targets a class of cause, so the
    simulator "succeeds" when the action plausibly addresses the failure.
    Deterministic given (run, action), so fallback chains are reproducible.
    """

    name = "simulated-v1"

    async def rerun(self, run: PipelineRun, action: FixAction) -> RerunOutcome:
        succeeded, detail = self._evaluate(run, action)
        logger.info(
            "orchestration.rerun.simulated",
            run_id=run.run_id,
            action=action.title,
            kind=action.kind,
            succeeded=succeeded,
        )
        return RerunOutcome(succeeded=succeeded, detail=detail)

    def _evaluate(self, run: PipelineRun, action: FixAction) -> tuple[bool, str]:
        error_class = (run.failure.error_class or "") if run.failure else ""
        title = action.title.lower()
        is_oom = "OutOfMemory" in error_class
        spilled = (run.metrics.memory_spilled_bytes + run.metrics.disk_spilled_bytes) > 0

        # Broadcasting the small side resolves the canonical skewed-join OOM.
        if is_oom and "broadcast" in title:
            return True, "Broadcast join removed the large shuffle; rerun succeeded."

        # Raising shuffle partitions helps spill-driven memory pressure.
        if spilled and "shuffle partition" in title:
            return (
                True,
                "Increased shuffle partitions reduced partition size; " "rerun succeeded.",
            )

        # Repartitioning addresses skew when there's no outright OOM.
        if not is_oom and spilled and "repartition" in title:
            return True, "Repartitioning balanced the skew; rerun succeeded."

        return (
            False,
            f"Fix '{action.title}' did not resolve the failure signature.",
        )
