"""LLM-backed fix generator.

Takes the RCA + run + similar past incidents and asks the LLM for a
strictly-typed FixProposal: concrete actions with parameter values
(e.g. exact Spark conf keys), per-action confidence, rollback notes, and
estimated impact.

Implements the same FixGenerator interface as RuleBasedFixGenerator, so
the orchestration service is unaware of which one is wired. On any LLM
failure (timeout, circuit open, budget exhausted, schema violation) the
generator falls back to the deterministic rule-based mapping — keeping
the self-healing loop available even when the API is unreachable.

The prompt instructs the model to use *canonical action title phrasing*
("Broadcast smaller side", "Increase shuffle partitions", "Repartition on
high-cardinality key") so the existing deterministic SimulatedExecutor can
match them. The richer fields (parameters, rollback) are LLM-only and
surfaced to humans at the approval step.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from dataforge.contracts.rca import RootCauseAnalysis
from dataforge.contracts.remediation_workflow import FixAction, FixProposal
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
from dataforge.modules.remediation.fixes.generator import FixGenerator
from dataforge.modules.remediation.fixes.rule_based import RuleBasedFixGenerator

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Structured LLM output schema
# ---------------------------------------------------------------------------


class _LLMFixActionOut(BaseModel):
    """One action exactly as the LLM returns it (no defaults for strict mode)."""

    title: str
    detail: str
    kind: Literal["spark_conf", "code_change", "rerun"]
    parameters: dict[str, str]
    confidence: float = Field(ge=0.0, le=1.0)
    rollback: str
    estimated_impact: str


class LLMFixProposalOut(BaseModel):
    """Strict schema the model fills.

    `actions` are ordered by the model from most-likely-to-fix to fallback.
    The workflow's existing fallback chain tries them in this order.
    """

    actions: list[_LLMFixActionOut]
    overall_confidence: float = Field(ge=0.0, le=1.0)


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------


_SYSTEM_PROMPT = (
    "You are a senior Spark / Databricks engineer producing a small set of"
    " concrete, parameterized fixes for a pipeline failure.\n"
    "\n"
    "You receive: the failing run's signature, the structured root-cause"
    " analysis already produced upstream, and the top-K operationally"
    " similar past incidents (which already include their applied fix when"
    " known).\n"
    "\n"
    "You return between 1 and 3 actions, ORDERED by likelihood-to-fix"
    " (highest first). The workflow tries them in order via a fallback"
    " chain, so the second and third actions are real fallbacks, not"
    " filler.\n"
    "\n"
    "For each action:\n"
    "- title: a short imperative phrase. Prefer canonical phrasing matching"
    " the analyzer taxonomy: 'Broadcast smaller side of the join',"
    " 'Increase shuffle partitions to N', 'Repartition on high-cardinality"
    " key', 'Retry with on-demand executors'. Stay terse.\n"
    "- detail: 1-2 sentences explaining what to change and why.\n"
    "- kind: one of `spark_conf` | `code_change` | `rerun`. Use `spark_conf`"
    " whenever the fix is a config knob; `code_change` for query-level"
    " changes (broadcast hints, repartition calls, salting); `rerun` for"
    " transient-failure retries.\n"
    "- parameters: a flat string-to-string map of concrete settings. For"
    " spark_conf give exact keys (`spark.sql.shuffle.partitions`,"
    " `spark.sql.autoBroadcastJoinThreshold`). Leave empty for code_change"
    " when the change is structural.\n"
    "- confidence: 0-1 for this specific action. Do not parrot the overall"
    " RCA confidence — actions can be high-confidence even when the cause"
    " is uncertain (and vice versa).\n"
    "- rollback: one sentence on how to undo this change cleanly.\n"
    "- estimated_impact: one-line expected effect on the failure mode"
    " (e.g. 'halves average partition size; should eliminate executor"
    " OOM').\n"
    "\n"
    "Never recommend manual triage as an action — that belongs in the RCA"
    " explanation, not the fix proposal. Never invent parameters whose"
    " keys aren't real Spark properties. Be terse; avoid hedging."
)


def _build_messages(
    run: PipelineRun,
    analysis: RootCauseAnalysis,
    similar: list[SimilarIncident],
) -> list[Message]:
    return [
        Message(role=Role.SYSTEM, content=_SYSTEM_PROMPT, cache=True),
        Message(role=Role.USER, content=_render_user_prompt(run, analysis, similar)),
    ]


def _render_user_prompt(
    run: PipelineRun,
    analysis: RootCauseAnalysis,
    similar: list[SimilarIncident],
) -> str:
    parts: list[str] = []

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

    m = run.metrics
    parts.append("\n## Metrics")
    parts.append(f"- num_tasks: {m.num_tasks}")
    parts.append(f"- num_failed_tasks: {m.num_failed_tasks}")
    parts.append(f"- memory_spilled_bytes: {m.memory_spilled_bytes:,}")
    parts.append(f"- disk_spilled_bytes: {m.disk_spilled_bytes:,}")

    parts.append("\n## Root-cause analysis")
    parts.append(f"- category: {analysis.category.value}")
    parts.append(f"- summary: {analysis.summary}")
    parts.append(f"- explanation: {analysis.explanation}")
    parts.append(f"- analyzer_confidence: {analysis.confidence:.2f}")
    if analysis.contributing_factors:
        parts.append("- contributing_factors:")
        for cf in analysis.contributing_factors:
            parts.append(f"  - {cf}")
    if analysis.recommended_actions:
        parts.append("- prior recommendations from the analyzer:")
        for a in analysis.recommended_actions:
            parts.append(f"  - [{a.kind}] {a.title}: {a.detail[:200]}")

    parts.append("\n## Similar past incidents (top-K from RAG)")
    if not similar:
        parts.append("- (none retrieved)")
    for s in similar:
        cat = s.category or "unknown"
        parts.append(
            f"- [{s.run_id}] {cat} (score={s.score:.2f}): " f"{(s.summary or s.app_name)[:280]}"
        )

    parts.append("\nProduce the fix proposal.")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# The generator
# ---------------------------------------------------------------------------


class LLMFixGenerator:
    """LLM-backed fix generator with deterministic fallback."""

    def __init__(
        self,
        llm_client: LLMClient,
        *,
        fallback: FixGenerator | None = None,
    ) -> None:
        self._llm = llm_client
        self._fallback: FixGenerator = fallback or RuleBasedFixGenerator()
        self.name = f"llm-v1:{llm_client.model}"

    async def generate(
        self,
        run: PipelineRun,
        analysis: RootCauseAnalysis,
        *,
        similar: list[SimilarIncident] | None = None,
    ) -> FixProposal:
        sims = similar or []
        try:
            response = await self._llm.complete(
                ChatRequest(
                    messages=_build_messages(run, analysis, sims),
                    response_schema=LLMFixProposalOut,
                )
            )
        except LLMError as exc:
            logger.warning(
                "llm_fix.llm_failed_falling_back",
                run_id=run.run_id,
                error=str(exc),
                error_code=exc.code,
            )
            return await self._fallback.generate(run, analysis, similar=sims)

        parsed = response.parsed
        if not isinstance(parsed, LLMFixProposalOut):
            logger.warning(
                "llm_fix.no_structured_output_falling_back",
                run_id=run.run_id,
                provider=response.provider,
            )
            return await self._fallback.generate(run, analysis, similar=sims)

        proposal = _to_proposal(parsed, run=run, analysis=analysis)
        if not proposal.actions:
            # An empty proposal is indistinguishable to the workflow from "no
            # actionable fix" — defer to the rule-based path so we at least
            # surface the analyzer's recommended actions.
            logger.info(
                "llm_fix.empty_proposal_falling_back",
                run_id=run.run_id,
            )
            return await self._fallback.generate(run, analysis, similar=sims)
        return proposal


def _to_proposal(
    out: LLMFixProposalOut,
    *,
    run: PipelineRun,
    analysis: RootCauseAnalysis,
) -> FixProposal:
    return FixProposal(
        run_id=run.run_id,
        cause_category=analysis.category.value,
        confidence=out.overall_confidence,
        actions=[
            FixAction(
                title=a.title,
                detail=a.detail,
                kind=a.kind,
                parameters=a.parameters,
                confidence=a.confidence,
                rollback=a.rollback,
                estimated_impact=a.estimated_impact,
            )
            for a in out.actions
        ],
    )
