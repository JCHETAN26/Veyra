"""The FixGenerator protocol.

A generator takes a run, its root-cause analysis, and the operationally
similar past incidents already retrieved by the coordinator, and returns
the FixProposal that the remediation workflow will gate on human approval.

Pure generation: no I/O to the metadata store, no persistence — the
orchestration service handles those.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from dataforge.contracts.rca import RootCauseAnalysis
from dataforge.contracts.remediation_workflow import FixProposal
from dataforge.contracts.retrieval import SimilarIncident
from dataforge.contracts.telemetry import PipelineRun


@runtime_checkable
class FixGenerator(Protocol):
    """Produces a FixProposal for a run + its RCA."""

    name: str

    async def generate(
        self,
        run: PipelineRun,
        analysis: RootCauseAnalysis,
        *,
        similar: list[SimilarIncident] | None = None,
    ) -> FixProposal:
        """Return the ordered fix proposal for this run."""
        ...
