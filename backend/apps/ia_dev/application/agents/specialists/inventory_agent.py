from __future__ import annotations

from apps.ia_dev.application.agents.specialists.base import BaseSpecialistAgent
from apps.ia_dev.application.runtime.tool_registry_service import ToolRegistryService


class InventoryAgent(BaseSpecialistAgent):
    agent_name = "inventory_agent"
    domain_scope = "inventario_logistica"
    description = (
        "Especialista de inventario y logistica. Interpreta alcance operativo, conserva gobierno "
        "semantico y prepara tools declarativas seguras del runtime."
    )
    supported_domains = ("inventario_logistica",)
    supported_intents = ("inventory_query", "stock_balance", "movement_history", "serial_holder_query")
    default_tool_ids = (ToolRegistryService.SQL_ASSISTED_TOOL_ID,)
