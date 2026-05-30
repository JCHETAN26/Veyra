"""Operational RAG retrieval contracts.

When a run fails, the platform retrieves *similar past failures* so engineers
(and the RCA/remediation layers) get precedent: "this happened before, here's
what it looked like." These contracts are the shape returned by that search.

The indexed unit is a run's *failure profile* — a consolidated view of its
failure signature, incidents, and root cause — rather than raw text, so
similarity reflects operational likeness, not prose overlap.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class SimilarIncident(BaseModel):
    """A past run whose failure profile resembles the query run."""

    run_id: str
    score: float = Field(..., ge=0.0, le=1.0, description="Cosine similarity.")
    app_name: str = ""
    category: str | None = None
    summary: str = ""
    severity: str | None = None
    anomaly_types: list[str] = Field(default_factory=list)
    occurred_at: datetime | None = None


class RetrievalResult(BaseModel):
    """Result of a similar-incident search for a query run."""

    query_run_id: str
    results: list[SimilarIncident] = Field(default_factory=list)
