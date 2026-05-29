"""Ingestion module.

Consumes pipeline/Spark events (Redpanda) and normalizes them into canonical
telemetry written to the metadata store + Bronze layer. Anchored on the Spark
event-log format so the same ingestion path works against real Databricks
later (see the fidelity discussion deferred in the build plan).
"""

from dataforge.modules.ingestion.module import module

__all__ = ["module"]
