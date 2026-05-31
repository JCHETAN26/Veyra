"""GitHub PR client.

Thin wrapper around the GitHub REST `POST /repos/{owner}/{repo}/pulls`
endpoint using the existing httpx client. No PyGithub / octokit dep.

The client is injected (rather than constructed inline) so tests can
swap in a stub httpx.AsyncClient or a transport with canned responses
without monkey-patching the module.
"""

from __future__ import annotations

from datetime import UTC, datetime

import httpx

from dataforge.contracts.git import PullRequestResult, RepoLocation
from dataforge.core.errors import DataForgeError
from dataforge.core.logging import get_logger

logger = get_logger(__name__)


class GitHubPRError(DataForgeError):
    """The GitHub PR API returned an error."""

    code = "github_pr_error"
    status_code = 502


class GitHubPRClient:
    """Opens pull requests via the GitHub REST API."""

    def __init__(
        self,
        *,
        token: str | None,
        api_url: str = "https://api.github.com",
        http_client: httpx.AsyncClient | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._token = token
        self._api_url = api_url.rstrip("/")
        self._timeout = timeout
        self._http: httpx.AsyncClient | None = http_client
        self._owns_http = http_client is None

    async def __aenter__(self) -> GitHubPRClient:
        if self._http is None:
            self._http = httpx.AsyncClient(timeout=self._timeout)
        return self

    async def __aexit__(self, *args: object) -> None:
        if self._owns_http and self._http is not None:
            await self._http.aclose()
            self._http = None

    async def open_pr(
        self,
        *,
        repo: RepoLocation,
        head_branch: str,
        base_branch: str,
        title: str,
        body: str,
        dry_run: bool = False,
    ) -> PullRequestResult:
        """Open a PR; return the API response shape we care about.

        In dry-run mode, no network call is made — the result envelope
        carries `number=None`, `url=None`, and `dry_run=True` so callers
        can render "would have opened: ..." messages without forking
        their downstream code paths.
        """
        if dry_run:
            logger.info(
                "github_pr.dry_run",
                repo=repo.api_repo_path,
                head=head_branch,
                base=base_branch,
            )
            return PullRequestResult(
                title=title,
                head_branch=head_branch,
                base_branch=base_branch,
                dry_run=True,
                opened_at=datetime.now(UTC),
            )

        if not self._token:
            raise GitHubPRError(
                "DATAFORGE_GITHUB_TOKEN is required to open a real PR. "
                "Pass dry_run=True for offline runs."
            )

        if self._http is None:
            self._http = httpx.AsyncClient(timeout=self._timeout)

        url = f"{self._api_url}/repos/{repo.api_repo_path}/pulls"
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        payload = {
            "title": title,
            "head": head_branch,
            "base": base_branch,
            "body": body,
        }

        try:
            response = await self._http.post(url, headers=headers, json=payload)
        except httpx.HTTPError as exc:
            raise GitHubPRError(f"GitHub transport error: {exc}") from exc

        if response.status_code >= 400:
            raise GitHubPRError(
                f"GitHub returned {response.status_code} opening PR: " f"{response.text[:500]}"
            )

        data = response.json()
        return PullRequestResult(
            number=data.get("number"),
            url=data.get("html_url"),
            title=data.get("title", title),
            head_branch=data.get("head", {}).get("ref", head_branch),
            base_branch=data.get("base", {}).get("ref", base_branch),
            dry_run=False,
            opened_at=datetime.now(UTC),
        )
