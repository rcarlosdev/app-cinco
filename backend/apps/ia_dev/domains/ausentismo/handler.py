from __future__ import annotations

import logging
import re
import time
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any

from apps.ia_dev.TOOLS.business.ausentismo_business_tool import (
    AusentismoBusinessTool,
    PeriodoAusentismo,
)
from apps.ia_dev.application.context.run_context import RunContext
from apps.ia_dev.application.contracts.query_intelligence_contracts import (
    QueryExecutionPlan,
    ResolvedQuerySpec,
)
from apps.ia_dev.application.semantic.cause_diagnostics_service import CauseDiagnosticsService
from apps.ia_dev.services.memory_service import SessionMemoryStore
from apps.ia_dev.services.organizational_context_service import OrganizationalContextService
from apps.ia_dev.services.period_service import resolve_period_from_text


logger = logging.getLogger(__name__)

_YES_FOLLOW_UP_RE = re.compile(
    r"^((si)([,! ]+por favor)?|ok|dale|perfecto|claro|adelante|continua|por favor)[.! ]*$",
    re.IGNORECASE,
)


@dataclass(slots=True)
class AusentismoHandleResult:
    ok: bool
    response: dict[str, Any] | None = None
    error: str | None = None
    metadata: dict[str, Any] | None = None


class AusentismoHandler:
    _ITEMIZED_TOKENS = (
        "dia a dia",
        "por ausentismo",
        "fecha por fecha",
        "registro por registro",
        "detalle por dia",
        "itemizado",
    )
    _GROUPED_TOKENS = (
        "agrupado",
        "resumen por empleado",
        "por empleado",
    )
    _PERSONAL_TOKENS = (
        "personal",
        "empleado",
        "supervisor",
        "area",
        "cargo",
        "nombre",
        "apellido",
    )
    _CHART_TOKENS = (
        "grafica",
        "grafico",
        "chart",
        "linea",
        "barra",
        "barras",
    )

    def __init__(
        self,
        *,
        tool: AusentismoBusinessTool | None = None,
        cause_diagnostics_service: CauseDiagnosticsService | None = None,
        org_context: OrganizationalContextService | None = None,
    ):
        self.tool = tool or AusentismoBusinessTool()
        self.cause_diagnostics_service = cause_diagnostics_service or CauseDiagnosticsService()
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
    ) -> AusentismoHandleResult:
        sid, _ = SessionMemoryStore.get_or_create(session_id)
        if reset_memory:
            SessionMemoryStore.reset(sid)

        started_at = time.perf_counter()
        tool_latencies_ms: dict[str, int] = {}
        trace: list[dict[str, Any]] = []
        used_tools: list[str] = []
        payload = {
            "kpis": {},
            "series": [],
            "labels": [],
            "insights": [],
            "table": {"columns": [], "rows": [], "rowcount": 0},
        }
        actions: list[dict[str, Any]] = []
        cause_generation_meta: dict[str, Any] = {}

        def _push_trace(phase: str, status: str, detail: Any, active_nodes: list[str] | None = None) -> None:
            trace.append(
                {
                    "phase": phase,
                    "status": status,
                    "at": datetime.now(timezone.utc).isoformat(),
                    "detail": detail,
                    "active_nodes": active_nodes or ["q", "gpt", "route", "aus", "result"],
                }
            )

        def _measure_tool(name: str, fn, *args, **kwargs):
            t0 = time.perf_counter()
            try:
                return fn(*args, **kwargs)
            finally:
                duration_ms = int((time.perf_counter() - t0) * 1000)
                tool_latencies_ms[name] = duration_ms
                if observability is not None and hasattr(observability, "record_event"):
                    observability.record_event(
                        event_type="tool_latency",
                        source=name,
                        duration_ms=duration_ms,
                        meta={"session_id": sid, "run_id": run_context.run_id},
                    )

        try:
            session_context = SessionMemoryStore.get_context(sid)
            constraints = dict((execution_plan.constraints if execution_plan else {}) or {})
            last_group_dimension_key = str(session_context.get("last_group_dimension_key") or "").strip().lower()
            last_group_dimension_label = str(session_context.get("last_group_dimension_label") or "").strip()
            last_aggregation_focus = str(session_context.get("last_aggregation_focus") or "").strip().lower()
            last_metric_key = str(session_context.get("last_metric_key") or "").strip().lower()
            period = self._resolve_period_for_attendance(
                message=message,
                session_context=session_context,
            )
            period = self._apply_constraints_to_period(period=period, constraints=constraints)
            target_cedula = self._resolve_target_cedula(
                message=message,
                constraints=constraints,
                resolved_query=resolved_query,
            )
            memory_hints = self._extract_memory_hints(memory_context)
            memory_hints_used: list[dict[str, Any]] = []
            personal_status = self._resolve_personal_status(
                message=message,
                session_context=session_context,
                hints=memory_hints,
                used=memory_hints_used,
            )
            attendance_reason_filter = self._resolve_attendance_reason_filter(
                message=message,
                constraints=constraints,
                resolved_query=resolved_query,
            )
            org_resolution = self._safe_resolve_org_reference(message=message)
            personal_filters = dict(org_resolution.get("filters") or {}) if org_resolution.get("resolved") else {}
            _push_trace(
                "period_resolver",
                "ok",
                {
                    "label": period.label,
                    "source": period.source,
                    "start": period.start.isoformat(),
                    "end": period.end.isoformat(),
                    "personal_status": personal_status,
                    "target_cedula": target_cedula,
                    "attendance_reason_filter": attendance_reason_filter,
                    "personal_filters": personal_filters,
                },
                ["q", "route", "rules", "aus"],
            )

            response_output_mode = "table"
            intent = "ausentismo_query"
            focus = "unjustified"
            needs_personal_join = False
            reply = ""

            if capability_id == "attendance.unjustified.summary.v1":
                focus = "all" if attendance_reason_filter else "unjustified"
                summary = _measure_tool(
                    "attendance_get_summary",
                    self.tool.get_attendance_summary,
                    period=period,
                    cedula=target_cedula,
                    focus=focus,
                    justificacion_filter=attendance_reason_filter,
                )
                used_tools.append("get_attendance_summary")
                response_output_mode = "summary"
                payload["kpis"] = {
                    "total_ausentismos": int(summary.get("total_ausentismos") or 0),
                    "justificados": int(summary.get("justificados") or 0),
                    "injustificados": int(summary.get("injustificados") or 0),
                }
                payload["insights"] = [
                    f"Periodo: {summary.get('periodo_inicio')} a {summary.get('periodo_fin')}",
                    "Puedes pedir tabla por empleado, supervisor, area o cargo.",
                ]
                summary_label = self._describe_attendance_scope(
                    focus=focus,
                    attendance_reason_filter=attendance_reason_filter,
                )
                reply = (
                    f"Resumen de {summary_label} del periodo {summary.get('periodo_inicio')} al {summary.get('periodo_fin')}: "
                    f"total={payload['kpis']['total_ausentismos']}, "
                    f"justificados={payload['kpis']['justificados']}, "
                    f"injustificados={payload['kpis']['injustificados']}."
                )

            elif capability_id in {
                "attendance.unjustified.table.v1",
                "attendance.unjustified.table_with_personal.v1",
            }:
                needs_personal_join = capability_id.endswith("table_with_personal.v1") or self._message_requests_personal_join(message)
                if not needs_personal_join and memory_hints.get("supervisor"):
                    needs_personal_join = True
                    memory_hints_used.append(
                        {
                            "memory_key": "attendance.supervisor",
                            "memory_value": memory_hints.get("supervisor"),
                            "reason": "join_personal_enabled_from_memory_hint",
                        }
                    )
                if attendance_reason_filter:
                    needs_personal_join = True
                    detail = _measure_tool(
                        "attendance_get_detail_with_personal",
                        self.tool.service.get_detail_with_personal,
                        period.start,
                        period.end,
                        limit=150,
                        personal_status=personal_status,
                        cedula=target_cedula,
                        justificacion_filter=attendance_reason_filter,
                        focus="all",
                    )
                    used_tools.append("get_attendance_detail_with_personal")
                else:
                    detail = _measure_tool(
                        "attendance_get_unjustified_with_personal"
                        if needs_personal_join
                        else "attendance_get_unjustified_table",
                        self.tool.get_unjustified_table,
                        period=period,
                        include_personal=needs_personal_join,
                        personal_status=personal_status,
                        limit=150,
                        cedula=target_cedula,
                    )
                    used_tools.append(
                        "get_attendance_unjustified_with_personal"
                        if needs_personal_join
                        else "get_attendance_unjustified_table"
                    )
                source_rows = list(detail.get("rows") or [])
                rows = [
                    {k: v for k, v in row.items() if k != "personal_match"}
                    for row in source_rows
                ]
                payload["table"] = {
                    "columns": list(rows[0].keys()) if rows else [],
                    "rows": rows,
                    "rowcount": len(rows),
                }
                if not rows:
                    detail_label = self._describe_attendance_scope(
                        focus="all" if attendance_reason_filter else "unjustified",
                        attendance_reason_filter=attendance_reason_filter,
                    )
                    reply = (
                        f"No se encontraron registros de {detail_label} entre "
                        f"{detail.get('periodo_inicio')} y {detail.get('periodo_fin')}."
                    )
                else:
                    detail_label = self._describe_attendance_scope(
                        focus="all" if attendance_reason_filter else "unjustified",
                        attendance_reason_filter=attendance_reason_filter,
                    )
                    reply = (
                        f"Tabla de {detail_label} del periodo "
                        f"{detail.get('periodo_inicio')} al {detail.get('periodo_fin')} "
                        f"({len(rows)} filas):\n\n{self._format_rows_table(rows)}"
                    )

                unmatched_personal = int(detail.get("unmatched_personal") or 0)
                if unmatched_personal > 0:
                    payload["insights"].append(
                        f"No fue posible homologar {unmatched_personal} registros con personal."
                    )

            elif capability_id in {
                "attendance.recurrence.grouped.v1",
                "attendance.recurrence.itemized.v1",
            }:
                intent = "ausentismo_recurrencia"
                needs_personal_join = True
                grouped = _measure_tool(
                    "attendance_get_recurrence_grouped",
                    self.tool.get_recurrence_grouped,
                        period=period,
                        threshold=3,
                        personal_status=personal_status,
                        limit=150,
                        personal_filters=personal_filters,
                    )
                used_tools.append("get_attendance_recurrent_unjustified_with_supervisor")
                wants_itemized = capability_id.endswith("itemized.v1")
                if capability_id.endswith("grouped.v1"):
                    if self._message_wants_itemized(message):
                        wants_itemized = True
                    elif memory_hints.get("recurrence_view") == "itemized" and not self._message_wants_grouped(message):
                        wants_itemized = True
                        memory_hints_used.append(
                            {
                                "memory_key": "attendance.recurrence.default_view",
                                "memory_value": "itemized",
                                "reason": "itemized_selected_from_business_hint",
                            }
                        )

                if wants_itemized:
                    itemized = _measure_tool(
                        "attendance_get_recurrence_itemized",
                        self.tool.get_recurrence_itemized,
                        period=period,
                        grouped_result=grouped,
                        personal_status=personal_status,
                        detail_limit=500,
                        personal_filters=personal_filters,
                    )
                    used_tools.append("get_attendance_unjustified_with_personal")
                    rows_for_response = list(itemized.get("rows") or [])
                    payload["table"] = {
                        "columns": list(rows_for_response[0].keys()) if rows_for_response else [],
                        "rows": rows_for_response,
                        "rowcount": len(rows_for_response),
                    }
                    payload["kpis"] = {
                        "total_reincidentes": int(itemized.get("recurrent_count") or grouped.get("rowcount") or 0),
                        "umbral_reincidencia": int(itemized.get("threshold") or grouped.get("threshold") or 3),
                        "total_ausentismos_reincidentes": len(rows_for_response),
                    }
                    if not rows_for_response:
                        reply = (
                            "No se encontraron ausentismos dia a dia para reincidentes en el periodo "
                            f"{itemized.get('periodo_inicio')} a {itemized.get('periodo_fin')}."
                        )
                    else:
                        reply = (
                            "Detalle de ausentismos injustificados (dia a dia) de empleados reincidentes "
                            f"en la ventana {itemized.get('periodo_inicio')} a {itemized.get('periodo_fin')} "
                            f"(umbral >= {payload['kpis']['umbral_reincidencia']}), "
                            f"total_reincidentes={payload['kpis']['total_reincidentes']}:\n\n"
                            f"{self._format_rows_table(rows_for_response)}"
                        )
                else:
                    grouped_rows = list(grouped.get("rows_grouped") or [])
                    payload["table"] = {
                        "columns": list(grouped_rows[0].keys()) if grouped_rows else [],
                        "rows": grouped_rows,
                        "rowcount": len(grouped_rows),
                    }
                    payload["kpis"] = {
                        "total_reincidentes": int(grouped.get("rowcount") or len(grouped_rows)),
                        "umbral_reincidencia": int(grouped.get("threshold") or 3),
                    }
                    if not grouped_rows:
                        reply = (
                            "No se encontraron reincidentes injustificados entre "
                            f"{grouped.get('periodo_inicio')} y {grouped.get('periodo_fin')}."
                        )
                    else:
                        reply = (
                            "Reincidentes injustificados en la ventana "
                            f"{grouped.get('periodo_inicio')} a {grouped.get('periodo_fin')} "
                            f"(umbral >= {payload['kpis']['umbral_reincidencia']}), "
                            f"total_reincidentes={payload['kpis']['total_reincidentes']}:\n\n"
                            f"{self._format_rows_table(grouped_rows)}"
                        )
                        payload["insights"].append(
                            "Si quieres, puedo mostrarlo dia a dia (ausentismo por ausentismo)."
                        )
            elif capability_id in {
                "attendance.summary.by_supervisor.v1",
                "attendance.summary.by_area.v1",
                "attendance.summary.by_cargo.v1",
                "attendance.summary.by_attribute.v1",
            }:
                response_output_mode = "summary"
                needs_personal_join = True
                top_n = self._extract_top_n(message, hints=memory_hints, default=10)
                chart_type = self._resolve_chart_type(message=message, hints=memory_hints)
                if chart_type and not self._message_requests_chart(message) and memory_hints.get("analytics_chart_type"):
                    memory_hints_used.append(
                        {
                            "memory_key": "attendance.analytics.chart_type",
                            "memory_value": chart_type,
                            "reason": "chart_type_loaded_from_user_memory",
                        }
                    )

                group_by, group_label = self._resolve_group_dimension(message=message, capability_id=capability_id)
                if constraints:
                    constrained_group_by, constrained_group_label = self._resolve_group_dimension(
                        message=message,
                        capability_id=capability_id,
                        constrained_group_by=list(constraints.get("group_by") or []),
                    )
                    if constrained_group_by:
                        group_by, group_label = constrained_group_by, constrained_group_label
                aggregation_focus = self._resolve_aggregation_focus(message=message)
                analytics = _measure_tool(
                    f"attendance_get_summary_by_{group_by}",
                    self.tool.get_attendance_aggregation,
                    period=period,
                    group_by=group_by,
                    personal_status=personal_status,
                    top_n=top_n,
                    chart_type=chart_type,
                    cedula=target_cedula,
                    focus=aggregation_focus,
                    justificacion_filter=attendance_reason_filter,
                    personal_filters=personal_filters,
                )
                used_tools.append(
                    "get_attendance_unjustified_with_personal"
                    if aggregation_focus == "unjustified" and not attendance_reason_filter
                    else "get_attendance_detail_with_personal"
                )
                used_tools.append(f"attendance_analytics_summary_by_{group_by}")

                rows_for_response = list(analytics.get("rows") or [])
                group_key = str(analytics.get("group_key") or group_by)
                group_label = str(analytics.get("group_label") or group_label)
                metric_key = str(analytics.get("metric_key") or "total_injustificados")
                total_metric = int(analytics.get(metric_key) or 0)
                payload["table"] = {
                    "columns": list(rows_for_response[0].keys()) if rows_for_response else [group_key, metric_key, "porcentaje"],
                    "rows": rows_for_response,
                    "rowcount": len(rows_for_response),
                }
                payload["kpis"] = {
                    metric_key: total_metric,
                    "total_grupos": int(analytics.get("total_groups") or 0),
                    "top_n": int(analytics.get("top_n") or top_n),
                }
                payload["labels"] = list(analytics.get("labels") or [])
                payload["series"] = list(analytics.get("series") or [])
                chart_payload = dict(analytics.get("chart") or {})
                if chart_payload:
                    payload["chart"] = chart_payload
                    payload["charts"] = [chart_payload]
                    actions.append(
                        {
                            "id": f"ausentismo-chart-{capability_id}",
                            "type": "render_chart",
                            "label": "Ver grafica de ausentismo",
                            "payload": {
                                "chart": chart_payload,
                                "capability_id": capability_id,
                            },
                        }
                    )

                if not rows_for_response:
                    grouped_label = self._describe_attendance_scope(
                        focus=aggregation_focus,
                        attendance_reason_filter=attendance_reason_filter,
                    )
                    reply = (
                        f"No se encontraron {grouped_label} para agrupar por "
                        f"{group_label.lower()} entre {analytics.get('periodo_inicio')} y {analytics.get('periodo_fin')}."
                    )
                else:
                    focus_label = self._describe_attendance_scope(
                        focus=aggregation_focus,
                        attendance_reason_filter=attendance_reason_filter,
                        plural_compact=True,
                    )
                    reply = (
                        f"Resumen de {focus_label} por {group_label.lower()} "
                        f"({analytics.get('periodo_inicio')} a {analytics.get('periodo_fin')}, top {payload['kpis']['top_n']}):\n\n"
                        f"{self._format_rows_table(rows_for_response)}"
                    )

                payload["insights"].append(
                    f"Se agruparon {total_metric} registros en {payload['kpis']['total_grupos']} grupos."
                )
                if bool(analytics.get("source_truncated")):
                    payload["insights"].append(
                        "La agregacion se calculo sobre una muestra truncada por limite de seguridad (max 500 registros)."
                    )
                if self._message_requests_probable_causes(message):
                    cause_result = self.cause_diagnostics_service.generate(
                        message=message,
                        rows=rows_for_response,
                        group_label=group_label,
                        metric_key=metric_key,
                        observability=observability,
                        run_id=run_context.run_id,
                        trace_id=run_context.trace_id,
                        domain_code="ausentismo",
                        capability_id=capability_id,
                    )
                    probable_causes = list(cause_result.get("insights") or [])
                    if probable_causes:
                        payload["insights"].extend(probable_causes)
                    cause_generation_meta = dict(cause_result.get("meta") or {})
                    _push_trace(
                        "cause_diagnostics",
                        "ok" if str(cause_generation_meta.get("generator") or "") == "openai" else "warning",
                        self._build_cause_diagnostics_trace_detail(
                            meta=cause_generation_meta,
                            capability_id=capability_id,
                        ),
                        ["q", "gpt", "route", "rules", "result"],
                    )
                last_group_dimension_key = str(group_key or "").strip().lower()
                last_group_dimension_label = str(group_label or "").strip()
                last_aggregation_focus = str(aggregation_focus or "").strip().lower()
                last_metric_key = str(metric_key or "").strip().lower()
            elif capability_id in {
                "attendance.trend.daily.v1",
                "attendance.trend.monthly.v1",
            }:
                response_output_mode = "summary"
                granularity = "monthly" if capability_id.endswith("monthly.v1") else "daily"
                chart_type = self._resolve_chart_type(
                    message=message,
                    hints=memory_hints,
                    fallback=("bar" if granularity == "monthly" else "line"),
                )
                if chart_type and not self._message_requests_chart(message) and memory_hints.get("analytics_chart_type"):
                    memory_hints_used.append(
                        {
                            "memory_key": "attendance.analytics.chart_type",
                            "memory_value": chart_type,
                            "reason": "chart_type_loaded_from_user_memory",
                        }
                    )
                trend = _measure_tool(
                    f"attendance_get_trend_{granularity}",
                    self.tool.get_unjustified_trend,
                    period=period,
                    granularity=granularity,
                    personal_status=personal_status,
                    chart_type=chart_type,
                    cedula=target_cedula,
                )
                used_tools.append("get_attendance_unjustified_table")
                used_tools.append(f"attendance_analytics_trend_{granularity}")

                rows_for_response = list(trend.get("rows") or [])
                payload["table"] = {
                    "columns": list(rows_for_response[0].keys()) if rows_for_response else ["periodo", "total_injustificados"],
                    "rows": rows_for_response,
                    "rowcount": len(rows_for_response),
                }
                payload["kpis"] = {
                    "total_injustificados": int(trend.get("total_injustificados") or 0),
                    "periodos": len(rows_for_response),
                    "granularity": granularity,
                }
                payload["labels"] = list(trend.get("labels") or [])
                payload["series"] = list(trend.get("series") or [])
                chart_payload = dict(trend.get("chart") or {})
                if chart_payload:
                    payload["chart"] = chart_payload
                    payload["charts"] = [chart_payload]
                    actions.append(
                        {
                            "id": f"ausentismo-chart-{capability_id}",
                            "type": "render_chart",
                            "label": "Ver grafica de tendencia",
                            "payload": {
                                "chart": chart_payload,
                                "capability_id": capability_id,
                            },
                        }
                    )

                granularity_label = "mensual" if granularity == "monthly" else "diaria"
                if not rows_for_response:
                    reply = (
                        f"No se encontraron datos para tendencia {granularity_label} "
                        f"entre {trend.get('periodo_inicio')} y {trend.get('periodo_fin')}."
                    )
                else:
                    reply = (
                        f"Tendencia {granularity_label} de ausentismos injustificados "
                        f"({trend.get('periodo_inicio')} a {trend.get('periodo_fin')}):\n\n"
                        f"{self._format_rows_table(rows_for_response)}"
                    )
                if bool(trend.get("source_truncated")):
                    payload["insights"].append(
                        "La tendencia se calculo sobre una muestra truncada por limite de seguridad (max 500 registros)."
                    )
            else:
                return AusentismoHandleResult(
                    ok=False,
                    error=f"ausentismo capability no soportada: {capability_id}",
                    metadata={"capability_id": capability_id},
                )

            period_alternative_hint = self._build_period_alternative_hint(message=message, period=period)
            if period_alternative_hint:
                payload["insights"].append(period_alternative_hint)
                reply = f"{reply}\n\n{period_alternative_hint}" if reply else period_alternative_hint
            if target_cedula:
                payload["insights"].append(f"Filtro aplicado por cedula: {target_cedula}.")

            if capability_id.startswith("attendance.summary.by_") or capability_id.startswith("attendance.trend."):
                self._record_analytics_event(
                    observability=observability,
                    run_context=run_context,
                    sid=sid,
                    capability_id=capability_id,
                    rowcount=int(payload.get("table", {}).get("rowcount") or 0),
                    chart_type=str(dict(payload.get("chart") or {}).get("type") or ""),
                )

            for hint in memory_hints_used:
                self._record_memory_hint_event(
                    observability=observability,
                    run_context=run_context,
                    sid=sid,
                    capability_id=capability_id,
                    hint=hint,
                )

            SessionMemoryStore.update_context(
                sid,
                {
                    "last_domain": "ausentismo",
                    "last_intent": intent,
                    "last_focus": focus,
                    "last_output_mode": response_output_mode,
                    "last_needs_database": True,
                    "last_personal_status": personal_status,
                    "last_selected_agent": "ausentismo_agent",
                    "last_period_start": period.start.isoformat(),
                    "last_period_end": period.end.isoformat(),
                    "last_group_dimension_key": last_group_dimension_key or None,
                    "last_group_dimension_label": last_group_dimension_label or None,
                    "last_aggregation_focus": last_aggregation_focus or None,
                    "last_metric_key": last_metric_key or None,
                },
            )
            SessionMemoryStore.append_turn(sid, message, reply)
            memory_status = SessionMemoryStore.status(sid)

            total_duration_ms = int((time.perf_counter() - started_at) * 1000)
            data_sources = {
                "ausentismo": {
                    "ok": True,
                    "ausentismo_table": self.tool.ausentismo_table,
                    "ausentismo_table_source": self.tool.ausentismo_table_source,
                    "personal_table": self.tool.personal_table,
                    "personal_table_source": self.tool.personal_table_source,
                },
                "ai_dictionary": {
                    "ok": True,
                    "source": "capability_handler",
                },
                "cause_diagnostics": {
                    "ok": bool(cause_generation_meta),
                    "generator": str(cause_generation_meta.get("generator") or ""),
                    "confidence": float(cause_generation_meta.get("confidence") or 0.0),
                },
            }
            if cause_generation_meta:
                payload["cause_generation_meta"] = cause_generation_meta
            response = {
                "session_id": sid,
                "reply": reply,
                "orchestrator": {
                    "intent": intent,
                    "domain": "ausentismo",
                    "selected_agent": "ausentismo_agent",
                    "classifier_source": "capability_handler",
                    "needs_database": True,
                    "output_mode": response_output_mode,
                    "used_tools": used_tools,
                },
                "data": payload,
                "actions": actions,
                "data_sources": data_sources,
                "trace": trace,
                "memory": memory_status,
                "observability": {
                    "enabled": bool(getattr(observability, "enabled", True)),
                    "duration_ms": total_duration_ms,
                    "tool_latencies_ms": tool_latencies_ms,
                    "tokens_in": 0,
                    "tokens_out": 0,
                    "estimated_cost_usd": 0.0,
                },
                "active_nodes": self._resolve_active_nodes(
                    output_mode=response_output_mode,
                    used_tools=used_tools,
                ),
            }
            _push_trace(
                "attendance_capability_execution",
                "ok",
                {
                    "capability_id": capability_id,
                    "rowcount": int(payload.get("table", {}).get("rowcount") or 0),
                    "memory_hints_used": len(memory_hints_used),
                },
                self._resolve_active_nodes(output_mode=response_output_mode, used_tools=used_tools),
            )

            return AusentismoHandleResult(
                ok=True,
                response=response,
                metadata={
                    "memory_hints": memory_hints,
                    "memory_hints_used": memory_hints_used,
                    "capability_id": capability_id,
                    "policy_tags": list(planned_capability.get("policy_tags") or []),
                },
            )
        except Exception as exc:
            logger.exception("Ausentismo capability handler failed")
            return AusentismoHandleResult(
                ok=False,
                error=str(exc),
                metadata={"capability_id": capability_id},
            )

    @staticmethod
    def _normalize_text(text: str) -> str:
        lowered = (text or "").strip().lower()
        normalized = unicodedata.normalize("NFKD", lowered)
        return "".join(ch for ch in normalized if not unicodedata.combining(ch))

    def _resolve_period_for_attendance(self, *, message: str, session_context: dict[str, Any]) -> PeriodoAusentismo:
        period = resolve_period_from_text(message)
        label = str(period.get("label") or "hoy")
        source = "rules"
        start = period.get("start")
        end = period.get("end")

        normalized = self._normalize_text(message)
        if (
            (_YES_FOLLOW_UP_RE.match(normalized) or self._is_contextual_reference_request(normalized))
            and not self._has_explicit_period(message)
        ):
            prev_start = str(session_context.get("last_period_start") or "").strip()
            prev_end = str(session_context.get("last_period_end") or "").strip()
            if prev_start and prev_end:
                try:
                    start = date.fromisoformat(prev_start)
                    end = date.fromisoformat(prev_end)
                    label = "contexto_previo"
                    source = "context"
                except ValueError:
                    pass

        if not isinstance(start, date) or not isinstance(end, date):
            today = date.today()
            start = today
            end = today
            label = "hoy"
            source = "rules"

        return PeriodoAusentismo(start=start, end=end, label=label, source=source)

    def _extract_memory_hints(self, memory_context: dict[str, Any] | None) -> dict[str, Any]:
        context = dict(memory_context or {})
        user_memory = list(context.get("user_memory") or [])
        business_memory = list(context.get("business_memory") or [])

        hints = {
            "output_mode": None,
            "personal_status": None,
            "recurrence_view": None,
            "team": None,
            "supervisor": None,
            "analytics_chart_type": None,
            "analytics_top_n": None,
        }

        for row in user_memory:
            key = str(row.get("memory_key") or "").strip().lower()
            value = self._coerce_memory_value(row.get("memory_value"))
            if key == "attendance.output_mode" and value:
                hints["output_mode"] = value
            elif key == "attendance.personal_status" and value:
                hints["personal_status"] = value
            elif key == "attendance.team" and value:
                hints["team"] = value
            elif key == "attendance.supervisor" and value:
                hints["supervisor"] = value
            elif key == "attendance.analytics.chart_type" and value:
                hints["analytics_chart_type"] = value
            elif key == "attendance.analytics.top_n" and value:
                hints["analytics_top_n"] = value

        for row in business_memory:
            key = str(row.get("memory_key") or "").strip().lower()
            value = self._coerce_memory_value(row.get("memory_value"))
            if key == "attendance.recurrence.default_view" and value:
                hints["recurrence_view"] = value
            elif key == "attendance.default.personal_status" and value and not hints.get("personal_status"):
                hints["personal_status"] = value

        return hints

    @staticmethod
    def _coerce_memory_value(value: Any) -> str | None:
        if isinstance(value, dict):
            if "value" in value:
                raw = value.get("value")
            else:
                raw = next(iter(value.values()), None)
        else:
            raw = value
        text = str(raw or "").strip().lower()
        return text or None

    def _resolve_personal_status(
        self,
        *,
        message: str,
        session_context: dict[str, Any],
        hints: dict[str, Any],
        used: list[dict[str, Any]],
    ) -> str:
        normalized = self._normalize_text(message)
        if "inactivo" in normalized or "inactivos" in normalized:
            return "inactivos"
        if "activo" in normalized or "activos" in normalized:
            return "activos"

        hint_value = str(hints.get("personal_status") or "").strip().lower()
        if hint_value in {"all", "activos", "inactivos"}:
            used.append(
                {
                    "memory_key": "attendance.personal_status",
                    "memory_value": hint_value,
                    "reason": "personal_status_loaded_from_user_memory",
                }
            )
            return hint_value

        if _YES_FOLLOW_UP_RE.match(normalized):
            previous = str(session_context.get("last_personal_status") or "").strip().lower()
            if previous in {"all", "activos", "inactivos"}:
                return previous

        return "all"

    def _message_requests_personal_join(self, message: str) -> bool:
        normalized = self._normalize_text(message)
        return any(token in normalized for token in self._PERSONAL_TOKENS)

    def _message_wants_itemized(self, message: str) -> bool:
        normalized = self._normalize_text(message)
        return any(token in normalized for token in self._ITEMIZED_TOKENS)

    def _message_wants_grouped(self, message: str) -> bool:
        normalized = self._normalize_text(message)
        return any(token in normalized for token in self._GROUPED_TOKENS)

    def _message_requests_chart(self, message: str) -> bool:
        normalized = self._normalize_text(message)
        return any(token in normalized for token in self._CHART_TOKENS)

    def _message_requests_probable_causes(self, message: str) -> bool:
        normalized = self._normalize_text(message)
        return any(
            token in normalized
            for token in (
                "causa",
                "causas",
                "probable",
                "probables",
                "sugiere",
                "sugerir",
                "sugerencia",
                "porque",
                "por que",
            )
        )

    @staticmethod
    def _build_probable_causes_insights(*, rows: list[dict[str, Any]], group_label: str) -> list[str]:
        if not rows:
            return [
                "No hay datos suficientes en el periodo para sugerir causas probables.",
            ]
        top_row = dict(rows[0] or {})
        top_group = str(
            top_row.get("grupo")
            or top_row.get("group")
            or top_row.get("area")
            or top_row.get("supervisor")
            or top_row.get("cargo")
            or ""
        ).strip()
        top_pct_raw = top_row.get("porcentaje")
        top_pct = ""
        try:
            if top_pct_raw is not None and str(top_pct_raw).strip() != "":
                top_pct = f"{float(top_pct_raw):.1f}%"
        except Exception:
            top_pct = str(top_pct_raw or "").strip()

        hints: list[str] = []
        if top_group and top_pct:
            hints.append(
                f"Concentracion principal en {group_label}: {top_group} ({top_pct}). Prioriza analisis operativo en ese frente."
            )
        elif top_group:
            hints.append(
                f"Concentracion principal en {group_label}: {top_group}. Prioriza analisis operativo en ese frente."
            )
        hints.extend(
            [
                "Posibles causas a validar: sobrecarga operativa, picos de incapacidades y cobertura insuficiente de reemplazos.",
                "Recomendacion: cruzar ausentismo con turnos, novedades medicas y dotacion por equipo para confirmar causa raiz.",
            ]
        )
        return hints

    @staticmethod
    def _build_cause_diagnostics_trace_detail(*, meta: dict[str, Any], capability_id: str) -> dict[str, Any]:
        payload = dict(meta or {})
        policy_decision = dict(payload.get("policy_decision") or {})
        fallback_reason = str(payload.get("fallback_reason") or "").strip()
        validation_errors = [
            str(item or "").strip()
            for item in list(payload.get("validation_errors") or [])
            if str(item or "").strip()
        ]
        try:
            confidence = float(payload.get("confidence") or 0.0)
        except Exception:
            confidence = 0.0
        try:
            top_pct = float(payload.get("top_pct") or 0.0)
        except Exception:
            top_pct = 0.0
        return {
            "capability_id": str(capability_id or ""),
            "generator": str(payload.get("generator") or ""),
            "confidence": confidence,
            "validated": bool(payload.get("validated")),
            "top_group": str(payload.get("top_group") or ""),
            "top_pct": top_pct,
            "fallback_reason": fallback_reason,
            "validation_errors": validation_errors,
            "prompt_hash": str(payload.get("prompt_hash") or ""),
            "policy_reason": str(policy_decision.get("reason") or ""),
            "policy_selected_generator": str(policy_decision.get("selected_generator") or ""),
            "policy_allowed": bool(policy_decision.get("allowed")),
        }

    @staticmethod
    def _is_contextual_reference_request(normalized: str) -> bool:
        return any(
            token in normalized
            for token in (
                "reporte",
                "resultado",
                "consulta",
                "este reporte",
                "este resultado",
                "esta consulta",
                "ese reporte",
                "ese resultado",
                "informacion anterior",
                "info anterior",
                "lo anterior",
                "mismo periodo",
                "mismo rango",
                "ese periodo",
                "ese rango",
            )
        )

    def _resolve_chart_type(
        self,
        *,
        message: str,
        hints: dict[str, Any],
        fallback: str = "bar",
    ) -> str:
        normalized = self._normalize_text(message)
        if "linea" in normalized:
            return "line"
        if "area" in normalized:
            return "area"
        if "barra" in normalized or "barras" in normalized:
            return "bar"

        hint_chart = str(hints.get("analytics_chart_type") or "").strip().lower()
        if hint_chart in {"bar", "line", "area"}:
            return hint_chart
        return fallback

    def _resolve_group_dimension(
        self,
        *,
        message: str,
        capability_id: str,
        constrained_group_by: list[str] | None = None,
    ) -> tuple[str, str]:
        requested = [str(item or "").strip().lower() for item in list(constrained_group_by or []) if str(item or "").strip()]
        if requested:
            first = requested[0]
            if first == "supervisor":
                return "supervisor", "Supervisor"
            if first == "area":
                return "area", "Area"
            if first == "cargo":
                return "cargo", "Cargo"
            if first in {"carpeta", "justificacion", "causa", "motivo"}:
                return "carpeta" if first == "carpeta" else "justificacion", "Carpeta" if first == "carpeta" else "Justificacion"
            if first in {"tipo_labor", "tipo labor", "tipo de labor", "labor"}:
                return "tipo_labor", "Tipo Labor"
            if first in {"centro_costo", "centro costo", "centro de costo", "cc"}:
                return "centro_costo", "Centro de costo"
            if first in {"estado", "estado_justificacion", "tipo_ausentismo", "tipo de ausentismo", "tipo de ausencia"}:
                return "estado_justificacion", "Estado"
            return first, first.replace("_", " ").strip().title()

        if capability_id.endswith("by_supervisor.v1"):
            return "supervisor", "Supervisor"
        if capability_id.endswith("by_area.v1"):
            return "area", "Area"
        if capability_id.endswith("by_cargo.v1"):
            return "cargo", "Cargo"

        normalized = self._normalize_text(message)
        mappings = (
            ("por supervisor", "supervisor", "Supervisor"),
            ("supervisor", "supervisor", "Supervisor"),
            ("por area", "area", "Area"),
            ("area", "area", "Area"),
            ("por cargo", "cargo", "Cargo"),
            ("cargo", "cargo", "Cargo"),
            ("por tipo de labor", "tipo_labor", "Tipo Labor"),
            ("tipo de labor", "tipo_labor", "Tipo Labor"),
            ("por tipo labor", "tipo_labor", "Tipo Labor"),
            ("tipo labor", "tipo_labor", "Tipo Labor"),
            ("por labor", "tipo_labor", "Tipo Labor"),
            ("labor", "tipo_labor", "Tipo Labor"),
            ("por centro de costo", "centro_costo", "Centro de costo"),
            ("centro de costo", "centro_costo", "Centro de costo"),
            ("por centro costo", "centro_costo", "Centro de costo"),
            ("centro costo", "centro_costo", "Centro de costo"),
            ("por cc", "centro_costo", "Centro de costo"),
            ("por carpeta", "carpeta", "Carpeta"),
            ("carpeta", "carpeta", "Carpeta"),
            ("por justificacion", "justificacion", "Justificacion"),
            ("justificacion", "justificacion", "Justificacion"),
            ("por causa", "justificacion", "Justificacion"),
            ("causa", "justificacion", "Justificacion"),
            ("por motivo", "justificacion", "Justificacion"),
            ("motivo", "justificacion", "Justificacion"),
            ("por tipo de ausentismo", "estado_justificacion", "Estado"),
            ("tipo de ausentismo", "estado_justificacion", "Estado"),
            ("por tipo de ausencia", "estado_justificacion", "Estado"),
            ("tipo de ausencia", "estado_justificacion", "Estado"),
            ("por estado", "estado_justificacion", "Estado"),
            ("estado", "estado_justificacion", "Estado"),
        )
        for token, key, label in mappings:
            if token in normalized:
                return key, label
        generic_match = re.search(r"\bpor\s+([a-z0-9_]{2,60})\b", normalized)
        if generic_match:
            generic = str(generic_match.group(1) or "").strip().lower()
            if generic:
                return generic, generic.replace("_", " ").strip().title()
        return "supervisor", "Supervisor"

    def _resolve_aggregation_focus(self, *, message: str) -> str:
        normalized = self._normalize_text(message)
        if "injustific" in normalized or "sin justificar" in normalized:
            return "unjustified"
        return "all"

    @classmethod
    def _resolve_attendance_reason_filter(
        cls,
        *,
        message: str,
        constraints: dict[str, Any],
        resolved_query: ResolvedQuerySpec | None,
    ) -> str:
        filters = dict(constraints.get("filters") or {})
        direct = str(filters.get("justificacion") or "").strip().upper()
        if direct:
            return direct
        if resolved_query is not None:
            direct = str((resolved_query.normalized_filters or {}).get("justificacion") or "").strip().upper()
            if direct:
                return direct
        normalized = cls._normalize_text(message)
        reason_signals = {
            "vacaciones": "VACACIONES",
            "vacacion": "VACACIONES",
            "incapacidad": "INCAPACIDAD",
            "incapacidades": "INCAPACIDAD",
            "licencia": "LICENCIA",
            "licencias": "LICENCIA",
            "permiso": "PERMISO",
            "permisos": "PERMISO",
            "calamidad": "CALAMIDAD",
        }
        for token, canonical in reason_signals.items():
            if re.search(rf"\b{re.escape(token)}\b", normalized):
                return canonical
        return ""

    @staticmethod
    def _describe_attendance_scope(
        *,
        focus: str,
        attendance_reason_filter: str | None,
        plural_compact: bool = False,
    ) -> str:
        reason = str(attendance_reason_filter or "").strip().lower()
        if reason:
            prefix = "ausentismos por " if plural_compact else "ausentismos por "
            return f"{prefix}{reason}"
        if str(focus or "").strip().lower() == "unjustified":
            return "ausentismos injustificados" if plural_compact else "ausentismos injustificados"
        return "ausentismos totales" if plural_compact else "ausentismos"

    def _extract_top_n(self, message: str, *, hints: dict[str, Any] | None = None, default: int = 10) -> int:
        normalized = self._normalize_text(message)
        match = re.search(r"\btop\s*(\d{1,2})\b", normalized)
        if match:
            try:
                return max(1, min(int(match.group(1)), 50))
            except ValueError:
                pass

        hint_raw = str((hints or {}).get("analytics_top_n") or "").strip()
        if hint_raw.isdigit():
            return max(1, min(int(hint_raw), 50))

        return max(1, min(int(default), 50))

    def _has_explicit_period(self, text: str) -> bool:
        msg = self._normalize_text(text)
        if re.search(r"\d{4}-\d{2}-\d{2}", msg):
            return True
        if re.search(r"\b(lunes|martes|miercoles|jueves|viernes|sabado|domingo)\b", msg):
            return True
        return any(
            token in msg
            for token in (
                "hoy",
                "ayer",
                "esta semana",
                "semana actual",
                "semana pasada",
                "semana anterior",
                "ultima semana",
                "ultimos",
                "mes",
                "anio",
                "rango",
            )
        )

    @staticmethod
    def _format_rows_table(rows: list[dict[str, Any]], max_rows: int = 20) -> str:
        if not rows:
            return "(sin resultados)"
        preview_rows = rows[:max_rows]
        columns = list(preview_rows[0].keys())
        header = " | ".join(columns)
        separator = " | ".join(["---"] * len(columns))
        body = []
        for row in preview_rows:
            body.append(" | ".join(str(row.get(col, "")) for col in columns))
        suffix = f"\n... ({len(rows) - max_rows} filas adicionales)" if len(rows) > max_rows else ""
        return f"{header}\n{separator}\n" + "\n".join(body) + suffix

    @staticmethod
    def _resolve_target_cedula(
        *,
        message: str,
        constraints: dict[str, Any],
        resolved_query: ResolvedQuerySpec | None,
    ) -> str | None:
        filters = dict(constraints.get("filters") or {})
        cedula = str(filters.get("cedula") or "").strip()
        if cedula:
            normalized = AusentismoHandler._normalize_identifier(cedula)
            return normalized or None
        if resolved_query is not None:
            normalized = AusentismoHandler._normalize_identifier(
                str((resolved_query.normalized_filters or {}).get("cedula") or "")
            )
            if normalized:
                return normalized
        return AusentismoHandler._extract_cedula_from_message(message)

    @staticmethod
    def _apply_constraints_to_period(
        *,
        period: PeriodoAusentismo,
        constraints: dict[str, Any],
    ) -> PeriodoAusentismo:
        period_scope = dict(constraints.get("period_scope") or {})
        start_text = str(period_scope.get("start_date") or "").strip()
        end_text = str(period_scope.get("end_date") or "").strip()
        if not start_text or not end_text:
            return period
        try:
            start = date.fromisoformat(start_text)
            end = date.fromisoformat(end_text)
        except Exception:
            return period
        if end < start:
            start, end = end, start
        return PeriodoAusentismo(
            start=start,
            end=end,
            label=str(period_scope.get("label") or period.label or "constraints_period"),
            source="query_constraints",
        )

    @staticmethod
    def _extract_cedula_from_message(message: str) -> str | None:
        match = re.search(r"\b\d{6,13}\b", str(message or ""))
        if not match:
            return None
        value = AusentismoHandler._normalize_identifier(match.group(0))
        return value or None

    @staticmethod
    def _normalize_identifier(value: Any) -> str:
        return "".join(ch for ch in str(value or "") if ch.isdigit())

    def _build_period_alternative_hint(self, *, message: str, period: PeriodoAusentismo) -> str | None:
        normalized = self._normalize_text(message)
        label = str(period.label or "").lower()
        today = date.today()

        if "mes anterior" in normalized or "mes pasado" in normalized or label == "mes_anterior":
            rolling_start = today - timedelta(days=29)
            rolling_end = today
            return (
                "Si quieres, tambien puedo mostrarlo como ultimo mes movil de 30 dias "
                f"({rolling_start.isoformat()} a {rolling_end.isoformat()}). "
                "Responde: si, ultimo mes."
            )

        if re.search(r"\bultim[oa]s?\s+mes\b", normalized) or label == "ultimo_mes_30_dias":
            first_current = today.replace(day=1)
            prev_end = first_current - timedelta(days=1)
            prev_start = prev_end.replace(day=1)
            return (
                "Si prefieres, tambien puedo mostrarlo como mes anterior calendario "
                f"({prev_start.isoformat()} a {prev_end.isoformat()}). "
                "Responde: si, mes anterior."
            )

        return None

    @staticmethod
    def _resolve_active_nodes(*, output_mode: str, used_tools: list[str]) -> list[str]:
        active = {"q", "gpt", "route", "aus", "result", "audit"}
        if output_mode in {"table", "list"}:
            active.update({"join", "check"})
        if any("personal" in tool for tool in used_tools):
            active.update({"personal", "join"})
        if any("recurrence" in tool for tool in used_tools):
            active.add("rules")
        if any("analytics" in tool or "trend" in tool for tool in used_tools):
            active.update({"chart", "rules"})
        return sorted(active)

    @staticmethod
    def _record_analytics_event(
        *,
        observability,
        run_context: RunContext,
        sid: str,
        capability_id: str,
        rowcount: int,
        chart_type: str,
    ) -> None:
        if observability is None or not hasattr(observability, "record_event"):
            return
        observability.record_event(
            event_type="attendance_analytics_generated",
            source="AusentismoHandler",
            meta={
                "run_id": run_context.run_id,
                "trace_id": run_context.trace_id,
                "session_id": sid,
                "capability_id": capability_id,
                "rowcount": int(rowcount),
                "chart_type": chart_type or None,
            },
        )

    @staticmethod
    def _record_memory_hint_event(
        *,
        observability,
        run_context: RunContext,
        sid: str,
        capability_id: str,
        hint: dict[str, Any],
    ) -> None:
        if observability is None or not hasattr(observability, "record_event"):
            return
        observability.record_event(
            event_type="attendance_memory_hint_used",
            source="AusentismoHandler",
            meta={
                "run_id": run_context.run_id,
                "trace_id": run_context.trace_id,
                "session_id": sid,
                "capability_id": capability_id,
                "memory_key": hint.get("memory_key"),
                "memory_value": hint.get("memory_value"),
                "reason": hint.get("reason"),
            },
        )

    def _safe_resolve_org_reference(self, *, message: str) -> dict[str, Any]:
        try:
            resolved = self.org_context.resolve_reference(message=message)
            return dict(resolved or {})
        except Exception:
            return {"resolved": False, "reference": "", "filters": {}, "candidates": []}


AttendanceHandleResult = AusentismoHandleResult
AttendanceHandler = AusentismoHandler
