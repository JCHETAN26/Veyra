"""ReliableLLMClient — the surface every caller actually uses.

Wraps a raw provider with three concentric layers, applied in this order:

  1. TokenBudget.before_call()    (cheapest; refuses pre-flight)
  2. CircuitBreaker.before_call() (refuses if upstream is unhealthy)
  3. retry_with_backoff(...)      (handles transient timeouts / 429)

This composition is the same for every provider so the policy is uniform
and testable in isolation against the NullProvider.
"""

from __future__ import annotations

from typing import Protocol

from dataforge.core.llm.reliability import (
    CircuitBreaker,
    TokenBudget,
    retry_with_backoff,
)
from dataforge.core.llm.types import ChatRequest, ChatResponse
from dataforge.core.logging import get_logger

logger = get_logger(__name__)


class _RawProvider(Protocol):
    """Minimal protocol that all raw provider adapters satisfy."""

    @property
    def provider(self) -> str: ...

    @property
    def model(self) -> str: ...

    async def complete(self, request: ChatRequest) -> ChatResponse: ...
    async def aclose(self) -> None: ...


class ReliableLLMClient:
    """Thin orchestrator that adds retry, circuit breaker, and budget."""

    def __init__(
        self,
        raw: _RawProvider,
        *,
        max_retries: int = 3,
        circuit: CircuitBreaker | None = None,
        budget: TokenBudget | None = None,
    ) -> None:
        self._raw = raw
        self._max_retries = max_retries
        self._circuit = circuit or CircuitBreaker()
        self._budget = budget or TokenBudget()

    # Convenience attrs so this class itself satisfies LLMClient ----------
    @property
    def provider(self) -> str:
        return self._raw.provider

    @property
    def model(self) -> str:
        return self._raw.model

    async def complete(self, request: ChatRequest) -> ChatResponse:
        self._budget.before_call()
        self._circuit.before_call()

        async def _call() -> ChatResponse:
            return await self._raw.complete(request)

        try:
            response = await retry_with_backoff(_call, max_retries=self._max_retries)
        except Exception:
            self._circuit.record_failure()
            raise

        self._circuit.record_success()
        self._budget.record_usage(response.usage.total_tokens)
        logger.info(
            "llm.complete",
            provider=response.provider,
            model=response.model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            cache_read=response.usage.cache_read_tokens,
            cache_write=response.usage.cache_write_tokens,
            finish_reason=response.finish_reason.value,
        )
        return response

    async def aclose(self) -> None:
        await self._raw.aclose()
