from __future__ import annotations

from apps.ia_dev.application.agents.specialists.base import BaseSpecialistAgent
from apps.ia_dev.application.runtime.tool_registry_service import ToolRegistryService


class SemanticResolutionAgent(BaseSpecialistAgent):
    agent_name = "semantic_resolution_agent"
    domain_scope = "shared"
    description = (
        "Especialista transversal para desambiguacion semantica y consolidacion de contexto "
        "gobernado antes de delegar al runtime deterministico."
    )
    supported_domains = ("general", "shared")
    supported_intents = ("fallback", "clarification", "semantic_resolution")
    default_tool_ids = (
        ToolRegistryService.SEMANTIC_DICTIONARY_TOOL_ID,
        ToolRegistryService.SEMANTIC_DOMAIN_TOOL_ID,
        ToolRegistryService.SEMANTIC_MEMORY_TOOL_ID,
        ToolRegistryService.SEMANTIC_BASELINE_TOOL_ID,
        ToolRegistryService.SEMANTIC_ROUTE_HINTS_TOOL_ID,
    )
