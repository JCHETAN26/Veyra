"""LLM-backed root-cause analyzer.

Implements the same RootCauseAnalyzer interface as RuleBasedAnalyzer so the
remediation service can swap between them via configuration. The LLM is
called with:

  - the failing run's signature (app, status, error class, key metrics),
  - the active incidents already raised by the deterministic detectors,
  - the top-K operationally similar past incidents from the RAG corpus.

The model returns a strict, schema-validated structured payload which we
map 1:1 onto the canonical RootCauseAnalysis contract — no free-form JSON
parsing in the application code.

On any LLM-layer failure (timeout, circuit open, budget exhausted, schema
violation), the analyzer falls back to the deterministic rule-based
analyzer so the self-healing loop never breaks because of a flaky API.

RAG retrieval is best-effort: if the RAG service is unavailable or raises,
the analysis still runs without similar-incident context.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, Field

from dataforge.contracts.incident import Incident
from dataforge.contracts.rca import (
    CauseCategory,
    RecommendedAction,
    RootCauseAnalysis,
)
from dataforge.contracts.retrieval import SimilarIncident
from dataforge.contracts.telemetry import PipelineRun
from dataforge.core.llm import (
    ChatRequest,
    LLMClient,
    LLMError,
    Message,
    Role,
)
from dataforge.core.logging import get_logger
from dataforge.modules.remediation.rca.analyzer import RootCauseAnalyzer
from dataforge.modules.remediation.rca.rule_based import RuleBasedAnalyzer

if TYPE_CHECKING:
    from dataforge.modules.rag.service import RagService

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Structured LLM output schema
# ---------------------------------------------------------------------------


class _LLMRecommendedAction(BaseModel):
    """Action recommendation as the LLM produces it (no defaults for strict mode)."""

    title: str
    detail: str
    kind: Literal["manual", "spark_conf", "code_change", "rerun"]


class LLMAnalysisOut(BaseModel):
    """The strict schema the LLM is asked to fill.

    Kept separate from RootCauseAnalysis so the contract returned to callers
    always carries our system-generated fields (analysis_id, analyzer name,
    incident_ids, created_at) — those are not the LLM's job.
    """

    category: CauseCategory
    summary: str = Field(..., description="One-sentence headline of the root cause.")
    explanation: str = Field(
        ...,
        description="2-4 sentences explaining why the run failed/anomalous, "
        "citing past incidents in square brackets where relevant.",
    )
    contributing_factors: list[str]
    recommended_actions: list[_LLMRecommendedAction]
    confidence: float = Field(..., ge=0.0, le=1.0)
    cited_run_ids: list[str] = Field(
        ...,
        description="run_ids of past incidents that informed this analysis.",
    )


# ---------------------------------------------------------------------------
# Prompt assembly
# ---------------------------------------------------------------------------


_SYSTEM_PROMPT = (
    "You are a senior data engineer doing root-cause analysis on Apache Spark"
    " / Databricks pipeline failures.\n"
    "\n"
    "Given a failed or anomalous run, plus any incidents detected by"
    " deterministic rules and top-K operationally similar past incidents, you"
    " produce a structured root-cause analysis.\n"
    "\n"
    "Classify the cause into exactly one category:\n"
    "- memory_pressure: OOM errors, executor crashes from memory exhaustion\n"
    "- data_skew: uneven partitioning, hot keys, lopsided shuffles, sustained"
    " spill from concentration\n"
    "- transient_failure: spot reclaim, network blip, executor loss, retries"
    " that recovered\n"
    "- performance_regression: jobs running far longer than usual without errors\n"
    "- dependency_failure: upstream source/connector failure, schema drift"
    " breaking ingestion\n"
    "- unknown: signature does not match a known category\n"
    "\n"
    "Confidence is a number in [0, 1] reflecting how certain you are. Set it"
    " lower when:\n"
    "- the signature is novel,\n"
    "- the active incidents conflict,\n"
    "- the past incidents do not corroborate the chosen category.\n"
    "\n"
    "When recommending an action that involves a Spark configuration, give the"
    " exact key (e.g. `spark.sql.shuffle.partitions`). When citing a past"
    " incident, reference it by its run_id in square brackets, e.g."
    " `[run-789]`. Be terse; avoid hedging language; prefer one concrete"
    " action over three vague ones.\n"
    "\n"
    "Cited run_ids in the `cited_run_ids` field must be drawn from the"
    " past-incident list provided to you. Do not invent run_ids."
)


def _build_messages(
    run: PipelineRun,
    incidents: list[Incident],
    similar: list[SimilarIncident],
) -> list[Message]:
    """Assemble the chat for one RCA call.

    System message is cache-flagged so Anthropic prompt caching amortizes the
    large stable prefix across subsequent calls.
    """
    return [
        Message(role=Role.SYSTEM, content=_SYSTEM_PROMPT, cache=True),
        Message(role=Role.USER, content=_render_user_prompt(run, incidents, similar)),
    ]


def _render_user_prompt(
    run: PipelineRun,
    incidents: list[Incident],
    similar: list[SimilarIncident],
) -> str:
    parts: list[str] = []

    # --- Run ----------------------------------------------------------------
    parts.append("## Run")
    parts.append(f"- run_id: {run.run_id}")
    parts.append(f"- app: {run.app_name}")
    parts.append(f"- status: {run.status.value}")
    if run.duration_ms is not None:
        parts.append(f"- duration_ms: {run.duration_ms:,}")
    if run.failure is not None:
        if run.failure.error_class:
            parts.append(f"- error_class: {run.failure.error_class}")
        if run.failure.message:
            parts.append(f"- failure_message: {run.failure.message[:600]}")

    # --- Metrics ------------------------------------------------------------
    m = run.metrics
    parts.append("\n## Metrics")
    parts.append(f"- num_tasks: {m.num_tasks}")
    parts.append(f"- num_failed_tasks: {m.num_failed_tasks}")
    parts.append(f"- memory_spilled_bytes: {m.memory_spilled_bytes:,}")
    parts.append(f"- disk_spilled_bytes: {m.disk_spilled_bytes:,}")

    # --- Active incidents ---------------------------------------------------
    parts.append("\n## Active incidents (detected by deterministic rules)")
    if not incidents:
        parts.append("- (none)")
    for inc in incidents:
        parts.append(f"- {inc.anomaly_type.value} [severity={inc.severity.label}]: {inc.title}")
        for sig in inc.signals[:4]:
            parts.append(f"  - {sig.name}={sig.value}{_threshold(sig.threshold)}")

    # --- Similar past incidents --------------------------------------------
    parts.append("\n## Similar past incidents (top-K from RAG)")
    if not similar:
        parts.append("- (none retrieved)")
    for s in similar:
        cat = s.category or "unknown"
        parts.append(
            f"- [{s.run_id}] {cat} (score={s.score:.2f}): "
            f"{s.summary[:280] if s.summary else s.app_name}"
        )

    parts.append("\nProduce your analysis.")
    return "\n".join(parts)


def _threshold(threshold: float | None) -> str:
    return f" (threshold={threshold})" if threshold is not None else ""


# ---------------------------------------------------------------------------
# The analyzer
# ---------------------------------------------------------------------------


class LLMAnalyzer:
    """LLM-backed analyzer with deterministic fallback."""

    def __init__(
        self,
        llm_client: LLMClient,
        *,
        rag_service: RagService | None = None,
        fallback: RootCauseAnalyzer | None = None,
        max_similar: int = 3,
    ) -> None:
        self._llm = llm_client
        self._rag = rag_service
        self._fallback: RootCauseAnalyzer = fallback or RuleBasedAnalyzer()
        self._max_similar = max_similar
        self.name = f"llm-v1:{llm_client.model}"

    def attach_rag(self, rag_service: RagService) -> None:
        """Late-bind the RAG service (used by the module's startup hook)."""
        self._rag = rag_service

    async def analyze(self, run: PipelineRun, incidents: list[Incident]) -> RootCauseAnalysis:
        similar = await self._fetch_similar(run.run_id)

        try:
            response = await self._llm.complete(
                ChatRequest(
                    messages=_build_messages(run, incidents, similar),
                    response_schema=LLMAnalysisOut,
                )
            )
        except LLMError as exc:
            logger.warning(
                "llm_rca.llm_failed_falling_back",
                run_id=run.run_id,
                error=str(exc),
                error_code=exc.code,
            )
            return await self._fallback.analyze(run, incidents)

        parsed = response.parsed
        if not isinstance(parsed, LLMAnalysisOut):
            logger.warning(
                "llm_rca.no_structured_output_falling_back",
                run_id=run.run_id,
                provider=response.provider,
            )
            return await self._fallback.analyze(run, incidents)

        return _to_analysis(parsed, run=run, incidents=incidents, analyzer=self.name)

    async def _fetch_similar(self, run_id: str) -> list[SimilarIncident]:
        """Best-effort RAG lookup; never blocks analysis on its failure."""
        if self._rag is None:
            return []
        try:
            result = await self._rag.find_similar(run_id, limit=self._max_similar)
        except Exception as exc:  # noqa: BLE001 - RAG must never block RCA
            logger.warning("llm_rca.rag_failed", run_id=run_id, error=str(exc))
            return []
        return result.results


def _to_analysis(
    out: LLMAnalysisOut,
    *,
    run: PipelineRun,
    incidents: list[Incident],
    analyzer: str,
) -> RootCauseAnalysis:
    """Map the LLM's structured output onto the canonical RCA contract."""
    return RootCauseAnalysis(
        analysis_id=f"rca-{run.run_id}",
        run_id=run.run_id,
        category=out.category,
        summary=out.summary,
        explanation=out.explanation,
        contributing_factors=out.contributing_factors,
        recommended_actions=[
            RecommendedAction(title=a.title, detail=a.detail, kind=a.kind)
            for a in out.recommended_actions
        ],
        confidence=out.confidence,
        incident_ids=[i.incident_id for i in incidents],
        analyzer=analyzer,
    )
