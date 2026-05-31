"""PatchGenerator protocol.

A patch generator turns "we should change the code" (a FixAction with
`kind="code_change"`) into "here is the actual code change" (a CodePatch
with concrete before/after content). The Protocol is async because the
production implementation calls an LLM; deterministic alternates can
swap in transparently.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from dataforge.contracts.patch import CodePatch
from dataforge.contracts.rca import RootCauseAnalysis
from dataforge.contracts.remediation_workflow import FixAction
from dataforge.contracts.telemetry import PipelineRun


@runtime_checkable
class PatchGenerator(Protocol):
    """Produces a CodePatch for a fix action + source-file context."""

    name: str

    async def generate(
        self,
        *,
        run: PipelineRun,
        analysis: RootCauseAnalysis,
        fix_action: FixAction,
        source_files: dict[str, str],
    ) -> CodePatch:
        """Return a CodePatch implementing `fix_action` against `source_files`.

        Args:
            run: the failing run that motivates the change.
            analysis: the LLM (or rule-based) RCA explaining the failure.
            fix_action: the typed action chosen — must have kind ==
                "code_change" for this to be meaningful, but the
                generator accepts any kind for forward compatibility.
            source_files: { relative_path: file_contents } — the files the
                generator is allowed to modify. Anything outside this map
                will be ignored (the generator never invents new file paths
                except via the CREATE operation, which is bounded to the
                same directory tree the caller controls).
        """
        ...
