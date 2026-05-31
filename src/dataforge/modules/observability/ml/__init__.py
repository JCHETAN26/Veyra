"""ML-based anomaly detectors.

These layer behind the same Finding contract as the rule-based detectors,
but take a *history* of past runs as additional input — so the platform
can flag "this run is anomalous relative to your team's recent baseline,"
not just "this run trips a fixed threshold."

Three detectors ship:

  - IsolationForestDetector: sklearn unsupervised tabular anomaly detection
    on run metric vectors (spill, shuffle, failed tasks, etc).
  - TimeseriesAnomalyDetector: pure-Python z-score on per-pipeline duration
    history. No external deps; ships in the default install.
  - LogTemplateDetector: drain3-based log-template miner — flags "we've
    never seen this error message shape before in this pipeline."

The protocol stays sync because every detector here is CPU-bound. The
factory `build_ml_detectors(settings)` reads the enabled flags and returns
the active list.
"""

from __future__ import annotations

from dataforge.modules.observability.ml.detector import (
    MLDetector,
    MLDetectorError,
    run_ml_detectors,
)
from dataforge.modules.observability.ml.factory import build_ml_detectors
from dataforge.modules.observability.ml.isolation_forest import IsolationForestDetector
from dataforge.modules.observability.ml.log_template import LogTemplateDetector
from dataforge.modules.observability.ml.timeseries import TimeseriesAnomalyDetector

__all__ = [
    "IsolationForestDetector",
    "LogTemplateDetector",
    "MLDetector",
    "MLDetectorError",
    "TimeseriesAnomalyDetector",
    "build_ml_detectors",
    "run_ml_detectors",
]
