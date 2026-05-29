"""Ingestion service.

Orchestrates the parse -> normalize -> persist path. The service depends on
the metadata module only through MetadataRepository (a typed port), preserving
the module boundary that lets ingestion become its own service later.
"""

from __future__ import annotations

from dataforge.contracts.telemetry import PipelineRun
from dataforge.core.db import session_scope
from dataforge.core.logging import get_logger
from dataforge.modules.ingestion.spark_eventlog import parse_event_log
from dataforge.modules.metadata.repository import MetadataRepository

logger = get_logger(__name__)


class IngestionService:
    """Ingests Spark telemetry into canonical storage."""

    async def ingest_event_log(self, content: str, *, run_id: str) -> PipelineRun:
        """Parse a Spark event log and persist the resulting run.

        Idempotent on run_id: re-ingesting the same log replaces the prior
        record rather than duplicating it.
        """
        run = parse_event_log(content, run_id=run_id)
        async with session_scope() as session:
            repo = MetadataRepository(session)
            await repo.upsert_run(run)
        logger.info("ingestion.completed", run_id=run_id, status=run.status)
        return run
