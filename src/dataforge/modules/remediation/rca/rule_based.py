"""Rule-based root-cause analyzer (MVP).

Deterministic mapping from failure signatures to a structured explanation.
Rules are ordered by specificity; the first matching rule wins, so the most
specific known cause is reported. Each rule sets a fixed confidence, so the
same run always yields the same analysis — important for testability and for
remediation to trust the output.

This is intentionally explainable rather than clever. An LLM-backed analyzer
implementing the same interface can layer in later for the long-tail cases the
rules classify as UNKNOWN.
"""

from __future__ import annotations

from collections.abc import Callable

from dataforge.contracts.incident import AnomalyType, Incident
from dataforge.contracts.rca import (
    CauseCategory,
    RecommendedAction,
    RootCauseAnalysis,
)
from dataforge.contracts.telemetry import PipelineRun, RunStatus


class _Signature:
    """Lightweight view over a run + its incidents for rule matching."""

    def __init__(self, run: PipelineRun, incidents: list[Incident]) -> None:
        self.run = run
        self.incidents = incidents
        self.incident_types = {i.anomaly_type for i in incidents}
        self.error_class = run.failure.error_class if run.failure else None
        self.total_spill = run.metrics.memory_spilled_bytes + run.metrics.disk_spilled_bytes
        total_tasks = run.metrics.num_tasks or 0
        self.failed_ratio = run.metrics.num_failed_tasks / total_tasks if total_tasks else 0.0


# A rule returns a RootCauseAnalysis (sans id/timestamp) if it matches, else None.
_RuleResult = tuple[CauseCategory, str, str, list[str], list[RecommendedAction], float]
_Rule = Callable[[_Signature], "_RuleResult | None"]


def _rule_oom(sig: _Signature) -> _RuleResult | None:
    is_oom = bool(sig.error_class and "OutOfMemory" in sig.error_class)
    if not is_oom:
        return None
    factors = [f"Failure error class: {sig.error_class}"]
    if sig.total_spill > 0:
        factors.append(f"{sig.total_spill:,} bytes spilled to memory/disk")
    if AnomalyType.EXCESSIVE_SPILL in sig.incident_types:
        factors.append("Excessive-spill anomaly was also raised for this run")
    actions = [
        RecommendedAction(
            title="Reduce per-task memory pressure",
            detail=(
                "Increase shuffle partitions to shrink partition size, e.g. "
                "set spark.sql.shuffle.partitions higher than the default."
            ),
            kind="spark_conf",
        ),
        RecommendedAction(
            title="Broadcast the smaller side of the join",
            detail=(
                "If a large join is driving the spill, broadcasting the small "
                "table avoids the expensive shuffle. Tune "
                "spark.sql.autoBroadcastJoinThreshold."
            ),
            kind="spark_conf",
        ),
    ]
    return (
        CauseCategory.MEMORY_PRESSURE,
        "Run ran out of memory, likely from a skewed or oversized shuffle.",
        (
            "The job failed with an OutOfMemoryError"
            + (f" after spilling {sig.total_spill:,} bytes" if sig.total_spill > 0 else "")
            + ". This pattern typically indicates memory pressure from a large "
            "or skewed join/aggregation where partitions exceed executor memory."
        ),
        factors,
        actions,
        0.85,
    )


def _rule_skew_spill(sig: _Signature) -> _RuleResult | None:
    # Heavy spill without an OOM -> likely skew/memory pressure short of failure.
    if sig.total_spill <= 0 or AnomalyType.EXCESSIVE_SPILL not in sig.incident_types:
        return None
    return (
        CauseCategory.DATA_SKEW,
        "Heavy spill suggests data skew or undersized partitions.",
        (
            f"The run spilled {sig.total_spill:,} bytes to memory/disk without "
            "failing outright. Sustained spill at this level usually points to "
            "skewed keys concentrating data into a few partitions, or partitions "
            "that are simply too large for available executor memory."
        ),
        [f"{sig.total_spill:,} bytes spilled", "Excessive-spill anomaly raised"],
        [
            RecommendedAction(
                title="Repartition on a higher-cardinality key",
                detail=(
                    "Skew concentrates rows into few partitions. Repartitioning "
                    "or salting the skewed key spreads the load."
                ),
                kind="code_change",
            ),
            RecommendedAction(
                title="Increase shuffle partitions",
                detail="Raise spark.sql.shuffle.partitions to reduce partition size.",
                kind="spark_conf",
            ),
        ],
        0.7,
    )


def _rule_flaky_tasks(sig: _Signature) -> _RuleResult | None:
    # Failed tasks but the run still succeeded -> transient/flaky execution.
    if (
        sig.run.status != RunStatus.SUCCEEDED
        or AnomalyType.HIGH_FAILED_TASK_RATIO not in sig.incident_types
    ):
        return None
    return (
        CauseCategory.TRANSIENT_FAILURE,
        "Elevated task failures despite overall success suggest transient issues.",
        (
            f"{sig.run.metrics.num_failed_tasks} of {sig.run.metrics.num_tasks} "
            "tasks failed but Spark retried them to a successful run. This "
            "usually reflects transient conditions (executor loss, network "
            "blips, spot reclaims) rather than a code defect."
        ),
        [f"Failed-task ratio: {sig.failed_ratio:.0%}"],
        [
            RecommendedAction(
                title="Investigate executor stability",
                detail=(
                    "Check for executor loss / spot reclamation in the cluster "
                    "event log; consider on-demand executors for critical runs."
                ),
                kind="manual",
            )
        ],
        0.6,
    )


def _rule_long_duration(sig: _Signature) -> _RuleResult | None:
    if AnomalyType.LONG_DURATION not in sig.incident_types:
        return None
    return (
        CauseCategory.PERFORMANCE_REGRESSION,
        "Run took unusually long; possible performance regression.",
        (
            f"The run ran for {sig.run.duration_ms:,} ms, beyond the expected "
            "envelope. Causes range from data-volume growth to an inefficient "
            "plan (missing broadcast, excessive shuffle) or resource starvation."
        ),
        ["Long-duration anomaly raised"],
        [
            RecommendedAction(
                title="Review the query plan and input volume",
                detail=(
                    "Compare input sizes and the physical plan against a healthy "
                    "run to isolate whether it's data growth or a plan change."
                ),
                kind="manual",
            )
        ],
        0.55,
    )


def _rule_generic_failure(sig: _Signature) -> _RuleResult | None:
    if sig.run.status != RunStatus.FAILED:
        return None
    msg = sig.run.failure.message if sig.run.failure else ""
    return (
        CauseCategory.UNKNOWN,
        "Run failed; root cause not matched by a known signature.",
        (
            "The run failed but its signature did not match a known cause. "
            + (f"Reported error: {msg[:300]}" if msg else "No error detail captured.")
        ),
        [f"Error class: {sig.error_class}"] if sig.error_class else [],
        [
            RecommendedAction(
                title="Inspect the full stack trace and stage logs",
                detail="Manual triage required; consider adding a detection rule.",
                kind="manual",
            )
        ],
        0.3,
    )


# Ordered most-specific first; first match wins.
_RULES: list[_Rule] = [
    _rule_oom,
    _rule_skew_spill,
    _rule_flaky_tasks,
    _rule_long_duration,
    _rule_generic_failure,
]


class RuleBasedAnalyzer:
    """Deterministic, explainable root-cause analyzer."""

    name = "rule-based-v1"

    async def analyze(self, run: PipelineRun, incidents: list[Incident]) -> RootCauseAnalysis:
        sig = _Signature(run, incidents)
        incident_ids = [i.incident_id for i in incidents]

        for rule in _RULES:
            result = rule(sig)
            if result is not None:
                category, summary, explanation, factors, actions, confidence = result
                return RootCauseAnalysis(
                    analysis_id=f"rca-{run.run_id}",
                    run_id=run.run_id,
                    category=category,
                    summary=summary,
                    explanation=explanation,
                    contributing_factors=factors,
                    recommended_actions=actions,
                    confidence=confidence,
                    incident_ids=incident_ids,
                    analyzer=self.name,
                )

        # No rule fired and the run didn't fail -> nothing to explain.
        return RootCauseAnalysis(
            analysis_id=f"rca-{run.run_id}",
            run_id=run.run_id,
            category=CauseCategory.UNKNOWN,
            summary="No anomaly requiring root-cause analysis.",
            explanation="The run completed without a detectable problem.",
            confidence=0.0,
            incident_ids=incident_ids,
            analyzer=self.name,
        )
