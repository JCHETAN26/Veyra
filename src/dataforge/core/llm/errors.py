"""LLM-specific error types.

All errors subclass DataForgeError so they flow through the existing API
error envelope and structured-logging boundary unchanged.
"""

from __future__ import annotations

from dataforge.core.errors import DataForgeError


class LLMError(DataForgeError):
    """Base class for all LLM-layer errors."""

    code = "llm_error"
    status_code = 502


class LLMConfigError(LLMError):
    """Provider misconfigured (missing key, unknown provider, ...)."""

    code = "llm_config_error"
    status_code = 500


class LLMTimeoutError(LLMError):
    """Provider call exceeded the configured timeout."""

    code = "llm_timeout"
    status_code = 504


class LLMRateLimitError(LLMError):
    """Provider returned 429 / quota exceeded."""

    code = "llm_rate_limit"
    status_code = 429


class LLMBudgetExceededError(LLMError):
    """Per-process token budget was already spent for the day."""

    code = "llm_budget_exceeded"
    status_code = 429


class LLMCircuitOpenError(LLMError):
    """The circuit breaker is open; calls are refused until cooldown elapses."""

    code = "llm_circuit_open"
    status_code = 503


class LLMResponseError(LLMError):
    """Provider returned an unexpected / unparseable response."""

    code = "llm_response_error"
    status_code = 502
