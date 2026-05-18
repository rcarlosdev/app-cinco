from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any

from apps.ia_dev.infrastructure.ai.model_policy import OpenAIModelPolicy
from apps.ia_dev.infrastructure.ai.openai_gateway_contracts import (
    OpenAIGatewayError,
    OpenAIGatewayRequest,
    OpenAIGatewayResponse,
    OpenAIToolLoopResult,
)
from apps.ia_dev.application.runtime.runtime_hardening_service import RuntimeHardeningService


logger = logging.getLogger(__name__)


class OpenAIGatewayService:
    def __init__(
        self,
        *,
        model_policy: OpenAIModelPolicy | None = None,
    ) -> None:
        self.model_policy = model_policy or OpenAIModelPolicy()
        self.runtime_hardening_service = RuntimeHardeningService()

    @staticmethod
    def get_api_key() -> str:
        return str(os.getenv("OPENAI_API_KEY") or os.getenv("IA_DEV_OPENAI_API_KEY") or "").strip()

    def is_enabled(self) -> bool:
        return bool(self.get_api_key())

    def create(self, request: OpenAIGatewayRequest) -> OpenAIGatewayResponse:
        api_key = self.get_api_key()
        if not api_key:
            raise OpenAIGatewayError(
                component=request.component,
                code="missing_api_key",
                message="OpenAI API key is not configured",
                metadata={
                    "component": request.component,
                    "trace_metadata": dict(request.trace_metadata or {}),
                    "request_metadata": dict(request.metadata or {}),
                },
            )

        selection = self.model_policy.resolve(
            component=request.component,
            route_key=request.model_route,
            explicit_model=request.model,
        )
        timeout_seconds = float(request.timeout_seconds or self._default_timeout_seconds())
        retries = max(0, int(request.retries if request.retries is not None else self._default_retries()))
        payload = self._build_payload(request=request, model=selection.model)
        logger.info(
            "IA_DEV OpenAI gateway request component=%s model=%s source=%s timeout_seconds=%s retries=%s",
            request.component,
            selection.model,
            selection.source,
            timeout_seconds,
            retries,
        )
        try:
            client = self._build_client(
                api_key=api_key,
                timeout_seconds=timeout_seconds,
                retries=retries,
            )
            response = client.responses.create(**payload)
        except Exception as exc:
            error_code = self._normalize_error_code(exc)
            error_metadata = {
                "component": request.component,
                "model": selection.model,
                "model_source": selection.source,
                "timeout_seconds": timeout_seconds,
                "retries": retries,
                "trace_metadata": dict(request.trace_metadata or {}),
                "request_metadata": dict(request.metadata or {}),
                "error_type": type(exc).__name__,
            }
            logger.warning(
                "IA_DEV OpenAI gateway error component=%s model=%s code=%s error_type=%s",
                request.component,
                selection.model,
                error_code,
                type(exc).__name__,
            )
            raise OpenAIGatewayError(
                component=request.component,
                code=error_code,
                message=f"{type(exc).__name__}: {exc}",
                model=selection.model,
                cause=exc,
                metadata=error_metadata,
            ) from exc

        usage = self._extract_usage(response)
        response_id = str(getattr(response, "id", "") or "")
        output_items = self._extract_output_items(response)
        function_calls = self._extract_function_calls(output_items)
        response_metadata = {
            "component": request.component,
            "model": selection.model,
            "model_source": selection.source,
            "response_id": response_id,
            "timeout_seconds": timeout_seconds,
            "retries": retries,
            "trace_metadata": dict(request.trace_metadata or {}),
            "request_metadata": dict(request.metadata or {}),
            "correlation": self.runtime_hardening_service.build_correlation_metadata(
                run_id=str((request.trace_metadata or {}).get("run_id") or ""),
                trace_id=str((request.trace_metadata or {}).get("trace_id") or ""),
                session_id=str((request.metadata or {}).get("session_id") or ""),
            ),
            "usage": usage,
            "output_item_count": len(output_items),
            "function_call_count": len(function_calls),
        }
        logger.info(
            "IA_DEV OpenAI gateway response component=%s model=%s response_id=%s input_tokens=%s output_tokens=%s",
            request.component,
            selection.model,
            response_id,
            usage.get("input_tokens"),
            usage.get("output_tokens"),
        )
        return OpenAIGatewayResponse(
            response=response,
            output_text=str(getattr(response, "output_text", "") or "").strip(),
            model=selection.model,
            model_source=selection.source,
            response_id=response_id,
            usage=usage,
            metadata=response_metadata,
            output_items=output_items,
            function_calls=function_calls,
        )

    def run_function_tool_loop(
        self,
        *,
        request: OpenAIGatewayRequest,
        tool_executor,
        max_rounds: int = 4,
        on_tool_result=None,
    ) -> OpenAIToolLoopResult:
        current_request = request
        tool_traces: list[dict[str, Any]] = []
        response_ids: list[str] = []
        rounds = min(
            max(1, int(max_rounds or 1)),
            self.runtime_hardening_service.max_tool_loop_rounds(),
        )

        for loop_iteration in range(1, rounds + 1):
            gateway_response = self.create(current_request)
            response_ids.append(str(gateway_response.response_id or ""))
            function_calls = list(gateway_response.function_calls or [])
            if not function_calls:
                return OpenAIToolLoopResult(
                    response=gateway_response,
                    tool_traces=tool_traces,
                    response_ids=response_ids,
                    turns=loop_iteration,
                )

            continuation_input = list(gateway_response.output_items or [])
            for function_call in function_calls:
                loop_decision = self.runtime_hardening_service.validate_tool_loop(
                    tool_traces=tool_traces,
                    function_call=function_call,
                )
                if not bool(loop_decision.get("allowed")):
                    raise OpenAIGatewayError(
                        component=request.component,
                        code=str(loop_decision.get("reason") or "tool_loop_blocked"),
                        message=f"Function tool loop blocked: {loop_decision.get('reason')}",
                        metadata={
                            "component": request.component,
                            "trace_metadata": dict(request.trace_metadata or {}),
                            "request_metadata": dict(request.metadata or {}),
                            "response_ids": response_ids,
                            "tool_trace_count": len(tool_traces),
                            "loop_decision": loop_decision,
                        },
                    )
                started_at = datetime.now(timezone.utc).isoformat()
                started = time.perf_counter()
                try:
                    execution_payload = dict(tool_executor(function_call) or {})
                except Exception as exc:
                    execution_payload = {
                        "output": {
                            "ok": False,
                            "error": f"{type(exc).__name__}: {exc}",
                        },
                        "execution_status": "failed",
                        "validation_status": "runtime_exception",
                        "evidence_metadata": {"error_type": type(exc).__name__},
                    }
                duration_ms = int((time.perf_counter() - started) * 1000)
                finished_at = datetime.now(timezone.utc).isoformat()
                output_value = execution_payload.get("output")
                trace = {
                    "tool_call_id": str(function_call.get("call_id") or ""),
                    "tool_name": str(function_call.get("name") or ""),
                    "arguments": dict(
                        self.runtime_hardening_service.sanitize_payload(
                            dict(function_call.get("arguments") or {})
                        )
                    ),
                    "execution_status": str(execution_payload.get("execution_status") or "completed"),
                    "validation_status": str(execution_payload.get("validation_status") or ""),
                    "duration_ms": duration_ms,
                    "evidence_metadata": dict(
                        self.runtime_hardening_service.sanitize_payload(
                            dict(execution_payload.get("evidence_metadata") or {})
                        )
                    ),
                    "output_payload": self.runtime_hardening_service.sanitize_payload(
                        self._normalize_tool_output_payload(output_value)
                    ),
                    "model_response_id": str(gateway_response.response_id or ""),
                    "loop_iteration": loop_iteration,
                    "started_at": started_at,
                    "finished_at": finished_at,
                }
                tool_traces.append(trace)
                if callable(on_tool_result):
                    on_tool_result(trace)
                continuation_input.append(
                    {
                        "type": "function_call_output",
                        "call_id": str(function_call.get("call_id") or ""),
                        "output": self._stringify_tool_output(output_value),
                    }
                )
            current_request = replace(
                current_request,
                input=continuation_input,
                previous_response_id=None,
            )

        raise OpenAIGatewayError(
            component=request.component,
            code="tool_loop_max_rounds_exceeded",
            message=f"Function tool loop exceeded {rounds} rounds",
            metadata={
                "component": request.component,
                "trace_metadata": dict(request.trace_metadata or {}),
                "request_metadata": dict(request.metadata or {}),
                "response_ids": response_ids,
                "tool_trace_count": len(tool_traces),
            },
        )

    @staticmethod
    def _default_timeout_seconds() -> float:
        raw = str(os.getenv("IA_DEV_OPENAI_TIMEOUT_SECONDS", "30") or "30").strip()
        try:
            return max(1.0, float(raw))
        except Exception:
            return 30.0

    @staticmethod
    def _default_retries() -> int:
        raw = str(os.getenv("IA_DEV_OPENAI_RETRIES", "1") or "1").strip()
        try:
            return max(0, int(raw))
        except Exception:
            return 1

    @staticmethod
    def _build_client(*, api_key: str, timeout_seconds: float, retries: int):
        from openai import OpenAI

        return OpenAI(
            api_key=api_key,
            timeout=timeout_seconds,
            max_retries=retries,
        )

    @staticmethod
    def _build_payload(*, request: OpenAIGatewayRequest, model: str) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": model,
            "input": request.input,
        }
        if request.reasoning is not None:
            payload["reasoning"] = dict(request.reasoning)
        if request.text is not None:
            payload["text"] = dict(request.text)
        if request.store is not None:
            payload["store"] = bool(request.store)
        if request.background is not None:
            payload["background"] = bool(request.background)
        if str(request.previous_response_id or "").strip():
            payload["previous_response_id"] = str(request.previous_response_id).strip()
        if request.tools is not None:
            payload["tools"] = list(request.tools)
        if request.tool_choice is not None:
            payload["tool_choice"] = request.tool_choice
        for key, value in dict(request.extra_options or {}).items():
            if value is not None:
                payload[key] = value
        return payload

    @staticmethod
    def _extract_usage(response: Any) -> dict[str, Any]:
        usage = getattr(response, "usage", None)
        if usage is None:
            return {}
        if isinstance(usage, dict):
            payload = dict(usage)
        else:
            payload = dict(getattr(usage, "__dict__", {}) or {})
        input_tokens = payload.get("input_tokens")
        output_tokens = payload.get("output_tokens")
        total_tokens = payload.get("total_tokens")
        if total_tokens in (None, ""):
            try:
                total_tokens = int(input_tokens or 0) + int(output_tokens or 0)
            except Exception:
                total_tokens = 0
        return {
            "input_tokens": int(input_tokens or 0),
            "output_tokens": int(output_tokens or 0),
            "total_tokens": int(total_tokens or 0),
        }

    @classmethod
    def _extract_output_items(cls, response: Any) -> list[dict[str, Any]]:
        raw_items = getattr(response, "output", None)
        if not isinstance(raw_items, list):
            return []
        items: list[dict[str, Any]] = []
        for item in raw_items:
            normalized = cls._to_dict(item)
            if normalized:
                items.append(normalized)
        return items

    @classmethod
    def _extract_function_calls(cls, output_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        calls: list[dict[str, Any]] = []
        for index, item in enumerate(list(output_items or [])):
            if str(item.get("type") or "").strip() != "function_call":
                continue
            raw_arguments = item.get("arguments")
            arguments: dict[str, Any]
            if isinstance(raw_arguments, dict):
                arguments = dict(raw_arguments)
            else:
                try:
                    parsed = json.loads(str(raw_arguments or "{}"))
                except Exception:
                    parsed = {}
                arguments = dict(parsed) if isinstance(parsed, dict) else {}
            calls.append(
                {
                    "id": str(item.get("id") or ""),
                    "call_id": str(item.get("call_id") or ""),
                    "name": str(item.get("name") or ""),
                    "arguments_raw": str(raw_arguments or ""),
                    "arguments": arguments,
                    "output_index": index,
                }
            )
        return calls

    @staticmethod
    def _to_dict(value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return dict(value)
        if hasattr(value, "model_dump") and callable(value.model_dump):
            try:
                payload = value.model_dump()
                return dict(payload or {}) if isinstance(payload, dict) else {}
            except Exception:
                return {}
        if hasattr(value, "__dict__"):
            return dict(getattr(value, "__dict__", {}) or {})
        return {}

    @staticmethod
    def _stringify_tool_output(value: Any) -> str:
        if isinstance(value, str):
            return value
        try:
            return json.dumps(value, ensure_ascii=True)
        except Exception:
            return json.dumps({"ok": False, "error": "tool_output_not_serializable"}, ensure_ascii=True)

    @staticmethod
    def _normalize_tool_output_payload(value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return dict(value)
        if isinstance(value, list):
            return {"items": list(value)}
        if value is None:
            return {}
        return {"value": value}

    @staticmethod
    def _normalize_error_code(exc: Exception) -> str:
        name = type(exc).__name__.lower()
        if "timeout" in name:
            return "timeout"
        if "rate" in name:
            return "rate_limit"
        if "auth" in name or "permission" in name:
            return "authentication_error"
        if "connection" in name or "api" in name:
            return "api_error"
        return "openai_request_error"
