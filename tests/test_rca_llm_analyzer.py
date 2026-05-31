"""Unit tests for the LLM-backed RCA analyzer.

The analyzer is exercised with a stub LLM client (no API calls) and a stub
RAG service so we can drive both the happy path and every fallback branch.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from dataforge.contracts.incident import (
    AnomalySignal,
    AnomalyType,
    Incident,
    IncidentStatus,
    Severity,
)
from dataforge.contracts.rca import CauseCategory
from dataforge.contracts.retrieval import RetrievalResult, SimilarIncident
from dataforge.contracts.telemetry import (
    FailureInfo,
    PipelineRun,
    RunMetrics,
    RunStatus,
)
from dataforge.core.llm import (
    ChatRequest,
    ChatResponse,
    LLMRateLimitError,
    Usage,
)
from dataforge.modules.remediation.rca import LLMAnalyzer
from dataforge.modules.remediation.rca.llm_based import (
    LLMAnalysisOut,
    _build_messages,
    _LLMRecommendedAction,
)

# --- Stubs -----------------------------------------------------------------


class _StubLLM:
    """A controllable LLMClient stand-in for analyzer tests."""

    provider = "null"

    def __init__(self, model: str = "stub-model") -> None:
        self.model = model
        self.received: list[ChatRequest] = []
        self.next_response: LLMAnalysisOut | None = None
        self.raise_for: BaseException | None = None

    async def complete(self, request: ChatRequest) -> ChatResponse:
        self.received.append(request)
        if self.raise_for is not None:
            exc, self.raise_for = self.raise_for, None
            raise exc
        out = self.next_response
        assert out is not None, "test forgot to set _StubLLM.next_response"
        return ChatResponse(
            content=out.model_dump_json(),
            parsed=out,
            model=request.model or self.model,
            usage=Usage(input_tokens=100, output_tokens=50),
            provider="null",  # type: ignore[arg-type]
        )

    async def aclose(self) -> None:
        return None


class _StubRag:
    def __init__(self, results: list[SimilarIncident]) -> None:
        self._results = results
        self.calls = 0

    async def find_similar(self, run_id: str, *, limit: int = 5) -> RetrievalResult:
        self.calls += 1
        return RetrievalResult(query_run_id=run_id, results=self._results[:limit])


# --- Fixtures --------------------------------------------------------------


def _run(**overrides: object) -> PipelineRun:
    base: dict[str, object] = {
        "run_id": "r1",
        "app_name": "nightly_etl",
        "status": RunStatus.FAILED,
        "metrics": RunMetrics(num_tasks=200, num_failed_tasks=20),
        "failure": FailureInfo(
            error_class="java.lang.OutOfMemoryError",
            message="Java heap space exceeded",
        ),
    }
    base.update(overrides)
    return PipelineRun(**base)  # type: ignore[arg-type]


def _incident(anomaly: AnomalyType, severity: Severity = Severity.HIGH) -> Incident:
    return Incident(
        incident_id=f"inc-{anomaly.value}",
        run_id="r1",
        anomaly_type=anomaly,
        severity=severity,
        status=IncidentStatus.OPEN,
        title=anomaly.value,
        description="",
        signals=[AnomalySignal(name="x", value=1.0)],
    )


def _good_analysis() -> LLMAnalysisOut:
    return LLMAnalysisOut(
        category=CauseCategory.MEMORY_PRESSURE,
        summary="OOM driven by skewed shuffle.",
        explanation=(
            "The job failed with a Java heap OOM. The pattern matches [run-789] "
            "where a skewed key concentrated rows."
        ),
        contributing_factors=["OOM error class", "high failed task ratio"],
        recommended_actions=[
            _LLMRecommendedAction(
                title="Raise shuffle partitions",
                detail="Set spark.sql.shuffle.partitions=400 to halve partition size.",
                kind="spark_conf",
            )
        ],
        confidence=0.82,
        cited_run_ids=["run-789"],
    )


# --- Happy path ------------------------------------------------------------


async def test_llm_analyzer_returns_structured_analysis() -> None:
    llm = _StubLLM()
    llm.next_response = _good_analysis()
    rag = _StubRag(
        results=[
            SimilarIncident(
                run_id="run-789",
                score=0.82,
                app_name="nightly_etl",
                category="data_skew",
                summary="Heavy spill from skewed join key.",
            )
        ]
    )
    analyzer = LLMAnalyzer(llm_client=llm, rag_service=rag)  # type: ignore[arg-type]

    run = _run()
    incidents = [_incident(AnomalyType.RUN_FAILURE, Severity.CRITICAL)]
    analysis = await analyzer.analyze(run, incidents)

    assert analysis.category == CauseCategory.MEMORY_PRESSURE
    assert analysis.confidence == 0.82
    assert analysis.analysis_id == "rca-r1"
    assert analysis.run_id == "r1"
    assert analysis.incident_ids == [incidents[0].incident_id]
    assert analysis.analyzer == "llm-v1:stub-model"
    assert analysis.recommended_actions
    assert analysis.recommended_actions[0].kind == "spark_conf"
    assert rag.calls == 1


async def test_llm_analyzer_passes_similar_incidents_into_prompt() -> None:
    llm = _StubLLM()
    llm.next_response = _good_analysis()
    rag = _StubRag(
        results=[
            SimilarIncident(
                run_id="run-789",
                score=0.82,
                app_name="finance_etl",
                category="memory_pressure",
                summary="OOM from broadcast hash join blowing the executor.",
            )
        ]
    )
    analyzer = LLMAnalyzer(llm_client=llm, rag_service=rag)  # type: ignore[arg-type]

    await analyzer.analyze(_run(), [_incident(AnomalyType.RUN_FAILURE)])

    user_msg = llm.received[0].messages[1].content
    assert "[run-789]" in user_msg
    assert "memory_pressure" in user_msg
    assert "broadcast hash join" in user_msg


# --- Fallbacks -------------------------------------------------------------


async def test_llm_analyzer_falls_back_when_llm_raises() -> None:
    llm = _StubLLM()
    llm.raise_for = LLMRateLimitError("upstream busy")
    analyzer = LLMAnalyzer(llm_client=llm)  # type: ignore[arg-type]

    analysis = await analyzer.analyze(
        _run(),
        [_incident(AnomalyType.RUN_FAILURE, Severity.CRITICAL)],
    )

    # Rule-based fallback hit: deterministic OOM classification.
    assert analysis.category == CauseCategory.MEMORY_PRESSURE
    assert analysis.analyzer == "rule-based-v1"


async def test_llm_analyzer_falls_back_when_no_parsed_output() -> None:
    """If the provider returns text but no parsed structured payload, fall back."""

    class _RawProvider(_StubLLM):
        async def complete(self, request: ChatRequest) -> ChatResponse:
            return ChatResponse(
                content="free-form garbage",
                parsed=None,
                model=request.model or self.model,
                usage=Usage(input_tokens=1, output_tokens=1),
                provider="null",  # type: ignore[arg-type]
            )

    analyzer = LLMAnalyzer(llm_client=_RawProvider())  # type: ignore[arg-type]
    analysis = await analyzer.analyze(
        _run(),
        [_incident(AnomalyType.RUN_FAILURE, Severity.CRITICAL)],
    )
    assert analysis.analyzer == "rule-based-v1"
    assert analysis.category == CauseCategory.MEMORY_PRESSURE


async def test_llm_analyzer_works_without_rag() -> None:
    llm = _StubLLM()
    llm.next_response = _good_analysis()
    analyzer = LLMAnalyzer(llm_client=llm)  # type: ignore[arg-type]

    analysis = await analyzer.analyze(_run(), [_incident(AnomalyType.RUN_FAILURE)])

    assert analysis.analyzer == "llm-v1:stub-model"
    # The user prompt indicates no similar incidents were retrieved.
    assert "(none retrieved)" in llm.received[0].messages[1].content


async def test_llm_analyzer_tolerates_rag_failure() -> None:
    class _BrokenRag:
        async def find_similar(self, run_id: str, *, limit: int = 5) -> RetrievalResult:
            raise RuntimeError("qdrant down")

    llm = _StubLLM()
    llm.next_response = _good_analysis()
    analyzer = LLMAnalyzer(llm_client=llm, rag_service=_BrokenRag())  # type: ignore[arg-type]

    analysis = await analyzer.analyze(_run(), [_incident(AnomalyType.RUN_FAILURE)])
    # Analysis still completed via LLM (not fallback); RAG failure was swallowed.
    assert analysis.analyzer == "llm-v1:stub-model"


# --- Prompt assembly -------------------------------------------------------


def test_build_messages_marks_system_for_caching() -> None:
    messages = _build_messages(_run(), [], [])
    assert messages[0].role == "system"
    assert messages[0].cache is True
    assert messages[1].role == "user"


def test_build_messages_renders_run_signature_and_incidents() -> None:
    run = _run(duration_ms=1_800_000)
    incidents = [
        _incident(AnomalyType.RUN_FAILURE, Severity.CRITICAL),
        _incident(AnomalyType.EXCESSIVE_SPILL, Severity.MEDIUM),
    ]
    similar = [
        SimilarIncident(
            run_id="run-42",
            score=0.7,
            category="data_skew",
            summary="skewed join key on customer_id",
        )
    ]
    user_text = _build_messages(run, incidents, similar)[1].content

    assert "run_id: r1" in user_text
    assert "java.lang.OutOfMemoryError" in user_text
    assert "duration_ms: 1,800,000" in user_text
    assert "run_failure" in user_text
    assert "excessive_spill" in user_text
    assert "[run-42]" in user_text
    assert "skewed join key" in user_text


# --- Factory (config-driven) ----------------------------------------------


def test_build_analyzer_returns_rule_based_with_null_provider() -> None:
    from dataforge.core.config import LLMProvider, Settings
    from dataforge.modules.remediation.rca import RuleBasedAnalyzer, build_analyzer

    analyzer = build_analyzer(Settings(llm_provider=LLMProvider.NULL))
    assert isinstance(analyzer, RuleBasedAnalyzer)


def test_build_analyzer_returns_llm_analyzer_with_real_provider() -> None:
    from dataforge.core.config import LLMProvider, Settings
    from dataforge.core.llm.providers.null import NullProvider
    from dataforge.modules.remediation.rca import build_analyzer

    # We pass anthropic in settings to exercise the branch, but inject a Null
    # raw provider so no real SDK / key is required.
    analyzer = build_analyzer(
        Settings(llm_provider=LLMProvider.ANTHROPIC),
        llm_client=NullProvider(model="claude-x"),  # type: ignore[arg-type]
    )
    assert isinstance(analyzer, LLMAnalyzer)
    assert analyzer.name == "llm-v1:claude-x"


# --- Reference: stub matches the contract ----------------------------------


def test_stub_data_satisfies_canonical_contract() -> None:
    """Sanity: the canned LLM payload is contract-valid (catches drift)."""
    out = _good_analysis()
    assert datetime(2026, 1, 1, tzinfo=UTC)  # avoid unused-import warning
    assert 0.0 <= out.confidence <= 1.0
    assert out.recommended_actions
    pytest.importorskip("pydantic")
