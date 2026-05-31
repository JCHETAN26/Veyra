"""End-to-end remediation pipeline.

Single async entry point that wires together the existing pieces from
tasks #14 + this task:

  RCA + FixAction
    -> read source files from the cloned repo
    -> LLMPatchGenerator -> CodePatch
    -> GitRepoConnector.apply_and_push (branch + commit + push)
    -> GitHubPRClient.open_pr

Each stage's outcome is recorded in `RemediationPipelineResult` so a
caller can render "we got as far as <stage> and stopped because <reason>"
without scraping logs. Stages run in order; the first failure short-
circuits the rest but the result is still well-formed.

The pipeline is dependency-injected — the connector, PR client, and
generator are all passed in — so tests substitute stubs without
patching globals.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from dataforge.contracts.git import (
    BranchPushResult,
    PullRequestResult,
    RemediationPipelineResult,
    RepoLocation,
)
from dataforge.contracts.rca import RootCauseAnalysis
from dataforge.contracts.remediation_workflow import FixAction
from dataforge.contracts.telemetry import PipelineRun
from dataforge.core.errors import DataForgeError
from dataforge.core.llm import LLMError
from dataforge.core.logging import get_logger
from dataforge.modules.remediation.git.github_pr import GitHubPRClient, GitHubPRError
from dataforge.modules.remediation.git.repo import GitOperationError, GitRepoConnector
from dataforge.modules.remediation.patches.llm_based import LLMPatchGenerator

logger = get_logger(__name__)


class RemediationPipelineError(DataForgeError):
    code = "remediation_pipeline_error"
    status_code = 502


class RemediationPipeline:
    """Orchestrates clone -> generate -> apply -> push -> PR."""

    def __init__(
        self,
        *,
        repo_connector: GitRepoConnector,
        pr_client: GitHubPRClient,
        patch_generator: LLMPatchGenerator,
    ) -> None:
        self._repo_connector = repo_connector
        self._pr_client = pr_client
        self._patch_generator = patch_generator

    async def execute(
        self,
        *,
        repo: RepoLocation,
        run: PipelineRun,
        analysis: RootCauseAnalysis,
        fix_action: FixAction,
        source_file_paths: list[str],
        base_branch: str | None = None,
        branch_name: str | None = None,
        dry_run: bool = False,
        keep_workspace: bool = False,
        clone_url_override: str | None = None,
    ) -> RemediationPipelineResult:
        """Run the full remediation against `repo`.

        Args:
            repo: target repository.
            run / analysis / fix_action: produced by the upstream loop.
            source_file_paths: repo-relative paths the patch is allowed
                to touch; their contents are read from the clone and
                handed to the LLMPatchGenerator. Files outside this list
                are invisible to the generator.
            base_branch: PR target branch. Defaults to repo.default_branch.
            branch_name: head branch name. Defaults to a deterministic
                run-scoped name so retries are idempotent.
            dry_run: when True, push and PR are skipped but the patch is
                generated, applied locally, and a local commit is made.
            keep_workspace: when True (or dry-run), the cloned working
                copy is left on disk for the caller to inspect.

        Returns a RemediationPipelineResult — never raises for "expected"
        failures (clone failed, patch refused, PR rejected). Those land
        in `failed_stage` + `error`. Unexpected errors still raise.
        """
        base = base_branch or repo.default_branch
        branch = branch_name or self._default_branch_for(run)
        result = RemediationPipelineResult(run_id=run.run_id, patch_summary="")

        # --- 1. Clone ------------------------------------------------------
        try:
            clone_path = await self._repo_connector.clone(repo, clone_url=clone_url_override)
        except GitOperationError as exc:
            result.failed_stage = "clone"
            result.error = str(exc)
            return result

        try:
            # --- 2. Read source files -----------------------------------
            source_files = self._read_source_files(clone_path, source_file_paths)

            # --- 3. Generate patch --------------------------------------
            try:
                patch = await self._patch_generator.generate(
                    run=run,
                    analysis=analysis,
                    fix_action=fix_action,
                    source_files=source_files,
                )
            except LLMError as exc:
                result.failed_stage = "patch_generation"
                result.error = str(exc)
                return result

            result.patch_summary = patch.summary

            # --- 4. Apply + commit + push -------------------------------
            commit_message = self._commit_message(run, analysis, patch.summary)
            try:
                push_result: BranchPushResult = await self._repo_connector.apply_and_push(
                    repo_path=clone_path,
                    patch=patch,
                    branch_name=branch,
                    commit_message=commit_message,
                    push=not dry_run,
                )
            except GitOperationError as exc:
                result.failed_stage = "apply_and_push"
                result.error = str(exc)
                return result

            result.push = push_result

            # --- 5. Open PR --------------------------------------------
            try:
                pr_result: PullRequestResult = await self._pr_client.open_pr(
                    repo=repo,
                    head_branch=branch,
                    base_branch=base,
                    title=self._pr_title(run, analysis),
                    body=self._pr_body(run, analysis, patch.summary, fix_action),
                    dry_run=dry_run,
                )
            except GitHubPRError as exc:
                result.failed_stage = "open_pr"
                result.error = str(exc)
                return result

            result.pull_request = pr_result
            return result

        finally:
            if not (dry_run or keep_workspace):
                shutil.rmtree(clone_path, ignore_errors=True)

    # --- helpers -----------------------------------------------------------

    def _default_branch_for(self, run: PipelineRun) -> str:
        # Deterministic so re-running the pipeline against the same run
        # updates the same branch instead of creating drift.
        return f"dataforge/fix/{run.run_id}"

    def _read_source_files(self, clone_path: Path, paths: list[str]) -> dict[str, str]:
        source_files: dict[str, str] = {}
        for rel in paths:
            target = (clone_path / rel).resolve()
            try:
                target.relative_to(clone_path.resolve())
            except ValueError:
                logger.warning("pipeline.path_escape_skipped", path=rel)
                continue
            if not target.exists():
                logger.warning("pipeline.source_file_missing", path=rel)
                continue
            source_files[rel] = target.read_text(encoding="utf-8")
        return source_files

    def _commit_message(self, run: PipelineRun, analysis: RootCauseAnalysis, summary: str) -> str:
        return (
            f"fix({analysis.category.value}): {summary}\n"
            f"\n"
            f"Auto-generated by DataForge AI from run {run.run_id}.\n"
            f"Root-cause analyzer: {analysis.analyzer}\n"
            f"Confidence: {analysis.confidence:.2f}\n"
        )

    def _pr_title(self, run: PipelineRun, analysis: RootCauseAnalysis) -> str:
        return f"fix({analysis.category.value}): {analysis.summary}".strip()

    def _pr_body(
        self,
        run: PipelineRun,
        analysis: RootCauseAnalysis,
        patch_summary: str,
        fix_action: FixAction,
    ) -> str:
        lines = [
            "## Auto-generated remediation",
            "",
            f"**Run:** `{run.run_id}` (`{run.app_name}`)",
            f"**Cause category:** `{analysis.category.value}`",
            f"**Analyzer confidence:** {analysis.confidence:.2f}",
            "",
            "### Root-cause analysis",
            analysis.explanation,
            "",
            "### Proposed fix",
            f"- **Action:** {fix_action.title}",
            f"- **Detail:** {fix_action.detail}",
        ]
        if fix_action.rollback:
            lines.append(f"- **Rollback:** {fix_action.rollback}")
        if fix_action.estimated_impact:
            lines.append(f"- **Estimated impact:** {fix_action.estimated_impact}")
        lines += [
            "",
            "### Patch summary",
            patch_summary,
            "",
            "---",
            "_Generated by DataForge AI._",
        ]
        return "\n".join(lines)
