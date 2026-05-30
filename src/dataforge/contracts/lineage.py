"""Data lineage contracts.

The lineage graph maps how datasets depend on each other: which jobs read which
inputs and produce which outputs. It powers two things in the self-healing loop:

- **Blast radius** — when a run fails, what's downstream and therefore at risk.
- **Upstream reasoning** — RCA can ask "did an upstream source change?"

Datasets are nodes; edges are directed upstream -> downstream, attributed to the
job/run that produced the downstream dataset. For the MVP, edges are populated
from *declared* job lineage (inputs/outputs); automatic plan-parsing layers in
later behind the same contracts.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class DatasetKind(StrEnum):
    TABLE = "table"
    PATH = "path"
    TOPIC = "topic"
    UNKNOWN = "unknown"


class Dataset(BaseModel):
    """A node in the lineage graph (a table, file path, or stream)."""

    name: str
    kind: DatasetKind = DatasetKind.TABLE
    first_seen: datetime | None = None


class LineageEdge(BaseModel):
    """A directed dependency: `upstream` feeds `downstream`."""

    upstream: str
    downstream: str
    job_name: str = ""
    run_id: str | None = None


class JobLineage(BaseModel):
    """Declared lineage for one job execution: inputs feed outputs.

    Registering this creates the dataset nodes and an edge from every input to
    every output, attributed to the job (and optionally the run that produced
    the outputs).
    """

    job_name: str = Field(..., min_length=1)
    run_id: str | None = None
    inputs: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)
    input_kind: DatasetKind = DatasetKind.TABLE
    output_kind: DatasetKind = DatasetKind.TABLE


class ImpactedDataset(BaseModel):
    """A downstream dataset reachable from a blast-radius root, with its depth."""

    name: str
    depth: int


class BlastRadius(BaseModel):
    """The downstream impact of a dataset (or a failed run's outputs)."""

    roots: list[str] = Field(default_factory=list)
    impacted: list[ImpactedDataset] = Field(default_factory=list)
    truncated: bool = False

    @property
    def count(self) -> int:
        return len(self.impacted)


class LineageNeighbors(BaseModel):
    """Direct or transitive neighbours of a dataset in one direction."""

    dataset: str
    direction: str  # "upstream" | "downstream"
    neighbors: list[ImpactedDataset] = Field(default_factory=list)
