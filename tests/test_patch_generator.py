"""Unit tests for the LLM patch generator + the on-disk applier.

The generator is exercised against a stub LLMClient that returns a
pre-baked CodePatch — same pattern used by the LLM RCA + fix-generator
tests. The applier runs against a real tmp_path so file I/O, drift
detection, CREATE refusal, and path-escape refusal are all exercised
for real.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dataforge.contracts.patch import (
    CodePatch,
    CodePatchAction,
    PatchOperation,
)
from dataforge.contracts.rca import (
    CauseCategory,
    RecommendedAction,
    RootCauseAnalysis,
)
from dataforge.contracts.remediation_workflow import FixAction
from dataforge.contracts.telemetry import (
    FailureInfo,
    PipelineRun,
    RunMetrics,
    RunStatus,
)
from dataforge.core.llm import ChatRequest, ChatResponse, LLMError, Usage
from dataforge.datasets.fixtures.buggy_pyspark_schema_drift import (
    BUGGY_PYSPARK_JOB,
)
from dataforge.modules.remediation.patches import LLMPatchGenerator, apply_patch

# --- Fixtures --------------------------------------------------------------


class _StubLLM:
    provider = "null"

    def __init__(self, model: str = "stub-model") -> None:
        self.model = model
        self.received: list[ChatRequest] = []
        self.next_response: CodePatch | None = None
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
            usage=Usage(input_tokens=200, output_tokens=400),
            provider="null",  # type: ignore[arg-type]
        )

    async def aclose(self) -> None:
        return None


def _run() -> PipelineRun:
    return PipelineRun(
        run_id="demo-001",
        app_name="customer_cdc",
        status=RunStatus.FAILED,
        metrics=RunMetrics(num_tasks=10, num_failed_tasks=1),
        failure=FailureInfo(
            error_class="java.lang.ClassCastException",
            message="java.lang.String cannot be cast to java.lang.Long",
        ),
    )


def _analysis() -> RootCauseAnalysis:
    return RootCauseAnalysis(
        analysis_id="rca-demo-001",
        run_id="demo-001",
        category=CauseCategory.DEPENDENCY_FAILURE,
        summary="Schema drift on customer_id (long -> string upstream).",
        explanation=(
            "The CDC source changed customer_id from BIGINT to STRING; the "
            "join in customer_cdc.py still expects long. Cast at ingestion."
        ),
        contributing_factors=["ClassCastException at column customer_id"],
        recommended_actions=[
            RecommendedAction(
                title="Cast customer_id to long after ingestion",
                detail="Use F.col('customer_id').cast('long')",
                kind="code_change",
            )
        ],
        confidence=0.85,
    )


def _fix_action() -> FixAction:
    return FixAction(
        title="Cast customer_id to long after ingestion",
        detail="Use F.col('customer_id').cast('long') before the join.",
        kind="code_change",
        parameters={},
        confidence=0.8,
        rollback="Remove the cast() call.",
        estimated_impact="Eliminates the ClassCastException at the join.",
    )


def _patched_pyspark_job() -> str:
    """The corrected file the LLM should produce — kept as a constant so the
    applier test stays deterministic and the generator test asserts an exact
    new_content."""
    return BUGGY_PYSPARK_JOB.replace(
        '    events = spark.read.json("s3://prod-events/customer_cdc/2026-05-30/")\n',
        '    events = spark.read.json("s3://prod-events/customer_cdc/2026-05-30/")\n'
        '    events = events.withColumn("customer_id", F.col("customer_id").cast("long"))\n',
    )


# --- Generator -------------------------------------------------------------


async def test_generator_returns_structured_patch() -> None:
    llm = _StubLLM()
    llm.next_response = CodePatch(
        summary="Cast customer_id to long after ingestion to fix schema drift.",
        actions=[
            CodePatchAction(
                path="jobs/customer_cdc.py",
                operation=PatchOperation.REPLACE,
                old_content=BUGGY_PYSPARK_JOB,
                new_content=_patched_pyspark_job(),
                rationale=(
                    "Cast the now-string customer_id back to long so the "
                    "downstream join keeps its type."
                ),
            )
        ],
        test_commands=[
            "uv run python -m py_compile jobs/customer_cdc.py",
        ],
        cause_category="dependency_failure",
        confidence=0.82,
    )

    generator = LLMPatchGenerator(llm_client=llm)  # type: ignore[arg-type]
    patch = await generator.generate(
        run=_run(),
        analysis=_analysis(),
        fix_action=_fix_action(),
        source_files={"jobs/customer_cdc.py": BUGGY_PYSPARK_JOB},
    )
    assert patch.summary.startswith("Cast")
    assert len(patch.actions) == 1
    action = patch.actions[0]
    assert action.path == "jobs/customer_cdc.py"
    assert action.operation is PatchOperation.REPLACE
    assert action.old_content == BUGGY_PYSPARK_JOB
    assert 'cast("long")' in action.new_content


async def test_generator_includes_source_files_in_prompt() -> None:
    llm = _StubLLM()
    llm.next_response = CodePatch(
        summary="x",
        actions=[
            CodePatchAction(
                path="jobs/customer_cdc.py",
                operation=PatchOperation.REPLACE,
                old_content=BUGGY_PYSPARK_JOB,
                new_content=_patched_pyspark_job(),
                rationale="x",
            )
        ],
    )
    generator = LLMPatchGenerator(llm_client=llm)  # type: ignore[arg-type]
    await generator.generate(
        run=_run(),
        analysis=_analysis(),
        fix_action=_fix_action(),
        source_files={"jobs/customer_cdc.py": BUGGY_PYSPARK_JOB},
    )

    user_msg = llm.received[0].messages[1].content
    assert "ClassCastException" in user_msg
    assert "customer_cdc.py" in user_msg
    assert "apply_cdc" in user_msg  # from the fixture body
    assert "dependency_failure" in user_msg


async def test_generator_propagates_llm_errors_without_fallback() -> None:
    """Patches must never be silently fabricated when the LLM fails."""
    llm = _StubLLM()
    llm.raise_for = LLMError("upstream busy")
    generator = LLMPatchGenerator(llm_client=llm)  # type: ignore[arg-type]
    with pytest.raises(LLMError):
        await generator.generate(
            run=_run(),
            analysis=_analysis(),
            fix_action=_fix_action(),
            source_files={"jobs/customer_cdc.py": BUGGY_PYSPARK_JOB},
        )


async def test_generator_raises_when_no_parsed_output() -> None:
    """If the provider returns text but no parsed CodePatch, refuse."""

    class _RawProvider(_StubLLM):
        async def complete(self, request: ChatRequest) -> ChatResponse:
            return ChatResponse(
                content="not a CodePatch",
                parsed=None,
                model=request.model or self.model,
                usage=Usage(input_tokens=1, output_tokens=1),
                provider="null",  # type: ignore[arg-type]
            )

    generator = LLMPatchGenerator(llm_client=_RawProvider())  # type: ignore[arg-type]
    with pytest.raises(LLMError):
        await generator.generate(
            run=_run(),
            analysis=_analysis(),
            fix_action=_fix_action(),
            source_files={"jobs/customer_cdc.py": BUGGY_PYSPARK_JOB},
        )


# --- Applier ---------------------------------------------------------------


def _seed_file(working: Path, rel: str, contents: str) -> Path:
    target = working / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(contents, encoding="utf-8")
    return target


def test_apply_replace_writes_new_content(tmp_path: Path) -> None:
    target = _seed_file(tmp_path, "jobs/customer_cdc.py", BUGGY_PYSPARK_JOB)
    patch = CodePatch(
        summary="cast id",
        actions=[
            CodePatchAction(
                path="jobs/customer_cdc.py",
                operation=PatchOperation.REPLACE,
                old_content=BUGGY_PYSPARK_JOB,
                new_content=_patched_pyspark_job(),
                rationale="r",
            )
        ],
    )
    result = apply_patch(tmp_path, patch)
    assert result.fully_applied
    assert result.applied_actions == 1
    assert target.read_text() == _patched_pyspark_job()


def test_apply_refuses_replace_when_file_drifted(tmp_path: Path) -> None:
    target = _seed_file(tmp_path, "jobs/customer_cdc.py", "# different content\n")
    patch = CodePatch(
        summary="cast id",
        actions=[
            CodePatchAction(
                path="jobs/customer_cdc.py",
                operation=PatchOperation.REPLACE,
                old_content=BUGGY_PYSPARK_JOB,  # not what's on disk
                new_content=_patched_pyspark_job(),
                rationale="r",
            )
        ],
    )
    result = apply_patch(tmp_path, patch)
    assert not result.fully_applied
    assert result.refused_actions == 1
    assert "drifted" in result.results[0].detail
    assert target.read_text() == "# different content\n"


def test_apply_refuses_replace_when_file_missing(tmp_path: Path) -> None:
    patch = CodePatch(
        summary="x",
        actions=[
            CodePatchAction(
                path="jobs/customer_cdc.py",
                operation=PatchOperation.REPLACE,
                old_content="",
                new_content="new",
                rationale="r",
            )
        ],
    )
    result = apply_patch(tmp_path, patch)
    assert result.refused_actions == 1
    assert "does not exist" in result.results[0].detail


def test_apply_create_writes_new_file(tmp_path: Path) -> None:
    patch = CodePatch(
        summary="add new file",
        actions=[
            CodePatchAction(
                path="jobs/customer_cdc_test.py",
                operation=PatchOperation.CREATE,
                old_content="",
                new_content="def test_apply(): assert True\n",
                rationale="r",
            )
        ],
    )
    result = apply_patch(tmp_path, patch)
    assert result.fully_applied
    created = tmp_path / "jobs/customer_cdc_test.py"
    assert created.read_text() == "def test_apply(): assert True\n"


def test_apply_refuses_create_when_target_exists(tmp_path: Path) -> None:
    _seed_file(tmp_path, "jobs/already_here.py", "# existing\n")
    patch = CodePatch(
        summary="x",
        actions=[
            CodePatchAction(
                path="jobs/already_here.py",
                operation=PatchOperation.CREATE,
                old_content="",
                new_content="new",
                rationale="r",
            )
        ],
    )
    result = apply_patch(tmp_path, patch)
    assert result.refused_actions == 1
    assert "already exists" in result.results[0].detail


def test_apply_refuses_path_escape(tmp_path: Path) -> None:
    """Paths that resolve outside the working dir are refused."""
    _seed_file(tmp_path, "jobs/customer_cdc.py", BUGGY_PYSPARK_JOB)
    patch = CodePatch(
        summary="x",
        actions=[
            CodePatchAction(
                path="../etc/passwd",
                operation=PatchOperation.REPLACE,
                old_content="root:x:0:0:root",
                new_content="root:x:0:0:OWNED",
                rationale="malicious",
            )
        ],
    )
    result = apply_patch(tmp_path, patch)
    assert result.refused_actions == 1
    assert "escapes" in result.results[0].detail


def test_apply_runs_each_action_independently(tmp_path: Path) -> None:
    """A refused action does not prevent the next action from applying."""
    _seed_file(tmp_path, "jobs/customer_cdc.py", BUGGY_PYSPARK_JOB)
    patch = CodePatch(
        summary="two changes",
        actions=[
            CodePatchAction(
                path="jobs/customer_cdc.py",
                operation=PatchOperation.REPLACE,
                old_content="drifted",  # will be refused
                new_content="x",
                rationale="r",
            ),
            CodePatchAction(
                path="jobs/new_helper.py",
                operation=PatchOperation.CREATE,
                old_content="",
                new_content="# helper\n",
                rationale="r",
            ),
        ],
    )
    result = apply_patch(tmp_path, patch)
    assert result.applied_actions == 1
    assert result.refused_actions == 1
    assert (tmp_path / "jobs/new_helper.py").exists()


def test_apply_raises_when_working_dir_missing(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist"
    patch = CodePatch(
        summary="x",
        actions=[
            CodePatchAction(
                path="a.py",
                operation=PatchOperation.CREATE,
                old_content="",
                new_content="x",
                rationale="r",
            )
        ],
    )
    with pytest.raises(FileNotFoundError):
        apply_patch(missing, patch)
