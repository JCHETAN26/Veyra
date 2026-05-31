"""LLM client layer.

Public surface for the rest of the platform. Importing from any submodule
directly is fine, but callers should prefer the names re-exported here so
the package can rearrange internals without breaking consumers.
"""

from __future__ import annotations

from dataforge.core.llm.client import ReliableLLMClient
from dataforge.core.llm.errors import (
    LLMBudgetExceededError,
    LLMCircuitOpenError,
    LLMConfigError,
    LLMError,
    LLMRateLimitError,
    LLMResponseError,
    LLMTimeoutError,
)
from dataforge.core.llm.factory import (
    build_llm_client,
    get_llm_client,
    reset_llm_client,
)
from dataforge.core.llm.protocol import LLMClient
from dataforge.core.llm.reliability import CircuitBreaker, CircuitState, TokenBudget
from dataforge.core.llm.types import (
    ChatRequest,
    ChatResponse,
    FinishReason,
    Message,
    Role,
    Usage,
)

__all__ = [
    "ChatRequest",
    "ChatResponse",
    "CircuitBreaker",
    "CircuitState",
    "FinishReason",
    "LLMBudgetExceededError",
    "LLMCircuitOpenError",
    "LLMClient",
    "LLMConfigError",
    "LLMError",
    "LLMRateLimitError",
    "LLMResponseError",
    "LLMTimeoutError",
    "Message",
    "ReliableLLMClient",
    "Role",
    "TokenBudget",
    "Usage",
    "build_llm_client",
    "get_llm_client",
    "reset_llm_client",
]
