"""Incident repository.

Typed persistence port for incidents. Idempotent on (run_id, anomaly_type):
re-running detection over the same run updates the existing incident rather
than creating duplicates, so detection can be safely replayed.
"""

from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dataforge.contracts.incident import (
    AnomalySignal,
    AnomalyType,
    Incident,
    IncidentStatus,
    Severity,
)
from dataforge.core.logging import get_logger
from dataforge.modules.metadata.models import IncidentRow

logger = get_logger(__name__)


class IncidentRepository:
    """Async repository over incidents."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert(self, incident: Incident) -> None:
        """Insert or update an incident, keyed on (run_id, anomaly_type)."""
        stmt = select(IncidentRow).where(
            IncidentRow.run_id == incident.run_id,
            IncidentRow.anomaly_type == incident.anomaly_type.value,
        )
        existing = (await self._session.execute(stmt)).scalar_one_or_none()

        signals_json = json.dumps([s.model_dump() for s in incident.signals], default=str)

        if existing is None:
            self._session.add(_to_row(incident, signals_json))
        else:
            existing.severity = int(incident.severity)
            existing.title = incident.title
            existing.description = incident.description
            existing.signals_json = signals_json
            # status is preserved across re-detection (don't reopen resolved).
        await self._session.flush()
        logger.info(
            "incident.upserted",
            incident_id=incident.incident_id,
            run_id=incident.run_id,
            anomaly_type=incident.anomaly_type,
            severity=incident.severity.label,
        )

    async def get(self, incident_id: str) -> Incident | None:
        row = await self._session.get(IncidentRow, incident_id)
        return _to_incident(row) if row is not None else None

    async def list_for_run(self, run_id: str) -> list[Incident]:
        stmt = (
            select(IncidentRow)
            .where(IncidentRow.run_id == run_id)
            .order_by(IncidentRow.severity.desc())
        )
        result = await self._session.execute(stmt)
        return [_to_incident(r) for r in result.scalars().all()]

    async def list_open(self, *, limit: int = 50) -> list[Incident]:
        stmt = (
            select(IncidentRow)
            .where(IncidentRow.status == IncidentStatus.OPEN.value)
            .order_by(IncidentRow.severity.desc(), IncidentRow.detected_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return [_to_incident(r) for r in result.scalars().all()]


def _to_row(incident: Incident, signals_json: str) -> IncidentRow:
    row = IncidentRow(
        incident_id=incident.incident_id,
        run_id=incident.run_id,
        anomaly_type=incident.anomaly_type.value,
        severity=int(incident.severity),
        status=incident.status.value,
        title=incident.title,
        description=incident.description,
        signals_json=signals_json,
    )
    if incident.detected_at is not None:
        row.detected_at = incident.detected_at
    return row


def _to_incident(row: IncidentRow) -> Incident:
    raw_signals = json.loads(row.signals_json or "[]")
    return Incident(
        incident_id=row.incident_id,
        run_id=row.run_id,
        anomaly_type=AnomalyType(row.anomaly_type),
        severity=Severity(row.severity),
        status=IncidentStatus(row.status),
        title=row.title,
        description=row.description,
        signals=[AnomalySignal(**s) for s in raw_signals],
        detected_at=row.detected_at,
    )
