"""Analyzer factory.

`build_analyzer()` is the only place that decides which analyzer the
remediation service uses, based on settings. With `llm_provider=null`
(the default), the rule-based analyzer is returned — so the platform
runs deterministically without any LLM credentials.
"""

from __future__ import annotations

from dataforge.core.config import LLMProvider, Settings, get_settings
from dataforge.core.llm import LLMClient, get_llm_client
from dataforge.modules.remediation.rca.analyzer import RootCauseAnalyzer
from dataforge.modules.remediation.rca.llm_based import LLMAnalyzer
from dataforge.modules.remediation.rca.rule_based import RuleBasedAnalyzer


def build_analyzer(
    settings: Settings | None = None,
    *,
    llm_client: LLMClient | None = None,
) -> RootCauseAnalyzer:
    """Return the analyzer configured for this environment.

    Args:
        settings: dependency-injected settings; falls back to the global cache.
        llm_client: dependency-injected LLM client; falls back to the global
            factory. Tests use this to bypass the real provider chain.
    """
    cfg = settings or get_settings()
    if cfg.llm_provider is LLMProvider.NULL:
        return RuleBasedAnalyzer()
    client = llm_client or get_llm_client()
    return LLMAnalyzer(llm_client=client)
