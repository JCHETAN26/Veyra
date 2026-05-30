"""Anthropic provider.

Uses the official AsyncAnthropic SDK. Structured output is implemented via
forced tool use — we declare a single `respond` tool whose input_schema is
the requested Pydantic model's JSON schema, and the model returns its
answer as the tool's input. This is more reliable than JSON-mode prompts.

Prompt caching is honored: any Message with `cache=True` becomes a system
block with `cache_control={"type": "ephemeral"}`. The first call writes the
cache; subsequent calls within ~5 min read it at ~10% of the input cost.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from dataforge.core.llm.errors import (
    LLMConfigError,
    LLMRateLimitError,
    LLMResponseError,
    LLMTimeoutError,
)
from dataforge.core.llm.types import (
    ChatRequest,
    ChatResponse,
    FinishReason,
    Message,
    Role,
    Usage,
)

if TYPE_CHECKING:
    from pydantic import BaseModel


_FINISH_MAP = {
    "end_turn": FinishReason.STOP,
    "max_tokens": FinishReason.LENGTH,
    "stop_sequence": FinishReason.STOP,
    "tool_use": FinishReason.TOOL_USE,
}


class AnthropicProvider:
    """Anthropic Claude provider."""

    provider = "anthropic"

    def __init__(
        self,
        api_key: str,
        model: str,
        timeout_seconds: float,
        max_output_tokens: int,
    ) -> None:
        try:
            import anthropic
        except ImportError as exc:  # pragma: no cover - dep gated
            raise LLMConfigError(
                "anthropic SDK not installed. Install dataforge with the [llm] extra."
            ) from exc

        if not api_key:
            raise LLMConfigError("ANTHROPIC_API_KEY is required for the anthropic provider.")

        self._anthropic = anthropic
        self._client = anthropic.AsyncAnthropic(api_key=api_key, timeout=timeout_seconds)
        self.model = model
        self._default_max_output = max_output_tokens

    async def complete(self, request: ChatRequest) -> ChatResponse:
        system_blocks, user_messages = _split_system(request.messages)
        kwargs: dict[str, Any] = {
            "model": request.model or self.model,
            "max_tokens": request.max_output_tokens or self._default_max_output,
            "temperature": request.temperature,
            "messages": user_messages,
        }
        if system_blocks:
            kwargs["system"] = system_blocks

        if request.response_schema is not None:
            schema = _pydantic_to_schema(request.response_schema)
            kwargs["tools"] = [
                {
                    "name": "respond",
                    "description": "Respond with the structured data.",
                    "input_schema": schema,
                }
            ]
            kwargs["tool_choice"] = {"type": "tool", "name": "respond"}

        try:
            response = await self._client.messages.create(**kwargs)
        except self._anthropic.APITimeoutError as exc:
            raise LLMTimeoutError(str(exc)) from exc
        except self._anthropic.RateLimitError as exc:
            raise LLMRateLimitError(str(exc)) from exc
        except self._anthropic.APIStatusError as exc:
            raise LLMResponseError(f"anthropic api error: {exc}") from exc

        return _to_chat_response(response, request.response_schema, fallback_model=self.model)

    async def aclose(self) -> None:
        await self._client.close()


def _split_system(messages: list[Message]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Pull system messages out into Anthropic's `system` array.

    Cache-flagged messages get `cache_control` so Anthropic caches the block.
    """
    system_blocks: list[dict[str, Any]] = []
    chat: list[dict[str, Any]] = []
    for m in messages:
        if m.role is Role.SYSTEM:
            block: dict[str, Any] = {"type": "text", "text": m.content}
            if m.cache:
                block["cache_control"] = {"type": "ephemeral"}
            system_blocks.append(block)
        else:
            chat.append({"role": m.role.value, "content": m.content})
    return system_blocks, chat


def _pydantic_to_schema(model: type[BaseModel]) -> dict[str, Any]:
    schema = model.model_json_schema()
    # Anthropic requires "object" at the root; pydantic always emits that, but
    # we strip $defs key references the API doesn't accept at the root.
    schema.pop("title", None)
    return schema


def _to_chat_response(
    response: Any,
    schema: type[BaseModel] | None,
    *,
    fallback_model: str,
) -> ChatResponse:
    text = ""
    parsed: BaseModel | None = None
    for block in response.content:
        if block.type == "text":
            text += block.text
        elif block.type == "tool_use" and schema is not None:
            parsed = schema.model_validate(block.input)
            text = parsed.model_dump_json()

    if schema is not None and parsed is None:
        raise LLMResponseError("anthropic returned no tool_use block for structured request")

    usage_raw = response.usage
    usage = Usage(
        input_tokens=getattr(usage_raw, "input_tokens", 0) or 0,
        output_tokens=getattr(usage_raw, "output_tokens", 0) or 0,
        cache_read_tokens=getattr(usage_raw, "cache_read_input_tokens", 0) or 0,
        cache_write_tokens=getattr(usage_raw, "cache_creation_input_tokens", 0) or 0,
    )

    return ChatResponse(
        content=text,
        parsed=parsed,
        finish_reason=_FINISH_MAP.get(response.stop_reason or "end_turn", FinishReason.STOP),
        model=response.model or fallback_model,
        usage=usage,
        provider=cast("Any", "anthropic"),
    )
