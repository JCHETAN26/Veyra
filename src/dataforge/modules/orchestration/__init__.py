"""Orchestration module.

Drives the multi-agent self-healing workflow (LangGraph for agent graphs,
Temporal for durable retry-safe execution). Owns approval gates and rollback.
"""

from dataforge.modules.orchestration.module import module

__all__ = ["module"]
