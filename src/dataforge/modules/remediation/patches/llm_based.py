"""LLM-backed code patch generator.

Calls the configured LLM with strict structured output (CodePatch as the
response schema) so the model returns a typed, validated patch rather
than free-form code in a markdown fence. The system prompt instructs
canonical PySpark / SQL idioms so applied patches are recognizable.

This generator deliberately does NOT fall back to a deterministic
rule-based alternative the way RCA / FixGenerator do. The reason: a
rule-based "I changed your source code" is dangerous — there is no
sensible default that could "almost" rewrite a user's PySpark file.
LLM errors surface as `LLMError` to the caller, which can decide
whether to retry, skip, or block on human triage.
"""

from __future__ import annotations

from dataforge.contracts.patch import CodePatch
from dataforge.contracts.rca import RootCauseAnalysis
from dataforge.contracts.remediation_workflow import FixAction
from dataforge.contracts.telemetry import PipelineRun
from dataforge.core.llm import ChatRequest, LLMClient, LLMError, Message, Role
from dataforge.core.logging import get_logger

logger = get_logger(__name__)


_SYSTEM_PROMPT = (
    "You are a senior Spark / Databricks engineer producing the exact"
    " source-code change needed to address a known failure.\n"
    "\n"
    "You receive: the failing run's signature, the structured root-cause"
    " analysis, the typed fix-action chosen by the upstream remediation"
    " layer, and the current contents of the source files you are allowed"
    " to modify.\n"
    "\n"
    "You return a strict CodePatch with one or more CodePatchAction"
    " entries. For each action:\n"
    "- path: must be one of the file paths provided to you (or a sibling"
    " path within the same directory tree for `create`). Never invent"
    " paths outside the working set.\n"
    "- operation: `replace` for an existing file, `create` for a new one.\n"
    "- old_content: for `replace`, the EXACT current contents of the file"
    " as it was given to you. For `create`, leave it empty. Do not"
    " paraphrase, re-indent, or normalize — byte-identical to the input.\n"
    "- new_content: the full file contents after the change. Include the"
    " imports, the unchanged lines, and the edited lines. The applier"
    " writes this verbatim.\n"
    "- rationale: one sentence on why this file specifically is changing.\n"
    "\n"
    "Style rules:\n"
    "- Prefer minimal, surgical edits. Don't reformat untouched code.\n"
    '- For schema-drift fixes, use `pyspark.sql.functions.col("col")'
    ".cast(...)`, `withColumn`, or `selectExpr` — whichever fits the"
    " existing idiom in the file.\n"
    '- For null-safety fixes, prefer `coalesce(col("x"), lit(default))`'
    " over `dropna` unless the RCA specifically says drop.\n"
    "- For partition/skew fixes, edit the relevant `.repartition()`,"
    " `.coalesce()`, or `spark.conf.set(...)` call.\n"
    "- Never edit a file that doesn't need changing.\n"
    "\n"
    "test_commands: 1-3 commands the human can run to verify the patch"
    " (pytest invocations, pyspark --dry-run, sql linting). Empty list is"
    " acceptable if no verification command is obvious.\n"
    "\n"
    "summary: one short sentence describing the change across all"
    " modified files. Do not echo the RCA explanation."
)


def _build_messages(
    run: PipelineRun,
    analysis: RootCauseAnalysis,
    fix_action: FixAction,
    source_files: dict[str, str],
) -> list[Message]:
    return [
        Message(role=Role.SYSTEM, content=_SYSTEM_PROMPT, cache=True),
        Message(
            role=Role.USER,
            content=_render_user_prompt(run, analysis, fix_action, source_files),
        ),
    ]


def _render_user_prompt(
    run: PipelineRun,
    analysis: RootCauseAnalysis,
    fix_action: FixAction,
    source_files: dict[str, str],
) -> str:
    parts: list[str] = []

    parts.append("## Failing run")
    parts.append(f"- run_id: {run.run_id}")
    parts.append(f"- app: {run.app_name}")
    parts.append(f"- status: {run.status.value}")
    if run.failure is not None:
        if run.failure.error_class:
            parts.append(f"- error_class: {run.failure.error_class}")
        if run.failure.message:
            parts.append(f"- failure_message: {run.failure.message[:600]}")

    parts.append("\n## Root cause")
    parts.append(f"- category: {analysis.category.value}")
    parts.append(f"- summary: {analysis.summary}")
    parts.append(f"- explanation: {analysis.explanation}")

    parts.append("\n## Fix action chosen by upstream")
    parts.append(f"- title: {fix_action.title}")
    parts.append(f"- detail: {fix_action.detail}")
    parts.append(f"- kind: {fix_action.kind}")
    if fix_action.parameters:
        parts.append("- parameters:")
        for k, v in fix_action.parameters.items():
            parts.append(f"  - {k}: {v}")
    if fix_action.rollback:
        parts.append(f"- rollback: {fix_action.rollback}")
    if fix_action.estimated_impact:
        parts.append(f"- estimated_impact: {fix_action.estimated_impact}")

    parts.append("\n## Source files you may modify")
    if not source_files:
        parts.append("- (none provided — return an empty patch only if no change is appropriate)")
    for path, content in source_files.items():
        parts.append(f"\n### {path}")
        parts.append("```")
        parts.append(content)
        parts.append("```")

    parts.append("\nProduce the CodePatch.")
    return "\n".join(parts)


class LLMPatchGenerator:
    """LLM-backed code patch generator (no deterministic fallback)."""

    def __init__(self, llm_client: LLMClient) -> None:
        self._llm = llm_client
        self.name = f"llm-patch-v1:{llm_client.model}"

    async def generate(
        self,
        *,
        run: PipelineRun,
        analysis: RootCauseAnalysis,
        fix_action: FixAction,
        source_files: dict[str, str],
    ) -> CodePatch:
        try:
            response = await self._llm.complete(
                ChatRequest(
                    messages=_build_messages(run, analysis, fix_action, source_files),
                    response_schema=CodePatch,
                )
            )
        except LLMError:
            logger.warning(
                "llm_patch.llm_failed",
                run_id=run.run_id,
                fix_action=fix_action.title,
            )
            raise

        parsed = response.parsed
        if not isinstance(parsed, CodePatch):
            logger.warning(
                "llm_patch.no_structured_output",
                run_id=run.run_id,
                provider=response.provider,
            )
            raise LLMError(
                "LLM patch generator did not return a parsed CodePatch; "
                "refusing to fabricate one."
            )
        return parsed
