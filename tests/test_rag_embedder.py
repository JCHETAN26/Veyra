"""Unit tests for the hashing embedder, profile, and in-memory store."""

from __future__ import annotations

import asyncio

from dataforge.contracts.incident import (
    AnomalyType,
    Incident,
    IncidentStatus,
    Severity,
)
from dataforge.contracts.rca import CauseCategory, RootCauseAnalysis
from dataforge.contracts.telemetry import (
    FailureInfo,
    PipelineRun,
    RunMetrics,
    RunStatus,
)
from dataforge.modules.rag.embedder import HashingEmbedder, cosine_similarity
from dataforge.modules.rag.profile import build_profile
from dataforge.modules.rag.vector_store import InMemoryVectorStore, StoredProfile


def _oom_run(run_id: str, app: str) -> PipelineRun:
    return PipelineRun(
        run_id=run_id,
        app_name=app,
        status=RunStatus.FAILED,
        failure=FailureInfo(error_class="java.lang.OutOfMemoryError"),
        metrics=RunMetrics(num_tasks=4, disk_spilled_bytes=500 * 1024 * 1024),
    )


def _incident(run_id: str, anomaly: AnomalyType) -> Incident:
    return Incident(
        incident_id=f"inc-{run_id}-{anomaly.value}",
        run_id=run_id,
        anomaly_type=anomaly,
        severity=Severity.CRITICAL,
        status=IncidentStatus.OPEN,
        title="t",
        description="",
    )


def _analysis(run_id: str, category: CauseCategory) -> RootCauseAnalysis:
    return RootCauseAnalysis(
        analysis_id=f"rca-{run_id}",
        run_id=run_id,
        category=category,
        summary="memory pressure",
        explanation="",
    )


def test_embedding_is_unit_normalized() -> None:
    profile = build_profile(
        _oom_run("r1", "app"),
        [_incident("r1", AnomalyType.RUN_FAILURE)],
        _analysis("r1", CauseCategory.MEMORY_PRESSURE),
    )
    vec = HashingEmbedder().embed(profile)
    norm = sum(v * v for v in vec) ** 0.5
    assert abs(norm - 1.0) < 1e-9


def test_embedding_is_deterministic() -> None:
    profile = build_profile(_oom_run("r1", "app"), [], None)
    emb = HashingEmbedder()
    assert emb.embed(profile) == emb.embed(profile)


def test_similar_failures_score_higher_than_dissimilar() -> None:
    emb = HashingEmbedder()

    oom_a = emb.embed(
        build_profile(
            _oom_run("a", "orders"),
            [_incident("a", AnomalyType.RUN_FAILURE)],
            _analysis("a", CauseCategory.MEMORY_PRESSURE),
        )
    )
    oom_b = emb.embed(
        build_profile(
            _oom_run("b", "payments"),
            [_incident("b", AnomalyType.RUN_FAILURE)],
            _analysis("b", CauseCategory.MEMORY_PRESSURE),
        )
    )
    clean = emb.embed(
        build_profile(
            PipelineRun(
                run_id="c",
                app_name="clean",
                status=RunStatus.SUCCEEDED,
                metrics=RunMetrics(num_tasks=4),
            ),
            [],
            None,
        )
    )

    sim_oom = cosine_similarity(oom_a, oom_b)
    sim_clean = cosine_similarity(oom_a, clean)
    # Two OOM failures (different apps) resemble each other far more than
    # either resembles a clean run.
    assert sim_oom > 0.5
    assert sim_oom > sim_clean


def test_in_memory_store_ranks_and_excludes() -> None:
    async def run() -> None:
        emb = HashingEmbedder()
        store = InMemoryVectorStore()
        for rid, app in [("a", "orders"), ("b", "payments")]:
            p = build_profile(
                _oom_run(rid, app),
                [_incident(rid, AnomalyType.RUN_FAILURE)],
                _analysis(rid, CauseCategory.MEMORY_PRESSURE),
            )
            await store.upsert(StoredProfile(profile=p, vector=emb.embed(p)))

        query = build_profile(_oom_run("a", "orders"), [], None)
        hits = await store.search(emb.embed(query), limit=5, exclude_run_id="a")
        assert [h.profile.run_id for h in hits] == ["b"]
        assert await store.count() == 2

    asyncio.run(run())


def test_upsert_is_idempotent_on_run_id() -> None:
    async def run() -> None:
        emb = HashingEmbedder()
        store = InMemoryVectorStore()
        p = build_profile(_oom_run("a", "orders"), [], None)
        await store.upsert(StoredProfile(profile=p, vector=emb.embed(p)))
        await store.upsert(StoredProfile(profile=p, vector=emb.embed(p)))
        assert await store.count() == 1

    asyncio.run(run())
