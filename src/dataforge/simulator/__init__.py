"""Spark pipeline simulator + chaos injector.

Generates realistic Spark event-log JSONL for a curated set of failure
scenarios (OOM, data skew, flaky executors, long duration, schema drift,
dependency failure) and a healthy baseline. The output is the same format
Spark's EventLoggingListener emits, so it flows straight into the existing
ingestion parser without a separate code path.

Demo-driving rather than chaos-engineering in the formal sense: each
scenario is parameterized and deterministic so a recorded demo replays
the same failure every time. A real-Spark mode (PySpark + NYC Taxi)
layers in later behind the same scenario interface.
"""

from __future__ import annotations

from dataforge.simulator.scenarios import (
    SCENARIOS,
    Scenario,
    build_scenario,
    events_to_jsonl,
)

__all__ = ["SCENARIOS", "Scenario", "build_scenario", "events_to_jsonl"]
