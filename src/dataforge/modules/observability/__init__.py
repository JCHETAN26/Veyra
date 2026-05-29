"""Observability module.

Anomaly detection, metric aggregation, health scoring and incident generation
over ingested pipeline telemetry. Entry point of the self-healing loop.
"""

from dataforge.modules.observability.module import module

__all__ = ["module"]
