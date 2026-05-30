"""Loghub-style Spark log loader.

Modeled after the logpai/loghub Spark dataset — structured log lines from
real Spark applications, with each anomalous line tagged by failure mode.
The bundled fixture is a license-clean curated sample suitable for offline
demos and CI; a live fetcher will sit behind the same interface later.

Each line becomes a FailureProfile so RAG can rank "have we seen a line
like this before" the same way it ranks past pipeline runs.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from importlib.resources import files

from dataforge.datasets.loader import DatasetRecord
from dataforge.modules.rag.profile import FailureProfile, build_profile_from_fields


class LoghubSparkLoader:
    """Bundled Spark log entries with anomaly hints."""

    name = "loghub_spark"
    description = "Spark log entries with anomaly hints (style: logpai/loghub)."

    FIXTURE = "loghub_spark_sample.json"

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
    # Spark log entries usually carry a "succeeded but anomalous" connotation;
    # we mark status=anomalous when an error_class is present, success when not.
    status = "failed" if record.error_class else "succeeded"
    return build_profile_from_fields(
        run_id=record.run_id,
        app_name=record.app_name,
        category=record.category,
        summary=record.summary,
        severity=record.severity,
        anomaly_types=record.anomaly_types,
        error_class=record.error_class,
        status=status,
    )
