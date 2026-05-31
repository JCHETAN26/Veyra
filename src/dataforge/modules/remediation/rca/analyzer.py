"""The RootCauseAnalyzer interface.

Any analyzer (rule-based, LLM-backed) takes a run plus the incidents raised
for it and returns a structured RootCauseAnalysis. Pure analysis: no I/O
to the metadata store, no persistence — the service handles loading and
saving so analyzers stay unit-testable.

The interface is async because the LLM-backed implementation calls a
remote API. The rule-based implementation is CPU-only and simply doesn't
yield, which is idiomatic for an async method that wraps sync work.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from dataforge.contracts.incident import Incident
from dataforge.contracts.rca import RootCauseAnalysis
from dataforge.contracts.telemetry import PipelineRun


@runtime_checkable
class RootCauseAnalyzer(Protocol):
    """Produces a root-cause analysis for a run and its incidents."""

    name: str

    async def analyze(self, run: PipelineRun, incidents: list[Incident]) -> RootCauseAnalysis:
        """Return a structured explanation of why the run failed/anomalous."""
        ...
