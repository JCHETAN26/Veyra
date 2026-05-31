"""Unit tests for the LLM reliability primitives.

CircuitBreaker, TokenBudget, and retry_with_backoff are exercised against
injectable clocks/RNGs so the tests are deterministic and don't sleep.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from dataforge.core.llm.errors import (
    LLMBudgetExceededError,
    LLMCircuitOpenError,
    LLMConfigError,
    LLMRateLimitError,
    LLMTimeoutError,
)
from dataforge.core.llm.reliability import (
    CircuitBreaker,
    CircuitState,
    TokenBudget,
    retry_with_backoff,
)

# --- CircuitBreaker --------------------------------------------------------


class _FakeClock:
    def __init__(self, start: float = 0.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def test_circuit_opens_after_threshold_failures() -> None:
    clock = _FakeClock()
    cb = CircuitBreaker(failure_threshold=3, cooldown_seconds=10.0, clock=clock)

    cb.before_call()
    for _ in range(3):
        cb.record_failure()

    assert cb.state is CircuitState.OPEN
    with pytest.raises(LLMCircuitOpenError):
        cb.before_call()


def test_circuit_half_opens_after_cooldown_then_closes_on_success() -> None:
    clock = _FakeClock()
    cb = CircuitBreaker(failure_threshold=2, cooldown_seconds=5.0, clock=clock)

    for _ in range(2):
        cb.record_failure()
    assert cb.state is CircuitState.OPEN

    clock.advance(6.0)
    cb.before_call()
    assert cb.state is CircuitState.HALF_OPEN

    cb.record_success()
    assert cb.state is CircuitState.CLOSED
    assert cb.consecutive_failures == 0


def test_circuit_reopens_when_half_open_call_fails() -> None:
    clock = _FakeClock()
    cb = CircuitBreaker(failure_threshold=2, cooldown_seconds=5.0, clock=clock)

    for _ in range(2):
        cb.record_failure()
    clock.advance(6.0)
    cb.before_call()  # -> HALF_OPEN

    cb.record_failure()
    assert cb.state is CircuitState.OPEN
    with pytest.raises(LLMCircuitOpenError):
        cb.before_call()


def test_circuit_success_resets_counter() -> None:
    cb = CircuitBreaker(failure_threshold=3)
    cb.record_failure()
    cb.record_failure()
    cb.record_success()
    cb.record_failure()
    assert cb.state is CircuitState.CLOSED
    assert cb.consecutive_failures == 1


# --- TokenBudget -----------------------------------------------------------


class _FakeWallClock:
    def __init__(self, dt: datetime) -> None:
        self.dt = dt

    def __call__(self) -> datetime:
        return self.dt


def test_budget_blocks_when_exhausted() -> None:
    clock = _FakeWallClock(datetime(2026, 5, 30, 12, 0, tzinfo=UTC))
    budget = TokenBudget(daily_limit=100, clock=clock)
    budget.record_usage(60)
    budget.before_call()  # still under limit
    budget.record_usage(50)
    with pytest.raises(LLMBudgetExceededError):
        budget.before_call()


def test_budget_resets_on_new_utc_day() -> None:
    clock = _FakeWallClock(datetime(2026, 5, 30, 23, 30, tzinfo=UTC))
    budget = TokenBudget(daily_limit=100, clock=clock)
    budget.record_usage(150)
    with pytest.raises(LLMBudgetExceededError):
        budget.before_call()

    clock.dt = clock.dt + timedelta(hours=1)
    budget.before_call()  # rolled over: a new day starts at 00:30
    assert budget.used == 0


def test_budget_zero_limit_disables_check() -> None:
    budget = TokenBudget(daily_limit=0)
    budget.record_usage(10_000_000)
    budget.before_call()  # must not raise


# --- retry_with_backoff ----------------------------------------------------


async def test_retry_returns_on_first_success() -> None:
    calls = 0

    async def op() -> int:
        nonlocal calls
        calls += 1
        return 42

    result = await retry_with_backoff(op, max_retries=3, sleep=_no_sleep, rng=lambda: 0.5)
    assert result == 42
    assert calls == 1


async def test_retry_retries_rate_limit_and_succeeds() -> None:
    calls = 0

    async def op() -> str:
        nonlocal calls
        calls += 1
        if calls < 3:
            raise LLMRateLimitError("slow down")
        return "ok"

    result = await retry_with_backoff(op, max_retries=3, sleep=_no_sleep, rng=lambda: 0.5)
    assert result == "ok"
    assert calls == 3


async def test_retry_gives_up_after_max_attempts() -> None:
    async def op() -> None:
        raise LLMTimeoutError("nope")

    with pytest.raises(LLMTimeoutError):
        await retry_with_backoff(op, max_retries=2, sleep=_no_sleep, rng=lambda: 0.5)


async def test_retry_does_not_retry_non_retryable() -> None:
    calls = 0

    async def op() -> None:
        nonlocal calls
        calls += 1
        raise LLMConfigError("missing key")

    with pytest.raises(LLMConfigError):
        await retry_with_backoff(op, max_retries=5, sleep=_no_sleep, rng=lambda: 0.5)
    assert calls == 1


async def _no_sleep(_seconds: float) -> None:
    return None
