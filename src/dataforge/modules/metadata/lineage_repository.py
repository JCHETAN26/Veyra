"""Lineage repository.

Typed persistence port for the lineage graph: register declared job lineage,
fetch neighbours, and compute blast radius (downstream reachability).

Traversal is breadth-first with a visited set (cycle-safe) and a hard node cap
(so a pathological graph can't run unbounded). Edge upserts are idempotent on
(upstream, downstream, job_name).
"""

from __future__ import annotations

from collections import deque

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dataforge.contracts.lineage import (
    BlastRadius,
    Dataset,
    DatasetKind,
    ImpactedDataset,
    JobLineage,
    LineageEdge,
    LineageNeighbors,
)
from dataforge.core.logging import get_logger
from dataforge.modules.metadata.models import DatasetRow, LineageEdgeRow

logger = get_logger(__name__)

# Safety cap on how many nodes a single traversal will visit.
_MAX_TRAVERSAL_NODES = 10_000


class LineageRepository:
    """Async repository over the dataset/lineage-edge graph."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def register_job_lineage(self, lineage: JobLineage) -> int:
        """Create nodes for inputs/outputs and an edge from each input to each
        output. Returns the number of edges created or already present.
        """
        await self._ensure_datasets(lineage.inputs, lineage.input_kind)
        await self._ensure_datasets(lineage.outputs, lineage.output_kind)

        edge_count = 0
        for upstream in lineage.inputs:
            for downstream in lineage.outputs:
                if upstream == downstream:
                    continue  # no self-loops
                await self._upsert_edge(
                    LineageEdge(
                        upstream=upstream,
                        downstream=downstream,
                        job_name=lineage.job_name,
                        run_id=lineage.run_id,
                    )
                )
                edge_count += 1

        await self._session.flush()
        logger.info(
            "lineage.registered",
            job_name=lineage.job_name,
            inputs=len(lineage.inputs),
            outputs=len(lineage.outputs),
            edges=edge_count,
        )
        return edge_count

    async def get_dataset(self, name: str) -> Dataset | None:
        row = await self._session.get(DatasetRow, name)
        if row is None:
            return None
        return Dataset(name=row.name, kind=DatasetKind(row.kind), first_seen=row.first_seen)

    async def neighbors(self, dataset: str, *, direction: str) -> LineageNeighbors:
        """Return direct (depth-1) neighbours in the given direction."""
        if direction == "downstream":
            stmt = select(LineageEdgeRow.downstream).where(LineageEdgeRow.upstream == dataset)
        else:
            stmt = select(LineageEdgeRow.upstream).where(LineageEdgeRow.downstream == dataset)
        rows = (await self._session.execute(stmt)).scalars().all()
        unique = sorted(set(rows))
        return LineageNeighbors(
            dataset=dataset,
            direction=direction,
            neighbors=[ImpactedDataset(name=n, depth=1) for n in unique],
        )

    async def blast_radius(self, roots: list[str]) -> BlastRadius:
        """Compute all datasets downstream of the given roots (BFS)."""
        adjacency = await self._downstream_adjacency()

        visited: dict[str, int] = {}
        queue: deque[tuple[str, int]] = deque((r, 0) for r in roots)
        seen_roots = set(roots)
        truncated = False

        while queue:
            node, depth = queue.popleft()
            for child in adjacency.get(node, ()):  # children = downstream
                if child in seen_roots:
                    continue  # don't report a root as its own impact
                existing = visited.get(child)
                if existing is None or depth + 1 < existing:
                    visited[child] = depth + 1
                    if len(visited) >= _MAX_TRAVERSAL_NODES:
                        truncated = True
                        queue.clear()
                        break
                    queue.append((child, depth + 1))

        impacted = sorted(
            (ImpactedDataset(name=n, depth=d) for n, d in visited.items()),
            key=lambda i: (i.depth, i.name),
        )
        return BlastRadius(roots=roots, impacted=impacted, truncated=truncated)

    async def outputs_for_run(self, run_id: str) -> list[str]:
        """Return datasets produced by a run (downstream of edges it created)."""
        stmt = select(LineageEdgeRow.downstream).where(LineageEdgeRow.run_id == run_id)
        rows = (await self._session.execute(stmt)).scalars().all()
        return sorted(set(rows))

    # --- internals -------------------------------------------------------
    async def _ensure_datasets(self, names: list[str], kind: DatasetKind) -> None:
        for name in names:
            existing = await self._session.get(DatasetRow, name)
            if existing is None:
                self._session.add(DatasetRow(name=name, kind=kind.value))
        await self._session.flush()

    async def _upsert_edge(self, edge: LineageEdge) -> None:
        stmt = select(LineageEdgeRow).where(
            LineageEdgeRow.upstream == edge.upstream,
            LineageEdgeRow.downstream == edge.downstream,
            LineageEdgeRow.job_name == edge.job_name,
        )
        existing = (await self._session.execute(stmt)).scalar_one_or_none()
        if existing is None:
            self._session.add(
                LineageEdgeRow(
                    upstream=edge.upstream,
                    downstream=edge.downstream,
                    job_name=edge.job_name,
                    run_id=edge.run_id,
                )
            )
        elif edge.run_id is not None:
            existing.run_id = edge.run_id  # keep the latest producing run

    async def _downstream_adjacency(self) -> dict[str, list[str]]:
        """Load the whole edge set into an upstream -> [downstream] map.

        Fine at MVP scale; a recursive CTE replaces this if the graph grows.
        """
        rows = (
            await self._session.execute(select(LineageEdgeRow.upstream, LineageEdgeRow.downstream))
        ).all()
        adjacency: dict[str, list[str]] = {}
        for upstream, downstream in rows:
            adjacency.setdefault(upstream, []).append(downstream)
        return adjacency
