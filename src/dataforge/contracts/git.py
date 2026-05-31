"""Git + GitHub PR contracts.

These types are the boundary the remediation pipeline crosses when it
goes from "we have a CodePatch" to "we have an open pull request." They
are deliberately HTTP-API-shaped (owner + repo + branch + token) rather
than VCS-shaped, so swapping GitHub for a different forge later is a
matter of writing a new client + connector pair behind the same
contracts.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class RepoLocation(BaseModel):
    """Identifies a repository on a remote forge."""

    owner: str = Field(..., min_length=1, description="GitHub user or org.")
    name: str = Field(..., min_length=1, description="Repo name without `.git`.")
    default_branch: str = "main"

    @property
    def clone_url(self) -> str:
        """HTTPS clone URL. Credentials are injected at clone time, not here."""
        return f"https://github.com/{self.owner}/{self.name}.git"

    @property
    def api_repo_path(self) -> str:
        """Path fragment used in GitHub REST endpoints."""
        return f"{self.owner}/{self.name}"


class BranchPushResult(BaseModel):
    """Outcome of cloning + branching + pushing a remediation patch."""

    branch: str
    commit_sha: str
    files_changed: list[str] = Field(default_factory=list)
    pushed: bool = False
    pushed_at: datetime | None = None
    dry_run: bool = False


class PullRequestResult(BaseModel):
    """The opened PR (or what would have been opened, in dry-run)."""

    number: int | None = None  # None in dry-run mode
    url: str | None = None
    title: str
    head_branch: str
    base_branch: str
    dry_run: bool = False
    opened_at: datetime | None = None


class RemediationPipelineResult(BaseModel):
    """Top-level envelope returned by the pipeline.

    Either every stage succeeded (push + pr both populated) or one of the
    earlier stages refused (patch_apply may be partial; push and pr None).
    Callers should inspect `error` and `failed_stage` for the failure
    mode.
    """

    run_id: str
    patch_summary: str
    push: BranchPushResult | None = None
    pull_request: PullRequestResult | None = None
    failed_stage: str | None = None
    error: str | None = None
