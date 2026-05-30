"""Pipeline coordinator.

The conductor of the self-healing loop. Given a run's telemetry it drives every
stage in order — ingest -> detect -> explain -> recall -> propose — and stops
at the human approval gate. It never approves: a proposed remediation waits for
an explicit human decision (build-plan: human-in-the-loop).

The coordinator composes the existing module services in-process rather than
calling the HTTP API, so the loop is a single transaction of work with no
network hops. Services are injected so the coordinator reuses the *same*
instances the API uses (notably the RAG index).

Outcomes:
- HEALTHY            — no incidents; nothing to do.
- NO_ACTIONABLE_FIX  — anomalies detected but no auto-applicable fix proposed.
- NEEDS_APPROVAL     — a remediation is proposed and awaiting human approval.
"""

from __future__ import annotations

from dataforge.contracts.lineage import BlastRadius
from dataforge.contracts.pipeline import PipelineOutcome, PipelineReport
from dataforge.contracts.telemetry import PipelineRun
from dataforge.core.db import session_scope
from dataforge.core.errors import ConflictError, NotFoundError
from dataforge.core.logging import get_logger
from dataforge.modules.ingestion.service import IngestionService
from dataforge.modules.metadata.lineage_repository import LineageRepository
from dataforge.modules.metadata.repository import MetadataRepository
from dataforge.modules.observability.service import ObservabilityService
from dataforge.modules.orchestration.service import OrchestrationService
from dataforge.modules.rag.service import RagService
from dataforge.modules.remediation.service import RemediationService

logger = get_logger(__name__)


class PipelineCoordinator:
    """Runs a run through the full self-healing loop, up to the approval gate."""

    def __init__(
        self,
        ingestion: IngestionService,
        observability: ObservabilityService,
        remediation: RemediationService,
        rag: RagService,
        orchestration: OrchestrationService,
    ) -> None:
        self._ingestion = ingestion
        self._observability = observability
        self._remediation = remediation
        self._rag = rag
        self._orchestration = orchestration

    async def process_event_log(self, content: str, *, run_id: str) -> PipelineReport:
        """Ingest a Spark event log, then run the rest of the loop over it."""
        await self._ingestion.ingest_event_log(content, run_id=run_id)
        return await self._process(run_id)

    async def process_run(self, run_id: str) -> PipelineReport:
        """Run the loop over an already-ingested run."""
        return await self._process(run_id)

    async def _process(self, run_id: str) -> PipelineReport:
        # 1. Detect anomalies -> incidents.
        incidents = await self._observability.evaluate_run(run_id)

        # 2. Always retrieve operational context (this also indexes the run).
        retrieval = await self._rag.find_similar(run_id)

        run = await self._load_run(run_id)

        # Healthy run: nothing to explain or remediate.
        if not incidents:
            logger.info("coordinator.healthy", run_id=run_id)
            return PipelineReport(
                run_id=run_id,
                outcome=PipelineOutcome.HEALTHY,
                run=run,
                similar_incidents=retrieval.results,
            )

        # 3. Explain the failure.
        analysis = await self._remediation.analyze_run(run_id)

        # 3b. Compute downstream blast radius from the run's known outputs.
        blast_radius = await self._blast_radius(run_id)

        # 4. Propose a remediation if an actionable fix exists. propose() raises
        #    ConflictError when there's nothing auto-applicable; that's a valid
        #    no-actionable-fix outcome, not an error.
        try:
            workflow = await self._orchestration.propose(run_id)
            outcome = PipelineOutcome.NEEDS_APPROVAL
        except ConflictError:
            workflow = None
            outcome = PipelineOutcome.NO_ACTIONABLE_FIX

        logger.info(
            "coordinator.processed",
            run_id=run_id,
            outcome=outcome,
            num_incidents=len(incidents),
            cause=analysis.category,
            blast_radius=blast_radius.count if blast_radius else 0,
        )
        return PipelineReport(
            run_id=run_id,
            outcome=outcome,
            run=run,
            incidents=incidents,
            analysis=analysis,
            similar_incidents=retrieval.results,
            workflow=workflow,
            blast_radius=blast_radius,
        )

    async def _blast_radius(self, run_id: str) -> BlastRadius | None:
        """Downstream impact of a run's outputs, if any lineage is known."""
        async with session_scope() as session:
            repo = LineageRepository(session)
            outputs = await repo.outputs_for_run(run_id)
            if not outputs:
                return None
            return await repo.blast_radius(outputs)

    async def _load_run(self, run_id: str) -> PipelineRun:
        async with session_scope() as session:
            run = await MetadataRepository(session).get_run(run_id)
        if run is None:
            raise NotFoundError(f"run '{run_id}' not found")
        return run
