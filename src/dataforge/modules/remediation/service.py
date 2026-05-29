"""Remediation service — root-cause analysis layer.

Loads a run and its incidents, runs the configured analyzer, and persists the
resulting RootCauseAnalysis. The analyzer is injected behind the
RootCauseAnalyzer interface so the rule-based MVP can be swapped for an
LLM-backed one without changing this orchestration.

Fix generation and the approval-gated rerun build on top of this next.
"""

from __future__ import annotations

from datetime import UTC, datetime

from dataforge.contracts.rca import RootCauseAnalysis
from dataforge.core.db import session_scope
from dataforge.core.errors import NotFoundError
from dataforge.core.logging import get_logger
from dataforge.modules.metadata.incident_repository import IncidentRepository
from dataforge.modules.metadata.rca_repository import RcaRepository
from dataforge.modules.metadata.repository import MetadataRepository
from dataforge.modules.remediation.rca import RootCauseAnalyzer, RuleBasedAnalyzer

logger = get_logger(__name__)


class RemediationService:
    """Produces and stores root-cause analyses for pipeline runs."""

    def __init__(self, analyzer: RootCauseAnalyzer | None = None) -> None:
        self._analyzer: RootCauseAnalyzer = analyzer or RuleBasedAnalyzer()

    async def analyze_run(self, run_id: str) -> RootCauseAnalysis:
        """Run root-cause analysis for a run and persist the result.

        Idempotent: re-analysis replaces the prior analysis for the run.
        """
        async with session_scope() as session:
            run = await MetadataRepository(session).get_run(run_id)
            if run is None:
                raise NotFoundError(f"run '{run_id}' not found")

            incidents = await IncidentRepository(session).list_for_run(run_id)
            analysis = self._analyzer.analyze(run, incidents)
            analysis.created_at = datetime.now(UTC)

            await RcaRepository(session).upsert(analysis)

        logger.info(
            "remediation.analyzed",
            run_id=run_id,
            category=analysis.category,
            confidence=analysis.confidence,
            analyzer=analysis.analyzer,
        )
        return analysis
