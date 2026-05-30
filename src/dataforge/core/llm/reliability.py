"""Reliability primitives shared by every LLM provider.

These run in front of the raw provider call so retry/circuit/budget logic
is identical regardless of vendor — which is the whole point of a single
LLMClient surface.

- `CircuitBreaker`: per-provider closed/open/half-open state machine.
- `TokenBudget`: in-process daily soft budget guarded before each call.
- `retry_with_backoff`: exponential backoff with full jitter for the
  retryable error classes only.

All three accept a clock callable so tests are deterministic without
patching the time module.
"""

from __future__ import annotations

import asyncio
import random
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

from dataforge.core.llm.errors import (
    LLMBudgetExceededError,
    LLMCircuitOpenError,
    LLMError,
    LLMRateLimitError,
    LLMTimeoutError,
)

Clock = Callable[[], float]


# ---------------------------------------------------------------------------
# Circuit breaker
# ---------------------------------------------------------------------------


class CircuitState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitBreaker:
    """Protects a provider from cascading failure.

    State machine:
      CLOSED      -> success: stay closed; failure: ++count, if >= threshold open.
      OPEN        -> reject calls until `cooldown` has elapsed since opening,
                     then transition to HALF_OPEN on the next attempt.
      HALF_OPEN   -> allow exactly one trial: success closes, failure re-opens.
    """

    failure_threshold: int = 5
    cooldown_seconds: float = 30.0
    clock: Clock = field(default=time.monotonic)
    state: CircuitState = CircuitState.CLOSED
    consecutive_failures: int = 0
    opened_at: float | None = None

    def before_call(self) -> None:
        """Raise LLMCircuitOpenError if the breaker is open and not yet cool."""
        if self.state is CircuitState.OPEN:
            # Defensive: an OPEN breaker should always have opened_at set, but
            # treat a missing timestamp as "just opened" rather than crash.
            opened_at = self.opened_at if self.opened_at is not None else self.clock()
            if self.clock() - opened_at < self.cooldown_seconds:
                raise LLMCircuitOpenError(
                    f"LLM circuit open; retry in "
                    f"{self.cooldown_seconds - (self.clock() - opened_at):.1f}s"
                )
            # Cooldown elapsed: allow a single trial.
            self.state = CircuitState.HALF_OPEN

    def record_success(self) -> None:
        self.state = CircuitState.CLOSED
        self.consecutive_failures = 0
        self.opened_at = None

    def record_failure(self) -> None:
        self.consecutive_failures += 1
        if (
            self.state is CircuitState.HALF_OPEN
            or self.consecutive_failures >= self.failure_threshold
        ):
            self.state = CircuitState.OPEN
            self.opened_at = self.clock()


# ---------------------------------------------------------------------------
# Token budget
# ---------------------------------------------------------------------------


WallClock = Callable[[], datetime]


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass
class TokenBudget:
    """Soft per-process daily token budget.

    Tokens are accumulated against the UTC calendar day; crossing midnight
    resets the counter. Zero `daily_limit` disables the budget (useful in
    tests and for the Null provider).
    """

    daily_limit: int = 1_000_000
    clock: WallClock = field(default=_utc_now)
    _used: int = 0
    _day: str = ""

    def _roll_if_new_day(self) -> None:
        today = self.clock().strftime("%Y-%m-%d")
        if today != self._day:
            self._day = today
            self._used = 0

    def before_call(self) -> None:
        """Raise if we've already exceeded today's budget."""
        if self.daily_limit <= 0:
            return
        self._roll_if_new_day()
        if self._used >= self.daily_limit:
            raise LLMBudgetExceededError(
                f"LLM daily token budget {self.daily_limit:,} exhausted " f"({self._used:,} used)."
            )

    def record_usage(self, tokens: int) -> None:
        if self.daily_limit <= 0:
            return
        self._roll_if_new_day()
        self._used += max(tokens, 0)

    @property
    def used(self) -> int:
        self._roll_if_new_day()
        return self._used


# ---------------------------------------------------------------------------
# Retry with backoff
# ---------------------------------------------------------------------------


_RETRYABLE: tuple[type[BaseException], ...] = (
    LLMTimeoutError,
    LLMRateLimitError,
    asyncio.TimeoutError,
)


async def retry_with_backoff[T](
    operation: Callable[[], Awaitable[T]],
    *,
    max_retries: int = 3,
    base_delay: float = 0.5,
    max_delay: float = 8.0,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    rng: Callable[[], float] = random.random,
) -> T:
    """Run `operation` with exponential backoff + full jitter.

    Only retries the well-known transient classes (timeouts, 429). 4xx auth /
    validation errors bubble up immediately — retrying them is just noise.
    """
    attempt = 0
    while True:
        try:
            return await operation()
        except _RETRYABLE as exc:
            if attempt >= max_retries:
                # Re-raise as the canonical type if it's a bare asyncio timeout.
                if isinstance(exc, asyncio.TimeoutError):
                    raise LLMTimeoutError("LLM call timed out") from exc
                raise
            delay = min(max_delay, base_delay * (2**attempt)) * rng()
            await sleep(delay)
            attempt += 1
        except LLMError:
            raise
