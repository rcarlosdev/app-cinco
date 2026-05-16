from __future__ import annotations

from typing import Any

from apps.ia_dev.application.runtime.tool_registry_service import ToolRegistryService


class BaseSpecialistAgent:
    agent_name = "specialist_agent"
    role = "specialist"
    domain_scope = "shared"
    description = ""
    supported_domains: tuple[str, ...] = ()
    supported_intents: tuple[str, ...] = ()
    default_tool_ids: tuple[str, ...] = ()

    def matches(
        self,
        *,
        candidate_domain: str,
        candidate_intent: str,
        candidate_capability: str,
    ) -> bool:
        normalized_domain = str(candidate_domain or "").strip().lower()
        normalized_intent = str(candidate_intent or "").strip().lower()
        normalized_capability = str(candidate_capability or "").strip().lower()
        if normalized_domain and normalized_domain in set(self.supported_domains):
            return True
        if normalized_intent and normalized_intent in set(self.supported_intents):
            return True
        return bool(
            normalized_capability
            and any(
                normalized_capability.startswith(prefix)
                for prefix in (
                    tuple(item for item in self.supported_domains if item)
                    + tuple(item for item in self.supported_intents if item)
                )
            )
        )

    def as_tool(self) -> dict[str, Any]:
        return {
            "type": "function",
            "name": f"agent.delegate.{self.agent_name}",
            "description": str(self.description or self.agent_name),
            "parameters": {
                "type": "object",
                "properties": {
                    "focus": {"type": "string"},
                    "candidate_domain": {"type": "string"},
                    "candidate_intent": {"type": "string"},
                    "candidate_capability": {"type": "string"},
                },
                "additionalProperties": False,
            },
        }

    def build_reasoning_steps(
        self,
        *,
        candidate_domain: str,
        candidate_intent: str,
        candidate_capability: str,
        semantic_orchestrator: dict[str, Any],
    ) -> list[dict[str, Any]]:
        return [
            {
                "step": "domain_alignment",
                "detail": (
                    f"domain={candidate_domain or 'unknown'} intent={candidate_intent or 'unknown'} "
                    f"capability={candidate_capability or 'unknown'}"
                ),
            },
            {
                "step": "runtime_authority",
                "detail": (
                    "Se mantiene ai_dictionary como autoridad estructural y "
                    "QueryExecutionPlanner como autoridad unica de SQL seguro."
                ),
            },
            {
                "step": "semantic_guardrails",
                "detail": str(semantic_orchestrator.get("reasoning_summary") or "Se aplica contexto semantico gobernado."),
            },
        ]

    def recommended_tool_ids(
        self,
        *,
        candidate_capability: str,
    ) -> list[str]:
        recommended = [str(item or "").strip() for item in self.default_tool_ids if str(item or "").strip()]
        capability = str(candidate_capability or "").strip()
        if capability:
            recommended.append(capability)
        return list(dict.fromkeys(recommended))

    def run(
        self,
        *,
        user_message: str,
        candidate_domain: str,
        candidate_intent: str,
        candidate_capability: str,
        semantic_orchestrator: dict[str, Any],
        tool_registry_service: ToolRegistryService,
    ) -> dict[str, Any]:
        available_tools = [
            tool_id
            for tool_id in self.recommended_tool_ids(candidate_capability=candidate_capability)
            if tool_registry_service.get_tool(tool_id) is not None
        ]
        return {
            "agent_name": self.agent_name,
            "role": self.role,
            "domain_scope": self.domain_scope,
            "status": "completed",
            "reasoning_steps": self.build_reasoning_steps(
                candidate_domain=candidate_domain,
                candidate_intent=candidate_intent,
                candidate_capability=candidate_capability,
                semantic_orchestrator=semantic_orchestrator,
            ),
            "tool_calls": [],
            "tool_outputs": [
                {
                    "type": "recommended_tools",
                    "tool_ids": available_tools,
                    "message_excerpt": str(user_message or "")[:160],
                }
            ],
            "validation_status": "validated",
            "evidence_metadata": {
                "recommended_tool_ids": available_tools,
                "candidate_capability": str(candidate_capability or ""),
                "candidate_domain": str(candidate_domain or ""),
                "candidate_intent": str(candidate_intent or ""),
            },
        }
