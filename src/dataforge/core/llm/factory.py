"""Construct the configured LLMClient from settings.

`get_llm_client()` is the only entry point application code should use.
"""

from __future__ import annotations

from dataforge.core.config import LLMProvider, Settings, get_settings
from dataforge.core.llm.client import ReliableLLMClient
from dataforge.core.llm.errors import LLMConfigError
from dataforge.core.llm.protocol import LLMClient
from dataforge.core.llm.providers.null import NullProvider
from dataforge.core.llm.reliability import CircuitBreaker, TokenBudget


def build_llm_client(settings: Settings | None = None) -> LLMClient:
    """Build the LLM client from the (possibly injected) settings."""
    cfg = settings or get_settings()

    raw = _build_raw(cfg)
    circuit = CircuitBreaker(
        failure_threshold=cfg.llm_circuit_failure_threshold,
        cooldown_seconds=cfg.llm_circuit_cooldown_seconds,
    )
    budget = TokenBudget(daily_limit=cfg.llm_daily_token_budget)
    return ReliableLLMClient(
        raw,
        max_retries=cfg.llm_max_retries,
        circuit=circuit,
        budget=budget,
    )


def _build_raw(cfg: Settings) -> LLMClient:
    provider = cfg.llm_provider
    if provider is LLMProvider.NULL:
        return NullProvider(model=cfg.llm_model)

    if provider is LLMProvider.ANTHROPIC:
        from dataforge.core.llm.providers.anthropic import AnthropicProvider

        return AnthropicProvider(
            api_key=cfg.anthropic_api_key or "",
            model=cfg.llm_model,
            timeout_seconds=cfg.llm_timeout_seconds,
            max_output_tokens=cfg.llm_max_output_tokens,
        )

    if provider is LLMProvider.OPENAI:
        from dataforge.core.llm.providers.openai import OpenAIProvider

        return OpenAIProvider(
            api_key=cfg.openai_api_key or "",
            model=cfg.llm_model,
            timeout_seconds=cfg.llm_timeout_seconds,
            max_output_tokens=cfg.llm_max_output_tokens,
        )

    if provider is LLMProvider.OLLAMA:
        from dataforge.core.llm.providers.ollama import OllamaProvider

        return OllamaProvider(
            base_url=cfg.ollama_base_url,
            model=cfg.llm_model,
            timeout_seconds=cfg.llm_timeout_seconds,
            max_output_tokens=cfg.llm_max_output_tokens,
        )

    raise LLMConfigError(f"unknown LLM provider: {provider}")


# Module-level cache so app code can call get_llm_client() like get_settings().
_cached_client: LLMClient | None = None


def get_llm_client() -> LLMClient:
    """Return the process-wide LLM client, building it on first use."""
    global _cached_client
    if _cached_client is None:
        _cached_client = build_llm_client()
    return _cached_client


def reset_llm_client() -> None:
    """Drop the cached client (used by tests and lifecycle teardown)."""
    global _cached_client
    _cached_client = None
