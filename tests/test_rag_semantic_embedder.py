"""Unit tests for the semantic embedder + the embedder factory.

The semantic embedder is wrapped around an external ONNX model that we
don't want to download in CI. The tests inject a fake fastembed-shaped
object so we exercise every wrapper code path (lazy load, normalization,
list-vs-ndarray inputs) without hitting the network.
"""

from __future__ import annotations

import math
from collections.abc import Iterable

import pytest

from dataforge.contracts.incident import (
    AnomalyType,
    Incident,
    IncidentStatus,
    Severity,
)
from dataforge.contracts.rca import CauseCategory, RootCauseAnalysis
from dataforge.contracts.telemetry import (
    FailureInfo,
    PipelineRun,
    RunMetrics,
    RunStatus,
)
from dataforge.core.config import EmbedderKind, Settings
from dataforge.modules.rag.embedder import (
    EmbedderConfigError,
    HashingEmbedder,
    SemanticEmbedder,
    build_embedder,
)
from dataforge.modules.rag.profile import build_profile

# --- Stubs -----------------------------------------------------------------


class _FakeModel:
    """Minimal stand-in for fastembed.TextEmbedding.

    Returns a deterministic, text-dependent vector so we can assert that
    different inputs produce different outputs without loading a real model.
    """

    def __init__(self, *, return_ndarray: bool = False, dim: int = 8) -> None:
        self.calls: list[list[str]] = []
        self._return_ndarray = return_ndarray
        self._dim = dim

    def embed(self, texts: list[str]) -> Iterable[object]:
        self.calls.append(list(texts))
        for text in texts:
            # Distribute byte values across `dim` slots so similar texts cluster.
            vec = [0.0] * self._dim
            for i, b in enumerate(text.encode("utf-8")):
                vec[i % self._dim] += float(b)
            if self._return_ndarray:
                yield _FakeArray(vec)
            else:
                yield vec


class _FakeArray:
    """Just-enough ndarray surface: a `tolist()` method."""

    def __init__(self, data: list[float]) -> None:
        self._data = data

    def tolist(self) -> list[float]:
        return list(self._data)


# --- Fixtures --------------------------------------------------------------


def _oom_profile(run_id: str = "r1", app: str = "etl") -> object:
    return build_profile(
        PipelineRun(
            run_id=run_id,
            app_name=app,
            status=RunStatus.FAILED,
            failure=FailureInfo(error_class="java.lang.OutOfMemoryError"),
            metrics=RunMetrics(num_tasks=4),
        ),
        [
            Incident(
                incident_id=f"inc-{run_id}",
                run_id=run_id,
                anomaly_type=AnomalyType.RUN_FAILURE,
                severity=Severity.CRITICAL,
                status=IncidentStatus.OPEN,
                title="t",
                description="",
            )
        ],
        RootCauseAnalysis(
            analysis_id=f"rca-{run_id}",
            run_id=run_id,
            category=CauseCategory.MEMORY_PRESSURE,
            summary="OOM",
            explanation="",
        ),
    )


# --- SemanticEmbedder ------------------------------------------------------


def test_semantic_embedder_returns_l2_normalized_vector() -> None:
    fake = _FakeModel(dim=16)
    embedder = SemanticEmbedder(_model=fake)
    vec = embedder.embed(_oom_profile())  # type: ignore[arg-type]
    norm = math.sqrt(sum(v * v for v in vec))
    assert abs(norm - 1.0) < 1e-9


def test_semantic_embedder_handles_ndarray_like_results() -> None:
    fake = _FakeModel(return_ndarray=True, dim=16)
    embedder = SemanticEmbedder(_model=fake)
    vec = embedder.embed(_oom_profile())  # type: ignore[arg-type]
    assert len(vec) == 16
    assert all(isinstance(v, float) for v in vec)


def test_semantic_embedder_is_deterministic_for_same_profile() -> None:
    embedder = SemanticEmbedder(_model=_FakeModel(dim=16))
    p = _oom_profile()
    assert embedder.embed(p) == embedder.embed(p)  # type: ignore[arg-type]


def test_semantic_embedder_separates_distinct_profiles() -> None:
    """OOM vs healthy must produce different vectors (sanity for ranking)."""
    embedder = SemanticEmbedder(_model=_FakeModel(dim=16))
    oom = embedder.embed(_oom_profile("r1"))  # type: ignore[arg-type]
    healthy = embedder.embed(
        build_profile(
            PipelineRun(
                run_id="r2",
                app_name="clean",
                status=RunStatus.SUCCEEDED,
                metrics=RunMetrics(num_tasks=4),
            ),
            [],
            None,
        )
    )
    assert oom != healthy


def test_semantic_embedder_passes_profile_text_into_model() -> None:
    fake = _FakeModel(dim=8)
    embedder = SemanticEmbedder(_model=fake)
    profile = _oom_profile()
    embedder.embed(profile)  # type: ignore[arg-type]
    assert len(fake.calls) == 1
    sent_text = fake.calls[0][0]
    # to_text() rendering carries the operational signals into the model.
    assert "memory_pressure" in sent_text
    assert "OutOfMemoryError" in sent_text


def test_semantic_embedder_carries_dim_metadata() -> None:
    e = SemanticEmbedder(dim=384, _model=_FakeModel(dim=384))
    assert e.dim == 384
    assert e.name == f"semantic-v1:{SemanticEmbedder.DEFAULT_MODEL}"


def test_semantic_embedder_lazy_load_fails_clearly_without_fastembed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If the dep is missing and no model is injected, _ensure_model raises."""
    monkeypatch.setitem(__import__("sys").modules, "fastembed", None)
    embedder = SemanticEmbedder(_model=None)
    with pytest.raises(EmbedderConfigError):
        embedder.embed(_oom_profile())  # type: ignore[arg-type]


# --- Factory ---------------------------------------------------------------


def test_factory_returns_hashing_by_default() -> None:
    embedder = build_embedder(Settings(rag_embedder=EmbedderKind.HASHING))
    assert isinstance(embedder, HashingEmbedder)


def test_factory_raises_for_semantic_without_dep(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(__import__("sys").modules, "fastembed", None)
    with pytest.raises(EmbedderConfigError):
        build_embedder(Settings(rag_embedder=EmbedderKind.SEMANTIC))


def test_factory_returns_semantic_when_dep_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Inject a fake fastembed module so the factory's import check passes."""
    import sys
    import types

    fake_module = types.ModuleType("fastembed")
    fake_module.TextEmbedding = _FakeModel  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "fastembed", fake_module)

    embedder = build_embedder(Settings(rag_embedder=EmbedderKind.SEMANTIC))
    assert isinstance(embedder, SemanticEmbedder)
    # Default model name preserved end-to-end.
    assert embedder._model_name == "BAAI/bge-small-en-v1.5"
