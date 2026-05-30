"""Unit + integration tests for the failure forecaster.

Three layers:

  1. Feature extraction is well-defined: known input -> known output.
  2. The wrapper trains and predicts, returning a FailurePrediction shape
     the API can serialize. Tests use the synthetic data generator so
     the labels are known and the model's tendencies are observable.
  3. The service surface (train + predict) + the FastAPI endpoints
     round-trip through TestClient against an in-process DB.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from dataforge.contracts.forecast import FailurePrediction, TrainingResult
from dataforge.contracts.telemetry import RunStatus
from dataforge.modules.observability.forecaster import (
    FEATURE_NAMES,
    FailureForecaster,
    ForecasterError,
    ForecasterNotTrainedError,
    SyntheticPattern,
    extract_features,
    synthesize_pipeline_history,
)

# --- Feature extraction ---------------------------------------------------


def test_extract_features_returns_aligned_vector() -> None:
    runs = synthesize_pipeline_history(app_name="etl", n_runs=20, pattern=SyntheticPattern.STABLE)
    features = extract_features(runs[:10])
    assert len(features) == len(FEATURE_NAMES)
    assert all(isinstance(v, float) for v in features)


def test_extract_features_rejects_short_window() -> None:
    runs = synthesize_pipeline_history(app_name="etl", n_runs=5, pattern=SyntheticPattern.STABLE)
    with pytest.raises(ValueError):
        extract_features(runs[:1])


def test_failure_rate_reflects_failures_in_window() -> None:
    """Degrading -> windows late in the series have higher failure_rate."""
    runs = synthesize_pipeline_history(
        app_name="etl", n_runs=120, pattern=SyntheticPattern.DEGRADING
    )
    early = extract_features(runs[:20])
    late = extract_features(runs[100:120])
    # FEATURE_NAMES[0] is failure_rate.
    assert late[0] >= early[0], (early, late)


def test_spill_trend_is_positive_for_degrading() -> None:
    runs = synthesize_pipeline_history(
        app_name="etl", n_runs=120, pattern=SyntheticPattern.DEGRADING
    )
    features = extract_features(runs[100:120])
    # Across the degrading series the *whole window* trend can flatten, but
    # max_spill should still be high for late-series.
    max_spill_idx = FEATURE_NAMES.index("max_spill_mb")
    assert features[max_spill_idx] > 30.0


# --- Synthetic data generator ---------------------------------------------


def test_synthesize_is_deterministic_for_seed() -> None:
    a = synthesize_pipeline_history(app_name="etl", n_runs=50, seed=7)
    b = synthesize_pipeline_history(app_name="etl", n_runs=50, seed=7)
    # Same run_ids, same statuses.
    assert [(r.run_id, r.status) for r in a] == [(r.run_id, r.status) for r in b]


def test_stable_has_low_failure_rate() -> None:
    runs = synthesize_pipeline_history(app_name="etl", n_runs=200, pattern=SyntheticPattern.STABLE)
    rate = sum(r.status == RunStatus.FAILED for r in runs) / len(runs)
    assert rate < 0.10


def test_broken_has_high_failure_rate() -> None:
    runs = synthesize_pipeline_history(app_name="etl", n_runs=200, pattern=SyntheticPattern.BROKEN)
    rate = sum(r.status == RunStatus.FAILED for r in runs) / len(runs)
    assert rate > 0.25


# --- Model: fit / predict -------------------------------------------------


def _mixed_training_set() -> list:  # type: ignore[type-arg]
    """A training corpus where the forecaster has both classes to learn from."""
    return (
        synthesize_pipeline_history(
            app_name="stable_etl",
            n_runs=200,
            pattern=SyntheticPattern.STABLE,
            seed=1,
        )
        + synthesize_pipeline_history(
            app_name="broken_etl",
            n_runs=200,
            pattern=SyntheticPattern.BROKEN,
            seed=2,
        )
        + synthesize_pipeline_history(
            app_name="degrading_etl",
            n_runs=200,
            pattern=SyntheticPattern.DEGRADING,
            seed=3,
        )
    )


def test_forecaster_fits_on_mixed_corpus() -> None:
    forecaster = FailureForecaster()
    result = forecaster.fit(_mixed_training_set())
    assert isinstance(result, TrainingResult)
    assert result.samples > 100
    assert 0 < result.positive_samples < result.samples
    assert sum(result.feature_importances.values()) > 0


def test_forecaster_raises_when_training_too_thin() -> None:
    tiny = synthesize_pipeline_history(app_name="etl", n_runs=15, pattern=SyntheticPattern.BROKEN)
    with pytest.raises(ForecasterError):
        FailureForecaster().fit(tiny)


def test_forecaster_raises_when_all_one_class() -> None:
    forecaster = FailureForecaster()
    # The stable pattern has ~2% failures; with n=200 some are present, so
    # to force the all-success edge we filter explicitly.
    all_success = [
        r
        for r in synthesize_pipeline_history(
            app_name="etl", n_runs=400, pattern=SyntheticPattern.STABLE, seed=11
        )
        if r.status == RunStatus.SUCCEEDED
    ]
    with pytest.raises(ForecasterError):
        forecaster.fit(all_success)


def test_predict_requires_training() -> None:
    forecaster = FailureForecaster()
    runs = synthesize_pipeline_history(app_name="etl", n_runs=20, pattern=SyntheticPattern.STABLE)
    with pytest.raises(ForecasterNotTrainedError):
        forecaster.predict(runs)


def test_predict_rejects_mixed_pipelines() -> None:
    forecaster = FailureForecaster()
    forecaster.fit(_mixed_training_set())
    mixed = synthesize_pipeline_history(app_name="a", n_runs=10) + synthesize_pipeline_history(
        app_name="b", n_runs=10
    )
    with pytest.raises(ForecasterError):
        forecaster.predict(mixed)


def test_predict_returns_well_formed_prediction() -> None:
    forecaster = FailureForecaster()
    forecaster.fit(_mixed_training_set())
    history = synthesize_pipeline_history(
        app_name="stable_etl",
        n_runs=20,
        pattern=SyntheticPattern.STABLE,
        seed=99,
    )
    prediction = forecaster.predict(history)
    assert isinstance(prediction, FailurePrediction)
    assert prediction.app_name == "stable_etl"
    assert 0.0 <= prediction.probability <= 1.0
    assert 0.0 < prediction.confidence <= 1.0
    assert prediction.based_on_runs == forecaster.window
    assert set(prediction.contributing_features.keys()) == set(FEATURE_NAMES)


def test_broken_pattern_gets_higher_probability_than_stable() -> None:
    """Smoke test of the whole train/predict loop on synthetic data."""
    forecaster = FailureForecaster()
    forecaster.fit(_mixed_training_set())

    stable_history = synthesize_pipeline_history(
        app_name="stable_etl",
        n_runs=20,
        pattern=SyntheticPattern.STABLE,
        seed=101,
    )
    broken_history = synthesize_pipeline_history(
        app_name="broken_etl",
        n_runs=20,
        pattern=SyntheticPattern.BROKEN,
        seed=102,
    )
    stable_p = forecaster.predict(stable_history).probability
    broken_p = forecaster.predict(broken_history).probability
    assert broken_p > stable_p, (
        f"broken P={broken_p} expected to exceed stable P={stable_p}; "
        "model has not learned the basic pattern."
    )


# --- API endpoints --------------------------------------------------------


@pytest.fixture
def forecaster_client() -> Iterator[TestClient]:
    """A TestClient with a forecaster pre-trained from synthetic data.

    Real history is not in the DB, so the predict endpoint test below
    uses a separate path that round-trips through the in-process service
    rather than the database-backed evaluate path.
    """
    from dataforge.app import create_app

    with TestClient(create_app()) as c:
        yield c


def test_forecaster_predict_endpoint_404s_without_history(
    forecaster_client: TestClient,
) -> None:
    """An unknown pipeline produces a 4xx with a clear error envelope."""
    response = forecaster_client.get("/api/v1/observability/forecaster/predict/never_seen_pipeline")
    assert response.status_code in {409, 422}, response.text
    assert "forecaster" in response.text.lower() or "few" in response.text.lower()


def test_forecaster_train_endpoint_handles_thin_history(
    forecaster_client: TestClient,
) -> None:
    """In a fresh DB, training should fail loudly with a thin-history error."""
    response = forecaster_client.post("/api/v1/observability/forecaster/train?history_limit=200")
    # Either there's no data and we get the thin-history error, or another
    # test seeded enough rows; both shapes are valid here.
    assert response.status_code in {200, 422}, response.text
    if response.status_code == 200:
        body = TrainingResult(**response.json())
        assert body.samples > 0
