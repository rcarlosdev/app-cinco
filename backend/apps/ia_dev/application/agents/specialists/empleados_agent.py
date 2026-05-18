from __future__ import annotations

from apps.ia_dev.application.agents.specialists.base import BaseSpecialistAgent


class EmpleadosAgent(BaseSpecialistAgent):
    agent_name = "empleados_agent"
    domain_scope = "empleados"
    description = (
        "Especialista de empleados. Prioriza herramientas declarativas del dominio y respeta "
        "el gobierno estructural vigente del ai_dictionary."
    )
    supported_domains = ("empleados", "rrhh")
    supported_intents = ("empleados_query", "employee_query", "analytics_query", "detail", "count")
    default_tool_ids = ("empleados.count.active.v1", "empleados.detail.v1")
