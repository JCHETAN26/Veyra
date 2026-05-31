"""Patch applier.

Writes a CodePatch's actions to a working directory with drift detection:
an action is refused if its `old_content` doesn't match the file on
disk (REPLACE) or if the target path already exists (CREATE). Per-action
refusals are recorded in the PatchApplyResult; one bad action doesn't
abort the others.

Path safety is enforced at the working-directory boundary: every path
must resolve inside `working_dir` (no `../etc/passwd` games). Symlink
escapes are rejected during the resolve step.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from dataforge.contracts.patch import (
    CodePatch,
    CodePatchAction,
    PatchActionResult,
    PatchApplyResult,
    PatchOperation,
)
from dataforge.core.logging import get_logger

logger = get_logger(__name__)


def apply_patch(working_dir: Path | str, patch: CodePatch) -> PatchApplyResult:
    """Apply each action in `patch` to `working_dir`.

    Args:
        working_dir: the root the actions are scoped to. Must exist.
        patch: the typed CodePatch to apply.

    Returns:
        A PatchApplyResult summarizing per-action outcomes. The applier
        never raises for "expected" failures (drift, path escape, missing
        file on REPLACE, existing path on CREATE) — those are reported as
        refusals. It does raise for genuinely-unexpected I/O errors.
    """
    root = Path(working_dir).resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"working_dir does not exist: {working_dir}")

    results: list[PatchActionResult] = []
    applied = 0
    refused = 0
    for action in patch.actions:
        result = _apply_one(root, action)
        results.append(result)
        if result.applied:
            applied += 1
        else:
            refused += 1

    summary = PatchApplyResult(
        applied_actions=applied,
        refused_actions=refused,
        results=results,
        applied_at=datetime.now(UTC),
    )
    logger.info(
        "patch.applied",
        summary=patch.summary,
        applied=applied,
        refused=refused,
    )
    return summary


def _apply_one(root: Path, action: CodePatchAction) -> PatchActionResult:
    target = _safe_resolve(root, action.path)
    if target is None:
        return PatchActionResult(
            path=action.path,
            applied=False,
            detail="refused: path escapes the working directory",
        )

    if action.operation is PatchOperation.REPLACE:
        if not target.exists():
            return PatchActionResult(
                path=action.path,
                applied=False,
                detail="refused: REPLACE target does not exist",
            )
        actual = target.read_text(encoding="utf-8")
        if actual != action.old_content:
            return PatchActionResult(
                path=action.path,
                applied=False,
                detail=(
                    "refused: file content drifted from old_content "
                    f"(on-disk {len(actual)} chars vs patch "
                    f"{len(action.old_content)} chars)"
                ),
            )
        target.write_text(action.new_content, encoding="utf-8")
        return PatchActionResult(path=action.path, applied=True, detail="replaced")

    # CREATE
    if target.exists():
        return PatchActionResult(
            path=action.path,
            applied=False,
            detail="refused: CREATE target already exists",
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(action.new_content, encoding="utf-8")
    return PatchActionResult(path=action.path, applied=True, detail="created")


def _safe_resolve(root: Path, rel: str) -> Path | None:
    """Resolve `rel` against `root`, refusing if it escapes the root.

    Uses Path.resolve() which collapses `..` and follows symlinks; the
    final path is checked against `root` with `is_relative_to`. Both
    sides of the comparison are resolved so the check is symlink-safe.
    """
    candidate = (root / rel).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    return candidate
