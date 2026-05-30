"""The LLMClient protocol.

Every provider adapter (Anthropic, OpenAI, Ollama, Null) implements this
interface. Callers (RCA analyzer, fix generator, RAG synth) depend only on
the protocol so swapping providers is a config change, not a code change.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from dataforge.core.llm.types import ChatRequest, ChatResponse


@runtime_checkable
class LLMClient(Protocol):
    """A reliable, structured-output-aware chat client.

    `provider` and `model` are declared as read-only properties on the
    Protocol so both instance-attribute providers (Null, Anthropic, ...) and
    property-based wrappers (ReliableLLMClient) satisfy the interface.
    """

    @property
    def provider(self) -> str: ...

    @property
    def model(self) -> str: ...

    async def complete(self, request: ChatRequest) -> ChatResponse:
        """Run a single chat completion, applying retry / circuit / budget."""
        ...

    async def aclose(self) -> None:
        """Release any underlying transport (HTTP session, etc.)."""
        ...
