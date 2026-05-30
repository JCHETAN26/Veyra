"""ML detector factory.

`build_ml_detectors(settings)` returns the list of detectors to run for
this process. When `ml_detectors_enabled=false` (the default), it returns
an empty list — the platform stays on the deterministic detectors only.

The factory validates optional deps eagerly so misconfiguration fails at
startup, not at the first evaluation.
"""

from __future__ import annotations

from dataforge.core.config import Settings, get_settings
from dataforge.modules.observability.ml.detector import (
    MLDetector,
    MLDetectorError,
)
from dataforge.modules.observability.ml.isolation_forest import IsolationForestDetector
from dataforge.modules.observability.ml.log_template import LogTemplateDetector
from dataforge.modules.observability.ml.timeseries import TimeseriesAnomalyDetector


def build_ml_detectors(settings: Settings | None = None) -> list[MLDetector]:
    """Return the active ML detectors based on settings."""
    cfg = settings or get_settings()
    if not cfg.ml_detectors_enabled:
        return []

    detectors: list[MLDetector] = []

    if cfg.ml_detector_isolation_forest:
        _require("scikit-learn", "sklearn")
        detectors.append(IsolationForestDetector())

    if cfg.ml_detector_timeseries:
        # Pure Python — no dep gating required.
        detectors.append(TimeseriesAnomalyDetector())

    if cfg.ml_detector_log_template:
        _require("drain3", "drain3")
        detectors.append(LogTemplateDetector())

    return detectors


def _require(pretty_name: str, import_name: str) -> None:
    """Fail-fast: confirm the optional dep is importable at factory time."""
    try:
        __import__(import_name)
    except ImportError as exc:
        raise MLDetectorError(
            f"{pretty_name} not installed. Run `uv sync --extra ml` to "
            "enable the ML detectors, or disable the corresponding "
            "DATAFORGE_ML_DETECTOR_* flag."
        ) from exc
