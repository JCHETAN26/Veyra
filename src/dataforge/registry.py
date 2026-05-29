"""Module registry.

The single place that declares which domain modules are active. The app
factory consumes this list to mount routers, manage lifecycle and aggregate
health. To split a module into its own service later, you remove it here and
point its router at a separate deployment — nothing else changes.
"""

from __future__ import annotations

from dataforge.modules.base import DomainModule
from dataforge.modules.gateway import module as gateway
from dataforge.modules.ingestion import module as ingestion
from dataforge.modules.metadata import module as metadata
from dataforge.modules.observability import module as observability
from dataforge.modules.orchestration import module as orchestration
from dataforge.modules.rag import module as rag
from dataforge.modules.remediation import module as remediation

# Ordered roughly along the self-healing data flow.
MODULES: list[DomainModule] = [
    gateway,
    ingestion,
    metadata,
    rag,
    observability,
    remediation,
    orchestration,
]
