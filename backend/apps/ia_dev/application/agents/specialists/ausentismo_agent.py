from __future__ import annotations

from apps.ia_dev.application.agents.specialists.base import BaseSpecialistAgent


class AusentismoAgent(BaseSpecialistAgent):
    agent_name = "ausentismo_agent"
    domain_scope = "ausentismo"
    description = (
        "Especialista de ausentismo/attendance. Coordina contexto del dominio y recomienda "
        "la tool declarativa alineada al runtime actual."
    )
    supported_domains = ("ausentismo", "attendance")
    supported_intents = ("ausentismo_query", "attendance_query", "analytics_query", "trend", "aggregate")
    default_tool_ids = (
        "attendance.unjustified.summary.v1",
        "attendance.summary.by_attribute.v1",
        "attendance.trend.daily.v1",
    )
