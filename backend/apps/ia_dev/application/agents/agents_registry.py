from __future__ import annotations

from typing import Any

from apps.ia_dev.application.agents.specialists import (
    AusentismoAgent,
    EmpleadosAgent,
    InventoryAgent,
    SemanticResolutionAgent,
)


class AgentsRegistryService:
    REGISTRY_VERSION = "agents_registry.v1"
    TOOL_PREFIX = "agent.delegate."

    def __init__(self) -> None:
        specialists = [
            InventoryAgent(),
            EmpleadosAgent(),
            AusentismoAgent(),
            SemanticResolutionAgent(),
        ]
        self._specialists = {agent.agent_name: agent for agent in specialists}

    def list_specialists(self) -> list[Any]:
        return list(self._specialists.values())

    def get_specialist(self, agent_name: str) -> Any | None:
        return self._specialists.get(str(agent_name or "").strip())

    def list_agent_tools(self) -> list[dict[str, Any]]:
        return [agent.as_tool() for agent in self.list_specialists()]

    def resolve_for_candidate(
        self,
        *,
        candidate_domain: str,
        candidate_intent: str,
        candidate_capability: str,
    ) -> Any:
        for specialist in self.list_specialists():
            if specialist.matches(
                candidate_domain=candidate_domain,
                candidate_intent=candidate_intent,
                candidate_capability=candidate_capability,
            ):
                return specialist
        return self.get_specialist("semantic_resolution_agent")

    @classmethod
    def parse_agent_tool_name(cls, tool_name: str) -> str:
        label = str(tool_name or "").strip()
        if not label.startswith(cls.TOOL_PREFIX):
            return label
        return label[len(cls.TOOL_PREFIX) :]
