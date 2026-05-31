"""Embedders.

The Embedder interface turns a FailureProfile into a fixed-length vector.
Two implementations ship behind the same interface:

  - HashingEmbedder: deterministic feature-hashing (the hashing trick).
    Zero-cost, offline, reproducible, no model download. The default so
    CI and fresh installs stay fast. Operationally meaningful because
    profiles sharing error class / cause / anomalies land close in
    vector space.

  - SemanticEmbedder: a real sentence-embedding model (bge-small-en-v1.5
    by default) via fastembed. ONNX-runtime backed (no torch dep, ~50MB
    install). Lazy-loads the model file on first embed. Produces 384-dim
    L2-normalized vectors so cosine similarity stays a dot product.

The factory `build_embedder(settings)` selects between them based on the
`DATAFORGE_RAG_EMBEDDER` setting.
"""

from __future__ import annotations

import hashlib
import math
from typing import Any, Protocol, runtime_checkable

from dataforge.core.config import EmbedderKind, Settings, get_settings
from dataforge.core.errors import DataForgeError
from dataforge.modules.rag.profile import FailureProfile


class EmbedderConfigError(DataForgeError):
    """Embedder is misconfigured (missing dep, unknown kind, ...)."""

    code = "embedder_config_error"
    status_code = 500


@runtime_checkable
class Embedder(Protocol):
    name: str
    dim: int

    def embed(self, profile: FailureProfile) -> list[float]:
        """Return a unit-normalized embedding for the profile."""
        ...


class HashingEmbedder:
    """Deterministic feature-hashing embedder (the hashing trick).

    Each token is hashed to a dimension index and a sign, accumulated, then the
    vector is L2-normalized so cosine similarity is a plain dot product. No
    training, no network, fully reproducible across processes.
    """

    name = "hashing-v1"

    def __init__(self, dim: int = 256) -> None:
        if dim <= 0:
            raise ValueError("dim must be positive")
        self.dim = dim

    def embed(self, profile: FailureProfile) -> list[float]:
        vec = [0.0] * self.dim
        for token in profile.tokens:
            idx, sign = self._hash(token)
            vec[idx] += sign
        return _l2_normalize(vec)

    def _hash(self, token: str) -> tuple[int, float]:
        # SHA1 used purely as a fast feature-hash (the hashing trick), not for
        # security; usedforsecurity=False documents that and satisfies linters.
        digest = hashlib.sha1(token.encode("utf-8"), usedforsecurity=False).digest()
        # First 4 bytes -> dimension; next byte's low bit -> sign.
        idx = int.from_bytes(digest[:4], "big") % self.dim
        sign = 1.0 if digest[4] & 1 else -1.0
        return idx, sign


class SemanticEmbedder:
    """Sentence-embedding model via fastembed (ONNX runtime).

    Default model is `BAAI/bge-small-en-v1.5` — 384-dim, ~130MB on disk,
    consistently top-of-leaderboard for English retrieval at this size class.
    The underlying model is loaded lazily on first embed() so app startup
    isn't blocked by the file download.

    The text input is the profile's `to_text()` rendering: a structured one-
    liner combining app, category, error class, anomalies, and summary. This
    keeps the embedding focused on operational signals rather than incidental
    prose.
    """

    DEFAULT_MODEL = "BAAI/bge-small-en-v1.5"
    DEFAULT_DIM = 384

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        *,
        dim: int = DEFAULT_DIM,
        cache_dir: str | None = None,
        _model: Any = None,
    ) -> None:
        self._model_name = model_name
        self._cache_dir = cache_dir
        self._model = _model
        self.name = f"semantic-v1:{model_name}"
        self.dim = dim

    def embed(self, profile: FailureProfile) -> list[float]:
        text = profile.to_text()
        model = self._ensure_model()
        # fastembed yields an iterable of vectors; we asked for one.
        raw = next(iter(model.embed([text])))
        # Convert numpy ndarray (or any iterable) to a plain list[float] so
        # the rest of the platform stays numpy-free.
        if hasattr(raw, "tolist"):
            vec = [float(x) for x in raw.tolist()]
        else:
            vec = [float(x) for x in raw]
        return _l2_normalize(vec)

    def _ensure_model(self) -> Any:
        if self._model is not None:
            return self._model
        try:
            from fastembed import TextEmbedding
        except ImportError as exc:  # pragma: no cover - dep gated
            raise EmbedderConfigError(
                "fastembed not installed. Install dataforge with the [embedder] "
                "extra to use the semantic embedder, or set "
                "DATAFORGE_RAG_EMBEDDER=hashing."
            ) from exc
        kwargs: dict[str, Any] = {"model_name": self._model_name}
        if self._cache_dir is not None:
            kwargs["cache_dir"] = self._cache_dir
        self._model = TextEmbedding(**kwargs)
        return self._model


def build_embedder(settings: Settings | None = None) -> Embedder:
    """Construct the embedder configured for this environment.

    Hashing is the safe default and needs no external dependency. Semantic
    requires the `embedder` extra to be installed; we validate at construction
    so startup fails fast on misconfiguration rather than at the first index.
    """
    cfg = settings or get_settings()
    if cfg.rag_embedder is EmbedderKind.HASHING:
        return HashingEmbedder()
    if cfg.rag_embedder is EmbedderKind.SEMANTIC:
        try:
            import fastembed  # noqa: F401
        except ImportError as exc:
            raise EmbedderConfigError(
                "DATAFORGE_RAG_EMBEDDER=semantic but fastembed is not "
                "installed. Run `uv sync --extra embedder` or switch back to "
                "DATAFORGE_RAG_EMBEDDER=hashing."
            ) from exc
        return SemanticEmbedder(
            model_name=cfg.rag_embedder_model,
            cache_dir=cfg.rag_embedder_cache_dir,
        )
    raise EmbedderConfigError(f"unknown rag_embedder: {cfg.rag_embedder}")


def _l2_normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vec))
    if norm == 0.0:
        return vec
    return [v / norm for v in vec]


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity of two equal-length vectors, clamped to [0, 1].

    Inputs are expected pre-normalized; negatives are clamped to 0 since
    operational similarity is non-negative for ranking purposes.
    """
    if len(a) != len(b):
        raise ValueError("vector length mismatch")
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    return max(0.0, min(1.0, dot))
