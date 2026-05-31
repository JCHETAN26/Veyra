"""Failure forecaster.

Predictive layer on top of the deterministic + ML anomaly detectors.
Trains a gradient-boosted classifier over rolling-window features derived
from a pipeline's recent runs and produces `FailurePrediction` rows
("P(next run fails) = 0.73; mainly because spill is trending up and
failure rate is 12%").

The wrapper accepts XGBoost transparently when installed — the fit /
predict_proba API is identical — but defaults to sklearn's
GradientBoostingClassifier so the `ml` extra alone is sufficient.
"""

from __future__ import annotations

from dataforge.modules.observability.forecaster.features import (
    FEATURE_NAMES,
    extract_features,
)
from dataforge.modules.observability.forecaster.model import (
    FailureForecaster,
    ForecasterError,
    ForecasterNotTrainedError,
)
from dataforge.modules.observability.forecaster.synthetic import (
    SyntheticPattern,
    synthesize_pipeline_history,
)

__all__ = [
    "FEATURE_NAMES",
    "FailureForecaster",
    "ForecasterError",
    "ForecasterNotTrainedError",
    "SyntheticPattern",
    "extract_features",
    "synthesize_pipeline_history",
]
