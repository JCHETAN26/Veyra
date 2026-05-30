"""Unit tests for the rule-based + LLM-backed fix generators."""

from __future__ import annotations

from dataforge.contracts.rca import (
    CauseCategory,
    RecommendedAction,
    RootCauseAnalysis,
)
from dataforge.contracts.retrieval import SimilarIncident
from dataforge.contracts.telemetry import (
    FailureInfo,
    PipelineRun,
    RunMetrics,
    RunStatus,
)
from dataforge.core.llm import ChatRequest, ChatResponse, LLMRateLimitError, Usage
from dataforge.modules.remediation.fixes import (
    LLMFixGenerator,
    LLMFixProposalOut,
    RuleBasedFixGenerator,
    build_fix_generator,
)
from dataforge.modules.remediation.fixes.llm_based import (
    _build_messages,
    _LLMFixActionOut,
)

# --- Stubs -----------------------------------------------------------------


class _StubLLM:
    provider = "null"

    def __init__(self, model: str = "stub-model") -> None:
        self.model = model
        self.received: list[ChatRequest] = []
        self.next_response: LLMFixProposalOut | None = None
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
            usage=Usage(input_tokens=50, output_tokens=30),
            provider="null",  # type: ignore[arg-type]
        )

    async def aclose(self) -> None:
        return None


# --- Fixtures --------------------------------------------------------------


def _run() -> PipelineRun:
    return PipelineRun(
        run_id="r1",
        app_name="nightly_etl",
        status=RunStatus.FAILED,
        metrics=RunMetrics(
            num_tasks=200,
            num_failed_tasks=20,
            memory_spilled_bytes=600 * 1024 * 1024,
        ),
        failure=FailureInfo(
            error_class="java.lang.OutOfMemoryError",
            message="Java heap space exceeded",
        ),
    )


def _analysis(actions: list[RecommendedAction] | None = None) -> RootCauseAnalysis:
    return RootCauseAnalysis(
        analysis_id="rca-r1",
        run_id="r1",
        category=CauseCategory.MEMORY_PRESSURE,
        summary="OOM from skewed shuffle.",
        explanation="The job ran out of memory.",
        contributing_factors=["OOM error class"],
        recommended_actions=actions
        or [
            RecommendedAction(
                title="Increase shuffle partitions",
                detail="Raise spark.sql.shuffle.partitions.",
                kind="spark_conf",
            ),
            RecommendedAction(
                title="Inspect logs",
                detail="Manual triage.",
                kind="manual",
            ),
        ],
        confidence=0.85,
        incident_ids=["inc-1"],
    )


# --- Rule-based generator --------------------------------------------------


async def test_rule_based_maps_actions_and_drops_manual() -> None:
    gen = RuleBasedFixGenerator()
    proposal = await gen.generate(_run(), _analysis())

    assert proposal.run_id == "r1"
    assert proposal.cause_category == CauseCategory.MEMORY_PRESSURE.value
    assert proposal.confidence == 0.85
    # The manual triage action is filtered out — only the spark_conf one remains.
    assert len(proposal.actions) == 1
    assert proposal.actions[0].title == "Increase shuffle partitions"
    assert proposal.actions[0].kind == "spark_conf"
    # Rule-based leaves the richer fields empty.
    assert proposal.actions[0].parameters == {}
    assert proposal.actions[0].confidence == 0.0
    assert proposal.actions[0].rollback == ""


async def test_rule_based_returns_empty_when_only_manual_actions() -> None:
    gen = RuleBasedFixGenerator()
    proposal = await gen.generate(
        _run(),
        _analysis(
            actions=[
                RecommendedAction(title="Read logs", detail="", kind="manual"),
            ]
        ),
    )
    assert proposal.actions == []


# --- LLM-backed generator --------------------------------------------------


def _llm_output() -> LLMFixProposalOut:
    return LLMFixProposalOut(
        actions=[
            _LLMFixActionOut(
                title="Increase shuffle partitions to 400",
                detail=(
                    "Raise spark.sql.shuffle.partitions from 200 to 400 " "to halve partition size."
                ),
                kind="spark_conf",
                parameters={"spark.sql.shuffle.partitions": "400"},
                confidence=0.78,
                rollback="Revert spark.sql.shuffle.partitions to 200.",
                estimated_impact="Halves average partition size; should remove the OOM.",
            ),
            _LLMFixActionOut(
                title="Broadcast smaller side of the join",
                detail="If the dim table is < 100MB, broadcast it to avoid the shuffle.",
                kind="code_change",
                parameters={},
                confidence=0.55,
                rollback="Remove the broadcast() hint.",
                estimated_impact="Eliminates the heavy shuffle for the join.",
            ),
        ],
        overall_confidence=0.7,
    )


async def test_llm_generator_returns_rich_actions() -> None:
    llm = _StubLLM()
    llm.next_response = _llm_output()
    gen = LLMFixGenerator(llm_client=llm)  # type: ignore[arg-type]

    proposal = await gen.generate(_run(), _analysis())

    assert proposal.run_id == "r1"
    assert proposal.confidence == 0.7
    assert len(proposal.actions) == 2

    first = proposal.actions[0]
    assert first.title == "Increase shuffle partitions to 400"
    assert first.kind == "spark_conf"
    assert first.parameters == {"spark.sql.shuffle.partitions": "400"}
    assert first.confidence == 0.78
    assert first.rollback.startswith("Revert")
    assert first.estimated_impact.startswith("Halves")

    second = proposal.actions[1]
    assert second.kind == "code_change"
    assert second.confidence == 0.55


async def test_llm_generator_passes_similar_incidents_into_prompt() -> None:
    llm = _StubLLM()
    llm.next_response = _llm_output()
    gen = LLMFixGenerator(llm_client=llm)  # type: ignore[arg-type]

    similar = [
        SimilarIncident(
            run_id="run-42",
            score=0.72,
            app_name="finance_etl",
            category="memory_pressure",
            summary="Same OOM; resolved by bumping shuffle partitions to 400.",
        )
    ]
    await gen.generate(_run(), _analysis(), similar=similar)

    user_msg = llm.received[0].messages[1].content
    assert "[run-42]" in user_msg
    assert "memory_pressure" in user_msg
    assert "bumping shuffle partitions" in user_msg


async def test_llm_generator_falls_back_when_llm_raises() -> None:
    llm = _StubLLM()
    llm.raise_for = LLMRateLimitError("quota")
    gen = LLMFixGenerator(llm_client=llm)  # type: ignore[arg-type]

    proposal = await gen.generate(_run(), _analysis())

    # Rule-based shape: title from RCA, no rich fields.
    assert len(proposal.actions) == 1
    assert proposal.actions[0].title == "Increase shuffle partitions"
    assert proposal.actions[0].parameters == {}


async def test_llm_generator_falls_back_when_no_parsed_output() -> None:
    class _RawProvider(_StubLLM):
        async def complete(self, request: ChatRequest) -> ChatResponse:
            return ChatResponse(
                content="not json",
                parsed=None,
                model=request.model or self.model,
                usage=Usage(input_tokens=1, output_tokens=1),
                provider="null",  # type: ignore[arg-type]
            )

    gen = LLMFixGenerator(llm_client=_RawProvider())  # type: ignore[arg-type]
    proposal = await gen.generate(_run(), _analysis())
    # Fell back to rule-based mapping of recommended actions.
    assert len(proposal.actions) == 1
    assert proposal.actions[0].title == "Increase shuffle partitions"


async def test_llm_generator_falls_back_when_empty_proposal() -> None:
    """An LLM proposal with zero actions degrades to rule-based, not 'no fix'."""
    llm = _StubLLM()
    llm.next_response = LLMFixProposalOut(actions=[], overall_confidence=0.0)
    gen = LLMFixGenerator(llm_client=llm)  # type: ignore[arg-type]

    proposal = await gen.generate(_run(), _analysis())
    # Falls back: rule-based shape, single auto-applicable action survives.
    assert len(proposal.actions) == 1


# --- Prompt assembly -------------------------------------------------------


def test_build_messages_marks_system_for_caching() -> None:
    messages = _build_messages(_run(), _analysis(), [])
    assert messages[0].role == "system"
    assert messages[0].cache is True
    assert messages[1].role == "user"


def test_user_prompt_includes_rca_and_metrics() -> None:
    user_text = _build_messages(_run(), _analysis(), [])[1].content
    assert "category: memory_pressure" in user_text
    assert "OOM from skewed shuffle" in user_text
    assert "memory_spilled_bytes: 629,145,600" in user_text
    assert "java.lang.OutOfMemoryError" in user_text


# --- Factory ---------------------------------------------------------------


def test_factory_returns_rule_based_with_null_provider() -> None:
    from dataforge.core.config import LLMProvider, Settings

    gen = build_fix_generator(Settings(llm_provider=LLMProvider.NULL))
    assert isinstance(gen, RuleBasedFixGenerator)


def test_factory_returns_llm_generator_with_real_provider() -> None:
    from dataforge.core.config import LLMProvider, Settings
    from dataforge.core.llm.providers.null import NullProvider

    gen = build_fix_generator(
        Settings(llm_provider=LLMProvider.ANTHROPIC),
        llm_client=NullProvider(model="claude-x"),  # type: ignore[arg-type]
    )
    assert isinstance(gen, LLMFixGenerator)
    assert gen.name == "llm-v1:claude-x"
