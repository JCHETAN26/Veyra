"""IsolationForest tabular anomaly detector.

Trains an unsupervised IsolationForest on a sliding window of past runs'
metric vectors and flags new runs whose anomaly score lands in the bottom
`contamination` quantile. No labels needed — the model learns "what
normal looks like for this team" from history alone.

The model is refit per evaluation because run history evolves slowly and
the dataset is tiny (~100 runs). The cost is milliseconds; not worth a
caching layer at this scale.
"""

from __future__ import annotations

from typing import Any

from dataforge.contracts.incident import (
    AnomalySignal,
    AnomalyType,
    Finding,
    Severity,
)
from dataforge.contracts.telemetry import PipelineRun
from dataforge.modules.observability.detectors import DetectorThresholds
from dataforge.modules.observability.ml.detector import MLDetectorError

# Features in a stable order: the model is fit and queried on this exact
# shape so adding a feature is a versioning concern, not a silent bug.
_FEATURES: tuple[str, ...] = (
    "memory_spilled_bytes",
    "disk_spilled_bytes",
    "shuffle_read_bytes",
    "shuffle_write_bytes",
    "num_failed_tasks",
    "executor_run_time_ms",
)


def _features(run: PipelineRun) -> list[float]:
    m = run.metrics
    return [
        float(m.memory_spilled_bytes),
        float(m.disk_spilled_bytes),
        float(m.shuffle_read_bytes),
        float(m.shuffle_write_bytes),
        float(m.num_failed_tasks),
        float(m.executor_run_time_ms),
    ]


class IsolationForestDetector:
    """Unsupervised metric-vector outlier detection."""

    name = "isolation_forest"

    def __init__(
        self,
        *,
        contamination: float = 0.05,
        n_estimators: int = 100,
        random_state: int = 42,
        requires_history: int = 30,
    ) -> None:
        if not 0.0 < contamination < 0.5:
            raise MLDetectorError(f"contamination must be in (0, 0.5); got {contamination}")
        self.contamination = contamination
        self.n_estimators = n_estimators
        self.random_state = random_state
        self.requires_history = requires_history

    def detect(
        self,
        run: PipelineRun,
        history: list[PipelineRun],
        thresholds: DetectorThresholds,
    ) -> Finding | None:
        del thresholds  # IsolationForest is parameter-free at threshold layer
        model = self._fit(history)

        x = [_features(run)]
        prediction = int(model.predict(x)[0])  # +1 normal, -1 anomaly
        score = float(model.decision_function(x)[0])
        if prediction != -1:
            return None

        return Finding(
            anomaly_type=AnomalyType.METRIC_OUTLIER,
            severity=Severity.MEDIUM,
            title="Run metrics fall outside learned baseline",
            description=(
                "IsolationForest classified this run's metric vector as an "
                f"outlier relative to the last {len(history)} runs "
                f"(anomaly score {score:.4f}; lower = more anomalous). "
                "Inspect spill, shuffle, and failed-task counts against the "
                "historical norm."
            ),
            signals=[
                AnomalySignal(
                    name="isolation_forest_score",
                    value=round(score, 6),
                    detail=f"contamination={self.contamination}",
                ),
                *self._feature_signals(run),
            ],
        )

    def _fit(self, history: list[PipelineRun]) -> Any:
        try:
            from sklearn.ensemble import IsolationForest
        except ImportError as exc:  # pragma: no cover - dep gated
            raise MLDetectorError(
                "scikit-learn not installed. Install dataforge with the [ml] "
                "extra to enable the IsolationForest detector."
            ) from exc

        x = [_features(h) for h in history]
        model = IsolationForest(
            n_estimators=self.n_estimators,
            contamination=self.contamination,
            random_state=self.random_state,
        )
        model.fit(x)
        return model

    def _feature_signals(self, run: PipelineRun) -> list[AnomalySignal]:
        values = _features(run)
        return [
            AnomalySignal(name=name, value=value)
            for name, value in zip(_FEATURES, values, strict=True)
        ]
