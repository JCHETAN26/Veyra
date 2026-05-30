"""Rule-based fix generator (deterministic MVP).

Maps the recommended actions on a RootCauseAnalysis 1:1 onto FixActions,
dropping any action whose `kind` is "manual" (manual triage actions can't
be auto-applied by the workflow). This is the same logic that used to live
inline in OrchestrationService — extracted into the FixGenerator surface so
the LLM-backed generator can swap in behind the same interface.
"""

from __future__ import annotations

from dataforge.contracts.rca import RootCauseAnalysis
from dataforge.contracts.remediation_workflow import FixAction, FixProposal
from dataforge.contracts.retrieval import SimilarIncident
from dataforge.contracts.telemetry import PipelineRun


class RuleBasedFixGenerator:
    """Deterministic mapper from RCA actions to FixActions."""

    name = "rule-based-v1"

    async def generate(
        self,
        run: PipelineRun,
        analysis: RootCauseAnalysis,
        *,
        similar: list[SimilarIncident] | None = None,
    ) -> FixProposal:
        del similar  # rule-based generator doesn't use retrieval context
        actions = [
            FixAction(title=a.title, detail=a.detail, kind=a.kind)
            for a in analysis.recommended_actions
            if a.kind != "manual"
        ]
        return FixProposal(
            run_id=run.run_id,
            cause_category=analysis.category.value,
            confidence=analysis.confidence,
            actions=actions,
        )
