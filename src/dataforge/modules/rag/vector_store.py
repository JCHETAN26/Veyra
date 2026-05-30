"""Vector stores.

The VectorStore interface is the index RAG writes profiles into and queries for
nearest neighbours. The MVP default is an in-process store (exact cosine
search) — correct, dependency-free, and the path exercised by tests. A Qdrant
adapter implementing the same interface backs the Docker Compose stack later.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from dataforge.modules.rag.embedder import cosine_similarity
from dataforge.modules.rag.profile import FailureProfile


@dataclass
class StoredProfile:
    """A profile plus its embedding, as held in the index."""

    profile: FailureProfile
    vector: list[float]


@dataclass
class ScoredProfile:
    """A search hit: the stored profile and its similarity to the query."""

    profile: FailureProfile
    score: float


@runtime_checkable
class VectorStore(Protocol):
    async def upsert(self, stored: StoredProfile) -> None:
        """Insert or replace a profile, keyed on its run_id."""
        ...

    async def search(
        self, vector: list[float], *, limit: int, exclude_run_id: str | None = None
    ) -> list[ScoredProfile]:
        """Return the nearest profiles by cosine similarity, best first."""
        ...

    async def count(self) -> int: ...


@dataclass
class InMemoryVectorStore:
    """Exact-search in-process vector store, keyed on run_id.

    Thread-safe for the test/single-process case. Linear scan is fine at MVP
    scale; the Qdrant adapter handles production-scale ANN search.
    """

    _items: dict[str, StoredProfile] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    async def upsert(self, stored: StoredProfile) -> None:
        with self._lock:
            self._items[stored.profile.run_id] = stored

    async def search(
        self, vector: list[float], *, limit: int, exclude_run_id: str | None = None
    ) -> list[ScoredProfile]:
        with self._lock:
            items = list(self._items.values())

        scored = [
            ScoredProfile(profile=item.profile, score=cosine_similarity(vector, item.vector))
            for item in items
            if item.profile.run_id != exclude_run_id
        ]
        scored.sort(key=lambda s: (s.score, s.profile.run_id), reverse=True)
        return scored[:limit]

    async def count(self) -> int:
        with self._lock:
            return len(self._items)
