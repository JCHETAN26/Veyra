"""LLM request/response contracts.

Provider-agnostic types. Each adapter translates these to/from its native
shape so the rest of the platform (RCA analyzer, fix generator, RAG synth)
never imports a vendor SDK.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class Role(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class Message(BaseModel):
    """A single chat message.

    `cache` is an Anthropic-prompt-caching hint: set it on large, stable
    system prompts (taxonomies, runbooks) so the provider can cache and
    re-use them across calls. Providers that don't support caching ignore it.
    """

    role: Role
    content: str
    cache: bool = False


class FinishReason(StrEnum):
    STOP = "stop"
    LENGTH = "length"
    TOOL_USE = "tool_use"
    CONTENT_FILTER = "content_filter"
    ERROR = "error"


class Usage(BaseModel):
    """Token accounting for a single completion."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


class ChatRequest(BaseModel):
    """Inputs to a single chat completion call."""

    messages: list[Message]
    # Per-request model override; falls back to the client's configured model.
    model: str | None = None
    max_output_tokens: int | None = Field(default=None, gt=0)
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    # If set, the provider is asked to return JSON conforming to this schema
    # (Pydantic model). The parsed instance is returned on ChatResponse.parsed.
    response_schema: type[BaseModel] | None = None

    model_config = {"arbitrary_types_allowed": True}


class ChatResponse(BaseModel):
    """Outputs from a single chat completion call."""

    content: str
    parsed: BaseModel | None = None
    finish_reason: FinishReason = FinishReason.STOP
    model: str
    usage: Usage = Field(default_factory=Usage)
    provider: Literal["anthropic", "openai", "ollama", "null"]

    model_config = {"arbitrary_types_allowed": True}
