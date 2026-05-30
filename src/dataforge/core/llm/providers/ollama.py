"""Ollama provider (local).

Talks to a local Ollama daemon over HTTP. No SDK dependency — we use the
httpx client that's already in the foundation deps. Structured output uses
Ollama's `format` field, which accepts a JSON schema in recent versions.

Default model assumption is a coder-strong open model (e.g. qwen2.5-coder),
configurable via settings. We do not pull the model — the operator is
responsible for `ollama pull <model>` on the host.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, cast

import httpx

from dataforge.core.llm.errors import (
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


class OllamaProvider:
    """Local Ollama provider over its /api/chat endpoint."""

    provider = "ollama"

    def __init__(
        self,
        base_url: str,
        model: str,
        timeout_seconds: float,
        max_output_tokens: int,
    ) -> None:
        self._client = httpx.AsyncClient(base_url=base_url, timeout=timeout_seconds)
        self.model = model
        self._default_max_output = max_output_tokens

    async def complete(self, request: ChatRequest) -> ChatResponse:
        payload: dict[str, Any] = {
            "model": request.model or self.model,
            "messages": [_to_ollama_message(m) for m in request.messages],
            "stream": False,
            "options": {
                "temperature": request.temperature,
                "num_predict": request.max_output_tokens or self._default_max_output,
            },
        }
        if request.response_schema is not None:
            payload["format"] = request.response_schema.model_json_schema()

        try:
            response = await self._client.post("/api/chat", json=payload)
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError(str(exc)) from exc
        except httpx.HTTPError as exc:
            raise LLMResponseError(f"ollama transport error: {exc}") from exc

        if response.status_code == 429:
            raise LLMRateLimitError("ollama rate limited")
        if response.status_code >= 400:
            raise LLMResponseError(f"ollama returned {response.status_code}: {response.text[:300]}")

        data = response.json()
        return _to_chat_response(data, request.response_schema, fallback_model=self.model)

    async def aclose(self) -> None:
        await self._client.aclose()


def _to_ollama_message(m: Message) -> dict[str, str]:
    return {"role": m.role.value, "content": m.content}


def _to_chat_response(
    data: dict[str, Any],
    schema: type[BaseModel] | None,
    *,
    fallback_model: str,
) -> ChatResponse:
    msg = data.get("message") or {}
    text = msg.get("content") or ""

    parsed: BaseModel | None = None
    if schema is not None:
        try:
            parsed = schema.model_validate_json(text)
        except Exception:
            # Ollama sometimes wraps JSON in markdown fences; try a salvage parse.
            try:
                parsed = schema.model_validate(json.loads(text.strip("`\n ").lstrip("json\n")))
            except Exception as exc:
                raise LLMResponseError(f"ollama structured response invalid: {exc}") from exc

    usage = Usage(
        input_tokens=int(data.get("prompt_eval_count") or 0),
        output_tokens=int(data.get("eval_count") or 0),
    )
    finish = FinishReason.LENGTH if data.get("done_reason") == "length" else FinishReason.STOP

    return ChatResponse(
        content=text,
        parsed=parsed,
        finish_reason=finish,
        model=str(data.get("model") or fallback_model),
        usage=usage,
        provider=cast("Any", "ollama"),
    )
