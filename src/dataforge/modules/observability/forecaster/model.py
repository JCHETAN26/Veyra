"""The FailureForecaster wrapper.

Trains a gradient-boosted classifier over the feature vectors emitted by
`features.extract_features`. The label for each training row is whether
*that* run failed; the features are extracted from the window of runs
*before* it. So the model learns: "given the recent state of this
pipeline, predict whether the next run will fail."

`fit` and `predict_proba` are the only methods the underlying model is
required to expose, so XGBoost and sklearn GBT (and any other sklearn-
compatible classifier) work transparently. The default is sklearn's
GradientBoostingClassifier — it's already in the `ml` extra via
scikit-learn and saves a 150MB xgboost wheel for an MVP-scale problem.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from dataforge.contracts.forecast import FailurePrediction, TrainingResult
from dataforge.contracts.telemetry import PipelineRun, RunStatus
from dataforge.core.errors import DataForgeError
from dataforge.core.logging import get_logger
from dataforge.modules.observability.forecaster.features import (
    FEATURE_NAMES,
    extract_features,
)

logger = get_logger(__name__)


class ForecasterError(DataForgeError):
    """Forecaster could not produce a prediction."""

    code = "forecaster_error"
    status_code = 422


class ForecasterNotTrainedError(ForecasterError):
    """Called predict() before fit()."""

    code = "forecaster_not_trained"
    status_code = 409


# Heuristic: anything below this many windowable rows is too thin to
# trust the resulting model's probability estimates.
_MIN_TRAINING_SAMPLES = 30


class FailureForecaster:
    """Predict the next failure for a pipeline from its recent history."""

    DEFAULT_WINDOW = 10
    MODEL_VERSION = "gbt-forecaster-v1"

    def __init__(
        self,
        *,
        window: int = DEFAULT_WINDOW,
        min_training_samples: int = _MIN_TRAINING_SAMPLES,
    ) -> None:
        if window < 2:
            raise ForecasterError(f"window must be >= 2; got {window}")
        self.window = window
        self.min_training_samples = min_training_samples
        self._model: Any = None
        self._trained_samples = 0
        self._positive_samples = 0
        self._feature_importances: dict[str, float] = {}

    # --- training ----------------------------------------------------------

    def fit(self, runs: list[PipelineRun]) -> TrainingResult:
        """Train the model from a flat list of historical runs.

        Runs are grouped by `app_name`, sorted by `started_at` (None last so
        unstarted rows don't influence the order), and unrolled into
        (feature, label) pairs where each label is whether *that* run
        failed and the features come from the `window` runs preceding it.
        """
        x, y = self._build_training_set(runs)

        if len(x) < self.min_training_samples:
            raise ForecasterError(
                f"not enough training samples: have {len(x)}, "
                f"need >= {self.min_training_samples}. Generate more "
                f"history or lower min_training_samples."
            )
        if sum(y) == 0:
            raise ForecasterError(
                "training set has zero failures; the classifier would "
                "collapse to a constant. Provide at least one failed run."
            )
        if sum(y) == len(y):
            raise ForecasterError(
                "training set is all failures; the classifier would "
                "collapse to a constant. Provide at least one successful run."
            )

        self._model = self._build_model()
        self._model.fit(x, y)
        self._trained_samples = len(x)
        self._positive_samples = int(sum(y))
        self._feature_importances = self._extract_importances(self._model)

        result = TrainingResult(
            samples=self._trained_samples,
            positive_samples=self._positive_samples,
            feature_importances=self._feature_importances,
            model_version=self.MODEL_VERSION,
            trained_at=datetime.now(UTC),
        )
        top = max(self._feature_importances.items(), key=lambda kv: kv[1], default=("?", 0.0))
        logger.info(
            "forecaster.trained",
            samples=result.samples,
            positives=result.positive_samples,
            top_feature=top[0],
        )
        return result

    # --- inference ---------------------------------------------------------

    def predict(self, recent_runs: list[PipelineRun]) -> FailurePrediction:
        """Predict P(next run fails) for one pipeline.

        Args:
            recent_runs: runs of a SINGLE pipeline, oldest first. The last
                `window` of them are used; older runs are ignored.
        """
        if self._model is None:
            raise ForecasterNotTrainedError(
                "forecaster has not been fit yet; call fit(runs) first."
            )
        if len(recent_runs) < 2:
            raise ForecasterError(
                "predict() needs at least 2 recent runs to derive trend "
                f"features; got {len(recent_runs)}."
            )

        app_names = {r.app_name for r in recent_runs}
        if len(app_names) != 1:
            raise ForecasterError(
                f"predict() takes runs from one pipeline; got: {sorted(app_names)}"
            )
        app_name = next(iter(app_names))

        window = recent_runs[-self.window :]
        features = extract_features(window)
        proba = float(self._model.predict_proba([features])[0][1])

        return FailurePrediction(
            app_name=app_name,
            probability=round(proba, 4),
            confidence=self._confidence_for(len(window)),
            based_on_runs=len(window),
            contributing_features=dict(self._feature_importances),
            model_version=self.MODEL_VERSION,
            predicted_at=datetime.now(UTC),
        )

    # --- internals ---------------------------------------------------------

    def _build_training_set(self, runs: list[PipelineRun]) -> tuple[list[list[float]], list[int]]:
        by_app: dict[str, list[PipelineRun]] = {}
        for r in runs:
            by_app.setdefault(r.app_name, []).append(r)

        x: list[list[float]] = []
        y: list[int] = []
        for app_runs in by_app.values():
            ordered = sorted(
                app_runs, key=lambda r: (r.started_at or datetime.min.replace(tzinfo=UTC))
            )
            for i in range(self.window, len(ordered)):
                window = ordered[i - self.window : i]
                features = extract_features(window)
                label = 1 if ordered[i].status == RunStatus.FAILED else 0
                x.append(features)
                y.append(label)
        return x, y

    def _build_model(self) -> Any:
        """Construct the underlying classifier.

        Preference order:
          1. xgboost.XGBClassifier (best quality, optional ~150MB dep)
          2. sklearn.ensemble.GradientBoostingClassifier (already in ml extra)
        """
        try:
            from xgboost import XGBClassifier

            return XGBClassifier(
                n_estimators=120,
                max_depth=4,
                learning_rate=0.1,
                random_state=42,
                eval_metric="logloss",
                use_label_encoder=False,
            )
        except ImportError:
            pass
        try:
            from sklearn.ensemble import GradientBoostingClassifier

            return GradientBoostingClassifier(
                n_estimators=120,
                max_depth=4,
                learning_rate=0.1,
                random_state=42,
            )
        except ImportError as exc:  # pragma: no cover - dep gated
            raise ForecasterError(
                "neither xgboost nor scikit-learn is installed; install "
                "dataforge with the [ml] extra."
            ) from exc

    def _extract_importances(self, model: Any) -> dict[str, float]:
        importances = getattr(model, "feature_importances_", None)
        if importances is None:
            return {}
        # Float-cast and round for stable serialization in API responses.
        return {
            name: round(float(value), 6)
            for name, value in zip(FEATURE_NAMES, importances, strict=True)
        }

    def _confidence_for(self, window_size: int) -> float:
        """A simple heuristic: more training + a full window -> higher confidence."""
        if self._trained_samples == 0:
            return 0.0
        window_factor = min(1.0, window_size / self.window)
        training_factor = min(1.0, self._trained_samples / 200.0)
        return round(0.5 * window_factor + 0.5 * training_factor, 4)
