"""The DomainModule contract.

Every domain module (ingestion, metadata, rag, orchestration, observability,
remediation, gateway) implements this. The app factory iterates over the
registered modules to mount routers, run startup/shutdown, and aggregate
health — so adding a module is uniform and boundaries stay explicit.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from fastapi import APIRouter

    from dataforge.contracts.health import DependencyHealth


@runtime_checkable
class DomainModule(Protocol):
    """Contract implemented by each domain module."""

    #: Stable module identifier, e.g. "ingestion". Used in URL prefix + logs.
    name: str

    def router(self) -> APIRouter:
        """Return the module's API router (mounted under /api/v1/<name>)."""
        ...

    async def startup(self) -> None:
        """Acquire resources (connections, clients). Called once at boot."""
        ...

    async def shutdown(self) -> None:
        """Release resources. Called once at shutdown."""
        ...

    async def health(self) -> list[DependencyHealth]:
        """Report health of this module's dependencies."""
        ...
