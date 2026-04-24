from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class CapabilityDefinition:
    capability_id: str
    domain: str
    handler_key: str
    description: str
    legacy_intents: tuple[str, ...] = ()
    policy_tags: tuple[str, ...] = ()
    rollout_flag: str | None = None
    version: str = "v1"

    def as_dict(self) -> dict[str, Any]:
        return {
            "capability_id": self.capability_id,
            "domain": self.domain,
            "handler_key": self.handler_key,
            "description": self.description,
            "legacy_intents": list(self.legacy_intents),
            "policy_tags": list(self.policy_tags),
            "rollout_flag": self.rollout_flag,
            "version": self.version,
        }


class CapabilityCatalog:
    def __init__(self):
        capabilities = self._build_default_capabilities()
        self._by_id: dict[str, CapabilityDefinition] = {
            item.capability_id: item for item in capabilities
        }

    def get(self, capability_id: str) -> CapabilityDefinition | None:
        return self._by_id.get(str(capability_id or "").strip())

    def list_all(self) -> list[CapabilityDefinition]:
        return list(self._by_id.values())

    @staticmethod
    def _build_default_capabilities() -> list[CapabilityDefinition]:
        return [
            CapabilityDefinition(
                capability_id="attendance.period.resolve.v1",
                domain="ausentismo",
                handler_key="attendance.period_resolver",
                description="Resolver periodo para consultas de asistencia.",
                legacy_intents=("attendance_period_probe",),
                policy_tags=("contains_personal_data",),
                rollout_flag="IA_DEV_CAP_ATTENDANCE_ENABLED",
            ),
            CapabilityDefinition(
                capability_id="attendance.unjustified.summary.v1",
                domain="ausentismo",
                handler_key="attendance.unjustified_summary",
                description="Resumen de ausentismos injustificados.",
                legacy_intents=("ausentismo_query", "attendance_query"),
                policy_tags=("contains_personal_data",),
                rollout_flag="IA_DEV_CAP_ATTENDANCE_ENABLED|IA_DEV_CAP_ATTENDANCE_SUMMARY_ENABLED",
            ),
            CapabilityDefinition(
                capability_id="attendance.unjustified.table.v1",
                domain="ausentismo",
                handler_key="attendance.unjustified_table",
                description="Tabla de ausentismos injustificados sin join de personal.",
                legacy_intents=("ausentismo_query", "attendance_query"),
                policy_tags=("contains_personal_data",),
                rollout_flag="IA_DEV_CAP_ATTENDANCE_ENABLED|IA_DEV_CAP_ATTENDANCE_TABLE_ENABLED",
            ),
            CapabilityDefinition(
                capability_id="attendance.unjustified.table_with_personal.v1",
                domain="ausentismo",
                handler_key="attendance.unjustified_table_with_personal",
                description="Tabla de ausentismos injustificados con personal.",
                legacy_intents=("ausentismo_query", "attendance_query"),
                policy_tags=("contains_personal_data",),
                rollout_flag="IA_DEV_CAP_ATTENDANCE_ENABLED|IA_DEV_CAP_ATTENDANCE_TABLE_ENABLED",
            ),
            CapabilityDefinition(
                capability_id="attendance.recurrence.grouped.v1",
                domain="ausentismo",
                handler_key="attendance.recurrence_grouped",
                description="Reincidencia agrupada por empleado.",
                legacy_intents=("ausentismo_recurrencia", "attendance_recurrence"),
                policy_tags=("contains_personal_data",),
                rollout_flag="IA_DEV_CAP_ATTENDANCE_ENABLED|IA_DEV_CAP_ATTENDANCE_RECURRENCE_ENABLED",
            ),
            CapabilityDefinition(
                capability_id="attendance.recurrence.itemized.v1",
                domain="ausentismo",
                handler_key="attendance.recurrence_itemized",
                description="Reincidencia en vista dia a dia.",
                legacy_intents=("ausentismo_recurrencia", "attendance_recurrence"),
                policy_tags=("contains_personal_data",),
                rollout_flag="IA_DEV_CAP_ATTENDANCE_ENABLED|IA_DEV_CAP_ATTENDANCE_RECURRENCE_ENABLED",
            ),
            CapabilityDefinition(
                capability_id="attendance.summary.by_supervisor.v1",
                domain="ausentismo",
                handler_key="attendance.summary_by_supervisor",
                description="Resumen de ausentismos injustificados agrupado por supervisor.",
                legacy_intents=("ausentismo_query", "attendance_query"),
                policy_tags=("contains_personal_data", "contains_operational_data"),
                rollout_flag="IA_DEV_CAP_ATTENDANCE_ENABLED|IA_DEV_CAP_ATTENDANCE_ANALYTICS_ENABLED",
            ),
            CapabilityDefinition(
                capability_id="attendance.summary.by_area.v1",
                domain="ausentismo",
                handler_key="attendance.summary_by_area",
                description="Resumen de ausentismos injustificados agrupado por area.",
                legacy_intents=("ausentismo_query", "attendance_query"),
                policy_tags=("contains_personal_data", "contains_operational_data"),
                rollout_flag="IA_DEV_CAP_ATTENDANCE_ENABLED|IA_DEV_CAP_ATTENDANCE_ANALYTICS_ENABLED",
            ),
            CapabilityDefinition(
                capability_id="attendance.summary.by_cargo.v1",
                domain="ausentismo",
                handler_key="attendance.summary_by_cargo",
                description="Resumen de ausentismos injustificados agrupado por cargo.",
                legacy_intents=("ausentismo_query", "attendance_query"),
                policy_tags=("contains_personal_data", "contains_operational_data"),
                rollout_flag="IA_DEV_CAP_ATTENDANCE_ENABLED|IA_DEV_CAP_ATTENDANCE_ANALYTICS_ENABLED",
            ),
            CapabilityDefinition(
                capability_id="attendance.summary.by_attribute.v1",
                domain="ausentismo",
                handler_key="attendance.summary_by_attribute",
                description="Resumen de ausentismos agrupado por atributo semantico (supervisor/area/cargo/carpeta/justificacion/tipo).",
                legacy_intents=("ausentismo_query", "attendance_query"),
                policy_tags=("contains_personal_data", "contains_operational_data"),
                rollout_flag="IA_DEV_CAP_ATTENDANCE_ENABLED|IA_DEV_CAP_ATTENDANCE_ANALYTICS_ENABLED",
            ),
            CapabilityDefinition(
                capability_id="attendance.trend.daily.v1",
                domain="ausentismo",
                handler_key="attendance.trend_daily",
                description="Tendencia diaria de ausentismos injustificados.",
                legacy_intents=("ausentismo_query", "attendance_query"),
                policy_tags=("contains_operational_data",),
                rollout_flag="IA_DEV_CAP_ATTENDANCE_ENABLED|IA_DEV_CAP_ATTENDANCE_ANALYTICS_ENABLED",
            ),
            CapabilityDefinition(
                capability_id="attendance.trend.monthly.v1",
                domain="ausentismo",
                handler_key="attendance.trend_monthly",
                description="Tendencia mensual de ausentismos injustificados.",
                legacy_intents=("ausentismo_query", "attendance_query"),
                policy_tags=("contains_operational_data",),
                rollout_flag="IA_DEV_CAP_ATTENDANCE_ENABLED|IA_DEV_CAP_ATTENDANCE_ANALYTICS_ENABLED",
            ),
            CapabilityDefinition(
                capability_id="transport.departures.summary.v1",
                domain="transport",
                handler_key="transport.departures_summary",
                description="Resumen de salidas de vehiculos por fecha.",
                legacy_intents=("transport_query",),
                policy_tags=("contains_operational_data",),
                rollout_flag="IA_DEV_CAP_TRANSPORT_ENABLED|IA_DEV_CAP_TRANSPORT_SUMMARY_ENABLED",
            ),
            CapabilityDefinition(
                capability_id="empleados.count.active.v1",
                domain="empleados",
                handler_key="empleados.count_active",
                description="Cantidad de empleados activos.",
                legacy_intents=("empleados_query",),
                policy_tags=("contains_personal_data", "contains_operational_data"),
                rollout_flag="IA_DEV_CAP_EMPLEADOS_ENABLED|IA_DEV_CAP_EMPLEADOS_COUNT_ENABLED",
            ),
            CapabilityDefinition(
                capability_id="empleados.detail.v1",
                domain="empleados",
                handler_key="empleados.detail",
                description="Detalle de empleado por identificador de negocio.",
                legacy_intents=("empleados_query",),
                policy_tags=("contains_personal_data",),
                rollout_flag="IA_DEV_CAP_EMPLEADOS_ENABLED",
            ),
            CapabilityDefinition(
                capability_id="knowledge.proposal.create.v1",
                domain="knowledge",
                handler_key="knowledge.proposal_create",
                description="Crear propuesta de conocimiento.",
                legacy_intents=("knowledge_change_request",),
                policy_tags=("requires_governance",),
                rollout_flag="IA_DEV_CAP_KNOWLEDGE_PROPOSAL_CREATE_V1",
            ),
            CapabilityDefinition(
                capability_id="knowledge.proposal.approve.v1",
                domain="knowledge",
                handler_key="knowledge.proposal_approve",
                description="Aprobar propuesta de conocimiento.",
                legacy_intents=("knowledge_approve",),
                policy_tags=("requires_approval", "requires_governance"),
                rollout_flag="IA_DEV_CAP_KNOWLEDGE_PROPOSAL_APPROVE_V1",
            ),
            CapabilityDefinition(
                capability_id="knowledge.proposal.reject.v1",
                domain="knowledge",
                handler_key="knowledge.proposal_reject",
                description="Rechazar propuesta de conocimiento.",
                legacy_intents=("knowledge_reject",),
                policy_tags=("requires_governance",),
                rollout_flag="IA_DEV_CAP_KNOWLEDGE_PROPOSAL_REJECT_V1",
            ),
            CapabilityDefinition(
                capability_id="general.answer.v1",
                domain="general",
                handler_key="general.answer",
                description="Respuesta general con LLM.",
                legacy_intents=("general_question", "create_ticket"),
                policy_tags=(),
                rollout_flag="IA_DEV_CAP_GENERAL_ANSWER_V1",
            ),
            CapabilityDefinition(
                capability_id="legacy.passthrough.v1",
                domain="legacy",
                handler_key="legacy.passthrough",
                description="Fallback para conservar comportamiento legacy.",
                legacy_intents=(),
                policy_tags=(),
                rollout_flag=None,
            ),
        ]
