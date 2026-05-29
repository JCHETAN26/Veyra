"""Root-cause analysis repository.

Typed persistence port for RootCauseAnalysis. One analysis per run (unique on
run_id); re-analysis replaces the prior result so it stays idempotent.
"""

from __future__ import annotations

import json

from sqlalchemy.ext.asyncio import AsyncSession

from dataforge.contracts.rca import (
    CauseCategory,
    RecommendedAction,
    RootCauseAnalysis,
)
from dataforge.core.logging import get_logger
from dataforge.modules.metadata.models import RootCauseAnalysisRow

logger = get_logger(__name__)


class RcaRepository:
    """Async repository over root-cause analyses."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert(self, analysis: RootCauseAnalysis) -> None:
        existing = await self._session.get(RootCauseAnalysisRow, analysis.analysis_id)
        if existing is not None:
            await self._session.delete(existing)
            await self._session.flush()

        self._session.add(_to_row(analysis))
        await self._session.flush()
        logger.info(
            "rca.upserted",
            analysis_id=analysis.analysis_id,
            run_id=analysis.run_id,
            category=analysis.category,
            confidence=analysis.confidence,
        )

    async def get_for_run(self, run_id: str) -> RootCauseAnalysis | None:
        # analysis_id is deterministic (rca-<run_id>), so look up directly.
        row = await self._session.get(RootCauseAnalysisRow, f"rca-{run_id}")
        return _to_analysis(row) if row is not None else None


def _to_row(a: RootCauseAnalysis) -> RootCauseAnalysisRow:
    row = RootCauseAnalysisRow(
        analysis_id=a.analysis_id,
        run_id=a.run_id,
        category=a.category.value,
        summary=a.summary,
        explanation=a.explanation,
        contributing_factors_json=json.dumps(a.contributing_factors),
        recommended_actions_json=json.dumps([act.model_dump() for act in a.recommended_actions]),
        incident_ids_json=json.dumps(a.incident_ids),
        confidence=a.confidence,
        analyzer=a.analyzer,
    )
    if a.created_at is not None:
        row.created_at = a.created_at
    return row


def _to_analysis(row: RootCauseAnalysisRow) -> RootCauseAnalysis:
    return RootCauseAnalysis(
        analysis_id=row.analysis_id,
        run_id=row.run_id,
        category=CauseCategory(row.category),
        summary=row.summary,
        explanation=row.explanation,
        contributing_factors=json.loads(row.contributing_factors_json or "[]"),
        recommended_actions=[
            RecommendedAction(**a) for a in json.loads(row.recommended_actions_json or "[]")
        ],
        incident_ids=json.loads(row.incident_ids_json or "[]"),
        confidence=row.confidence,
        analyzer=row.analyzer,
        created_at=row.created_at,
    )
