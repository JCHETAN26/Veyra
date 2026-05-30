"""Fix generation subpackage.

Maps a RootCauseAnalysis into a FixProposal — an ordered list of concrete
actions the workflow can apply. A FixGenerator is the second LLM-touching
surface (after the RCA analyzer) and follows the same pattern:

  - rule-based generator: deterministic, ships with every install,
  - LLM-backed generator: richer, parameterized actions with rollback notes,
  - factory: picks one based on settings,
  - fallback: LLM errors degrade to the rule-based generator.
"""

from dataforge.modules.remediation.fixes.factory import build_fix_generator
from dataforge.modules.remediation.fixes.generator import FixGenerator
from dataforge.modules.remediation.fixes.llm_based import (
    LLMFixGenerator,
    LLMFixProposalOut,
)
from dataforge.modules.remediation.fixes.rule_based import RuleBasedFixGenerator

__all__ = [
    "FixGenerator",
    "LLMFixGenerator",
    "LLMFixProposalOut",
    "RuleBasedFixGenerator",
    "build_fix_generator",
]
