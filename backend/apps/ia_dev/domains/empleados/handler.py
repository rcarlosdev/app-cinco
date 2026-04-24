from __future__ import annotations

import time
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any

from apps.empleados.services.empleado_service import EmpleadoService
from apps.ia_dev.application.context.run_context import RunContext
from apps.ia_dev.application.contracts.query_intelligence_contracts import (
    QueryExecutionPlan,
    ResolvedQuerySpec,
)
from apps.ia_dev.application.delegation.task_contracts import DelegationResult, DelegationTask
from apps.ia_dev.services.employee_identifier_service import EmployeeIdentifierService
from apps.ia_dev.services.memory_service import SessionMemoryStore
from apps.ia_dev.services.organizational_context_service import OrganizationalContextService


@dataclass(slots=True)
class EmpleadosHandleResult:
    ok: bool
    response: dict[str, Any] | None = None
    error: str | None = None
    metadata: dict[str, Any] | None = None


class EmpleadosHandler:
    _ALLOWED_TEMPORAL_COLUMNS = {"fecha_ingreso", "fecha_egreso"}

    def __init__(self, *, service: EmpleadoService | None = None, org_context: OrganizationalContextService | None = None):
        self.service = service or EmpleadoService()
        self.org_context = org_context or OrganizationalContextService()

    def handle(
        self,
        *,
        capability_id: str,
        message: str,
        session_id: str | None,
        reset_memory: bool,
        run_context: RunContext,
        planned_capability: dict[str, Any],
        memory_context: dict[str, Any] | None = None,
        resolved_query: ResolvedQuerySpec | None = None,
        execution_plan: QueryExecutionPlan | None = None,
        observability=None,
    ) -> EmpleadosHandleResult:
        sid, _ = SessionMemoryStore.get_or_create(session_id)
        if reset_memory:
            SessionMemoryStore.reset(sid)

        started_at = time.perf_counter()
        trace: list[dict[str, Any]] = []
        used_tools: list[str] = []
        output_mode = "summary"
        payload = {
            "kpis": {},
            "series": [],
            "labels": [],
            "insights": [],
            "table": {"columns": [], "rows": [], "rowcount": 0},
        }

        def _push_trace(phase: str, status: str, detail: Any, active_nodes: list[str] | None = None) -> None:
            trace.append(
                {
                    "phase": phase,
                    "status": status,
                    "at": datetime.now(timezone.utc).isoformat(),
                    "detail": detail,
                    "active_nodes": active_nodes or ["q", "gpt", "route", "empleados", "result"],
                }
            )

        try:
            if capability_id not in {"empleados.count.active.v1", "empleados.detail.v1"}:
                return EmpleadosHandleResult(
                    ok=False,
                    error=f"empleados capability no soportada: {capability_id}",
                    metadata={"capability_id": capability_id},
                )
            target_status = ""
            temporal_scope: dict[str, Any] = {}
            filtros_aplicados: dict[str, Any] = {}

            if capability_id == "empleados.detail.v1":
                output_mode = "table"
                detalle_rows, filtros_aplicados = self.obtener_detalle_empleados(
                    consulta=message,
                    execution_plan=execution_plan,
                    resolved_query=resolved_query,
                )
                used_tools.append("get_empleados_detail")
                table_columns = self._resolve_detail_table_columns(
                    empleados=detalle_rows,
                    filtros_aplicados=filtros_aplicados,
                )
                payload["kpis"] = {"total_empleados": int(len(detalle_rows))}
                payload["table"] = {
                    "columns": table_columns,
                    "rows": detalle_rows,
                    "rowcount": len(detalle_rows),
                }
                payload["insights"] = [
                    f"Consulta de detalle de empleados resuelta con filtros: {filtros_aplicados or {}}."
                ]
                reply = self._build_employee_detail_reply(
                    empleados=detalle_rows,
                    filtros_aplicados=filtros_aplicados,
                )
                _push_trace(
                    "empleados_detail",
                    "ok",
                    {
                        "capability_id": capability_id,
                        "total_empleados": len(detalle_rows),
                        "filtros_aplicados": filtros_aplicados,
                    },
                )
            else:
                target_status = self._resolve_target_status(
                    message=message,
                    resolved_query=resolved_query,
                    execution_plan=execution_plan,
                )
                runtime_filters = self._resolve_runtime_filters(
                    execution_plan=execution_plan,
                    resolved_query=resolved_query,
                )
                org_resolution = self._safe_resolve_org_reference(message=message)
                if org_resolution.get("resolved"):
                    runtime_filters.update(dict(org_resolution.get("filters") or {}))
                temporal_scope = self._resolve_temporal_scope(
                    execution_plan=execution_plan,
                )
                group_dimensions = self._resolve_group_dimensions(
                    execution_plan=execution_plan,
                    resolved_query=resolved_query,
                )
                is_turnover_query = self._is_turnover_query(
                    message=message,
                    resolved_query=resolved_query,
                    execution_plan=execution_plan,
                )
                if is_turnover_query and not temporal_scope:
                    temporal_scope = self._resolve_turnover_temporal_scope(
                        execution_plan=execution_plan,
                        resolved_query=resolved_query,
                    )
                trace_phase = "empleados_count_active"

                if is_turnover_query:
                    trace_phase = "empleados_turnover"
                    used_tools.append("get_empleados_turnover_rate")
                    if group_dimensions:
                        output_mode = "table"
                        grouped_rows, filtros_aplicados = self.obtener_rotacion_personal_agrupada(
                            consulta=message,
                            temporal_scope=temporal_scope,
                            filters=runtime_filters,
                            group_dimensions=group_dimensions,
                        )
                        group_labels = [
                            str(item.get("logical_name") or item.get("physical_name") or "grupo").strip().lower()
                            for item in list(group_dimensions or [])
                            if isinstance(item, dict)
                        ]
                        total_activos = sum(int(item.get("total_egresos") or 0) for item in grouped_rows)
                        payload["kpis"] = {
                            "total_egresos": int(total_activos),
                            "total_grupos": int(len(grouped_rows)),
                        }
                        payload["table"] = {
                            "columns": [
                                *group_labels,
                                "total_egresos",
                                "total_ingresos",
                                "planta_inicio",
                                "planta_fin",
                                "planta_promedio",
                                "rotacion_porcentaje",
                            ],
                            "rows": grouped_rows,
                            "rowcount": len(grouped_rows),
                        }
                        payload["labels"] = [
                            " | ".join(str(item.get(label) or "SIN_DATO") for label in group_labels)
                            for item in grouped_rows[:10]
                        ]
                        payload["series"] = [
                            {
                                "name": "rotacion_porcentaje",
                                "data": [float(item.get("rotacion_porcentaje") or 0.0) for item in grouped_rows[:10]],
                            }
                        ]
                        reply = self._build_grouped_turnover_reply(
                            rows=grouped_rows,
                            group_labels=group_labels,
                            temporal_scope=temporal_scope,
                        )
                    else:
                        group_dimensions = []
                        turnover_stats, filtros_aplicados = self.obtener_rotacion_personal(
                            consulta=message,
                            temporal_scope=temporal_scope,
                            filters=runtime_filters,
                        )
                        total_activos = int(turnover_stats.get("total_egresos") or 0)
                        payload["kpis"] = {
                            "rotacion_porcentaje": float(turnover_stats.get("rotacion_porcentaje") or 0.0),
                            "total_egresos": int(turnover_stats.get("total_egresos") or 0),
                            "total_ingresos": int(turnover_stats.get("total_ingresos") or 0),
                            "planta_promedio": float(turnover_stats.get("planta_promedio") or 0.0),
                            "planta_inicio": int(turnover_stats.get("planta_inicio") or 0),
                            "planta_fin": int(turnover_stats.get("planta_fin") or 0),
                        }
                        payload["table"] = {
                            "columns": [
                                "fecha_inicio",
                                "fecha_fin",
                                "total_egresos",
                                "total_ingresos",
                                "planta_inicio",
                                "planta_fin",
                                "planta_promedio",
                                "rotacion_porcentaje",
                                "denominador_fuente",
                            ],
                            "rows": [turnover_stats],
                            "rowcount": 1,
                        }
                        reply = self._build_turnover_reply(stats=turnover_stats)
                    payload["insights"] = [
                        (
                            "Rotacion de personal calculada como egresos inactivos del periodo sobre "
                            "planta promedio estimada."
                        )
                    ]
                    if org_resolution.get("resolved"):
                        payload["insights"].append(
                            f"Filtro organizacional aplicado: {dict(org_resolution.get('filters') or {})}."
                        )
                elif group_dimensions:
                    output_mode = "table"
                    grouped_rows, filtros_aplicados = self.obtener_cantidad_agrupada_por_estado(
                        consulta=message,
                        estado=target_status,
                        temporal_scope=temporal_scope,
                        filters=runtime_filters,
                        group_dimensions=group_dimensions,
                    )
                    total_activos = sum(int(item.get("cantidad") or 0) for item in grouped_rows)
                    group_labels = [
                        str(item.get("logical_name") or item.get("physical_name") or "grupo").strip().lower()
                        for item in list(group_dimensions or [])
                        if isinstance(item, dict)
                    ]
                    primary_logical_name = str(group_labels[0] if group_labels else "grupo")
                    logical_group_text = " y ".join(group_labels) if group_labels else "grupo"
                    physical_group_text = "_".join(
                        str(item.get("physical_name") or item.get("logical_name") or "grupo").strip().lower()
                        for item in list(group_dimensions or [])
                        if isinstance(item, dict)
                    ) or primary_logical_name
                    used_tools.append(f"get_empleados_count_grouped_by_{physical_group_text}")
                    payload["kpis"] = {
                        "total_empleados": int(total_activos),
                        "total_grupos": int(len(grouped_rows)),
                    }
                    payload["labels"] = [
                        " | ".join(str(item.get(label) or "SIN_DATO") for label in group_labels)
                        for item in grouped_rows[:10]
                    ]
                    payload["series"] = [
                        {
                            "name": "cantidad",
                            "data": [int(item.get("cantidad") or 0) for item in grouped_rows[:10]],
                        }
                    ]
                    payload["table"] = {
                        "columns": [*group_labels, "cantidad"],
                        "rows": grouped_rows,
                        "rowcount": len(grouped_rows),
                    }
                    payload["insights"] = [
                        (
                            f"Distribucion de empleados {target_status.lower()} por {logical_group_text} "
                            f"calculada con filtros: {filtros_aplicados or {'estado': target_status}}."
                        )
                    ]
                    top_rows = grouped_rows[:3]
                    top_summary = ", ".join(
                        (
                            f"{' | '.join(str(item.get(label) or 'SIN_DATO') for label in group_labels)}: "
                            f"{int(item.get('cantidad') or 0)}"
                        )
                        for item in top_rows
                    )
                    if temporal_scope.get("column_hint") and temporal_scope.get("start_date") and temporal_scope.get("end_date"):
                        reply = (
                            f"Distribucion de empleados {target_status.lower()} por {logical_group_text} "
                            f"entre {temporal_scope.get('start_date')} y {temporal_scope.get('end_date')}: "
                            f"{int(total_activos)} empleados en {len(grouped_rows)} grupos."
                        )
                    else:
                        reply = (
                            f"Distribucion de empleados {target_status.lower()} por {logical_group_text}: "
                            f"{int(total_activos)} empleados en {len(grouped_rows)} grupos."
                        )
                    if top_summary:
                        reply = f"{reply} Principales resultados: {top_summary}."
                else:
                    total_activos, filtros_aplicados = self.obtener_cantidad_por_estado(
                        consulta=message,
                        estado=target_status,
                        temporal_scope=temporal_scope,
                        filters=runtime_filters,
                    )
                    used_tools.append("get_empleados_count_active")
                    payload["kpis"] = {"total_empleados": int(total_activos)}
                    payload["table"] = {
                        "columns": ["estado", "total_empleados"],
                        "rows": [{"estado": target_status, "total_empleados": int(total_activos)}],
                        "rowcount": 1,
                    }
                    payload["insights"] = [
                        f"Total de empleados {target_status.lower()} calculado con filtros: {filtros_aplicados or {'estado': target_status}}."
                    ]
                    if temporal_scope.get("column_hint") and temporal_scope.get("start_date") and temporal_scope.get("end_date"):
                        reply = (
                            f"Cantidad de empleados {target_status.lower()} con "
                            f"{temporal_scope.get('column_hint')} entre {temporal_scope.get('start_date')} "
                            f"y {temporal_scope.get('end_date')}: {int(total_activos)}."
                        )
                    else:
                        reply = f"Cantidad de empleados {target_status.lower()}: {int(total_activos)}."
                _push_trace(
                    trace_phase,
                    "ok",
                    {
                        "capability_id": capability_id,
                        "total_activos": int(total_activos),
                        "estado_objetivo": target_status,
                        "filtros_aplicados": filtros_aplicados,
                        "temporal_scope": temporal_scope,
                        "group_dimensions": group_dimensions,
                    },
                )

            SessionMemoryStore.update_context(
                sid,
                {
                    "last_domain": "empleados",
                    "last_intent": "empleados_query",
                    "last_focus": "employee_detail" if capability_id == "empleados.detail.v1" else "count_active",
                    "last_output_mode": output_mode,
                    "last_needs_database": True,
                    "last_selected_agent": "empleados_agent",
                },
            )
            SessionMemoryStore.append_turn(sid, message, reply)
            memory_status = SessionMemoryStore.status(sid)

            total_duration_ms = int((time.perf_counter() - started_at) * 1000)
            response = {
                "session_id": sid,
                "reply": reply,
                "orchestrator": {
                    "intent": "empleados_query",
                    "domain": "empleados",
                    "selected_agent": "empleados_agent",
                    "classifier_source": "capability_handler",
                    "needs_database": True,
                    "output_mode": output_mode,
                    "used_tools": used_tools,
                },
                "data": payload,
                "actions": [],
                "data_sources": {
                    "empleados": {"ok": True, "source": "capability_handler"},
                    "ai_dictionary": {"ok": True, "source": "capability_handler"},
                },
                "trace": trace,
                "memory": memory_status,
                "observability": {
                    "enabled": bool(getattr(observability, "enabled", True)),
                    "duration_ms": total_duration_ms,
                    "tool_latencies_ms": {},
                    "tokens_in": 0,
                    "tokens_out": 0,
                    "estimated_cost_usd": 0.0,
                },
                "active_nodes": ["empleados", "q", "result", "route"],
            }
            return EmpleadosHandleResult(
                ok=True,
                response=response,
                metadata={
                    "capability_id": capability_id,
                    "filtros_aplicados": filtros_aplicados,
                    "estado_objetivo": target_status,
                    "temporal_scope": temporal_scope,
                    "policy_tags": list(planned_capability.get("policy_tags") or []),
                },
            )
        except Exception as exc:
            return EmpleadosHandleResult(
                ok=False,
                error=str(exc),
                metadata={"capability_id": capability_id},
            )

    def resolver_entidad_objetivo(self, *, consulta: str, limite: int = 120) -> dict[str, Any]:
        filtros = self._extraer_filtros_desde_texto(consulta=consulta)
        empleados = self._buscar_empleados(filtros=filtros, limite=limite)
        entidad = self._resolver_tipo_entidad(filtros=filtros)
        return {
            "entity_type": entidad,
            "entity_ids": [str(item.get("cedula") or "") for item in empleados if item.get("cedula")],
            "entity_attributes": {
                "filtros_normalizados": filtros,
                "total_empleados": len(empleados),
            },
            "empleados": empleados,
        }

    def obtener_cantidad_activos(self, *, consulta: str = "") -> tuple[int, dict[str, str]]:
        return self.obtener_cantidad_por_estado(consulta=consulta, estado="ACTIVO")

    def obtener_cantidad_por_estado(
        self,
        *,
        consulta: str = "",
        estado: str = "ACTIVO",
        temporal_scope: dict[str, Any] | None = None,
        filters: dict[str, Any] | None = None,
    ) -> tuple[int, dict[str, str]]:
        query_params = self._build_query_params(
            consulta=consulta,
            estado=estado,
            temporal_scope=temporal_scope,
            filters=filters,
        )
        queryset = self.service.listar_runtime(query_params=query_params)
        return int(queryset.count()), query_params

    def obtener_rotacion_personal(
        self,
        *,
        consulta: str = "",
        temporal_scope: dict[str, Any] | None = None,
        filters: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], dict[str, str]]:
        query_params = self._build_query_params(
            consulta=consulta,
            estado="INACTIVO",
            temporal_scope=temporal_scope,
            filters=filters,
        )
        stats = self.service.calcular_rotacion_personal(query_params=query_params)
        return dict(stats or {}), query_params

    def obtener_rotacion_personal_agrupada(
        self,
        *,
        consulta: str = "",
        temporal_scope: dict[str, Any] | None = None,
        filters: dict[str, Any] | None = None,
        group_dimensions: list[dict[str, str]],
    ) -> tuple[list[dict[str, Any]], dict[str, str]]:
        query_params = self._build_query_params(
            consulta=consulta,
            estado="INACTIVO",
            temporal_scope=temporal_scope,
            filters=filters,
        )
        normalized_dimensions = [
            {
                "logical_name": str(item.get("logical_name") or item.get("physical_name") or "grupo").strip().lower(),
                "physical_name": str(item.get("physical_name") or item.get("logical_name") or "grupo").strip().lower(),
            }
            for item in list(group_dimensions or [])
            if isinstance(item, dict)
        ]
        physical_names = [str(item.get("physical_name") or item.get("logical_name") or "grupo") for item in normalized_dimensions]
        logical_names = [str(item.get("logical_name") or "grupo") for item in normalized_dimensions]
        rows = self.service.calcular_rotacion_personal_agrupada(
            query_params=query_params,
            group_by_field=physical_names,
            limit=200,
        )
        normalized_rows = []
        for row in list(rows or []):
            normalized = dict(row or {})
            for idx, physical in enumerate(physical_names):
                logical = logical_names[idx]
                if logical != physical and physical in normalized:
                    normalized[logical] = normalized.pop(physical)
            normalized_rows.append(normalized)
        return normalized_rows, query_params

    def obtener_cantidad_agrupada_por_estado(
        self,
        *,
        consulta: str = "",
        estado: str = "ACTIVO",
        temporal_scope: dict[str, Any] | None = None,
        filters: dict[str, Any] | None = None,
        group_dimensions: list[dict[str, str]],
    ) -> tuple[list[dict[str, Any]], dict[str, str]]:
        query_params = self._build_query_params(
            consulta=consulta,
            estado=estado,
            temporal_scope=temporal_scope,
            filters=filters,
        )
        normalized_dimensions = [
            {
                "logical_name": str(item.get("logical_name") or item.get("physical_name") or "grupo").strip().lower(),
                "physical_name": str(item.get("physical_name") or item.get("logical_name") or "grupo").strip().lower(),
            }
            for item in list(group_dimensions or [])
            if isinstance(item, dict)
        ]
        if not normalized_dimensions:
            return [], query_params
        logical_names = [str(item.get("logical_name") or "grupo") for item in normalized_dimensions]
        physical_names = [str(item.get("physical_name") or item.get("logical_name") or "grupo") for item in normalized_dimensions]
        raw_rows = self.service.contar_agrupado_runtime(
            query_params=query_params,
            group_by_field=physical_names,
            limit=200,
        )
        merged_rows: dict[tuple[str, ...], int] = {}
        for row in list(raw_rows or []):
            labels: list[str] = []
            if isinstance(row, dict):
                for physical_name in physical_names:
                    labels.append(str(row.get(physical_name) or "").strip() or "SIN_DATO")
            else:
                labels = ["SIN_DATO" for _ in physical_names]
            label_key = tuple(labels)
            merged_rows[label_key] = merged_rows.get(label_key, 0) + int((row or {}).get("total_empleados") or 0)

        normalized_rows = [
            {
                **{logical_names[idx]: label_tuple[idx] for idx in range(len(logical_names))},
                "cantidad": int(total),
            }
            for label_tuple, total in sorted(
                merged_rows.items(),
                key=lambda item: (
                    -int(item[1]),
                    " | ".join(str(part).lower() for part in item[0]),
                ),
            )
        ]
        return normalized_rows, query_params

    def obtener_detalle_empleados(
        self,
        *,
        consulta: str,
        execution_plan: QueryExecutionPlan | None,
        resolved_query: ResolvedQuerySpec | None,
        limit: int = 20,
    ) -> tuple[list[dict[str, Any]], dict[str, str]]:
        query_params = self._resolve_detail_filters(
            consulta=consulta,
            execution_plan=execution_plan,
            resolved_query=resolved_query,
        )
        queryset = self.service.listar(query_params=query_params)
        rows = list(
            queryset.values(
                "id",
                "cedula",
                "nombre",
                "apellido",
                "movil",
                "cargo",
                "area",
                "supervisor",
                "carpeta",
                "tipo_labor",
                "estado",
                "codigo_sap",
                "sede",
                "link_foto",
            )[: max(1, min(int(limit), 20))]
        )
        empleados: list[dict[str, Any]] = []
        for row in rows:
            nombre = str(row.get("nombre") or "").strip()
            apellido = str(row.get("apellido") or "").strip()
            empleados.append(
                {
                    "id": row.get("id"),
                    "cedula": str(row.get("cedula") or "").strip(),
                    "nombre": nombre,
                    "apellido": apellido,
                    "nombre_completo": f"{nombre} {apellido}".strip(),
                    "movil": str(row.get("movil") or "").strip(),
                    "cargo": str(row.get("cargo") or "").strip(),
                    "area": str(row.get("area") or "").strip(),
                    "supervisor": str(row.get("supervisor") or "").strip(),
                    "carpeta": str(row.get("carpeta") or "").strip(),
                    "tipo_labor": str(row.get("tipo_labor") or "").strip(),
                    "estado": str(row.get("estado") or "").strip(),
                    "codigo_sap": str(row.get("codigo_sap") or "").strip(),
                    "sede": str(row.get("sede") or "").strip(),
                    "link_foto": str(row.get("link_foto") or "").strip(),
                }
            )
        return empleados, query_params

    @staticmethod
    def _resolve_detail_table_columns(
        *,
        empleados: list[dict[str, Any]],
        filtros_aplicados: dict[str, Any],
    ) -> list[str]:
        if str((filtros_aplicados or {}).get("movil") or "").strip():
            return ["cedula", "nombre", "apellido", "cargo", "area", "carpeta", "tipo_labor", "movil"]
        if empleados:
            return list(empleados[0].keys())
        return [
            "cedula",
            "nombre",
            "apellido",
            "cargo",
            "area",
            "carpeta",
            "tipo_labor",
            "estado",
        ]

    def _resolve_detail_filters(
        self,
        *,
        consulta: str,
        execution_plan: QueryExecutionPlan | None,
        resolved_query: ResolvedQuerySpec | None,
    ) -> dict[str, str]:
        merged: dict[str, str] = {}
        for source in (
            dict((execution_plan.constraints if execution_plan else {}).get("filters") or {}),
            dict((resolved_query.normalized_filters if resolved_query else {}) or {}),
            self._extraer_filtros_desde_texto(consulta=consulta),
        ):
            for key in ("cedula", "movil", "codigo_sap", "nombre", "area", "cargo", "tipo_labor", "supervisor", "carpeta", "search"):
                value = str(source.get(key) or "").strip()
                if value:
                    merged.setdefault(key, value)
        return EmployeeIdentifierService.prune_redundant_search_filter(merged)

    @staticmethod
    def _build_employee_detail_reply(
        *,
        empleados: list[dict[str, Any]],
        filtros_aplicados: dict[str, Any],
    ) -> str:
        movil = str((filtros_aplicados or {}).get("movil") or "").strip()
        if not empleados:
            filtro_texto = ", ".join(
                f"{key}={value}" for key, value in dict(filtros_aplicados or {}).items() if str(value or "").strip()
            )
            if filtro_texto:
                return f"No encontre empleados activos con esos criterios ({filtro_texto})."
            return "No encontre empleados activos con esos criterios."
        if movil:
            integrantes = len(empleados)
            return (
                f"Encontre {integrantes} integrantes de la movil {movil}. "
                "Te muestro cedula, nombre, apellido, cargo, area, carpeta y tipo de labor. "
                "Si deseas conocer algo especifico adicional de esta movil, puedo ayudarte."
            )
        if len(empleados) == 1:
            row = dict(empleados[0] or {})
            return (
                f"Empleado encontrado: {str(row.get('nombre_completo') or 'N/D')}. "
                f"Cedula: {str(row.get('cedula') or 'N/D')}. "
                f"Movil: {str(row.get('movil') or 'N/D')}. "
                f"Cargo: {str(row.get('cargo') or 'N/D')}. "
                f"Area: {str(row.get('area') or 'N/D')}. "
                f"Supervisor: {str(row.get('supervisor') or 'N/D')}. "
                f"Estado: {str(row.get('estado') or 'N/D')}."
            )
        preview = ", ".join(str(item.get("nombre_completo") or item.get("cedula") or "N/D") for item in empleados[:3])
        return f"Encontre {len(empleados)} empleados que coinciden. Primeros resultados: {preview}."

    @staticmethod
    def _build_turnover_reply(*, stats: dict[str, Any]) -> str:
        return (
            f"Rotacion de personal entre {stats.get('fecha_inicio')} y {stats.get('fecha_fin')}: "
            f"{float(stats.get('rotacion_porcentaje') or 0.0):.2f}%. "
            f"Egresos: {int(stats.get('total_egresos') or 0)}. "
            f"Ingresos: {int(stats.get('total_ingresos') or 0)}. "
            f"Planta promedio: {float(stats.get('planta_promedio') or 0.0):.2f} "
            f"(inicio {int(stats.get('planta_inicio') or 0)}, fin {int(stats.get('planta_fin') or 0)})."
        )

    @staticmethod
    def _build_grouped_turnover_reply(
        *,
        rows: list[dict[str, Any]],
        group_labels: list[str],
        temporal_scope: dict[str, Any],
    ) -> str:
        label = " y ".join(group_labels or ["grupo"])
        start = str((temporal_scope or {}).get("start_date") or "").strip()
        end = str((temporal_scope or {}).get("end_date") or "").strip()
        period_text = f" entre {start} y {end}" if start and end else ""
        if not rows:
            return f"No encontre rotacion de personal por {label}{period_text}."
        if len(rows) == 1 and len(group_labels or []) == 1:
            row = dict(rows[0] or {})
            group_value = str(row.get(group_labels[0]) or "SIN_DATO")
            return (
                f"Rotacion de personal de {group_value}{period_text}: "
                f"{float(row.get('rotacion_porcentaje') or 0.0):.2f}%. "
                f"Egresos: {int(row.get('total_egresos') or 0)}. "
                f"Ingresos: {int(row.get('total_ingresos') or 0)}. "
                f"Planta promedio: {float(row.get('planta_promedio') or 0.0):.2f} "
                f"(inicio {int(row.get('planta_inicio') or 0)}, fin {int(row.get('planta_fin') or 0)})."
            )
        preview = ", ".join(
            (
                f"{' | '.join(str(row.get(item) or 'SIN_DATO') for item in group_labels)}: "
                f"{float(row.get('rotacion_porcentaje') or 0.0):.2f}% "
                f"({int(row.get('total_egresos') or 0)} egresos)"
            )
            for row in rows[:3]
        )
        return (
            f"Rotacion de personal por {label}{period_text}: {len(rows)} grupos. "
            f"Principales resultados: {preview}."
        )

    @staticmethod
    def _is_turnover_query(
        *,
        message: str,
        resolved_query: ResolvedQuerySpec | None,
        execution_plan: QueryExecutionPlan | None,
    ) -> bool:
        normalized = str(message or "").strip().lower()
        if "rotacion" in normalized or "rotaci" in normalized:
            return True
        if resolved_query is not None:
            entity_type = str(resolved_query.intent.entity_type or "").strip().lower()
            entity_value = str(resolved_query.intent.entity_value or "").strip().lower()
            metrics = [str(item or "").strip().lower() for item in list(resolved_query.intent.metrics or [])]
            if "rotacion" in entity_type or "rotacion" in entity_value:
                return True
            if any(metric in {"rotacion", "rotacion_personal", "turnover", "turnover_rate"} for metric in metrics):
                return True
        constraints = dict((execution_plan.constraints if execution_plan else {}) or {})
        metrics = [str(item or "").strip().lower() for item in list(constraints.get("metrics") or [])]
        return any(metric in {"rotacion", "rotacion_personal", "turnover", "turnover_rate"} for metric in metrics)

    def _safe_resolve_org_reference(self, *, message: str) -> dict[str, Any]:
        try:
            resolved = self.org_context.resolve_reference(message=message)
            return dict(resolved or {})
        except Exception:
            return {"resolved": False, "reference": "", "filters": {}, "candidates": []}

    def resolver_subtarea(self, *, task: DelegationTask, observability=None) -> DelegationResult:
        consulta = str(task.business_objective or "").strip() or str(
            (task.trace_context or {}).get("message") or ""
        )
        if not consulta:
            consulta = "resolver entidad objetivo de empleados"
        resolved = self.resolver_entidad_objetivo(
            consulta=consulta,
            limite=max(1, min(int(task.constraints.get("limit") or 200), 500)),
        )
        empleados = list(resolved.get("empleados") or [])
        table = {
            "columns": list(empleados[0].keys()) if empleados else [],
            "rows": empleados,
            "rowcount": len(empleados),
        }
        kpis = {
            "total_empleados_resueltos": len(empleados),
            "total_entidades_objetivo": len(list(resolved.get("entity_ids") or [])),
        }
        insights = [
            (
                f"Entidad objetivo resuelta como {resolved.get('entity_type') or 'empresa'} "
                f"con {kpis['total_empleados_resueltos']} empleados."
            )
        ]
        self._record_event(
            observability=observability,
            event_type="delegation_empleados_resolver_entidad",
            meta={
                "task_id": task.task_id,
                "entity_type": resolved.get("entity_type"),
                "total_empleados": kpis["total_empleados_resueltos"],
            },
        )
        return DelegationResult(
            task_id=task.task_id,
            domain_code=task.domain_code,
            status="ok" if empleados else "partial",
            reply_text="Entidad objetivo de empleados resuelta.",
            kpis=kpis,
            table=table,
            insights=insights,
            data_lineage={
                "tables_used": ["cinco_base_de_personal"],
                "filters_applied": dict((resolved.get("entity_attributes") or {}).get("filtros_normalizados") or {}),
                "rowcount": len(empleados),
            },
        )

    def obtener_empleados_por_supervisor(self, *, supervisor: str, limite: int = 200) -> dict[str, Any]:
        filtros = {"supervisor": str(supervisor or "").strip()}
        empleados = self._buscar_empleados(filtros=filtros, limite=limite)
        return {
            "supervisor": filtros["supervisor"],
            "total_empleados": len(empleados),
            "empleados": empleados,
            "cedulas": [str(item.get("cedula") or "") for item in empleados if item.get("cedula")],
        }

    def obtener_empleados_por_area(self, *, area: str, limite: int = 300) -> dict[str, Any]:
        filtros = {"area": str(area or "").strip()}
        empleados = self._buscar_empleados(filtros=filtros, limite=limite)
        return {
            "area": filtros["area"],
            "total_empleados": len(empleados),
            "empleados": empleados,
            "cedulas": [str(item.get("cedula") or "") for item in empleados if item.get("cedula")],
        }

    @staticmethod
    def _resolver_tipo_entidad(*, filtros: dict[str, str]) -> str:
        if filtros.get("cedula") or filtros.get("movil") or filtros.get("codigo_sap") or filtros.get("nombre"):
            return "empleado"
        if filtros.get("supervisor"):
            return "supervisor"
        if filtros.get("area"):
            return "area"
        if filtros.get("cargo"):
            return "cargo"
        if filtros.get("carpeta"):
            return "carpeta"
        return "empresa"

    def _buscar_empleados(self, *, filtros: dict[str, str], limite: int) -> list[dict[str, Any]]:
        query_params: dict[str, str] = {}
        for key in ("cedula", "movil", "codigo_sap", "nombre", "area", "cargo", "tipo_labor", "supervisor", "carpeta"):
            value = str(filtros.get(key) or "").strip()
            if value:
                query_params[key] = value
        if not query_params and filtros.get("search"):
            query_params["search"] = str(filtros["search"])

        try:
            queryset = self.service.listar(query_params=query_params)
            rows = list(
                queryset.values(
                    "id",
                    "cedula",
                    "nombre",
                    "apellido",
                    "area",
                    "cargo",
                    "movil",
                    "supervisor",
                    "carpeta",
                    "estado",
                )[: max(1, min(int(limite), 500))]
            )
        except Exception:
            return []

        empleados: list[dict[str, Any]] = []
        for row in rows:
            nombre = str(row.get("nombre") or "").strip()
            apellido = str(row.get("apellido") or "").strip()
            empleados.append(
                {
                    "id": row.get("id"),
                    "cedula": str(row.get("cedula") or "").strip(),
                    "nombre": nombre,
                    "apellido": apellido,
                    "nombre_completo": f"{nombre} {apellido}".strip(),
                    "area": str(row.get("area") or "").strip(),
                    "cargo": str(row.get("cargo") or "").strip(),
                    "movil": str(row.get("movil") or "").strip(),
                    "supervisor": str(row.get("supervisor") or "").strip(),
                    "carpeta": str(row.get("carpeta") or "").strip(),
                    "estado": str(row.get("estado") or "").strip(),
                }
            )
        return empleados

    @staticmethod
    def _extraer_filtros_desde_texto(*, consulta: str) -> dict[str, str]:
        text = str(consulta or "").strip()
        lowered = text.lower()
        filters: dict[str, str] = {}

        cedula_match = re.search(r"\b\d{6,13}\b", lowered)
        if cedula_match:
            filters["cedula"] = cedula_match.group(0)

        movil = EmployeeIdentifierService.extract_movil_identifier(text)
        if not movil:
            movil = EmpleadosHandler._extract_after_keyword(lowered, keyword="movil")
        if movil:
            filters["movil"] = movil

        supervisor = EmpleadosHandler._extract_after_keyword(lowered, keyword="supervisor")
        if supervisor:
            filters["supervisor"] = supervisor

        area = EmpleadosHandler._extract_after_keyword(lowered, keyword="area")
        if area:
            filters["area"] = area

        cargo = EmpleadosHandler._extract_after_keyword(lowered, keyword="cargo")
        if cargo:
            filters["cargo"] = cargo

        labor = EmpleadosHandler._extract_after_keyword(lowered, keyword="labor")
        if labor:
            filters["tipo_labor"] = labor

        carpeta = EmpleadosHandler._extract_after_keyword(lowered, keyword="carpeta")
        if carpeta:
            filters["carpeta"] = carpeta

        generic_lookup = re.search(
            r"\b(?:info|informacion|detalle|datos|ficha)\s+de\s+([a-z0-9_-]{3,40})\b",
            lowered,
        )
        if not generic_lookup:
            generic_lookup = re.search(
                r"^\s*(?:info|informacion|detalle|datos|ficha)\s+([a-z0-9_-]{3,40})\s*$",
                lowered,
            )
        if generic_lookup and "cedula" not in filters and "movil" not in filters:
            token = str(generic_lookup.group(1) or "").strip()
            if re.fullmatch(r"\d{6,13}", token):
                filters["cedula"] = token
            elif re.search(r"[a-z]", token) and re.search(r"\d", token):
                filters["movil"] = token

        if "empleado " in lowered and "cedula" not in filters:
            maybe_name = lowered.split("empleado ", 1)[1].strip()
            if maybe_name and len(maybe_name) >= 3:
                filters["nombre"] = maybe_name[:80]

        if not filters:
            filters["search"] = lowered[:80]
        return filters

    @staticmethod
    def _extract_after_keyword(text: str, *, keyword: str) -> str:
        pattern = rf"{re.escape(keyword)}\s+([a-z0-9_ .-]{{2,80}})"
        match = re.search(pattern, text)
        if not match:
            return ""
        value = str(match.group(1) or "").strip()
        for token in (" y ", ",", ".", ";"):
            if token in value:
                value = value.split(token, 1)[0].strip()
        if EmpleadosHandler._looks_like_grouping_placeholder(keyword=keyword, value=value):
            return ""
        return value

    def _extraer_filtros_count_activos(self, *, consulta: str) -> dict[str, str]:
        lowered = str(consulta or "").strip().lower()
        filtros: dict[str, str] = {}
        for key in ("supervisor", "area", "cargo", "carpeta"):
            value = self._extract_after_keyword(lowered, keyword=key)
            if value:
                filtros[key] = value
        labor = self._extract_after_keyword(lowered, keyword="labor")
        if labor:
            filtros["tipo_labor"] = labor
        return filtros

    @staticmethod
    def _looks_like_grouping_placeholder(*, keyword: str, value: str) -> bool:
        clean = str(value or "").strip().lower()
        if not clean:
            return False
        if clean.startswith(("por ", "segun ", "según ", "agrup", "group by ")):
            return True
        if clean in {"por", "segun", "según", "agrupado", "agrupacion", "agrupación", "group"}:
            return True
        if clean in {keyword, f"{keyword}s", f"{keyword}es"}:
            return True
        return False

    @staticmethod
    def _resolve_target_status(
        *,
        message: str,
        resolved_query: ResolvedQuerySpec | None,
        execution_plan: QueryExecutionPlan | None,
    ) -> str:
        constraints_filters = dict((execution_plan.constraints if execution_plan else {}).get("filters") or {})
        status = str(constraints_filters.get("estado") or "").strip().upper()
        if status in {"ACTIVO", "INACTIVO"}:
            return status
        if resolved_query is not None:
            status = str((resolved_query.normalized_filters or {}).get("estado") or "").strip().upper()
            if status in {"ACTIVO", "INACTIVO"}:
                return status
        normalized = str(message or "").strip().lower()
        if any(
            token in normalized
            for token in (
                "inactivo",
                "inactivos",
                "egreso",
                "egresos",
                "retirado",
                "retirados",
                "retiro",
                "retiros",
                "egresado",
                "egresados",
                "desvinculado",
                "desvinculados",
                "baja",
                "bajas",
                "rotacion",
                "rotaciones",
            )
        ):
            return "INACTIVO"
        return "ACTIVO"

    def _resolve_temporal_scope(
        self,
        *,
        execution_plan: QueryExecutionPlan | None,
    ) -> dict[str, Any]:
        constraints = dict((execution_plan.constraints if execution_plan else {}) or {})
        temporal_scope = dict(constraints.get("temporal_scope") or {})
        if not temporal_scope:
            return {}
        if bool(temporal_scope.get("ambiguous")):
            return {
                "ambiguous": True,
                "reason": str(temporal_scope.get("reason") or "temporal_scope_ambiguous"),
            }
        column_hint = str(temporal_scope.get("column_hint") or "").strip().lower()
        start_date = str(temporal_scope.get("start_date") or "").strip()
        end_date = str(temporal_scope.get("end_date") or "").strip()
        if column_hint not in self._ALLOWED_TEMPORAL_COLUMNS:
            return {}
        if not start_date or not end_date:
            return {}
        if self._parse_iso_date(start_date) is None or self._parse_iso_date(end_date) is None:
            return {}
        return {
            "column_hint": column_hint,
            "start_date": start_date,
            "end_date": end_date,
            "source": str(temporal_scope.get("source") or "query_constraints"),
            "confidence": float(temporal_scope.get("confidence") or 0.0),
            "status_value": str(temporal_scope.get("status_value") or "").strip().upper(),
            "ambiguous": False,
        }

    def _resolve_turnover_temporal_scope(
        self,
        *,
        execution_plan: QueryExecutionPlan | None,
        resolved_query: ResolvedQuerySpec | None,
    ) -> dict[str, Any]:
        constraints = dict((execution_plan.constraints if execution_plan else {}) or {})
        period_scope = dict(constraints.get("period_scope") or {})
        if not period_scope and resolved_query is not None:
            period_scope = dict(resolved_query.normalized_period or resolved_query.intent.period or {})
        start_date = str(period_scope.get("start_date") or "").strip()
        end_date = str(period_scope.get("end_date") or "").strip()
        if not start_date or not end_date:
            return {}
        if self._parse_iso_date(start_date) is None or self._parse_iso_date(end_date) is None:
            return {}
        return {
            "column_hint": "fecha_egreso",
            "start_date": start_date,
            "end_date": end_date,
            "source": str(period_scope.get("source") or "period_scope_turnover_default"),
            "confidence": float(period_scope.get("confidence") or 0.75),
            "status_value": "INACTIVO",
            "ambiguous": False,
        }

    @staticmethod
    def _resolve_runtime_filters(
        *,
        execution_plan: QueryExecutionPlan | None,
        resolved_query: ResolvedQuerySpec | None,
    ) -> dict[str, Any]:
        source_filters = dict((execution_plan.constraints if execution_plan else {}).get("filters") or {})
        if not source_filters and resolved_query is not None:
            source_filters = dict(resolved_query.normalized_filters or {})

        mapped_columns = dict(resolved_query.mapped_columns or {}) if resolved_query is not None else {}
        runtime_filters: dict[str, Any] = {}
        for raw_key, raw_value in source_filters.items():
            clean_key = str(raw_key or "").strip().lower()
            if clean_key in {"estado", "estado_empleado"}:
                continue
            if raw_value in (None, ""):
                continue
            physical_key = str(mapped_columns.get(clean_key) or clean_key).strip().lower()
            if not physical_key:
                continue
            runtime_filters[physical_key] = raw_value
        return runtime_filters

    @staticmethod
    def _resolve_group_dimensions(
        *,
        execution_plan: QueryExecutionPlan | None,
        resolved_query: ResolvedQuerySpec | None,
    ) -> list[dict[str, str]]:
        requested = [
            str(item or "").strip().lower()
            for item in list((execution_plan.constraints if execution_plan else {}).get("group_by") or [])
            if str(item or "").strip()
        ]
        if not requested and resolved_query is not None:
            requested = [
                str(item or "").strip().lower()
                for item in list(resolved_query.intent.group_by or [])
                if str(item or "").strip()
            ]
        if not requested:
            return []

        semantic_context = dict(resolved_query.semantic_context or {}) if resolved_query is not None else {}
        group_resolutions = list((semantic_context.get("resolved_semantic") or {}).get("group_by") or [])
        aliases = dict(semantic_context.get("aliases") or {})
        resolved_dimensions: list[dict[str, str]] = []
        seen_pairs: set[tuple[str, str]] = set()

        for token in requested:
            resolved_item: dict[str, str] | None = None
            for item in group_resolutions:
                if not isinstance(item, dict):
                    continue
                canonical = str(item.get("canonical_term") or "").strip().lower()
                column_name = str(item.get("column_name") or "").strip().lower()
                requested_term = str(item.get("requested_term") or "").strip().lower()
                if token not in {canonical, column_name, requested_term}:
                    continue
                physical_name = column_name or str(aliases.get(canonical) or aliases.get(token) or "").strip().lower()
                if not physical_name:
                    continue
                resolved_item = {
                    "logical_name": canonical or token,
                    "physical_name": physical_name,
                }
                break
            if resolved_item is None:
                physical_name = str(aliases.get(token) or token).strip().lower()
                if physical_name:
                    resolved_item = {
                        "logical_name": token,
                        "physical_name": physical_name,
                    }
            if resolved_item is None:
                continue
            dedupe_key = (
                str(resolved_item.get("logical_name") or "").strip().lower(),
                str(resolved_item.get("physical_name") or "").strip().lower(),
            )
            if dedupe_key in seen_pairs:
                continue
            seen_pairs.add(dedupe_key)
            resolved_dimensions.append(resolved_item)
        return resolved_dimensions

    def _build_query_params(
        self,
        *,
        consulta: str,
        estado: str,
        temporal_scope: dict[str, Any] | None,
        filters: dict[str, Any] | None,
    ) -> dict[str, str]:
        target_status = str(estado or "ACTIVO").strip().upper()
        if target_status not in {"ACTIVO", "INACTIVO"}:
            target_status = "ACTIVO"
        query_params: dict[str, str] = {"estado": target_status}
        scope = dict(temporal_scope or {})
        if scope.get("column_hint") and scope.get("start_date") and scope.get("end_date"):
            query_params["temporal_column_hint"] = str(scope.get("column_hint") or "")
            query_params["temporal_start_date"] = str(scope.get("start_date") or "")
            query_params["temporal_end_date"] = str(scope.get("end_date") or "")

        normalized_filters = dict(filters or {})
        if not normalized_filters:
            normalized_filters = self._extraer_filtros_count_activos(consulta=consulta)

        for key, value in normalized_filters.items():
            clean_key = str(key or "").strip().lower()
            clean_value = str(value or "").strip()
            if clean_key in {"estado", "estado_empleado"}:
                continue
            if not clean_key or not clean_value:
                continue
            query_params[clean_key] = clean_value
        return query_params

    @staticmethod
    def _parse_iso_date(value: str) -> date | None:
        raw = str(value or "").strip()
        if not raw:
            return None
        try:
            return date.fromisoformat(raw)
        except Exception:
            return None

    @staticmethod
    def _record_event(*, observability, event_type: str, meta: dict[str, Any]) -> None:
        if observability is None or not hasattr(observability, "record_event"):
            return
        observability.record_event(
            event_type=event_type,
            source="EmpleadosHandler",
            meta=dict(meta or {}),
        )
