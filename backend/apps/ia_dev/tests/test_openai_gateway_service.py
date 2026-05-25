from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from apps.ia_dev.infrastructure.ai.openai_gateway_contracts import (
    OpenAIGatewayError,
    OpenAIGatewayRequest,
)
from apps.ia_dev.infrastructure.ai.openai_gateway_service import OpenAIGatewayService


class OpenAIGatewayServiceTests(SimpleTestCase):
    def test_create_uses_model_policy_and_returns_uniform_metadata(self):
        captured: dict = {}

        class _ResponsesClient:
            @staticmethod
            def create(**kwargs):
                captured.update(kwargs)
                return SimpleNamespace(
                    id="resp_123",
                    output_text='{"ok":true}',
                    usage=SimpleNamespace(input_tokens=12, output_tokens=7, total_tokens=19),
                )

        class _Client:
            responses = _ResponsesClient()

        service = OpenAIGatewayService()
        request = OpenAIGatewayRequest(
            component="intent_classifier_service",
            model_route="intent_classifier",
            input=[{"role": "user", "content": "hola"}],
            timeout_seconds=15,
            retries=2,
            reasoning={"effort": "low"},
            metadata={"phase": "bootstrap"},
            trace_metadata={"run_id": "run-1"},
        )

        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key", "IA_DEV_INTENT_MODEL": "gpt-test-fast"}, clear=False):
            with patch.object(OpenAIGatewayService, "_build_client", return_value=_Client()):
                result = service.create(request)

        self.assertEqual(captured["model"], "gpt-test-fast")
        self.assertEqual(captured["reasoning"], {"effort": "low"})
        self.assertEqual(result.output_text, '{"ok":true}')
        self.assertEqual(result.usage["total_tokens"], 19)
        self.assertEqual(result.metadata["component"], "intent_classifier_service")
        self.assertEqual(result.metadata["model"], "gpt-test-fast")
        self.assertEqual(result.metadata["request_metadata"]["phase"], "bootstrap")
        self.assertEqual(result.metadata["trace_metadata"]["run_id"], "run-1")
        self.assertEqual(result.metadata["correlation"]["run_id"], "run-1")
        self.assertEqual(result.metadata["correlation"]["correlation_id"], "run-1")

    def test_create_allows_explicit_model_and_optional_response_features(self):
        captured: dict = {}

        class _ResponsesClient:
            @staticmethod
            def create(**kwargs):
                captured.update(kwargs)
                return SimpleNamespace(
                    id="resp_456",
                    output_text="ok",
                    usage={"input_tokens": 1, "output_tokens": 2, "total_tokens": 3},
                )

        class _Client:
            responses = _ResponsesClient()

        service = OpenAIGatewayService()
        request = OpenAIGatewayRequest(
            component="attendance_period_resolver_service",
            model="gpt-custom-period",
            input=[{"role": "user", "content": "ultimo mes"}],
            store=False,
            background=False,
            previous_response_id="resp_prev",
            tools=[{"type": "function", "name": "demo"}],
            tool_choice="auto",
            text={"format": {"type": "json_schema", "name": "period"}},
        )

        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}, clear=False):
            with patch.object(OpenAIGatewayService, "_build_client", return_value=_Client()):
                result = service.create(request)

        self.assertEqual(captured["model"], "gpt-custom-period")
        self.assertEqual(captured["previous_response_id"], "resp_prev")
        self.assertEqual(captured["tools"][0]["name"], "demo")
        self.assertEqual(captured["tool_choice"], "auto")
        self.assertEqual(result.metadata["model_source"], "explicit")

    def test_create_raises_missing_api_key_error(self):
        service = OpenAIGatewayService()
        request = OpenAIGatewayRequest(
            component="semantic_normalization_service",
            model_route="semantic_normalization_llm",
            input=[{"role": "user", "content": "x"}],
        )

        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(OpenAIGatewayError) as ctx:
                service.create(request)

        self.assertEqual(ctx.exception.code, "missing_api_key")

    def test_run_function_tool_loop_executes_function_calls_and_continues_reasoning(self):
        responses = [
            SimpleNamespace(
                id="resp_tool_1",
                output_text="",
                usage={"input_tokens": 3, "output_tokens": 4, "total_tokens": 7},
                output=[
                    {
                        "type": "reasoning",
                        "id": "rs_1",
                        "summary": [],
                    },
                    {
                        "type": "function_call",
                        "id": "fc_1",
                        "call_id": "call_1",
                        "name": "demo.lookup",
                        "arguments": "{\"value\":\"abc\"}",
                    },
                ],
            ),
            SimpleNamespace(
                id="resp_tool_2",
                output_text='{"ok": true}',
                usage={"input_tokens": 5, "output_tokens": 6, "total_tokens": 11},
                output=[],
            ),
        ]
        captured_payloads: list[dict] = []

        class _ResponsesClient:
            @staticmethod
            def create(**kwargs):
                captured_payloads.append(dict(kwargs))
                return responses.pop(0)

        class _Client:
            responses = _ResponsesClient()

        service = OpenAIGatewayService()
        request = OpenAIGatewayRequest(
            component="semantic_orchestrator_service",
            model="gpt-tool-test",
            input=[{"role": "user", "content": "hola"}],
            tools=[{"type": "function", "name": "demo.lookup", "parameters": {"type": "object"}}],
            tool_choice="auto",
        )

        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}, clear=False):
            with patch.object(OpenAIGatewayService, "_build_client", return_value=_Client()):
                result = service.run_function_tool_loop(
                    request=request,
                    tool_executor=lambda function_call: {
                        "output": {"resolved": function_call["arguments"]["value"].upper()},
                        "execution_status": "completed",
                        "validation_status": "validated",
                        "evidence_metadata": {"source": "test"},
                    },
                )

        self.assertEqual(result.response.output_text, '{"ok": true}')
        self.assertEqual(len(result.tool_traces), 1)
        self.assertEqual(str((result.tool_traces[0] or {}).get("tool_name") or ""), "demo.lookup")
        self.assertEqual(str((captured_payloads[-1].get("input")[-1] or {}).get("type") or ""), "function_call_output")
        self.assertEqual(str((captured_payloads[-1].get("input")[-1] or {}).get("call_id") or ""), "call_1")

    def test_create_normalizes_provider_errors(self):
        service = OpenAIGatewayService()
        request = OpenAIGatewayRequest(
            component="cause_diagnostics_service",
            model_route="cause_diagnostics",
            input=[{"role": "user", "content": "x"}],
        )

        class RateLimitError(Exception):
            pass

        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}, clear=False):
            with patch.object(OpenAIGatewayService, "_build_client", side_effect=RateLimitError("slow down")):
                with self.assertRaises(OpenAIGatewayError) as ctx:
                    service.create(request)

        self.assertEqual(ctx.exception.code, "rate_limit")
        self.assertEqual(ctx.exception.component, "cause_diagnostics_service")

    def test_run_function_tool_loop_blocks_repeated_same_tool_calls(self):
        responses = [
            SimpleNamespace(
                id="resp_tool_1",
                output_text="",
                usage={"input_tokens": 3, "output_tokens": 4, "total_tokens": 7},
                output=[
                    {
                        "type": "function_call",
                        "id": "fc_1",
                        "call_id": "call_1",
                        "name": "demo.lookup",
                        "arguments": "{\"value\":\"abc\"}",
                    },
                ],
            ),
            SimpleNamespace(
                id="resp_tool_2",
                output_text="",
                usage={"input_tokens": 3, "output_tokens": 4, "total_tokens": 7},
                output=[
                    {
                        "type": "function_call",
                        "id": "fc_2",
                        "call_id": "call_2",
                        "name": "demo.lookup",
                        "arguments": "{\"value\":\"abc\"}",
                    },
                ],
            ),
            SimpleNamespace(
                id="resp_tool_3",
                output_text="",
                usage={"input_tokens": 3, "output_tokens": 4, "total_tokens": 7},
                output=[
                    {
                        "type": "function_call",
                        "id": "fc_3",
                        "call_id": "call_3",
                        "name": "demo.lookup",
                        "arguments": "{\"value\":\"abc\"}",
                    },
                ],
            ),
        ]

        class _ResponsesClient:
            @staticmethod
            def create(**kwargs):
                return responses.pop(0)

        class _Client:
            responses = _ResponsesClient()

        service = OpenAIGatewayService()
        request = OpenAIGatewayRequest(
            component="semantic_orchestrator_service",
            model="gpt-tool-test",
            input=[{"role": "user", "content": "hola"}],
            tools=[{"type": "function", "name": "demo.lookup", "parameters": {"type": "object"}}],
            tool_choice="auto",
        )

        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}, clear=False):
            with patch.object(OpenAIGatewayService, "_build_client", return_value=_Client()):
                with self.assertRaises(OpenAIGatewayError) as ctx:
                    service.run_function_tool_loop(
                        request=request,
                        tool_executor=lambda function_call: {
                            "output": {"resolved": function_call["arguments"]["value"].upper()},
                            "execution_status": "completed",
                            "validation_status": "validated",
                            "evidence_metadata": {"token": "super-secret"},
                        },
                    )

        self.assertEqual(ctx.exception.code, "tool_loop_repeat_detected")
