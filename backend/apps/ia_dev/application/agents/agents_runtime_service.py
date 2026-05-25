from __future__ import annotations

import importlib.util
import json
import os
from typing import Any

from apps.ia_dev.application.agents.agents_registry import AgentsRegistryService
from apps.ia_dev.application.agents.manager_agent import ManagerAgent
from apps.ia_dev.application.context.run_context import RunContext
from apps.ia_dev.application.runtime.handoff_trace_service import HandoffTraceService
from apps.ia_dev.application.runtime.tool_registry_service import ToolRegistryService
from apps.ia_dev.infrastructure.ai.openai_gateway_contracts import OpenAIGatewayRequest
from apps.ia_dev.infrastructure.ai.openai_gateway_service import OpenAIGatewayService


class AgentsRuntimeService:
    REGISTRY_VERSION = "agents_runtime.v1"

    def __init__(
        self,
        *,
        gateway: OpenAIGatewayService | None = None,
        tool_registry_service: ToolRegistryService | None = None,
        agents_registry: AgentsRegistryService | None = None,
        handoff_trace_service: HandoffTraceService | None = None,
    ) -> None:
        self.gateway = gateway or OpenAIGatewayService()
        self.tool_registry_service = tool_registry_service or ToolRegistryService()
        self.agents_registry = agents_registry or AgentsRegistryService()
        self.handoff_trace_service = handoff_trace_service or HandoffTraceService()

    @staticmethod
    def _enabled() -> bool:
        raw = os.getenv("IA_DEV_AGENTS_RUNTIME_ENABLED", "1")
        return str(raw or "").strip().lower() in {"1", "true", "yes", "on"}

    @staticmethod
    def _sdk_available() -> bool:
        for module_name in ("agents", "openai_agents", "openai.agents"):
            try:
                if importlib.util.find_spec(module_name):
                    return True
            except Exception:
                continue
        return False

    def bootstrap_status(self) -> dict[str, Any]:
        sdk_available = self._sdk_available()
        return {
            "enabled": self._enabled(),
            "sdk_available": sdk_available,
            "implementation": "openai_agents_sdk" if sdk_available else "gateway_function_loop",
            "registry_version": self.REGISTRY_VERSION,
            "agent_registry_version": self.agents_registry.REGISTRY_VERSION,
        }

    def orchestrate(
        self,
        *,
        user_message: str,
        candidate_domain: str,
        candidate_intent: str,
        candidate_capability: str,
        semantic_orchestrator: dict[str, Any] | None,
        route_debug_hints: dict[str, Any] | None,
        run_context: RunContext | None,
        observability=None,
    ) -> dict[str, Any]:
        bootstrap = self.bootstrap_status()
        if not bootstrap["enabled"]:
            payload = {
                "enabled": False,
                "bootstrap": bootstrap,
                "manager": ManagerAgent.as_dict(),
                "agents": [],
                "handoffs": [],
                "agent_trace": [],
            }
            if run_context is not None:
                run_context.metadata["agents_runtime"] = payload
            return payload

        specialist = self.agents_registry.resolve_for_candidate(
            candidate_domain=candidate_domain,
            candidate_intent=candidate_intent,
            candidate_capability=candidate_capability,
        )
        specialist_tool_name = f"{self.agents_registry.TOOL_PREFIX}{specialist.agent_name}"
        specialist_payload: dict[str, Any] | None = None
        manager_reasoning = [
            {
                "step": "intake",
                "detail": (
                    f"domain={candidate_domain or 'unknown'} intent={candidate_intent or 'unknown'} "
                    f"capability={candidate_capability or 'unknown'}"
                ),
            },
            {
                "step": "delegation_policy",
                "detail": "El manager coordina y delega; el runtime deterministico conserva la autoridad de ejecucion.",
            },
        ]
        manager_tool_calls: list[dict[str, Any]] = []
        llm_used = False

        if self.gateway.is_enabled():
            try:
                specialist_payload, tool_traces, response_ids = self._run_manager_tool_loop(
                    user_message=user_message,
                    candidate_domain=candidate_domain,
                    candidate_intent=candidate_intent,
                    candidate_capability=candidate_capability,
                    semantic_orchestrator=dict(semantic_orchestrator or {}),
                    route_debug_hints=dict(route_debug_hints or {}),
                    selected_tool_name=specialist_tool_name,
                    run_context=run_context,
                )
                llm_used = specialist_payload is not None
                manager_tool_calls = list(tool_traces or [])
                if response_ids:
                    manager_reasoning.append(
                        {
                            "step": "manager_reasoning_loop",
                            "detail": f"Se ejecuto tool loop de manager con {len(response_ids)} respuestas OpenAI.",
                        }
                    )
            except Exception:
                specialist_payload = None

        if not isinstance(specialist_payload, dict) or not specialist_payload:
            specialist_payload = specialist.run(
                user_message=user_message,
                candidate_domain=candidate_domain,
                candidate_intent=candidate_intent,
                candidate_capability=candidate_capability,
                semantic_orchestrator=dict(semantic_orchestrator or {}),
                tool_registry_service=self.tool_registry_service,
            )

        manager_reasoning.append(
            {
                "step": "selected_specialist",
                "detail": f"Delegacion preparada hacia {specialist.agent_name}.",
            }
        )
        recommended_tools = list((specialist_payload.get("evidence_metadata") or {}).get("recommended_tool_ids") or [])
        handoff = self.handoff_trace_service.build_handoff(
            run_context=run_context,
            handoff_origin=ManagerAgent.AGENT_NAME,
            handoff_target=str(specialist_payload.get("agent_name") or specialist.agent_name),
            requested_by_agent=ManagerAgent.AGENT_NAME,
            reason="domain_aligned_specialist_selection",
            target_tool=str((recommended_tools[0] if recommended_tools else "") or specialist_tool_name),
            evidence={
                "candidate_domain": str(candidate_domain or ""),
                "candidate_intent": str(candidate_intent or ""),
                "candidate_capability": str(candidate_capability or ""),
                "recommended_tool_ids": recommended_tools,
                "agent_tool_name": specialist_tool_name,
            },
            status="completed",
        )
        manager_agent = {
            "agent_name": ManagerAgent.AGENT_NAME,
            "role": "manager",
            "status": "completed",
            "reasoning_steps": manager_reasoning,
            "tool_calls": manager_tool_calls,
            "tool_outputs": [
                {
                    "type": "specialist_selection",
                    "selected_specialist": str(specialist_payload.get("agent_name") or specialist.agent_name),
                    "llm_used": llm_used,
                }
            ],
            "validation_status": "validated",
            "evidence_metadata": {
                "selected_specialist": str(specialist_payload.get("agent_name") or specialist.agent_name),
                "candidate_domain": str(candidate_domain or ""),
                "candidate_intent": str(candidate_intent or ""),
                "candidate_capability": str(candidate_capability or ""),
                "implementation": bootstrap["implementation"],
            },
        }
        specialist_agent = {
            **dict(specialist_payload or {}),
            "handoff_origin": ManagerAgent.AGENT_NAME,
        }
        agents = [manager_agent, specialist_agent]
        agent_trace = [
            {
                "agent_name": str(manager_agent.get("agent_name") or ""),
                "handoff_origin": "",
                "handoff_target": str(handoff.get("handoff_target") or ""),
                "reasoning_steps": list(manager_agent.get("reasoning_steps") or []),
                "tool_calls": list(manager_agent.get("tool_calls") or []),
                "tool_outputs": list(manager_agent.get("tool_outputs") or []),
                "validation_status": str(manager_agent.get("validation_status") or ""),
                "evidence_metadata": dict(manager_agent.get("evidence_metadata") or {}),
                "handoff_id": str(handoff.get("handoff_id") or ""),
            },
            {
                "agent_name": str(specialist_agent.get("agent_name") or ""),
                "handoff_origin": str(handoff.get("handoff_origin") or ""),
                "handoff_target": "",
                "reasoning_steps": list(specialist_agent.get("reasoning_steps") or []),
                "tool_calls": list(specialist_agent.get("tool_calls") or []),
                "tool_outputs": list(specialist_agent.get("tool_outputs") or []),
                "validation_status": str(specialist_agent.get("validation_status") or ""),
                "evidence_metadata": dict(specialist_agent.get("evidence_metadata") or {}),
                "handoff_id": str(handoff.get("handoff_id") or ""),
            },
        ]
        payload = {
            "enabled": True,
            "bootstrap": bootstrap,
            "manager": ManagerAgent.as_dict(),
            "selected_specialist": str(specialist_agent.get("agent_name") or ""),
            "routing": {
                "candidate_domain": str(candidate_domain or ""),
                "candidate_intent": str(candidate_intent or ""),
                "candidate_capability": str(candidate_capability or ""),
                "selected_specialist": str(specialist_agent.get("agent_name") or ""),
                "implementation": bootstrap["implementation"],
            },
            "agents": agents,
            "handoffs": [handoff],
            "handoff_trace": [handoff],
            "agent_trace": agent_trace,
        }
        if run_context is not None:
            run_context.metadata["agents_runtime"] = payload
        self._record_events(
            observability=observability,
            run_context=run_context,
            manager_agent=manager_agent,
            specialist_agent=specialist_agent,
            handoff=handoff,
        )
        return payload

    def _run_manager_tool_loop(
        self,
        *,
        user_message: str,
        candidate_domain: str,
        candidate_intent: str,
        candidate_capability: str,
        semantic_orchestrator: dict[str, Any],
        route_debug_hints: dict[str, Any],
        selected_tool_name: str,
        run_context: RunContext | None,
    ) -> tuple[dict[str, Any] | None, list[dict[str, Any]], list[str]]:
        captured_outputs: dict[str, dict[str, Any]] = {}
        request = OpenAIGatewayRequest(
            component="agents_runtime_service",
            model_route="semantic_orchestrator",
            timeout_seconds=30,
            retries=1,
            tool_choice={
                "type": "function",
                "name": selected_tool_name,
            },
            tools=self.agents_registry.list_agent_tools(),
            metadata={
                "candidate_domain": str(candidate_domain or ""),
                "candidate_intent": str(candidate_intent or ""),
            },
            trace_metadata={
                "run_id": str((run_context.run_id if run_context else "") or ""),
                "trace_id": str((run_context.trace_id if run_context else "") or ""),
                "flow": "agents_runtime",
            },
            input=[
                {
                    "role": "system",
                    "content": [
                        {
                            "type": "input_text",
                            "text": (
                                "Actuas como manager agent. Debes delegar exactamente un especialista como function tool. "
                                "No generes SQL. No sustituyas ai_dictionary, planners, validadores ni runtime. "
                                "Usa la herramienta del especialista y luego responde JSON valido y breve."
                            ),
                        }
                    ],
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": json.dumps(
                                {
                                    "user_message": user_message,
                                    "candidate_domain": candidate_domain,
                                    "candidate_intent": candidate_intent,
                                    "candidate_capability": candidate_capability,
                                    "semantic_orchestrator": semantic_orchestrator,
                                    "route_debug_hints": route_debug_hints,
                                    "required_output": {
                                        "selected_specialist": "string",
                                        "reasoning_steps": ["string"],
                                        "recommended_tools": ["string"],
                                    },
                                },
                                ensure_ascii=True,
                            ),
                        }
                    ],
                },
            ],
        )

        def tool_executor(function_call: dict[str, Any]) -> dict[str, Any]:
            tool_name = str(function_call.get("name") or "")
            specialist_name = self.agents_registry.parse_agent_tool_name(tool_name)
            specialist = self.agents_registry.get_specialist(specialist_name)
            if specialist is None:
                return {
                    "output": {"ok": False, "error": f"specialist_not_registered:{tool_name}"},
                    "execution_status": "blocked",
                    "validation_status": "specialist_not_registered",
                    "evidence_metadata": {"tool_name": tool_name},
                }
            payload = specialist.run(
                user_message=user_message,
                candidate_domain=str(function_call.get("arguments", {}).get("candidate_domain") or candidate_domain),
                candidate_intent=str(function_call.get("arguments", {}).get("candidate_intent") or candidate_intent),
                candidate_capability=str(function_call.get("arguments", {}).get("candidate_capability") or candidate_capability),
                semantic_orchestrator=semantic_orchestrator,
                tool_registry_service=self.tool_registry_service,
            )
            captured_outputs[tool_name] = dict(payload)
            return {
                "output": payload,
                "execution_status": "completed",
                "validation_status": "validated",
                "evidence_metadata": {
                    "agent_name": specialist.agent_name,
                    "candidate_domain": candidate_domain,
                },
            }

        result = self.gateway.run_function_tool_loop(
            request=request,
            tool_executor=tool_executor,
        )
        payload: dict[str, Any] | None = None
        selected_payload = captured_outputs.get(selected_tool_name)
        if isinstance(selected_payload, dict) and selected_payload:
            payload = selected_payload
        return payload, list(result.tool_traces or []), list(result.response_ids or [])

    @staticmethod
    def _record_events(
        *,
        observability,
        run_context: RunContext | None,
        manager_agent: dict[str, Any],
        specialist_agent: dict[str, Any],
        handoff: dict[str, Any],
    ) -> None:
        if observability is None or not hasattr(observability, "record_event"):
            return
        base_meta = {
            "run_id": str((run_context.run_id if run_context else "") or ""),
            "trace_id": str((run_context.trace_id if run_context else "") or ""),
        }
        observability.record_event(
            event_type="agents_runtime_manager_selected",
            source="AgentsRuntimeService",
            meta={
                **base_meta,
                "agent_name": str(manager_agent.get("agent_name") or ""),
                "selected_specialist": str((manager_agent.get("evidence_metadata") or {}).get("selected_specialist") or ""),
            },
        )
        observability.record_event(
            event_type="agents_runtime_handoff",
            source="AgentsRuntimeService",
            meta={**base_meta, **dict(handoff or {})},
        )
        observability.record_event(
            event_type="agents_runtime_handoff_trace_recorded",
            source="AgentsRuntimeService",
            meta={**base_meta, **dict(handoff or {})},
        )
        observability.record_event(
            event_type="agents_runtime_specialist_completed",
            source="AgentsRuntimeService",
            meta={
                **base_meta,
                "agent_name": str(specialist_agent.get("agent_name") or ""),
                "validation_status": str(specialist_agent.get("validation_status") or ""),
            },
        )
