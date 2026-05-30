"""Time-series anomaly detector (z-score baseline).

Flags runs whose duration deviates from the same pipeline's historical
duration distribution by more than `z_threshold` standard deviations.
Pure Python — no external deps, no model file — so this detector ships
in the default install. A heavier forecaster (Prophet, statsforecast) can
swap in behind the same MLDetector interface later.

History is filtered to the same `app_name` before computing the baseline:
mixing pipelines would dilute the signal (a 10-min ETL is "anomalously
fast" vs. a 2-hour ML job).
"""

from __future__ import annotations

import math

from dataforge.contracts.incident import (
    AnomalySignal,
    AnomalyType,
    Finding,
    Severity,
)
from dataforge.contracts.telemetry import PipelineRun, RunStatus
from dataforge.modules.observability.detectors import DetectorThresholds


class TimeseriesAnomalyDetector:
    """Per-pipeline duration z-score."""

    name = "timeseries_zscore"

    def __init__(
        self,
        *,
        z_threshold: float = 3.0,
        requires_history: int = 10,
    ) -> None:
        if z_threshold <= 0:
            raise ValueError("z_threshold must be positive")
        self.z_threshold = z_threshold
        self.requires_history = requires_history

    def detect(
        self,
        run: PipelineRun,
        history: list[PipelineRun],
        thresholds: DetectorThresholds,
    ) -> Finding | None:
        del thresholds  # this detector is self-tuning against history
        if run.duration_ms is None:
            return None

        peers = [
            h.duration_ms
            for h in history
            if h.app_name == run.app_name
            and h.duration_ms is not None
            and h.status == RunStatus.SUCCEEDED
            and h.run_id != run.run_id
        ]
        if len(peers) < self.requires_history:
            return None

        mu = sum(peers) / len(peers)
        var = sum((d - mu) ** 2 for d in peers) / len(peers)
        sigma = math.sqrt(var)
        if sigma == 0:
            return None

        z = (run.duration_ms - mu) / sigma
        if abs(z) < self.z_threshold:
            return None

        direction = "slower" if z > 0 else "faster"
        return Finding(
            anomaly_type=AnomalyType.DURATION_OUTLIER,
            severity=Severity.MEDIUM if abs(z) < 5 else Severity.HIGH,
            title=f"Run duration {direction} than baseline by {abs(z):.1f}σ",
            description=(
                f"Run took {run.duration_ms:,} ms vs historical mean "
                f"{mu:,.0f} ms (σ={sigma:,.0f}) over {len(peers)} prior "
                f"'{run.app_name}' runs. Z-score = {z:+.2f}."
            ),
            signals=[
                AnomalySignal(
                    name="duration_zscore",
                    value=round(z, 4),
                    threshold=self.z_threshold,
                ),
                AnomalySignal(name="duration_ms", value=float(run.duration_ms)),
                AnomalySignal(name="baseline_mean_ms", value=round(mu, 1)),
                AnomalySignal(name="baseline_stddev_ms", value=round(sigma, 1)),
            ],
        )
