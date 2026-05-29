"""Metadata module.

Owns schemas, lineage edges, DAG mapping, pipeline runs and incidents — the
operational graph other modules reason over (Postgres-backed).
"""

from dataforge.modules.metadata.module import module

__all__ = ["module"]
