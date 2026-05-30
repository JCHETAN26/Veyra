"""Unit tests for the lineage graph repository (blast radius, traversal)."""

from __future__ import annotations

import pytest

from dataforge.contracts.lineage import JobLineage
from dataforge.modules.metadata.lineage_repository import LineageRepository


@pytest.fixture
def repo(db_session: object) -> LineageRepository:
    from sqlalchemy.ext.asyncio import AsyncSession

    assert isinstance(db_session, AsyncSession)
    return LineageRepository(db_session)


async def _register(
    repo: LineageRepository,
    job: str,
    inputs: list[str],
    outputs: list[str],
    run_id: str | None = None,
) -> int:
    return await repo.register_job_lineage(
        JobLineage(job_name=job, run_id=run_id, inputs=inputs, outputs=outputs)
    )


async def test_register_creates_edges(repo: LineageRepository) -> None:
    n = await _register(repo, "etl", ["raw_orders"], ["clean_orders"])
    assert n == 1
    nb = await repo.neighbors("raw_orders", direction="downstream")
    assert [x.name for x in nb.neighbors] == ["clean_orders"]


async def test_fan_out_edges(repo: LineageRepository) -> None:
    n = await _register(repo, "etl", ["src"], ["a", "b", "c"])
    assert n == 3
    nb = await repo.neighbors("src", direction="downstream")
    assert {x.name for x in nb.neighbors} == {"a", "b", "c"}


async def test_register_is_idempotent(repo: LineageRepository) -> None:
    await _register(repo, "etl", ["src"], ["dst"])
    await _register(repo, "etl", ["src"], ["dst"])
    nb = await repo.neighbors("src", direction="downstream")
    assert len(nb.neighbors) == 1  # no duplicate edge


async def test_blast_radius_multi_hop(repo: LineageRepository) -> None:
    # raw -> clean -> agg -> dashboard
    await _register(repo, "j1", ["raw"], ["clean"])
    await _register(repo, "j2", ["clean"], ["agg"])
    await _register(repo, "j3", ["agg"], ["dashboard"])

    blast = await repo.blast_radius(["raw"])
    impacted = {i.name: i.depth for i in blast.impacted}
    assert impacted == {"clean": 1, "agg": 2, "dashboard": 3}
    assert blast.count == 3
    assert not blast.truncated


async def test_blast_radius_diamond(repo: LineageRepository) -> None:
    # raw -> {a, b} -> merged ; merged reachable via two paths, shortest depth.
    await _register(repo, "j1", ["raw"], ["a", "b"])
    await _register(repo, "j2", ["a"], ["merged"])
    await _register(repo, "j3", ["b"], ["merged"])

    blast = await repo.blast_radius(["raw"])
    impacted = {i.name: i.depth for i in blast.impacted}
    assert impacted == {"a": 1, "b": 1, "merged": 2}


async def test_blast_radius_handles_cycles(repo: LineageRepository) -> None:
    # a -> b -> c -> a (cycle); traversal must terminate.
    await _register(repo, "j1", ["a"], ["b"])
    await _register(repo, "j2", ["b"], ["c"])
    await _register(repo, "j3", ["c"], ["a"])

    blast = await repo.blast_radius(["a"])
    # b and c are downstream; a is the root, not reported as its own impact.
    names = {i.name for i in blast.impacted}
    assert names == {"b", "c"}


async def test_upstream_neighbors(repo: LineageRepository) -> None:
    await _register(repo, "j1", ["raw"], ["clean"])
    nb = await repo.neighbors("clean", direction="upstream")
    assert [x.name for x in nb.neighbors] == ["raw"]


async def test_outputs_for_run(repo: LineageRepository) -> None:
    await _register(repo, "etl", ["raw"], ["out1", "out2"], run_id="run-x")
    outputs = await repo.outputs_for_run("run-x")
    assert outputs == ["out1", "out2"]


async def test_blast_radius_empty_for_leaf(repo: LineageRepository) -> None:
    await _register(repo, "j1", ["raw"], ["leaf"])
    blast = await repo.blast_radius(["leaf"])
    assert blast.count == 0
