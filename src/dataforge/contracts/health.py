"""Health and readiness contracts (§6 Rule 6 — observability first)."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class HealthStatus(StrEnum):
    OK = "ok"
    DEGRADED = "degraded"
    DOWN = "down"


class DependencyHealth(BaseModel):
    name: str
    status: HealthStatus
    detail: str | None = None


class HealthReport(BaseModel):
    status: HealthStatus
    version: str
    environment: str
    dependencies: list[DependencyHealth] = Field(default_factory=list)
