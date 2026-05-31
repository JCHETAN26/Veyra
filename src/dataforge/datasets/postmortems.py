"""Public-incident postmortems loader.

Modeled after the danluu/post-mortems list — short references to widely-
publicized engineering failures, categorized by the failure mode they
exhibit. The bundled fixture is a curated, license-clean sample suitable
for offline demos and CI; a live fetcher targeting the upstream README
will sit behind the same interface in a follow-on change.

Each record is mapped onto a FailureProfile so RAG retrieval over the
corpus uses the exact same code path as retrieval over real Spark runs.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from importlib.resources import files

from dataforge.datasets.loader import DatasetRecord
from dataforge.modules.rag.profile import FailureProfile, build_profile_from_fields


class PostmortemsLoader:
    """Bundled curated postmortem references."""

    name = "postmortems"
    description = "Curated public engineering postmortems (style: danluu/post-mortems)."

    FIXTURE = "postmortems_sample.json"

    def records(self, *, limit: int | None = None) -> Sequence[DatasetRecord]:
        raw = self._read_bundled()
        records = [DatasetRecord(**row) for row in raw]
        if limit is not None:
            records = records[:limit]
        return records

    def profiles(self, *, limit: int | None = None) -> list[FailureProfile]:
        return [_to_profile(r) for r in self.records(limit=limit)]

    def _read_bundled(self) -> list[dict[str, object]]:
        text = files("dataforge.datasets.fixtures").joinpath(self.FIXTURE).read_text("utf-8")
        data = json.loads(text)
        if not isinstance(data, list):
            raise ValueError(f"{self.FIXTURE} must be a JSON list of records")
        return data


def _to_profile(record: DatasetRecord) -> FailureProfile:
    return build_profile_from_fields(
        run_id=record.run_id,
        app_name=record.app_name,
        category=record.category,
        summary=record.summary,
        severity=record.severity,
        anomaly_types=record.anomaly_types,
        error_class=record.error_class,
        # Postmortems are by definition records of past failures.
        status="failed",
    )
