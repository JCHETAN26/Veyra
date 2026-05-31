"""Code-patch generation + application.

Closes the gap between the FixGenerator's typed `FixAction` and the
on-disk source code that needs to change. A two-stage pipeline:

  1. LLMPatchGenerator: takes the run's RootCauseAnalysis, the chosen
     FixAction, and the current source-file content, and asks the LLM
     for a strict CodePatch (per-file before/after).
  2. apply_patch: writes the new content to the working directory with
     drift detection — if the on-disk content doesn't match what the
     LLM observed, the action refuses and is reported, not silently
     overwritten.

The GitHub-push half is intentionally out of scope here. This sub-package
is the "AI writes real fix code into the working tree" surface; pushing
to a branch + opening a PR is a follow-on (see task #15 candidate when
we wire up gitpython).
"""

from __future__ import annotations

from dataforge.modules.remediation.patches.applier import apply_patch
from dataforge.modules.remediation.patches.generator import PatchGenerator
from dataforge.modules.remediation.patches.llm_based import LLMPatchGenerator

__all__ = ["LLMPatchGenerator", "PatchGenerator", "apply_patch"]
