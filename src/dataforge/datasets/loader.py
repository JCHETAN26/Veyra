"""Loader interface shared by every dataset.

A loader returns its records as :class:`FailureProfile` instances so the
RAG service can index them via the same `index_profile` path used by
in-process runs. Loaders are intentionally simple and synchronous — the
expensive part (downloading large corpora) is opt-in.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from pydantic import BaseModel

from dataforge.modules.rag.profile import FailureProfile


class DatasetRecord(BaseModel):
    """Raw row a loader reads from its bundled or fetched source.

    Loaders translate their source-specific schema into this shape, then
    `to_profile()` maps it onto the canonical FailureProfile. Keeping a
    separate record type makes loader tests independent of the profile
    representation (which can evolve).
    """

    run_id: str
    app_name: str = ""
    category: str | None = None
    summary: str = ""
    error_class: str | None = None
    anomaly_types: list[str] = []
    severity: str | None = None
    # Source-specific metadata that doesn't fit elsewhere (e.g. log line
    # number, postmortem URL). Indexing keys ignore this.
    extras: dict[str, str] = {}


@runtime_checkable
class DatasetLoader(Protocol):
    """A named source of FailureProfile records."""

    name: str
    description: str

    def records(self, *, limit: int | None = None) -> Sequence[DatasetRecord]:
        """Load (or re-read) the bundled records, optionally truncated."""
        ...

    def profiles(self, *, limit: int | None = None) -> list[FailureProfile]:
        """Convenience: map records to FailureProfiles directly."""
        ...
