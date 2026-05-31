"""Predictive forecast contracts.

The failure forecaster turns historical run telemetry into a forward-
looking probability that the *next* run of a given pipeline will fail.
This is the "shift from reactive to proactive" surface the platform
exposes alongside the detect-explain-remediate loop.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class FailurePrediction(BaseModel):
    """A single forecast for one pipeline."""

    app_name: str
    probability: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="P(next run of this pipeline fails); 0 = safe, 1 = certain failure.",
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description=(
            "Heuristic confidence in the prediction itself: low when the "
            "window is short or the training set was small."
        ),
    )
    based_on_runs: int = Field(
        ..., ge=0, description="How many prior runs of this pipeline went in."
    )
    contributing_features: dict[str, float] = Field(
        default_factory=dict,
        description=(
            "Feature -> importance (from the trained model). Surfaces the "
            "drivers behind the prediction to humans."
        ),
    )
    model_version: str = "gbt-forecaster-v1"
    predicted_at: datetime | None = None


class TrainingResult(BaseModel):
    """Summary returned by FailureForecaster.fit, useful for the audit log."""

    samples: int = Field(..., ge=0)
    positive_samples: int = Field(..., ge=0)
    feature_importances: dict[str, float] = Field(default_factory=dict)
    model_version: str = "gbt-forecaster-v1"
    trained_at: datetime | None = None
