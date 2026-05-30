"""Root-cause analysis subpackage.

Lives inside the remediation module because build-plan §4 assigns "Spark
failure analysis" to remediation, ahead of fix generation which builds on
it. The analyzer is defined behind a Protocol so the rule-based MVP and
the LLM-backed analyzer are interchangeable from the service's perspective.
"""

from dataforge.modules.remediation.rca.analyzer import RootCauseAnalyzer
from dataforge.modules.remediation.rca.factory import build_analyzer
from dataforge.modules.remediation.rca.llm_based import LLMAnalysisOut, LLMAnalyzer
from dataforge.modules.remediation.rca.rule_based import RuleBasedAnalyzer

__all__ = [
    "LLMAnalysisOut",
    "LLMAnalyzer",
    "RootCauseAnalyzer",
    "RuleBasedAnalyzer",
    "build_analyzer",
]
