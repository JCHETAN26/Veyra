"""Tests for the GitHub connector, PR client, and remediation pipeline.

The git half is tested against a real local bare repo on tmp_path — no
GitHub network calls. The PR-API client uses httpx.MockTransport. The
pipeline is exercised with stub connector + PR client + generator so it
covers the success path and every per-stage failure surface
deterministically.
"""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest

from dataforge.contracts.git import (
    BranchPushResult,
    PullRequestResult,
    RepoLocation,
)
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
from dataforge.core.llm import LLMError
from dataforge.datasets.fixtures.buggy_pyspark_schema_drift import (
    BUGGY_PYSPARK_JOB,
)
from dataforge.modules.remediation.git import (
    GitHubPRClient,
    GitHubPRError,
    GitOperationError,
    GitRepoConnector,
    RemediationPipeline,
)

GIT_AVAILABLE = shutil.which("git") is not None
pytestmark = pytest.mark.skipif(
    not GIT_AVAILABLE, reason="git CLI not available in this environment"
)


# --- Local-repo fixture ----------------------------------------------------


def _run_git(cwd: Path, *args: str, env: dict[str, str] | None = None) -> None:
    subprocess.run(  # noqa: ASYNC221  # nosec B603 - controlled test setup
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        env=env,
    )


@pytest.fixture
def local_git_remote(tmp_path: Path) -> Iterator[tuple[Path, str]]:
    """Build a bare 'origin' repo + seed it with the buggy PySpark file.

    Yields (bare_path, file_url) so tests can pass file_url to
    GitRepoConnector.clone(clone_url=...).
    """
    bare = tmp_path / "origin.git"
    _run_git(tmp_path, "init", "--bare", "-b", "main", str(bare))

    seed = tmp_path / "seed"
    seed.mkdir()
    _run_git(seed, "init", "-b", "main")
    _run_git(seed, "config", "user.name", "seed")
    _run_git(seed, "config", "user.email", "seed@example.com")
    (seed / "jobs").mkdir()
    (seed / "jobs" / "customer_cdc.py").write_text(BUGGY_PYSPARK_JOB)
    _run_git(seed, "add", ".")
    _run_git(seed, "commit", "-m", "seed: buggy customer_cdc.py")
    _run_git(seed, "remote", "add", "origin", str(bare))
    _run_git(seed, "push", "origin", "main")

    file_url = f"file://{bare}"
    yield bare, file_url


# --- Fixtures for the pipeline ---------------------------------------------


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
        explanation="The upstream CDC source changed customer_id from BIGINT to STRING.",
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


def _fixed_pyspark() -> str:
    return BUGGY_PYSPARK_JOB.replace(
        '    events = spark.read.json("s3://prod-events/customer_cdc/2026-05-30/")\n',
        '    events = spark.read.json("s3://prod-events/customer_cdc/2026-05-30/")\n'
        '    events = events.withColumn("customer_id", F.col("customer_id").cast("long"))\n',
    )


# --- GitRepoConnector ------------------------------------------------------


async def test_connector_clones_from_local_remote(
    local_git_remote: tuple[Path, str],
) -> None:
    _, url = local_git_remote
    connector = GitRepoConnector(token=None)
    repo = RepoLocation(owner="dataforge", name="local-test")
    checkout = await connector.clone(repo, clone_url=url)
    try:
        assert (checkout / "jobs" / "customer_cdc.py").is_file()
        # Identity was configured.
        result = subprocess.run(  # noqa: ASYNC221  # nosec B603 - controlled test inspection
            ["git", "config", "--get", "user.email"],
            cwd=checkout,
            check=True,
            capture_output=True,
            text=True,
        )
        assert result.stdout.strip() == "bot@dataforge.ai"
    finally:
        shutil.rmtree(checkout, ignore_errors=True)


async def test_connector_apply_and_push_writes_branch_to_remote(
    local_git_remote: tuple[Path, str],
) -> None:
    bare, url = local_git_remote
    connector = GitRepoConnector(token=None)
    repo = RepoLocation(owner="dataforge", name="local-test")
    checkout = await connector.clone(repo, clone_url=url)
    try:
        patch = CodePatch(
            summary="cast customer_id to long",
            actions=[
                CodePatchAction(
                    path="jobs/customer_cdc.py",
                    operation=PatchOperation.REPLACE,
                    old_content=BUGGY_PYSPARK_JOB,
                    new_content=_fixed_pyspark(),
                    rationale="cast to long",
                )
            ],
        )
        result = await connector.apply_and_push(
            repo_path=checkout,
            patch=patch,
            branch_name="dataforge/fix/demo-001",
            commit_message="fix(dependency_failure): cast customer_id to long",
            push=True,
        )
        assert isinstance(result, BranchPushResult)
        assert result.pushed is True
        assert result.dry_run is False
        assert result.commit_sha and len(result.commit_sha) == 40

        # Verify the branch landed on the bare remote.
        check = subprocess.run(  # noqa: ASYNC221  # nosec B603 - controlled test inspection
            ["git", "branch", "-a"],
            cwd=bare,
            check=True,
            capture_output=True,
            text=True,
        )
        assert "dataforge/fix/demo-001" in check.stdout
    finally:
        shutil.rmtree(checkout, ignore_errors=True)


async def test_connector_dry_run_commits_locally_but_does_not_push(
    local_git_remote: tuple[Path, str],
) -> None:
    bare, url = local_git_remote
    connector = GitRepoConnector(token=None)
    repo = RepoLocation(owner="dataforge", name="local-test")
    checkout = await connector.clone(repo, clone_url=url)
    try:
        patch = CodePatch(
            summary="x",
            actions=[
                CodePatchAction(
                    path="jobs/customer_cdc.py",
                    operation=PatchOperation.REPLACE,
                    old_content=BUGGY_PYSPARK_JOB,
                    new_content=_fixed_pyspark(),
                    rationale="r",
                )
            ],
        )
        result = await connector.apply_and_push(
            repo_path=checkout,
            patch=patch,
            branch_name="dataforge/dry/demo-001",
            commit_message="local-only",
            push=False,
        )
        assert result.dry_run is True
        assert result.pushed is False

        # Remote does NOT carry the branch.
        check = subprocess.run(  # noqa: ASYNC221  # nosec B603 - controlled test inspection
            ["git", "branch", "-a"],
            cwd=bare,
            check=True,
            capture_output=True,
            text=True,
        )
        assert "dataforge/dry/demo-001" not in check.stdout
    finally:
        shutil.rmtree(checkout, ignore_errors=True)


async def test_connector_refuses_partial_apply(
    local_git_remote: tuple[Path, str],
) -> None:
    """A patch that fails drift-detection must not commit/push at all."""
    _, url = local_git_remote
    connector = GitRepoConnector(token=None)
    repo = RepoLocation(owner="dataforge", name="local-test")
    checkout = await connector.clone(repo, clone_url=url)
    try:
        patch = CodePatch(
            summary="x",
            actions=[
                CodePatchAction(
                    path="jobs/customer_cdc.py",
                    operation=PatchOperation.REPLACE,
                    old_content="drifted content that doesn't match",
                    new_content="new",
                    rationale="r",
                )
            ],
        )
        with pytest.raises(GitOperationError):
            await connector.apply_and_push(
                repo_path=checkout,
                patch=patch,
                branch_name="should-not-exist",
                commit_message="should not be committed",
                push=False,
            )
    finally:
        shutil.rmtree(checkout, ignore_errors=True)


async def test_connector_raises_clearly_on_bad_clone() -> None:
    connector = GitRepoConnector(token=None)
    repo = RepoLocation(owner="x", name="y")
    with pytest.raises(GitOperationError):
        await connector.clone(repo, clone_url="file:///does-not-exist.git")


# --- GitHubPRClient --------------------------------------------------------


async def test_pr_client_posts_to_pulls_endpoint() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["method"] = request.method
        captured["auth"] = request.headers.get("authorization")
        captured["body"] = request.read()
        return httpx.Response(
            201,
            json={
                "number": 42,
                "html_url": "https://github.com/acme/widgets/pull/42",
                "title": "fix(...)",
                "head": {"ref": "dataforge/fix/demo-001"},
                "base": {"ref": "main"},
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        pr_client = GitHubPRClient(token="ghp_test", http_client=client)
        result = await pr_client.open_pr(
            repo=RepoLocation(owner="acme", name="widgets"),
            head_branch="dataforge/fix/demo-001",
            base_branch="main",
            title="fix(...)",
            body="...",
        )

    assert isinstance(result, PullRequestResult)
    assert result.number == 42
    assert result.url == "https://github.com/acme/widgets/pull/42"
    assert "/repos/acme/widgets/pulls" in str(captured["url"])
    assert captured["method"] == "POST"
    assert captured["auth"] == "Bearer ghp_test"


async def test_pr_client_dry_run_skips_network() -> None:
    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("dry-run should not perform any HTTP call")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        pr_client = GitHubPRClient(token=None, http_client=client)
        result = await pr_client.open_pr(
            repo=RepoLocation(owner="acme", name="widgets"),
            head_branch="dataforge/dry/demo-001",
            base_branch="main",
            title="t",
            body="b",
            dry_run=True,
        )

    assert result.dry_run is True
    assert result.number is None
    assert result.url is None


async def test_pr_client_raises_without_token_in_real_mode() -> None:
    pr_client = GitHubPRClient(token=None)
    with pytest.raises(GitHubPRError):
        await pr_client.open_pr(
            repo=RepoLocation(owner="x", name="y"),
            head_branch="h",
            base_branch="b",
            title="t",
            body="b",
            dry_run=False,
        )


async def test_pr_client_surfaces_github_errors() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(422, text="Validation Failed: branch not found")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        pr_client = GitHubPRClient(token="ghp_x", http_client=client)
        with pytest.raises(GitHubPRError) as excinfo:
            await pr_client.open_pr(
                repo=RepoLocation(owner="x", name="y"),
                head_branch="h",
                base_branch="b",
                title="t",
                body="b",
            )
        assert "422" in str(excinfo.value)


# --- RemediationPipeline ---------------------------------------------------


class _StubPatchGenerator:
    """Bypasses LLM. Records the call and returns a canned CodePatch."""

    name = "stub-patch-v1"

    def __init__(
        self, patch: CodePatch | None = None, raise_with: BaseException | None = None
    ) -> None:
        self._patch = patch
        self._raise = raise_with
        self.received: list[dict[str, object]] = []

    async def generate(
        self,
        *,
        run: PipelineRun,
        analysis: RootCauseAnalysis,
        fix_action: FixAction,
        source_files: dict[str, str],
    ) -> CodePatch:
        self.received.append({"run_id": run.run_id, "files": list(source_files)})
        if self._raise is not None:
            raise self._raise
        assert self._patch is not None
        return self._patch


async def test_pipeline_runs_end_to_end_in_dry_run_against_local_remote(
    local_git_remote: tuple[Path, str],
) -> None:
    _, url = local_git_remote
    patch = CodePatch(
        summary="cast customer_id to long",
        actions=[
            CodePatchAction(
                path="jobs/customer_cdc.py",
                operation=PatchOperation.REPLACE,
                old_content=BUGGY_PYSPARK_JOB,
                new_content=_fixed_pyspark(),
                rationale="r",
            )
        ],
    )
    generator = _StubPatchGenerator(patch=patch)
    pipeline = RemediationPipeline(
        repo_connector=GitRepoConnector(token=None),
        pr_client=GitHubPRClient(token=None),
        patch_generator=generator,  # type: ignore[arg-type]
    )

    result = await pipeline.execute(
        repo=RepoLocation(owner="dataforge", name="local-test"),
        run=_run(),
        analysis=_analysis(),
        fix_action=_fix_action(),
        source_file_paths=["jobs/customer_cdc.py"],
        dry_run=True,
        keep_workspace=False,
        clone_url_override=url,
    )

    assert result.failed_stage is None, result.error
    assert result.patch_summary.startswith("cast")
    assert result.push is not None
    assert result.push.dry_run is True
    assert result.pull_request is not None
    assert result.pull_request.dry_run is True
    assert generator.received  # generator saw the source file


async def test_pipeline_records_patch_generation_failure(
    local_git_remote: tuple[Path, str],
) -> None:
    _, url = local_git_remote
    generator = _StubPatchGenerator(raise_with=LLMError("rate limited"))
    pipeline = RemediationPipeline(
        repo_connector=GitRepoConnector(token=None),
        pr_client=GitHubPRClient(token=None),
        patch_generator=generator,  # type: ignore[arg-type]
    )

    result = await pipeline.execute(
        repo=RepoLocation(owner="dataforge", name="local-test"),
        run=_run(),
        analysis=_analysis(),
        fix_action=_fix_action(),
        source_file_paths=["jobs/customer_cdc.py"],
        dry_run=True,
        clone_url_override=url,
    )

    assert result.failed_stage == "patch_generation"
    assert "rate limited" in (result.error or "")
    assert result.push is None
    assert result.pull_request is None


async def test_pipeline_records_clone_failure() -> None:
    """A bad clone URL stops the pipeline at stage 1 with a clean envelope."""
    generator = _StubPatchGenerator(
        patch=CodePatch(
            summary="never reached",
            actions=[
                CodePatchAction(
                    path="x",
                    operation=PatchOperation.CREATE,
                    old_content="",
                    new_content="y",
                    rationale="r",
                )
            ],
        )
    )
    pipeline = RemediationPipeline(
        repo_connector=GitRepoConnector(token=None),
        pr_client=GitHubPRClient(token=None),
        patch_generator=generator,  # type: ignore[arg-type]
    )

    result = await pipeline.execute(
        repo=RepoLocation(owner="x", name="y"),
        run=_run(),
        analysis=_analysis(),
        fix_action=_fix_action(),
        source_file_paths=["x"],
        dry_run=True,
        clone_url_override="file:///definitely-not-a-real-repo.git",
    )

    assert result.failed_stage == "clone"
    assert result.error
    assert generator.received == []  # patch generator was never called
