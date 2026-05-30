"""Integration tests for ReliableLLMClient + NullProvider + factory."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import BaseModel

from dataforge.core.config import LLMProvider, Settings
from dataforge.core.llm import (
    ChatRequest,
    ChatResponse,
    LLMBudgetExceededError,
    LLMCircuitOpenError,
    LLMRateLimitError,
    Message,
    ReliableLLMClient,
    Role,
    Usage,
    build_llm_client,
)
from dataforge.core.llm.providers.null import NullProvider
from dataforge.core.llm.reliability import CircuitBreaker, TokenBudget


class _SampleSchema(BaseModel):
    summary: str
    confidence: float


# --- NullProvider ----------------------------------------------------------


async def test_null_provider_returns_echo() -> None:
    provider = NullProvider()
    response = await provider.complete(
        ChatRequest(messages=[Message(role=Role.USER, content="hello world")])
    )
    assert "hello world" in response.content
    assert response.provider == "null"
    assert response.usage.total_tokens > 0


async def test_null_provider_structured_returns_parsed_instance() -> None:
    provider = NullProvider()
    response = await provider.complete(
        ChatRequest(
            messages=[Message(role=Role.USER, content="x")],
            response_schema=_SampleSchema,
        )
    )
    assert response.parsed is not None
    assert isinstance(response.parsed, _SampleSchema)


# --- ReliableLLMClient composition -----------------------------------------


class _FlakyProvider:
    """A controllable provider used to exercise the reliability layer."""

    provider = "null"

    def __init__(self, model: str = "test-model") -> None:
        self.model = model
        self.calls = 0
        self.raise_for: list[BaseException] = []
        self.usage_per_call = 100

    async def complete(self, request: ChatRequest) -> ChatResponse:
        self.calls += 1
        if self.raise_for:
            raise self.raise_for.pop(0)
        return ChatResponse(
            content="ok",
            model=self.model,
            usage=Usage(input_tokens=self.usage_per_call, output_tokens=0),
            provider="null",  # type: ignore[arg-type]
        )

    async def aclose(self) -> None:
        return None


async def test_client_retries_rate_limit_and_records_success() -> None:
    raw = _FlakyProvider()
    raw.raise_for = [LLMRateLimitError("x"), LLMRateLimitError("x")]
    client = ReliableLLMClient(
        raw,
        max_retries=3,
        circuit=CircuitBreaker(failure_threshold=5),
        budget=TokenBudget(daily_limit=0),
    )
    # Patch retry sleep so the test is instant.
    import dataforge.core.llm.client as client_module
    import dataforge.core.llm.reliability as reliability_module

    orig_retry = reliability_module.retry_with_backoff

    async def fast_retry(op: Any, **kwargs: Any) -> Any:
        kwargs["sleep"] = lambda _s: _aiosleep_noop()
        kwargs["rng"] = lambda: 0.0
        return await orig_retry(op, **kwargs)

    client_module.retry_with_backoff = fast_retry  # type: ignore[assignment]
    try:
        await client.complete(ChatRequest(messages=[Message(role=Role.USER, content="hi")]))
    finally:
        client_module.retry_with_backoff = orig_retry  # type: ignore[assignment]

    assert raw.calls == 3


async def _aiosleep_noop() -> None:
    return None


async def test_client_opens_circuit_after_repeated_failures() -> None:
    raw = _FlakyProvider()
    cb = CircuitBreaker(failure_threshold=2, cooldown_seconds=1000.0)
    client = ReliableLLMClient(
        raw,
        max_retries=0,
        circuit=cb,
        budget=TokenBudget(daily_limit=0),
    )

    raw.raise_for = [LLMRateLimitError("a")]
    with pytest.raises(LLMRateLimitError):
        await client.complete(ChatRequest(messages=[Message(role=Role.USER, content="x")]))

    raw.raise_for = [LLMRateLimitError("b")]
    with pytest.raises(LLMRateLimitError):
        await client.complete(ChatRequest(messages=[Message(role=Role.USER, content="x")]))

    # Now the circuit is open — the next call should be refused without
    # touching the raw provider.
    raw.raise_for = []
    pre_calls = raw.calls
    with pytest.raises(LLMCircuitOpenError):
        await client.complete(ChatRequest(messages=[Message(role=Role.USER, content="x")]))
    assert raw.calls == pre_calls


async def test_client_blocks_when_budget_exhausted() -> None:
    raw = _FlakyProvider()
    raw.usage_per_call = 80
    client = ReliableLLMClient(
        raw,
        max_retries=0,
        circuit=CircuitBreaker(failure_threshold=99),
        budget=TokenBudget(daily_limit=100),
    )

    await client.complete(ChatRequest(messages=[Message(role=Role.USER, content="x")]))
    # Second call: budget was 80 used; pre-flight is still under 100 so it
    # proceeds. After it lands the budget is 160 and the next call is blocked.
    await client.complete(ChatRequest(messages=[Message(role=Role.USER, content="x")]))
    with pytest.raises(LLMBudgetExceededError):
        await client.complete(ChatRequest(messages=[Message(role=Role.USER, content="x")]))


# --- Factory ---------------------------------------------------------------


def test_factory_builds_null_provider_by_default() -> None:
    s = Settings(llm_provider=LLMProvider.NULL, llm_model="m")
    client = build_llm_client(s)
    assert client.provider == "null"
    assert client.model == "m"


def test_factory_unknown_provider_raises() -> None:
    s = Settings(llm_provider=LLMProvider.NULL)
    # Force an invalid value past Pydantic to exercise the factory branch.
    object.__setattr__(s, "llm_provider", "bogus")
    from dataforge.core.llm.errors import LLMConfigError

    with pytest.raises(LLMConfigError):
        build_llm_client(s)
