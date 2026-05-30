"""Fix generator factory.

Settings-driven: with `llm_provider=null` (default) the rule-based generator
is returned, so the platform produces deterministic proposals without an
API key. Any real provider returns the LLM-backed generator, which falls
back to rule-based on transport failure.
"""

from __future__ import annotations

from dataforge.core.config import LLMProvider, Settings, get_settings
from dataforge.core.llm import LLMClient, get_llm_client
from dataforge.modules.remediation.fixes.generator import FixGenerator
from dataforge.modules.remediation.fixes.llm_based import LLMFixGenerator
from dataforge.modules.remediation.fixes.rule_based import RuleBasedFixGenerator


def build_fix_generator(
    settings: Settings | None = None,
    *,
    llm_client: LLMClient | None = None,
) -> FixGenerator:
    cfg = settings or get_settings()
    if cfg.llm_provider is LLMProvider.NULL:
        return RuleBasedFixGenerator()
    client = llm_client or get_llm_client()
    return LLMFixGenerator(llm_client=client)
