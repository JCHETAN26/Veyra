"""RAG service.

Indexes run failure profiles and retrieves operationally similar past runs.
Embedder and vector store are injected behind their interfaces so the
deterministic MVP (hashing embedder + in-process store) can be swapped for a
model embedder + Qdrant without changing this orchestration.

Reads runs/incidents/analyses through the existing repository ports, keeping
the module boundary intact.
"""

from __future__ import annotations

from dataforge.contracts.retrieval import RetrievalResult, SimilarIncident
from dataforge.core.db import session_scope
from dataforge.core.errors import NotFoundError
from dataforge.core.logging import get_logger
from dataforge.modules.metadata.incident_repository import IncidentRepository
from dataforge.modules.metadata.rca_repository import RcaRepository
from dataforge.modules.metadata.repository import MetadataRepository
from dataforge.modules.rag.embedder import Embedder, HashingEmbedder
from dataforge.modules.rag.profile import FailureProfile, build_profile
from dataforge.modules.rag.vector_store import (
    InMemoryVectorStore,
    StoredProfile,
    VectorStore,
)

logger = get_logger(__name__)


class RagService:
    """Operational RAG over run failure profiles."""

    def __init__(
        self,
        embedder: Embedder | None = None,
        store: VectorStore | None = None,
    ) -> None:
        self._embedder: Embedder = embedder or HashingEmbedder()
        self._store: VectorStore = store or InMemoryVectorStore()

    async def index_run(self, run_id: str) -> FailureProfile:
        """Build and index the failure profile for a run."""
        profile = await self._load_profile(run_id)
        return await self.index_profile(profile)

    async def index_profile(self, profile: FailureProfile) -> FailureProfile:
        """Index a pre-built profile directly into the vector store.

        Used by dataset loaders that produce profiles from external corpora
        (postmortems, Loghub samples, ...) — those records have no real
        PipelineRun in the metadata store, so the regular index_run path
        doesn't apply.
        """
        vector = self._embedder.embed(profile)
        await self._store.upsert(StoredProfile(profile=profile, vector=vector))
        logger.info(
            "rag.indexed",
            run_id=profile.run_id,
            category=profile.category,
            embedder=self._embedder.name,
        )
        return profile

    async def find_similar(
        self, run_id: str, *, limit: int = 5, min_score: float = 0.1
    ) -> RetrievalResult:
        """Find past runs whose failure profile resembles this run's.

        The query run is indexed first (idempotent) so repeated failures of the
        same job are themselves retrievable, then excluded from its own results.
        """
        profile = await self.index_run(run_id)
        vector = self._embedder.embed(profile)
        hits = await self._store.search(vector, limit=limit, exclude_run_id=run_id)

        results = [
            SimilarIncident(
                run_id=h.profile.run_id,
                score=round(h.score, 4),
                app_name=h.profile.app_name,
                category=h.profile.category,
                summary=h.profile.summary,
                severity=h.profile.severity,
                anomaly_types=h.profile.anomaly_types,
                occurred_at=h.profile.occurred_at,
            )
            for h in hits
            if h.score >= min_score
        ]
        logger.info(
            "rag.searched",
            run_id=run_id,
            num_results=len(results),
            corpus_size=await self._store.count(),
        )
        return RetrievalResult(query_run_id=run_id, results=results)

    async def _load_profile(self, run_id: str) -> FailureProfile:
        async with session_scope() as session:
            run = await MetadataRepository(session).get_run(run_id)
            if run is None:
                raise NotFoundError(f"run '{run_id}' not found")
            incidents = await IncidentRepository(session).list_for_run(run_id)
            analysis = await RcaRepository(session).get_for_run(run_id)
        return build_profile(run, incidents, analysis)
