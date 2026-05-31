"""Synthetic pipeline-history generator.

Bootstraps the forecaster with believable training data when there isn't
enough real DB history yet. Also drives the forecaster's tests: the
patterns are labeled by construction, so we can assert "this 'broken'
pipeline gets P(failure) > 0.5 after training on a mix."

Four patterns, each producing a deterministic series for a given seed:

  - stable:    boring baseline. Low spill, low duration variance, ~2%
               failure rate from transient flake.
  - degrading: spill and failure rate rise monotonically with run index;
               simulates a slow regression.
  - broken:    consistent ~40% failure rate, high spill.
  - flaky:    alternates good/bad runs; ~25% failure rate.

Generated runs land in the same FailureProfile-friendly schema as real
ingested runs (no missing fields), so the forecaster's feature extractor
sees them indistinguishably from production data.
"""

from __future__ import annotations

import random  # noqa: S311 - synthetic-data generator, not security-sensitive
from datetime import UTC, datetime, timedelta
from enum import StrEnum

from dataforge.contracts.telemetry import (
    FailureInfo,
    PipelineRun,
    RunMetrics,
    RunStatus,
)


class SyntheticPattern(StrEnum):
    STABLE = "stable"
    DEGRADING = "degrading"
    BROKEN = "broken"
    FLAKY = "flaky"


_BASE_TIMESTAMP = datetime(2026, 1, 1, tzinfo=UTC)


def synthesize_pipeline_history(
    *,
    app_name: str,
    n_runs: int,
    pattern: SyntheticPattern = SyntheticPattern.STABLE,
    seed: int = 42,
    run_id_prefix: str | None = None,
) -> list[PipelineRun]:
    """Produce a deterministic synthetic history for one pipeline."""
    rng = random.Random(  # noqa: S311  # nosec B311 - synthetic-data generator, not security-sensitive
        f"{seed}:{app_name}:{pattern.value}"
    )
    prefix = run_id_prefix or f"synth-{pattern.value}-{app_name}"

    runs: list[PipelineRun] = []
    for i in range(n_runs):
        started = _BASE_TIMESTAMP + timedelta(hours=i)
        run = _generate_one(
            run_id=f"{prefix}-{i:04d}",
            app_name=app_name,
            index=i,
            n_runs=n_runs,
            pattern=pattern,
            started_at=started,
            rng=rng,
        )
        runs.append(run)
    return runs


def _generate_one(
    *,
    run_id: str,
    app_name: str,
    index: int,
    n_runs: int,
    pattern: SyntheticPattern,
    started_at: datetime,
    rng: random.Random,
) -> PipelineRun:
    progress = index / max(1, n_runs - 1)

    if pattern is SyntheticPattern.STABLE:
        fail_prob = 0.02
        spill_mb = rng.randint(0, 8)
        duration_ms = rng.randint(580_000, 620_000)
    elif pattern is SyntheticPattern.DEGRADING:
        # Smoothly climbs from 2% to 60% over the series.
        fail_prob = 0.02 + 0.58 * progress
        spill_mb = int(8 + 200 * progress + rng.randint(-5, 5))
        duration_ms = int(600_000 + 400_000 * progress + rng.randint(-20_000, 20_000))
    elif pattern is SyntheticPattern.BROKEN:
        fail_prob = 0.4
        spill_mb = rng.randint(50, 250)
        duration_ms = rng.randint(800_000, 1_500_000)
    else:  # FLAKY
        fail_prob = 0.25
        spill_mb = rng.randint(0, 30)
        duration_ms = rng.randint(550_000, 700_000)

    failed = rng.random() < fail_prob
    status = RunStatus.FAILED if failed else RunStatus.SUCCEEDED

    failure: FailureInfo | None = None
    if failed:
        # Bias toward OOM in degrading/broken, generic exception in flaky/stable.
        if pattern in (SyntheticPattern.DEGRADING, SyntheticPattern.BROKEN):
            failure = FailureInfo(
                error_class="java.lang.OutOfMemoryError",
                message="Java heap space",
            )
        else:
            failure = FailureInfo(
                error_class="java.lang.RuntimeException",
                message="transient failure",
            )

    duration_ms = max(duration_ms, 1)
    return PipelineRun(
        run_id=run_id,
        app_name=app_name,
        source="synthetic",
        status=status,
        started_at=started_at,
        completed_at=started_at + timedelta(milliseconds=duration_ms),
        duration_ms=duration_ms,
        metrics=RunMetrics(
            num_jobs=1,
            num_stages=1,
            num_tasks=10,
            num_failed_tasks=rng.randint(0, 2) if failed else 0,
            executor_run_time_ms=duration_ms // 2,
            shuffle_read_bytes=32 * 1024 * 1024 + rng.randint(0, 32 * 1024 * 1024),
            shuffle_write_bytes=16 * 1024 * 1024 + rng.randint(0, 16 * 1024 * 1024),
            memory_spilled_bytes=spill_mb * 1024 * 1024 // 2,
            disk_spilled_bytes=spill_mb * 1024 * 1024 // 2,
        ),
        failure=failure,
    )
