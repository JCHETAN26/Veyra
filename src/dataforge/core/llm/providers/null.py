"""Null LLM provider.

Deterministic, dependency-free, no network. Returns a predictable stub for
each request so the rest of the platform exercises the LLM-touching code
paths in CI without an API key. If a response_schema is provided, returns
an instance built from `model_construct` to bypass field validation in cases
where the schema requires data we don't synthesize.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from dataforge.core.llm.types import (
    ChatRequest,
    ChatResponse,
    FinishReason,
    Usage,
)


class NullProvider:
    """A no-op LLM that always returns a deterministic stub."""

    provider = "null"

    def __init__(self, model: str = "null-model") -> None:
        self.model = model

    async def complete(self, request: ChatRequest) -> ChatResponse:
        last_user = next(
            (m.content for m in reversed(request.messages) if m.role == "user"),
            "",
        )
        content = f"[null-llm] echo: {last_user[:200]}"

        parsed: BaseModel | None = None
        if request.response_schema is not None:
            parsed = _stub_instance(request.response_schema)
            content = parsed.model_dump_json()

        approx_in = sum(len(m.content) for m in request.messages) // 4
        approx_out = len(content) // 4
        return ChatResponse(
            content=content,
            parsed=parsed,
            finish_reason=FinishReason.STOP,
            model=request.model or self.model,
            usage=Usage(input_tokens=approx_in, output_tokens=approx_out),
            provider="null",
        )

    async def aclose(self) -> None:
        return None


def _stub_instance(schema: type[BaseModel]) -> BaseModel:
    """Build a schema instance with type-appropriate zero values.

    Uses model_construct to skip validation so we can populate required
    fields without knowing their semantics.
    """
    values: dict[str, Any] = {}
    for name, field in schema.model_fields.items():
        ann = field.annotation
        values[name] = _zero_for(ann)
    return schema.model_construct(**values)


def _zero_for(annotation: Any) -> Any:
    if annotation in (str, "str"):
        return ""
    if annotation in (int, "int"):
        return 0
    if annotation in (float, "float"):
        return 0.0
    if annotation in (bool, "bool"):
        return False
    if annotation in (list, "list"):
        return []
    if annotation in (dict, "dict"):
        return {}
    return None
