from __future__ import annotations

import os
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from apps.ia_dev.application.context.run_context import RunContext
from apps.ia_dev.application.contracts.query_intelligence_contracts import (
    QueryExecutionPlan,
    ResolvedQuerySpec,
    StructuredQueryIntent,
)
from apps.ia_dev.application.orchestration.chat_application_service import (
    ChatApplicationService,
)
from apps.ia_dev.application.runtime.service_runtime_bootstrap import (
    apply_service_runtime_bootstrap,
)
from apps.ia_dev.application.semantic.query_execution_planner import QueryExecutionPlanner
from apps.ia_dev.application.workflow.task_state_service import TaskStateService


def _period(*, label: str = "2026-04", start: str = "2026-04-01", end: str = "2026-04-30") -> dict[str, str]:
    return {
        "label": label,
        "start_date": start,
        "end_date": end,
    }


def _transport_period(
    *,
    label: str = "2018-06_a_2018-08",
    start: str = "2018-06-01",
    end: str = "2018-08-31",
) -> dict[str, str]:
    return _period(label=label, start=start, end=end)


def _ausentismo_context(*, supports_sql_assisted: bool = True, allowed_columns: list[str] | None = None) -> dict[str, Any]:
    columns = list(
        allowed_columns
        or [
            "fecha_edit",
            "justificacion",
            "area",
            "cargo",
            "zona_nodo",
            "nombre",
            "apellido",
            "cedula",
        ]
    )
    return {
        "tables": [
            {
                "schema_name": "cincosas_cincosas",
                "table_name": "gestionh_ausentismo",
                "table_fqn": "cincosas_cincosas.gestionh_ausentismo",
                "rol": "fact",
            },
            {
                "schema_name": "cincosas_cincosas",
                "table_name": "cinco_base_de_personal",
                "table_fqn": "cincosas_cincosas.cinco_base_de_personal",
            },
        ],
        "column_profiles": [
            {
                "table_name": "gestionh_ausentismo",
                "logical_name": "fecha_ausentismo",
                "column_name": "fecha_edit",
                "is_date": True,
            },
            {"table_name": "gestionh_ausentismo", "logical_name": "justificacion", "column_name": "justificacion"},
            {
                "table_name": "gestionh_ausentismo",
                "logical_name": "dias_perdidos",
                "column_name": "dias_perdidos",
                "supports_metric": True,
            },
            {
                "table_name": "cinco_base_de_personal",
                "logical_name": "area",
                "column_name": "area",
                "supports_group_by": True,
                "supports_dimension": True,
            },
            {
                "table_name": "cinco_base_de_personal",
                "logical_name": "cargo",
                "column_name": "cargo",
                "supports_group_by": True,
                "supports_dimension": True,
            },
            {
                "table_name": "cinco_base_de_personal",
                "logical_name": "sede",
                "column_name": "zona_nodo",
                "supports_group_by": True,
                "supports_dimension": True,
            },
            {"table_name": "cinco_base_de_personal", "logical_name": "nombre", "column_name": "nombre"},
            {"table_name": "cinco_base_de_personal", "logical_name": "apellido", "column_name": "apellido"},
            {
                "table_name": "cinco_base_de_personal",
                "logical_name": "cedula",
                "column_name": "cedula",
                "is_identifier": True,
            },
        ],
        "allowed_tables": [
            "cincosas_cincosas.gestionh_ausentismo",
            "cincosas_cincosas.cinco_base_de_personal",
        ],
        "allowed_columns": columns,
        "dictionary": {
            "relations": [
                {
                    "nombre_relacion": "ausentismo_empleado",
                    "join_sql": "gestionh_ausentismo.cedula = cinco_base_de_personal.cedula",
                }
            ]
        },
        "synonym_index": {
            "areas": "area",
            "cargos": "cargo",
            "sedes": "sede",
            "empleados": "empleado",
        },
        "aliases": {"areas": "area", "cargos": "cargo", "sedes": "sede"},
        "source_of_truth": {
            "pilot_sql_assisted_enabled": supports_sql_assisted,
            "used_dictionary": True,
            "used_yaml": True,
            "structural": "ai_dictionary.dd_*",
            "narrative": "yaml_domain_context",
            "structural_authority": "dictionary_first",
        },
        "supports_sql_assisted": supports_sql_assisted,
        "domain_status": "partial",
    }


def _empleados_context(*, supports_sql_assisted: bool = False) -> dict[str, Any]:
    return {
        "tables": [
            {
                "schema_name": "cincosas_cincosas",
                "table_name": "cinco_base_de_personal",
                "table_fqn": "cincosas_cincosas.cinco_base_de_personal",
                "rol": "fact",
            },
        ],
        "column_profiles": [
            {
                "table_name": "cinco_base_de_personal",
                "logical_name": "cedula",
                "column_name": "cedula",
                "is_identifier": True,
            },
            {"table_name": "cinco_base_de_personal", "logical_name": "nombre", "column_name": "nombre"},
            {"table_name": "cinco_base_de_personal", "logical_name": "apellido", "column_name": "apellido"},
            {"table_name": "cinco_base_de_personal", "logical_name": "cargo", "column_name": "cargo"},
            {"table_name": "cinco_base_de_personal", "logical_name": "area", "column_name": "area"},
            {"table_name": "cinco_base_de_personal", "logical_name": "sede", "column_name": "zona_nodo"},
            {
                "table_name": "cinco_base_de_personal",
                "logical_name": "fecha_nacimiento",
                "column_name": "fnacimiento",
                "is_date": True,
            },
            {
                "table_name": "cinco_base_de_personal",
                "logical_name": "estado",
                "column_name": "estado",
                "allowed_values": ["ACTIVO", "INACTIVO"],
            },
        ],
        "allowed_tables": ["cincosas_cincosas.cinco_base_de_personal"],
        "allowed_columns": [
            "cedula",
            "nombre",
            "apellido",
            "cargo",
            "area",
            "zona_nodo",
            "fnacimiento",
            "estado",
        ],
        "source_of_truth": {
            "pilot_sql_assisted_enabled": supports_sql_assisted,
            "used_dictionary": True,
            "used_yaml": True,
            "structural": "ai_dictionary.dd_*",
            "narrative": "yaml_domain_context",
            "structural_authority": "dictionary_first",
        },
        "supports_sql_assisted": supports_sql_assisted,
        "domain_status": "active",
    }


def _transporte_context(
    *,
    supports_sql_assisted: bool = True,
    include_employee_dimension: bool = True,
) -> dict[str, Any]:
    tables = [
        {
            "schema_name": "cincosas_cincosas",
            "table_name": "nokia_base_ruta_programacion",
            "table_fqn": "cincosas_cincosas.nokia_base_ruta_programacion",
            "rol": "fact",
            "es_principal": True,
        },
    ]
    if include_employee_dimension:
        tables.append(
            {
                "schema_name": "cincosas_cincosas",
                "table_name": "cinco_base_de_personal",
                "table_fqn": "cincosas_cincosas.cinco_base_de_personal",
                "rol": "dimension",
            }
        )

    column_profiles = [
        {
            "table_name": "nokia_base_ruta_programacion",
            "logical_name": "fecha_programacion",
            "column_name": "fprogramacion",
            "is_date": True,
            "supports_filter": True,
            "supports_group_by": True,
            "supports_dimension": True,
        },
        {
            "table_name": "nokia_base_ruta_programacion",
            "logical_name": "fecha_actualizacion",
            "column_name": "fecha_edit",
            "is_date": True,
        },
        {
            "table_name": "nokia_base_ruta_programacion",
            "logical_name": "ruta",
            "column_name": "wp",
            "supports_filter": True,
            "supports_group_by": True,
            "supports_dimension": True,
        },
        {
            "table_name": "nokia_base_ruta_programacion",
            "logical_name": "sitio",
            "column_name": "sitio",
            "supports_filter": True,
            "supports_group_by": True,
            "supports_dimension": True,
        },
        {
            "table_name": "nokia_base_ruta_programacion",
            "logical_name": "tecnico",
            "column_name": "cedula",
            "supports_filter": True,
            "supports_group_by": True,
            "supports_dimension": True,
            "is_identifier": True,
        },
        {
            "table_name": "nokia_base_ruta_programacion",
            "logical_name": "tecnico_cedula",
            "column_name": "cedula",
            "supports_filter": True,
            "supports_group_by": True,
            "supports_dimension": True,
            "is_identifier": True,
        },
        {
            "table_name": "nokia_base_ruta_programacion",
            "logical_name": "estado",
            "column_name": "estado",
            "supports_filter": True,
            "supports_group_by": True,
            "supports_dimension": True,
        },
        {
            "table_name": "nokia_base_ruta_programacion",
            "logical_name": "razon",
            "column_name": "razon",
            "supports_filter": True,
            "supports_group_by": True,
            "supports_dimension": True,
        },
        {
            "table_name": "nokia_base_ruta_programacion",
            "logical_name": "proyecto",
            "column_name": "proyecto",
            "supports_filter": True,
            "supports_group_by": True,
            "supports_dimension": True,
        },
        {
            "table_name": "nokia_base_ruta_programacion",
            "logical_name": "region",
            "column_name": "region",
            "supports_filter": True,
            "supports_group_by": True,
            "supports_dimension": True,
        },
        {
            "table_name": "nokia_base_ruta_programacion",
            "logical_name": "ciudad",
            "column_name": "ciudad",
            "supports_filter": True,
            "supports_group_by": True,
            "supports_dimension": True,
        },
        {
            "table_name": "nokia_base_ruta_programacion",
            "logical_name": "subvector",
            "column_name": "sv",
            "supports_filter": True,
            "supports_group_by": True,
            "supports_dimension": True,
        },
        {
            "table_name": "nokia_base_ruta_programacion",
            "logical_name": "facturacion",
            "column_name": "facturacion",
            "supports_filter": True,
            "supports_group_by": True,
            "supports_dimension": True,
        },
    ]
    if include_employee_dimension:
        column_profiles.extend(
            [
                {
                    "table_name": "cinco_base_de_personal",
                    "logical_name": "supervisor",
                    "column_name": "supervisor",
                    "supports_filter": True,
                    "supports_group_by": True,
                    "supports_dimension": True,
                },
                {
                    "table_name": "cinco_base_de_personal",
                    "logical_name": "area",
                    "column_name": "area",
                    "supports_filter": True,
                    "supports_group_by": True,
                    "supports_dimension": True,
                },
                {
                    "table_name": "cinco_base_de_personal",
                    "logical_name": "cargo",
                    "column_name": "cargo",
                    "supports_filter": True,
                    "supports_group_by": True,
                    "supports_dimension": True,
                },
                {
                    "table_name": "cinco_base_de_personal",
                    "logical_name": "sede",
                    "column_name": "zona_nodo",
                    "supports_filter": True,
                    "supports_group_by": True,
                    "supports_dimension": True,
                },
                {
                    "table_name": "cinco_base_de_personal",
                    "logical_name": "nombre_tecnico",
                    "column_name": "nombre",
                },
                {
                    "table_name": "cinco_base_de_personal",
                    "logical_name": "apellido_tecnico",
                    "column_name": "apellido",
                },
                {
                    "table_name": "cinco_base_de_personal",
                    "logical_name": "cedula_empleado",
                    "column_name": "cedula",
                    "is_identifier": True,
                },
            ]
        )

    allowed_columns = [
        "fprogramacion",
        "fecha_edit",
        "wp",
        "sitio",
        "cedula",
        "estado",
        "razon",
        "proyecto",
        "region",
        "ciudad",
        "sv",
        "facturacion",
    ]
    if include_employee_dimension:
        allowed_columns.extend(
            [
                "nombre",
                "apellido",
                "supervisor",
                "area",
                "cargo",
                "zona_nodo",
            ]
        )

    return {
        "tables": tables,
        "column_profiles": column_profiles,
        "allowed_tables": [
            "cincosas_cincosas.nokia_base_ruta_programacion",
            *(
                ["cincosas_cincosas.cinco_base_de_personal"]
                if include_employee_dimension
                else []
            ),
        ],
        "allowed_columns": allowed_columns,
        "dictionary": {
            "relations": (
                [
                    {
                        "nombre_relacion": "ruta_programada_empleado",
                        "join_sql": "nokia_base_ruta_programacion.cedula = cinco_base_de_personal.cedula",
                    }
                ]
                if include_employee_dimension
                else []
            )
        },
        "synonym_index": {
            "rutas": "ruta",
            "programacion": "fecha_programacion",
            "tecnicos": "tecnico",
            "zonas": "ciudad",
            "estados": "estado",
        },
        "aliases": {
            "tecnicos": "tecnico",
            "técnicos": "tecnico",
            "zona": "ciudad",
            "zonas": "ciudad",
            "rutas": "ruta",
            "fechas": "fecha_programacion",
        },
        "source_of_truth": {
            "pilot_sql_assisted_enabled": supports_sql_assisted,
            "used_dictionary": True,
            "used_yaml": True,
            "structural": "ai_dictionary.dd_*",
            "narrative": "yaml_domain_context",
            "structural_authority": "dictionary_first",
        },
        "supports_sql_assisted": supports_sql_assisted,
        "domain_status": "partial",
    }


@dataclass(frozen=True, slots=True)
class ValidationCase:
    case_id: str
    question: str
    resolved_query: ResolvedQuerySpec
    expected_domain: str
    expected_runtime_flow: str
    expected_compiler: str
    expected_task_status: str
    expected_fallback: bool
    required_tables: tuple[str, ...]
    required_columns: tuple[str, ...]
    required_relations: tuple[str, ...]
    requires_actionable_insight: bool = True
    sql_rows: tuple[dict[str, Any], ...] = ()
    handler_response: dict[str, Any] | None = None
    legacy_response: dict[str, Any] | None = None


class _ObservabilityStub:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def record_event(self, *, event_type: str, source: str, meta: dict[str, Any]) -> None:
        self.events.append(
            {
                "event_type": str(event_type or ""),
                "source": str(source or ""),
                "meta": dict(meta or {}),
            }
        )


class _InMemoryWorkflowRepo:
    def __init__(self) -> None:
        self.rows: dict[str, dict[str, Any]] = {}

    def get_workflow_state(self, workflow_key: str, *, for_update: bool = False) -> dict[str, Any] | None:
        row = self.rows.get(workflow_key)
        return dict(row) if row else None

    def upsert_workflow_state(
        self,
        *,
        workflow_type: str,
        workflow_key: str,
        status: str,
        state: dict[str, Any],
        retry_count: int = 0,
        lock_version: int = 1,
        next_retry_at: int | None = None,
        last_error: str | None = None,
    ) -> None:
        self.rows[workflow_key] = {
            "workflow_type": workflow_type,
            "workflow_key": workflow_key,
            "status": status,
            "state": dict(state or {}),
            "retry_count": retry_count,
            "lock_version": lock_version,
            "next_retry_at": next_retry_at,
            "last_error": last_error,
        }


def _handler_response(
    *,
    domain: str,
    reply: str,
    rows: list[dict[str, Any]],
    insights: list[str],
    columns_used: list[str],
) -> dict[str, Any]:
    return {
        "session_id": "ia-runtime-diagnose",
        "reply": reply,
        "orchestrator": {
            "intent": "detail",
            "domain": domain,
            "selected_agent": f"{domain}_agent",
            "classifier_source": "handler_runtime",
            "needs_database": True,
            "output_mode": "table",
            "used_tools": ["domain_handler"],
            "runtime_flow": "handler",
        },
        "data": {
            "kpis": {"rowcount": len(rows)},
            "series": [],
            "labels": [],
            "insights": list(insights),
            "table": {
                "columns": list(rows[0].keys()) if rows else [],
                "rows": list(rows),
                "rowcount": len(rows),
            },
            "findings": [
                {
                    "title": "Hallazgo",
                    "detail": insights[0] if insights else "",
                }
            ],
        },
        "actions": [
            {
                "id": "followup-handler",
                "type": "followup",
                "label": "Profundizar",
                "payload": {"columns_used": list(columns_used)},
            }
        ],
        "data_sources": {
            "query_intelligence": {
                "ok": True,
                "strategy": "capability",
                "compiler": "",
                "columns_used": list(columns_used),
            }
        },
        "trace": [],
        "observability": {"enabled": True, "duration_ms": 0},
        "active_nodes": ["q", "gpt", "route", "handler", "result"],
    }


def _legacy_response(*, reply: str, insights: list[str]) -> dict[str, Any]:
    return {
        "session_id": "ia-runtime-diagnose",
        "reply": reply,
        "orchestrator": {
            "intent": "general_question",
            "domain": "general",
            "selected_agent": "analista_agent",
            "classifier_source": "general_answer",
            "needs_database": False,
            "output_mode": "summary",
            "used_tools": [],
            "runtime_flow": "legacy_fallback",
        },
        "data": {
            "kpis": {},
            "series": [],
            "labels": [],
            "insights": list(insights),
            "table": {"columns": [], "rows": [], "rowcount": 0},
            "findings": [],
        },
        "actions": [
            {
                "id": "followup-legacy",
                "type": "followup",
                "label": "Revisar alertas",
                "payload": {"next": "segmentar por area o sede"},
            }
        ],
        "data_sources": {
            "query_intelligence": {
                "ok": False,
                "strategy": "fallback",
                "compiler": "",
            }
        },
        "trace": [],
        "observability": {"enabled": True, "duration_ms": 0},
        "active_nodes": ["q", "gpt", "route", "result"],
    }


def build_functional_validation_cases() -> list[ValidationCase]:
    aus = _ausentismo_context()
    empleados = _empleados_context()
    return [
        ValidationCase(
            case_id="ausentismo_areas_top",
            question="Que areas tienen mas ausentismo",
            resolved_query=ResolvedQuerySpec(
                intent=StructuredQueryIntent(
                    raw_query="Que areas tienen mas ausentismo",
                    domain_code="ausentismo",
                    operation="aggregate",
                    template_id="aggregate_by_group_and_period",
                    group_by=["area"],
                    metrics=["count"],
                ),
                semantic_context=aus,
                normalized_period=_period(),
            ),
            expected_domain="ausentismo",
            expected_runtime_flow="sql_assisted",
            expected_compiler="join_aware_pilot",
            expected_task_status="completed",
            expected_fallback=False,
            required_tables=("gestionh_ausentismo", "cinco_base_de_personal"),
            required_columns=("area", "fecha_edit"),
            required_relations=("gestionh_ausentismo.cedula = cinco_base_de_personal.cedula",),
            sql_rows=(
                {"area": "Operaciones", "total_ausentismos": 37},
                {"area": "Logistica", "total_ausentismos": 21},
            ),
        ),
        ValidationCase(
            case_id="ausentismo_riesgo_empleados",
            question="Que empleados tienen mas riesgo de ausentismo",
            resolved_query=ResolvedQuerySpec(
                intent=StructuredQueryIntent(
                    raw_query="Que empleados tienen mas riesgo de ausentismo",
                    domain_code="ausentismo",
                    operation="aggregate",
                    template_id="aggregate_by_group_and_period",
                    metrics=["count"],
                ),
                semantic_context=aus,
                normalized_period=_period(),
            ),
            expected_domain="ausentismo",
            expected_runtime_flow="sql_assisted",
            expected_compiler="join_aware_pilot",
            expected_task_status="completed",
            expected_fallback=False,
            required_tables=("gestionh_ausentismo", "cinco_base_de_personal"),
            required_columns=("cedula", "nombre", "apellido"),
            required_relations=("gestionh_ausentismo.cedula = cinco_base_de_personal.cedula",),
            sql_rows=(
                {"empleado": "Ana Perez", "cedula": "101", "total_ausentismos": 7, "nivel_riesgo": "alto"},
                {"empleado": "Luis Diaz", "cedula": "102", "total_ausentismos": 5, "nivel_riesgo": "medio"},
            ),
        ),
        ValidationCase(
            case_id="empleados_cumpleanos_mayo",
            question="Que empleados cumplen anos en Mayo",
            resolved_query=ResolvedQuerySpec(
                intent=StructuredQueryIntent(
                    raw_query="Que empleados cumplen anos en Mayo",
                    domain_code="empleados",
                    operation="detail",
                    template_id="detail_by_entity_and_period",
                    filters={"birth_month": "05", "estado": "ACTIVO"},
                    metrics=["count"],
                ),
                semantic_context=empleados,
                normalized_filters={"birth_month": "05", "estado": "ACTIVO"},
                normalized_period={"label": "mayo"},
            ),
            expected_domain="empleados",
            expected_runtime_flow="handler",
            expected_compiler="",
            expected_task_status="completed",
            expected_fallback=False,
            required_tables=("cinco_base_de_personal",),
            required_columns=("fecha_nacimiento", "nombre", "cargo"),
            required_relations=(),
            handler_response=_handler_response(
                domain="empleados",
                reply="Se identificaron 3 empleados activos con cumpleanos en mayo.",
                rows=[
                    {"cedula": "201", "nombre": "Diana", "apellido": "Lopez", "cargo": "Analista", "fecha_nacimiento": "1992-05-10"},
                    {"cedula": "202", "nombre": "Carlos", "apellido": "Rios", "cargo": "Supervisor", "fecha_nacimiento": "1988-05-22"},
                ],
                insights=[
                    "Talento humano puede anticipar comunicacion, cobertura y reconocimientos para los cumpleanos de mayo."
                ],
                columns_used=["cedula", "nombre", "apellido", "cargo", "fecha_nacimiento", "estado"],
            ),
        ),
        ValidationCase(
            case_id="ausentismo_cargos_incapacidades",
            question="Que cargos concentran mas incapacidades",
            resolved_query=ResolvedQuerySpec(
                intent=StructuredQueryIntent(
                    raw_query="Que cargos concentran mas incapacidades",
                    domain_code="ausentismo",
                    operation="aggregate",
                    template_id="aggregate_by_group_and_period",
                    group_by=["cargo"],
                    metrics=["count"],
                ),
                semantic_context=aus,
                normalized_period=_period(),
            ),
            expected_domain="ausentismo",
            expected_runtime_flow="sql_assisted",
            expected_compiler="join_aware_pilot",
            expected_task_status="completed",
            expected_fallback=False,
            required_tables=("gestionh_ausentismo", "cinco_base_de_personal"),
            required_columns=("cargo", "justificacion"),
            required_relations=("gestionh_ausentismo.cedula = cinco_base_de_personal.cedula",),
            sql_rows=(
                {"cargo": "Operario", "total_ausentismos": 8},
                {"cargo": "Tecnico", "total_ausentismos": 5},
            ),
        ),
        ValidationCase(
            case_id="ausentismo_sedes_top",
            question="Que sedes presentan mas ausencias",
            resolved_query=ResolvedQuerySpec(
                intent=StructuredQueryIntent(
                    raw_query="Que sedes presentan mas ausencias",
                    domain_code="ausentismo",
                    operation="aggregate",
                    template_id="aggregate_by_group_and_period",
                    group_by=["sede"],
                    metrics=["count"],
                ),
                semantic_context=aus,
                normalized_period=_period(),
            ),
            expected_domain="ausentismo",
            expected_runtime_flow="sql_assisted",
            expected_compiler="join_aware_pilot",
            expected_task_status="completed",
            expected_fallback=False,
            required_tables=("gestionh_ausentismo", "cinco_base_de_personal"),
            required_columns=("zona_nodo", "fecha_edit"),
            required_relations=("gestionh_ausentismo.cedula = cinco_base_de_personal.cedula",),
            sql_rows=(
                {"sede": "Bogota", "total_ausentismos": 11},
                {"sede": "Medellin", "total_ausentismos": 7},
            ),
        ),
        ValidationCase(
            case_id="ausentismo_tendencia_mes",
            question="Como evoluciona el ausentismo por mes",
            resolved_query=ResolvedQuerySpec(
                intent=StructuredQueryIntent(
                    raw_query="Como evoluciona el ausentismo por mes",
                    domain_code="ausentismo",
                    operation="trend",
                    template_id="trend_by_period",
                    metrics=["count"],
                ),
                semantic_context=aus,
                normalized_period=_period(label="mensual", start="2026-01-01", end="2026-04-30"),
            ),
            expected_domain="ausentismo",
            expected_runtime_flow="sql_assisted",
            expected_compiler="default_sql_builder",
            expected_task_status="completed",
            expected_fallback=False,
            required_tables=("gestionh_ausentismo",),
            required_columns=("fecha_edit",),
            required_relations=(),
            sql_rows=(
                {"periodo": "2026-01-01", "total_registros": 18},
                {"periodo": "2026-02-01", "total_registros": 21},
                {"periodo": "2026-03-01", "total_registros": 16},
            ),
        ),
        ValidationCase(
            case_id="ausentismo_recurrencia_empleados",
            question="Que empleados tienen ausencias repetitivas",
            resolved_query=ResolvedQuerySpec(
                intent=StructuredQueryIntent(
                    raw_query="Que empleados tienen ausencias repetitivas",
                    domain_code="ausentismo",
                    operation="aggregate",
                    template_id="aggregate_by_group_and_period",
                    group_by=["empleado"],
                    metrics=["count"],
                ),
                semantic_context=_ausentismo_context(),
                normalized_period=_period(),
            ),
            expected_domain="ausentismo",
            expected_runtime_flow="sql_assisted",
            expected_compiler="join_aware_pilot",
            expected_task_status="completed",
            expected_fallback=False,
            required_tables=("gestionh_ausentismo", "cinco_base_de_personal"),
            required_columns=("cedula", "nombre", "fecha_edit"),
            required_relations=("gestionh_ausentismo.cedula = cinco_base_de_personal.cedula",),
            sql_rows=(
                {"empleado": "Ana Perez", "cedula": "101", "total_ausentismos": 7, "nivel_riesgo": "alto"},
                {"empleado": "Luis Diaz", "cedula": "102", "total_ausentismos": 5, "nivel_riesgo": "medio"},
            ),
        ),
        ValidationCase(
            case_id="ausentismo_justificaciones_top",
            question="Que justificaciones concentran mas ausencias",
            resolved_query=ResolvedQuerySpec(
                intent=StructuredQueryIntent(
                    raw_query="Que justificaciones concentran mas ausencias",
                    domain_code="ausentismo",
                    operation="aggregate",
                    template_id="aggregate_by_group_and_period",
                    group_by=["justificacion"],
                    metrics=["count"],
                ),
                semantic_context=aus,
                normalized_period=_period(),
            ),
            expected_domain="ausentismo",
            expected_runtime_flow="sql_assisted",
            expected_compiler="default_sql_builder",
            expected_task_status="completed",
            expected_fallback=False,
            required_tables=("gestionh_ausentismo",),
            required_columns=("justificacion",),
            required_relations=("gestionh_ausentismo.cedula = cinco_base_de_personal.cedula",),
            sql_rows=(
                {"justificacion": "INCAPACIDAD", "total_ausentismos": 12},
                {"justificacion": "VACACIONES", "total_ausentismos": 9},
            ),
        ),
        ValidationCase(
            case_id="ausentismo_cargos_frecuencia",
            question="Que cargos tienen mayor frecuencia de ausencias",
            resolved_query=ResolvedQuerySpec(
                intent=StructuredQueryIntent(
                    raw_query="Que cargos tienen mayor frecuencia de ausencias",
                    domain_code="ausentismo",
                    operation="aggregate",
                    template_id="aggregate_by_group_and_period",
                    group_by=["cargo"],
                    metrics=["count"],
                ),
                semantic_context=aus,
                normalized_period=_period(),
            ),
            expected_domain="ausentismo",
            expected_runtime_flow="sql_assisted",
            expected_compiler="join_aware_pilot",
            expected_task_status="completed",
            expected_fallback=False,
            required_tables=("gestionh_ausentismo", "cinco_base_de_personal"),
            required_columns=("cargo",),
            required_relations=("gestionh_ausentismo.cedula = cinco_base_de_personal.cedula",),
            sql_rows=(
                {"cargo": "Operario", "total_ausentismos": 14},
                {"cargo": "Tecnico", "total_ausentismos": 8},
            ),
        ),
        ValidationCase(
            case_id="ausentismo_patrones_multidimension",
            question="Que patrones existen por area, cargo y sede",
            resolved_query=ResolvedQuerySpec(
                intent=StructuredQueryIntent(
                    raw_query="Que patrones existen por area, cargo y sede",
                    domain_code="ausentismo",
                    operation="aggregate",
                    template_id="aggregate_by_group_and_period",
                    group_by=["area", "cargo", "sede"],
                    metrics=["count"],
                ),
                semantic_context=aus,
                normalized_period=_period(),
            ),
            expected_domain="ausentismo",
            expected_runtime_flow="sql_assisted",
            expected_compiler="join_aware_pilot",
            expected_task_status="completed",
            expected_fallback=False,
            required_tables=("gestionh_ausentismo", "cinco_base_de_personal"),
            required_columns=("area", "cargo", "zona_nodo"),
            required_relations=("gestionh_ausentismo.cedula = cinco_base_de_personal.cedula",),
            sql_rows=(
                {"area": "Operaciones", "total_ausentismos": 12},
                {"area": "Logistica", "total_ausentismos": 9},
            ),
        ),
        ValidationCase(
            case_id="rrhh_alertas_revision",
            question="Que alertas deberia revisar talento humano",
            resolved_query=ResolvedQuerySpec(
                intent=StructuredQueryIntent(
                    raw_query="Que alertas deberia revisar talento humano",
                    domain_code="",
                    operation="summary",
                    template_id="summary_alerts",
                    metrics=["count"],
                ),
                semantic_context={"tables": [], "source_of_truth": {"used_dictionary": True, "used_yaml": True}},
            ),
            expected_domain="",
            expected_runtime_flow="legacy_fallback",
            expected_compiler="",
            expected_task_status="completed",
            expected_fallback=True,
            required_tables=(),
            required_columns=(),
            required_relations=(),
            legacy_response=_legacy_response(
                reply="Conviene revisar alertas por recurrencia, incapacidades concentradas y sedes con picos recientes de ausentismo.",
                insights=[
                    "Talento humano puede priorizar primero recurrencia alta, luego incapacidades por cargo y finalmente sedes con desviacion mensual."
                ],
            ),
        ),
    ]


def _response_contains_actionable_insight(response: dict[str, Any]) -> bool:
    data = dict(response.get("data") or {})
    insights = [str(item or "").strip().lower() for item in list(data.get("insights") or []) if str(item or "").strip()]
    if any(
        token in insight
        for insight in insights
        for token in ("deberia", "puede", "conviene", "priorizar", "revisar", "anticipar", "profundizar")
    ):
        return True
    return bool(list(response.get("actions") or []))


def _top_columns(counter: Counter[str]) -> list[dict[str, Any]]:
    return [{"column": key, "count": count} for key, count in counter.most_common(10)]


def _normalize_tables(values: list[str]) -> list[str]:
    normalized: list[str] = []
    for value in values:
        token = str(value or "").strip()
        if not token:
            continue
        normalized.append(token.split(".")[-1].lower())
    return normalized


def _normalize_columns(values: list[str]) -> list[str]:
    normalized: list[str] = []
    for value in values:
        token = str(value or "").strip().lower()
        if not token:
            continue
        normalized.append(token.split(".")[-1])
    return normalized


def _detect_critical_null_columns(*, rows: list[dict[str, Any]], required_columns: tuple[str, ...]) -> list[str]:
    if not rows:
        return []
    null_columns: list[str] = []
    for column in required_columns:
        key = str(column or "").strip().lower()
        if not key:
            continue
        present = False
        non_null = False
        for row in rows:
            row_map = {str(name or "").strip().lower(): value for name, value in dict(row or {}).items()}
            if key not in row_map:
                continue
            present = True
            if row_map.get(key) is not None:
                non_null = True
                break
        if present and not non_null:
            null_columns.append(key)
    return null_columns


def _extract_case_artifacts(
    *,
    case: ValidationCase,
    execution_plan: QueryExecutionPlan,
    response: dict[str, Any],
) -> tuple[list[str], list[str], list[str], str]:
    metadata = dict(execution_plan.metadata or {})
    semantic_context = dict(case.resolved_query.semantic_context or {})
    runtime_flow = str(((response.get("orchestrator") or {}).get("runtime_flow") or "")).strip()
    tables = list(metadata.get("tables_detected") or [])
    if not tables:
        tables = [
            str(item.get("table_name") or "")
            for item in list(semantic_context.get("tables") or [])
            if isinstance(item, dict)
        ]
    columns = list(metadata.get("physical_columns_used") or [])
    if not columns:
        columns = list((((response.get("data_sources") or {}).get("query_intelligence") or {}).get("columns_used") or []))
    if not columns and str(execution_plan.sql_query or "").strip():
        query = str(execution_plan.sql_query or "").lower()
        allowed_columns = [
            str(item or "").strip().lower()
            for item in list(semantic_context.get("allowed_columns") or [])
            if str(item or "").strip()
        ]
        columns = [column for column in allowed_columns if f"{column}".lower() in query]
    relations = list(metadata.get("relations_used") or [])
    if not relations:
        relations = [
            str(item.get("join_sql") or "")
            for item in list(((semantic_context.get("dictionary") or {}).get("relations") or []))
            if isinstance(item, dict)
        ]
    compiler_used = str(metadata.get("compiler") or (((response.get("data_sources") or {}).get("query_intelligence") or {}).get("compiler") or ""))
    return (_normalize_tables(tables), _normalize_columns(columns), relations, compiler_used)


def run_functional_validation_suite(
    *,
    domain: str = "ausentismo",
    with_empleados: bool = False,
    real_data: bool = False,
) -> dict[str, Any]:
    apply_service_runtime_bootstrap(force=True)
    os.environ["IA_DEV_QUERY_SQL_ASSISTED_ENABLED"] = "1"
    os.environ["IA_DEV_CAP_ATTENDANCE_RECURRENCE_ENABLED"] = "1"
    os.environ["IA_DEV_CAP_GENERAL_ANSWER_V1"] = "1"
    planner = QueryExecutionPlanner()
    workflow_repo = _InMemoryWorkflowRepo()
    task_state_service = TaskStateService(repo=workflow_repo)
    observability = _ObservabilityStub()
    runtime_helper = ChatApplicationService(task_state_service=task_state_service)
    cases = []
    for case in build_functional_validation_cases():
        if case.expected_domain == "empleados" and not with_empleados:
            continue
        if domain and case.expected_domain == "":
            continue
        if domain and case.expected_domain not in {domain, ""} and not (with_empleados and case.expected_domain == "empleados"):
            continue
        cases.append(case)

    results: list[dict[str, Any]] = []
    relation_counter: Counter[str] = Counter()
    column_counter: Counter[str] = Counter()
    real_data_success = 0
    real_data_without_data = 0
    real_data_sql_errors = 0
    real_data_actionable_insights = 0
    real_data_critical_null_columns: Counter[str] = Counter()
    real_data_poor_cases: list[str] = []

    for index, case in enumerate(cases, start=1):
        run_context = RunContext.create(
            message=case.question,
            session_id=f"ia-runtime-diagnose-{index}",
            reset_memory=False,
        )
        execution_plan = planner.plan(run_context=run_context, resolved_query=case.resolved_query)
        response_flow = "legacy_fallback"
        response: dict[str, Any]
        fallback_used = bool(case.expected_fallback)
        fallback_reason = str(execution_plan.reason or "")
        execution_error = ""
        rows_returned = 0
        execution_mode = "fixture"

        if execution_plan.strategy == "sql_assisted":
            if real_data:
                execution_mode = "real_db"
                execution = planner.execute_sql_assisted(
                    run_context=run_context,
                    resolved_query=case.resolved_query,
                    execution_plan=execution_plan,
                    observability=observability,
                )
                if bool(execution.get("ok")):
                    response = dict(execution.get("response") or {})
                    response_flow = "sql_assisted"
                    fallback_used = False
                    fallback_reason = ""
                else:
                    execution_error = str(execution.get("error") or "sql_execution_error")
                    response = _legacy_response(
                        reply=f"No fue posible ejecutar SQL real para el caso {case.case_id}.",
                        insights=[execution_error],
                    )
                    response_flow = "legacy_fallback"
                    fallback_used = True
                    fallback_reason = execution_error
            else:
                row_payload = [dict(row) for row in list(case.sql_rows)]
                columns = list(row_payload[0].keys()) if row_payload else []
                response = planner._build_sql_response(
                    run_context=run_context,
                    resolved_query=case.resolved_query,
                    execution_plan=execution_plan,
                    sql_query=str(execution_plan.sql_query or ""),
                    rows=row_payload,
                    columns=columns,
                    duration_ms=19,
                    db_alias="diagnostic_fixture",
                )
                response_flow = "sql_assisted"
                fallback_used = False
                fallback_reason = ""
        elif execution_plan.strategy == "capability":
            response = dict(case.handler_response or {})
            response_flow = "handler"
            fallback_used = False
            fallback_reason = ""
        else:
            response = dict(case.legacy_response or _legacy_response(reply="Fallback seguro ejecutado.", insights=["Revisar cobertura del runtime."]))
            response_flow = "legacy_fallback"
            fallback_used = True

        runtime_helper._save_task_state(
            run_context=run_context,
            status=case.expected_task_status,
            original_question=case.question,
            detected_domain=case.expected_domain,
            plan={
                "query_intelligence": {
                    "mode": "active",
                    "execution_plan": execution_plan.as_dict(),
                }
            },
            source_used=runtime_helper._build_source_used_payload(
                query_intelligence={
                    "mode": "active",
                    "resolved_query": case.resolved_query.as_dict(),
                    "execution_plan": execution_plan.as_dict(),
                },
                route={"reason": execution_plan.reason},
                response_flow=response_flow,
            ),
            executed_query=str(execution_plan.sql_query or ""),
            validation_result={"satisfied": True, "reason": "ok", "gate_score": 1.0},
            fallback_used={"used": fallback_used, "reason": fallback_reason, "flow": response_flow if fallback_used else ""},
            recommendations=[str(item or "") for item in list(((response.get("data") or {}).get("insights") or []))[:2]],
        )
        response = runtime_helper._attach_runtime_metadata(
            response=response,
            run_context=run_context,
            response_flow=response_flow,
        )
        runtime_helper._record_runtime_resolution_event(
            observability=observability,
            run_context=run_context,
            query_intelligence={
                "execution_plan": execution_plan.as_dict(),
                "resolved_query": case.resolved_query.as_dict(),
            },
            route={"reason": execution_plan.reason},
            response=response,
            execution_meta={"used_legacy": fallback_used, "fallback_reason": fallback_reason},
            response_flow=response_flow,
            satisfaction_snapshot={"satisfied": True, "gate_score": 1.0},
        )

        actual_tables, actual_columns, actual_relations, compiler_used = _extract_case_artifacts(
            case=case,
            execution_plan=execution_plan,
            response=response,
        )
        actionable = _response_contains_actionable_insight(response)
        table_payload = dict((response.get("data") or {}).get("table") or {})
        rows_payload = [dict(item) for item in list(table_payload.get("rows") or []) if isinstance(item, dict)]
        rows_returned = int(table_payload.get("rowcount") or len(rows_payload) or 0)
        critical_null_columns = _detect_critical_null_columns(
            rows=rows_payload,
            required_columns=case.required_columns,
        )
        technically_valid_but_poor = bool(
            response_flow == "sql_assisted"
            and not execution_error
            and (rows_returned == 0 or not actionable)
        )
        task_state = dict((response.get("task_state") or {}).get("state") or {})
        actual_domain = str(case.resolved_query.intent.domain_code or "")
        checks = {
            "domain_detected": actual_domain == case.expected_domain,
            "tables_used": all(item in actual_tables for item in _normalize_tables(list(case.required_tables))),
            "columns_used": all(item in actual_columns for item in _normalize_columns(list(case.required_columns))),
            "relations_used": all(item in actual_relations for item in list(case.required_relations)),
            "runtime_flow": response_flow == case.expected_runtime_flow,
            "compiler_used": compiler_used == case.expected_compiler,
            "task_state_final": str(task_state.get("task_status") or "") == case.expected_task_status,
            "fallback": bool((task_state.get("fallback_used") or {}).get("used")) == case.expected_fallback,
            "actionable_insight": actionable if case.requires_actionable_insight else True,
        }
        failures = [name for name, ok in checks.items() if not ok]
        if real_data and execution_mode == "real_db":
            if execution_error:
                real_data_sql_errors += 1
            elif rows_returned <= 0:
                real_data_without_data += 1
            else:
                real_data_success += 1
            if actionable:
                real_data_actionable_insights += 1
            for column in critical_null_columns:
                real_data_critical_null_columns.update([column])
            if technically_valid_but_poor:
                real_data_poor_cases.append(case.question)
        for relation in actual_relations:
            relation_counter.update([relation])
        for column in actual_columns:
            column_counter.update([column])
        results.append(
            {
                "case_id": case.case_id,
                "question": case.question,
                "status": "passed" if not failures else "failed",
                "checks": checks,
                "failures": failures,
                "domain_detected": actual_domain,
                "tables_used": actual_tables,
                "columns_used": actual_columns,
                "relations_used": actual_relations,
                "runtime_flow": response_flow,
                "compiler_used": compiler_used,
                "task_state_final": str(task_state.get("task_status") or ""),
                "fallback_used": bool((task_state.get("fallback_used") or {}).get("used")),
                "fallback_reason": str((task_state.get("fallback_used") or {}).get("reason") or ""),
                "actionable_insight": actionable,
                "execution_mode": execution_mode,
                "execution_error": execution_error,
                "rows_returned": rows_returned,
                "without_data": bool(rows_returned <= 0 and not execution_error and response_flow == "sql_assisted"),
                "critical_null_columns": critical_null_columns,
                "technically_valid_but_poor": technically_valid_but_poor,
                "reply": str(response.get("reply") or ""),
                "task_state_key": str((response.get("task_state") or {}).get("workflow_key") or ""),
                "execution_plan": execution_plan.as_dict(),
                "observability_event_count": len(observability.events),
            }
        )

    passed = sum(1 for item in results if item["status"] == "passed")
    failed = len(results) - passed
    runtime_flow_counter = Counter(str(item.get("runtime_flow") or "") for item in results)
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "domain": domain,
        "with_empleados": bool(with_empleados),
        "real_data": bool(real_data),
        "questions_executed": len(results),
        "passed": passed,
        "failed": failed,
        "fallback_count": sum(1 for item in results if bool(item.get("fallback_used"))),
        "sql_assisted_count": int(runtime_flow_counter.get("sql_assisted") or 0),
        "handler_count": int(runtime_flow_counter.get("handler") or 0),
        "legacy_count": int(runtime_flow_counter.get("legacy_fallback") or 0),
        "questions_without_actionable_insight": [
            item["question"] for item in results if not bool(item.get("actionable_insight"))
        ],
        "relations_used": [relation for relation, _ in relation_counter.most_common(10)],
        "most_used_columns": _top_columns(column_counter),
        "errors_or_blockers": [
            {
                "question": item["question"],
                "fallback_reason": item["fallback_reason"],
                "failed_checks": list(item["failures"]),
            }
            for item in results
            if item["status"] != "passed"
        ],
        "results": results,
        "observability_events": list(observability.events),
        "real_data_validation": {
            "queries_exitosas": int(real_data_success),
            "queries_sin_datos": int(real_data_without_data),
            "errores_sql": int(real_data_sql_errors),
            "columnas_nulas_criticas": [
                {"column": key, "count": count}
                for key, count in real_data_critical_null_columns.most_common(10)
            ],
            "insights_accionables_generados": int(real_data_actionable_insights),
            "casos_tecnicamente_validos_pero_pobres": list(real_data_poor_cases),
        },
    }
    return summary
