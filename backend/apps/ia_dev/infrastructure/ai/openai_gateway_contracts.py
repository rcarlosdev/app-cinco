from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class OpenAIGatewayRequest:
    component: str
    input: Any
    model_route: str | None = None
    model: str | None = None
    timeout_seconds: float | None = None
    retries: int | None = None
    reasoning: dict[str, Any] | None = None
    text: dict[str, Any] | None = None
    store: bool | None = None
    background: bool | None = None
    previous_response_id: str | None = None
    tools: list[dict[str, Any]] | None = None
    tool_choice: str | dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    trace_metadata: dict[str, Any] = field(default_factory=dict)
    extra_options: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class OpenAIGatewayResponse:
    response: Any
    output_text: str
    model: str
    model_source: str
    response_id: str
    usage: dict[str, Any]
    metadata: dict[str, Any]
    output_items: list[dict[str, Any]] = field(default_factory=list)
    function_calls: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class OpenAIToolLoopResult:
    response: OpenAIGatewayResponse
    tool_traces: list[dict[str, Any]] = field(default_factory=list)
    response_ids: list[str] = field(default_factory=list)
    turns: int = 0


class OpenAIGatewayError(RuntimeError):
    def __init__(
        self,
        *,
        component: str,
        code: str,
        message: str,
        model: str = "",
        cause: Exception | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.component = str(component or "").strip()
        self.code = str(code or "openai_gateway_error").strip()
        self.model = str(model or "").strip()
        self.cause = cause
        self.metadata = dict(metadata or {})
