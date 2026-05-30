"""Embedders.

The Embedder interface turns a FailureProfile into a fixed-length vector.
Behind it, the MVP ships a deterministic feature-hashing embedder: zero-cost,
offline, reproducible, and operationally meaningful (profiles sharing error
class / cause / anomalies land close in vector space).

A model- or API-backed embedder implements the same interface later without
touching the index or retrieval code — the same swap-behind-interface pattern
used for the DB and the RCA analyzer.
"""

from __future__ import annotations

import hashlib
import math
from typing import Protocol, runtime_checkable

from dataforge.modules.rag.profile import FailureProfile


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
