"""Root-cause analysis subpackage.

Lives inside the remediation module because build-plan §4 assigns "Spark
failure analysis" to remediation, ahead of fix generation which builds on it.
The analyzer is defined behind an interface so the rule-based MVP can be
swapped for an LLM-backed implementation later.
"""

from dataforge.modules.remediation.rca.analyzer import RootCauseAnalyzer
from dataforge.modules.remediation.rca.rule_based import RuleBasedAnalyzer

__all__ = ["RootCauseAnalyzer", "RuleBasedAnalyzer"]
