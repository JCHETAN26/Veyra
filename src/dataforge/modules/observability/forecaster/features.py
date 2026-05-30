"""Feature extraction for the failure forecaster.

Given a window of recent runs for a single pipeline (oldest-first), we
emit a fixed-length feature vector. Features are kept simple and
interpretable so SHAP-like importances translate cleanly into "why"
explanations on the prediction surface.

The window must be at least 2 runs long for the slope (trend) features
to be well-defined. Callers gate on `min_window`; this module fails
loudly if invariants are violated rather than silently producing a
degenerate vector.
"""

from __future__ import annotations

from dataforge.contracts.telemetry import PipelineRun, RunStatus

# Feature order is part of the contract: the model is fit on this exact
# layout, so reordering is a versioning concern, not a refactor.
FEATURE_NAMES: tuple[str, ...] = (
    "failure_rate",
    "recent_failure_rate",
    "mean_spill_mb",
    "max_spill_mb",
    "spill_trend",
    "mean_duration_ms",
    "duration_trend",
    "mean_failed_task_ratio",
    "recent_oom_count",
    "window_size",
)


def extract_features(window: list[PipelineRun]) -> list[float]:
    """Build the feature vector for one prediction window.

    Args:
        window: runs from one pipeline, oldest first. Length must be >= 2.

    Returns:
        Fixed-length list[float] aligned with FEATURE_NAMES.
    """
    if len(window) < 2:
        raise ValueError(f"feature extraction needs at least 2 runs; got {len(window)}")

    n = len(window)
    spills_mb = [_spill_mb(r) for r in window]
    durations = [float(r.duration_ms) if r.duration_ms is not None else 0.0 for r in window]
    failed_ratios = [_failed_ratio(r) for r in window]

    failure_rate = sum(r.status == RunStatus.FAILED for r in window) / n
    # "Recent" = last quarter of the window; falls back to the last run.
    tail = max(1, n // 4)
    recent_failures = sum(r.status == RunStatus.FAILED for r in window[-tail:])
    recent_failure_rate = recent_failures / tail

    return [
        failure_rate,
        recent_failure_rate,
        sum(spills_mb) / n,
        max(spills_mb),
        _slope(spills_mb),
        sum(durations) / n,
        _slope(durations),
        sum(failed_ratios) / n,
        float(sum(1 for r in window if _is_oom(r))),
        float(n),
    ]


def _spill_mb(run: PipelineRun) -> float:
    total = run.metrics.memory_spilled_bytes + run.metrics.disk_spilled_bytes
    return total / (1024.0 * 1024.0)


def _failed_ratio(run: PipelineRun) -> float:
    total = run.metrics.num_tasks
    if total <= 0:
        return 0.0
    return run.metrics.num_failed_tasks / total


def _is_oom(run: PipelineRun) -> bool:
    if run.failure is None or run.failure.error_class is None:
        return False
    return "OutOfMemory" in run.failure.error_class


def _slope(values: list[float]) -> float:
    """Least-squares slope of values over index 0..n-1.

    Pure Python implementation so feature extraction itself has no numpy
    dependency. Returns 0 when the input is too short or has zero variance
    along the x-axis (impossible for evenly-spaced indices but the guard
    keeps the function total).
    """
    n = len(values)
    if n < 2:
        return 0.0
    mean_x = (n - 1) / 2.0
    mean_y = sum(values) / n
    num = sum((i - mean_x) * (y - mean_y) for i, y in enumerate(values))
    den = sum((i - mean_x) ** 2 for i in range(n))
    if den == 0:
        return 0.0
    return num / den
