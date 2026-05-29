"""RAG module.

Operational retrieval over Spark logs, past incidents, docs and execution
plans. Handles embedding, vector indexing (Qdrant), retrieval and reranking.
"""

from dataforge.modules.rag.module import module

__all__ = ["module"]
