"""OpenAI provider.

Uses the official AsyncOpenAI SDK. Structured output uses native
`response_format={"type": "json_schema", ...}` with strict mode, which is
the recommended path for OpenAI models that support it.
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
    Usage,
)

if TYPE_CHECKING:
    from pydantic import BaseModel


_FINISH_MAP = {
    "stop": FinishReason.STOP,
    "length": FinishReason.LENGTH,
    "tool_calls": FinishReason.TOOL_USE,
    "content_filter": FinishReason.CONTENT_FILTER,
}


class OpenAIProvider:
    """OpenAI Chat Completions provider."""

    provider = "openai"

    def __init__(
        self,
        api_key: str,
        model: str,
        timeout_seconds: float,
        max_output_tokens: int,
    ) -> None:
        try:
            import openai
        except ImportError as exc:  # pragma: no cover - dep gated
            raise LLMConfigError(
                "openai SDK not installed. Install dataforge with the [llm] extra."
            ) from exc

        if not api_key:
            raise LLMConfigError("OPENAI_API_KEY is required for the openai provider.")

        self._openai = openai
        self._client = openai.AsyncOpenAI(api_key=api_key, timeout=timeout_seconds)
        self.model = model
        self._default_max_output = max_output_tokens

    async def complete(self, request: ChatRequest) -> ChatResponse:
        kwargs: dict[str, Any] = {
            "model": request.model or self.model,
            "max_tokens": request.max_output_tokens or self._default_max_output,
            "temperature": request.temperature,
            "messages": [_to_openai_message(m) for m in request.messages],
        }

        if request.response_schema is not None:
            kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": request.response_schema.__name__,
                    "schema": request.response_schema.model_json_schema(),
                    "strict": True,
                },
            }

        try:
            response = await self._client.chat.completions.create(**kwargs)
        except self._openai.APITimeoutError as exc:
            raise LLMTimeoutError(str(exc)) from exc
        except self._openai.RateLimitError as exc:
            raise LLMRateLimitError(str(exc)) from exc
        except self._openai.APIStatusError as exc:
            raise LLMResponseError(f"openai api error: {exc}") from exc

        return _to_chat_response(response, request.response_schema, fallback_model=self.model)

    async def aclose(self) -> None:
        await self._client.close()


def _to_openai_message(m: Message) -> dict[str, str]:
    return {"role": m.role.value, "content": m.content}


def _to_chat_response(
    response: Any,
    schema: type[BaseModel] | None,
    *,
    fallback_model: str,
) -> ChatResponse:
    choice = response.choices[0]
    text = choice.message.content or ""

    parsed: BaseModel | None = None
    if schema is not None:
        try:
            parsed = schema.model_validate_json(text)
        except Exception as exc:
            raise LLMResponseError(f"openai structured response invalid: {exc}") from exc

    usage_raw = response.usage
    usage = Usage(
        input_tokens=getattr(usage_raw, "prompt_tokens", 0) or 0,
        output_tokens=getattr(usage_raw, "completion_tokens", 0) or 0,
    )

    return ChatResponse(
        content=text,
        parsed=parsed,
        finish_reason=_FINISH_MAP.get(choice.finish_reason or "stop", FinishReason.STOP),
        model=response.model or fallback_model,
        usage=usage,
        provider=cast("Any", "openai"),
    )
