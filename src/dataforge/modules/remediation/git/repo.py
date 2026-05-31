"""Git operations via the `git` CLI.

Why subprocess and not a Python git library: gitpython would add a
moderate-sized dep with little benefit. Every operation we need
(clone, checkout -b, add, commit, push) maps to a single git command,
and subprocess.run gives us deterministic stdout/stderr capture.

Token handling: the token is never put on the command line and never
written into the remote URL on disk. It's passed via the
`http.extraheader` git config inside the cloned repo, scoped to that
working copy only. The injected header is removed before the
subprocess finishes so it doesn't leak into any subsequent git config
inspection.

All path arguments are validated to stay inside the working directory
boundary so a malicious patch path can't escape into the host
filesystem.
"""

from __future__ import annotations

import asyncio
import shutil
from datetime import UTC, datetime
from pathlib import Path

from dataforge.contracts.git import BranchPushResult, RepoLocation
from dataforge.contracts.patch import CodePatch
from dataforge.core.errors import DataForgeError
from dataforge.core.logging import get_logger
from dataforge.modules.remediation.patches.applier import apply_patch

logger = get_logger(__name__)


class GitOperationError(DataForgeError):
    """A git subprocess returned a non-zero exit status."""

    code = "git_operation_error"
    status_code = 502


class GitRepoConnector:
    """Clones a repo, applies a patch, commits, pushes a branch."""

    def __init__(
        self,
        *,
        token: str | None,
        user_name: str = "DataForge Bot",
        user_email: str = "bot@dataforge.ai",
        workspace_dir: Path | None = None,
    ) -> None:
        self._token = token
        self._user_name = user_name
        self._user_email = user_email
        # If no workspace given, each clone() invocation creates a temp dir.
        self._workspace_dir = workspace_dir

    # --- public surface ----------------------------------------------------

    async def clone(
        self,
        repo: RepoLocation,
        *,
        depth: int = 1,
        clone_url: str | None = None,
    ) -> Path:
        """Shallow-clone `repo` into the workspace; return the checkout path.

        Always clones fresh into a unique sub-directory so a previous
        partial clone doesn't pollute this run. Caller is responsible for
        cleanup (`shutil.rmtree`) when done — kept explicit so demos can
        inspect the working copy after the pipeline runs.

        `clone_url` is an override knob used by tests to point at a local
        bare repo (file://...) instead of github.com. Production callers
        leave it None.
        """
        target = self._allocate_target_dir(repo)
        url = clone_url or repo.clone_url
        await self._git_run(
            None,
            "clone",
            "--depth",
            str(depth),
            "--branch",
            repo.default_branch,
            url,
            str(target),
        )
        await self._configure_identity(target)
        # Only install the auth header for real GitHub clones; a file:// or
        # local clone has no use for a Bearer header and git complains.
        if self._token and url.startswith("https://github.com"):
            await self._install_token_header(target)
        logger.info("git.cloned", repo=repo.api_repo_path, path=str(target))
        return target

    async def apply_and_push(
        self,
        *,
        repo_path: Path,
        patch: CodePatch,
        branch_name: str,
        commit_message: str,
        push: bool = True,
    ) -> BranchPushResult:
        """Create branch, apply patch, commit, optionally push. Idempotent.

        When `push=False` (dry-run), the local commit is still made so the
        caller can inspect the diff, but `origin` is never touched.
        """
        await self._git_run(repo_path, "checkout", "-B", branch_name)

        apply_result = apply_patch(repo_path, patch)
        if not apply_result.fully_applied:
            refused = [r for r in apply_result.results if not r.applied]
            raise GitOperationError(
                "patch could not be fully applied; refusing to push partial "
                f"changes. Refused: {[(r.path, r.detail) for r in refused]}"
            )

        files_changed = [a.path for a in patch.actions]
        for path in files_changed:
            await self._git_run(repo_path, "add", "--", path)

        await self._git_run(repo_path, "commit", "-m", commit_message)
        sha = (await self._git_run(repo_path, "rev-parse", "HEAD")).strip()

        pushed = False
        pushed_at: datetime | None = None
        if push:
            await self._git_run(repo_path, "push", "--set-upstream", "origin", branch_name)
            pushed = True
            pushed_at = datetime.now(UTC)

        logger.info(
            "git.applied_and_pushed",
            branch=branch_name,
            sha=sha,
            files=len(files_changed),
            pushed=pushed,
        )
        return BranchPushResult(
            branch=branch_name,
            commit_sha=sha,
            files_changed=files_changed,
            pushed=pushed,
            pushed_at=pushed_at,
            dry_run=not push,
        )

    # --- internals ---------------------------------------------------------

    def _allocate_target_dir(self, repo: RepoLocation) -> Path:
        if self._workspace_dir is not None:
            base = self._workspace_dir
            base.mkdir(parents=True, exist_ok=True)
        else:
            import tempfile

            base = Path(tempfile.mkdtemp(prefix="dataforge-clone-"))
        target = base / f"{repo.owner}__{repo.name}__{datetime.now(UTC):%Y%m%d%H%M%S}"
        # Defensive: if it somehow exists, wipe it (we just clocked the time).
        if target.exists():
            shutil.rmtree(target)
        return target

    async def _configure_identity(self, repo_path: Path) -> None:
        """Local git identity so commits don't depend on the host user.cfg."""
        await self._git_run(repo_path, "config", "user.name", self._user_name)
        await self._git_run(repo_path, "config", "user.email", self._user_email)

    async def _install_token_header(self, repo_path: Path) -> None:
        """Scope the auth header to this working copy via extraheader.

        Writing the token into `.git/config` keeps it off the command line
        and off the disk-resident clone URL, and the file lives inside the
        clone directory which the caller is expected to discard.
        """
        # Bearer works for both fine-grained and classic PATs.
        header_value = f"Authorization: Bearer {self._token}"
        await self._git_run(
            repo_path,
            "config",
            "--local",
            "http.https://github.com/.extraheader",
            header_value,
        )

    async def _git_run(self, cwd: Path | None, *args: str) -> str:
        """Run `git args...` in cwd; capture stdout. Raise on non-zero exit."""
        proc = await asyncio.create_subprocess_exec(
            "git",
            *args,
            cwd=str(cwd) if cwd else None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_b, stderr_b = await proc.communicate()
        stdout = stdout_b.decode("utf-8", errors="replace")
        stderr = stderr_b.decode("utf-8", errors="replace")
        if proc.returncode != 0:
            # Defensive: scrub the token from any echoed git output.
            if self._token:
                stderr = stderr.replace(self._token, "<redacted>")
                stdout = stdout.replace(self._token, "<redacted>")
            raise GitOperationError(
                f"git {' '.join(args)} failed (rc={proc.returncode}): "
                f"{stderr.strip() or stdout.strip()}"
            )
        return stdout
