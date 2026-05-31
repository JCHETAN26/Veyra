"""Code-patch contracts.

A `CodePatch` is the concrete source-code change the remediation layer
proposes after deciding a `FixAction(kind="code_change")` is the right
move. It is the bridge between the abstract "what to do" (FixAction)
and the eventual git push.

Whole-file replacement is the MVP unit of change — Spark notebooks and
small ETL files are typically <500 lines, and reasoning over the full
file gives the LLM more context than a diff hunk would. The applier
validates `old_content` against the file's actual content before
writing, so concurrent edits or stale patches refuse cleanly instead
of silently overwriting fresher work.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class PatchOperation(StrEnum):
    """What the patch does to a target file."""

    # Replace the file's contents. `old_content` must match the file on disk.
    REPLACE = "replace"
    # Create a new file. The applier refuses if the path already exists.
    CREATE = "create"


class CodePatchAction(BaseModel):
    """One file modification within a patch.

    `path` is relative to the patch's working directory. `old_content` is
    what the LLM observed (and is what the applier verifies before writing
    `new_content`). For CREATE, `old_content` is empty.
    """

    path: str = Field(..., min_length=1)
    operation: PatchOperation
    old_content: str = ""
    new_content: str
    rationale: str = Field(
        ...,
        description="One-sentence explanation of why this specific file is changing.",
    )


class CodePatch(BaseModel):
    """A complete patch — one or more file modifications + how to verify."""

    summary: str = Field(
        ...,
        description="One-sentence headline summarizing the change across all files.",
    )
    actions: list[CodePatchAction] = Field(..., min_length=1)
    test_commands: list[str] = Field(
        default_factory=list,
        description=(
            "Shell commands the human (or a CI runner) can use to validate "
            "the patch. e.g. ['pyspark jobs/finance_etl.py --dry-run']."
        ),
    )
    cause_category: str | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class PatchActionResult(BaseModel):
    """The outcome of applying one action."""

    path: str
    applied: bool
    detail: str = ""


class PatchApplyResult(BaseModel):
    """Aggregated result of applying every action in a patch."""

    applied_actions: int = 0
    refused_actions: int = 0
    results: list[PatchActionResult] = Field(default_factory=list)
    applied_at: datetime | None = None

    @property
    def fully_applied(self) -> bool:
        return self.refused_actions == 0 and self.applied_actions > 0
