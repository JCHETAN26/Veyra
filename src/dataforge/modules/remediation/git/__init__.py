"""Git + GitHub integration.

Three layers:

  - `GitRepoConnector` (repo.py): clones a remote repo into a workspace
    via the `git` CLI invoked as a subprocess (no Python git dep), then
    drives the create-branch / commit / push lifecycle for one patch.
  - `GitHubPRClient` (github_pr.py): opens a pull request via the
    GitHub REST API using the httpx client already in core deps.
  - `RemediationPipeline` (pipeline.py): glues the two together with
    the LLMPatchGenerator from task #14 to produce a single
    "RCA -> patch -> branch -> push -> PR" call.

The token is read from settings and never logged; the subprocess
runner injects it into the remote URL via the `extraheader` mechanism
so it never appears on the command line. Dry-run mode short-circuits
the push and PR creation so demos and tests run offline.
"""

from __future__ import annotations

from dataforge.modules.remediation.git.github_pr import (
    GitHubPRClient,
    GitHubPRError,
)
from dataforge.modules.remediation.git.pipeline import (
    RemediationPipeline,
    RemediationPipelineError,
)
from dataforge.modules.remediation.git.repo import (
    GitOperationError,
    GitRepoConnector,
)

__all__ = [
    "GitHubPRClient",
    "GitHubPRError",
    "GitOperationError",
    "GitRepoConnector",
    "RemediationPipeline",
    "RemediationPipelineError",
]
