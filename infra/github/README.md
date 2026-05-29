# GitHub repository configuration

Version-controlled record of repo governance (build-plan.md §6 Rule 1, §16).

## Branch protection — `main`

Applied via the GitHub API:

```bash
gh api -X PUT repos/JCHETAN26/Veyra/branches/main/protection \
  -H "Accept: application/vnd.github+json" \
  --input infra/github/branch-protection.json
```

### Rules enforced
- Pull request required before merge (no direct pushes to `main`).
- Required status checks (strict / up-to-date): `Backend validation`,
  `Security scan`, `Container build`.
- Linear history (squash or rebase merges only).
- Force pushes and branch deletion disabled.
- Conversation resolution required before merge.

### Notes
- `required_approving_review_count` is `0` because this is currently a
  single-maintainer repo (GitHub disallows self-approval). Raise to `1`
  once a second maintainer joins.
- `enforce_admins` is `false` so an admin can recover if a required check
  becomes misconfigured. Enable it once CI is proven stable.
