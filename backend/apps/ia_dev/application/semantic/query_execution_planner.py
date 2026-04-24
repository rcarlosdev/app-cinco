from __future__ import annotations

import os
import re
import time
from datetime import datetime, timezone
from typing import Any

from django.db import connections

from apps.ia_dev.application.context.run_context import RunContext
from apps.ia_dev.application.contracts.query_intelligence_contracts import (
    QueryExecutionPlan,
    ResolvedQuerySpec,
)
from apps.ia_dev.application.policies.query_execution_policy import QueryExecutionPolicy
from apps.ia_dev.application.routing.capability_catalog import CapabilityCatalog


class QueryExecutionPlanner:
    SAFE_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9_\.]+$")

    def __init__(
        self,
        *,
        catalog: CapabilityCatalog | None = None,
        query_policy: QueryExecutionPolicy | None = None,
    ):
        self.catalog = catalog or CapabilityCatalog()
        self.query_policy = query_policy or QueryExecutionPolicy()

    def plan(
        self,
        *,
        run_context: RunContext,
        resolved_query: ResolvedQuerySpec,
    ) -> QueryExecutionPlan:
        domain_code = str(resolved_query.intent.domain_code or "").strip().lower()
        template_id = str(resolved_query.intent.template_id or "").strip().lower()
        constraints = self._build_constraints(resolved_query=resolved_query)

        capability_id = self._resolve_capability_id(
            domain_code=domain_code,
            template_id=template_id,
            resolved_query=resolved_query,
        )
        if capability_id and self._is_capability_rollout_enabled(capability_id):
            return QueryExecutionPlan(
                strategy="capability",
                reason="capability_selected_from_query_intelligence",
                domain_code=domain_code,
                capability_id=capability_id,
                constraints=constraints,
                policy={"allowed": True, "reason": "capability_first"},
                metadata={
                    "template_id": template_id,
                    "operation": resolved_query.intent.operation,
                },
            )

        sql_policy = self.query_policy.evaluate_sql_assisted(
            run_context=run_context,
            resolved_query=resolved_query,
        )
        if sql_policy.allowed:
            sql_query, sql_reason = self._build_sql_query(resolved_query=resolved_query)
            if sql_query:
                validation = self.query_policy.validate_sql_query(
                    query=sql_query,
                    allowed_tables=list((resolved_query.semantic_context or {}).get("allowed_tables") or []),
                    allowed_columns=list((resolved_query.semantic_context or {}).get("allowed_columns") or []),
                    max_limit=self._max_sql_limit(),
                )
                if validation.allowed:
                    return QueryExecutionPlan(
                        strategy="sql_assisted",
                        reason=sql_reason,
                        domain_code=domain_code,
                        sql_query=sql_query,
                        constraints=constraints,
                        policy={
                            "allowed": True,
                            "reason": validation.reason,
                            "metadata": validation.metadata,
                        },
                        metadata={
                            "template_id": template_id,
                            "operation": resolved_query.intent.operation,
                            "capability_id": capability_id,
                        },
                    )
                return QueryExecutionPlan(
                    strategy="fallback",
                    reason=f"sql_rejected:{validation.reason}",
                    domain_code=domain_code,
                    capability_id=capability_id,
                    constraints=constraints,
                    policy={
                        "allowed": False,
                        "reason": validation.reason,
                        "metadata": validation.metadata,
                    },
                    metadata={"template_id": template_id},
                )

        # General-domain requests are conversational and should continue to legacy/OpenAI reply
        # generation instead of triggering context-collection flows intended for DB analytics.
        if domain_code in {"", "general"}:
            return QueryExecutionPlan(
                strategy="fallback",
                reason="general_domain_conversational_fallback",
                domain_code=domain_code or "general",
                capability_id=capability_id,
                constraints=constraints,
                policy={"allowed": False, "reason": "fallback_legacy"},
                metadata={"template_id": template_id},
            )

        missing_context = self._detect_missing_context(resolved_query=resolved_query)
        if missing_context:
            return QueryExecutionPlan(
                strategy="ask_context",
                reason="missing_context_for_safe_execution",
                domain_code=domain_code,
                requires_context=True,
                missing_context=missing_context,
                constraints=constraints,
                policy={
                    "allowed": False,
                    "reason": "missing_context",
                    "metadata": {"missing_context": missing_context},
                },
                metadata={"template_id": template_id},
            )

        return QueryExecutionPlan(
            strategy="fallback",
            reason="no_capability_or_sql_plan_available",
            domain_code=domain_code,
            capability_id=capability_id,
            constraints=constraints,
            policy={"allowed": False, "reason": "fallback_legacy"},
            metadata={"template_id": template_id},
        )

    def execute_sql_assisted(
        self,
        *,
        run_context: RunContext,
        resolved_query: ResolvedQuerySpec,
        execution_plan: QueryExecutionPlan,
        observability=None,
    ) -> dict[str, Any]:
        sql_query = str(execution_plan.sql_query or "").strip()
        if not sql_query:
            return {"ok": False, "error": "sql_query_missing"}

        db_alias = str(os.getenv("IA_DEV_DB_READONLY_ALIAS", os.getenv("IA_DEV_DB_ALIAS", "default")) or "default").strip()
        started = time.perf_counter()
        try:
            with connections[db_alias].cursor() as cursor:
                cursor.execute(sql_query)
                rows = cursor.fetchall()
                columns = [str(getattr(col, "name", col[0]) or "") for col in (cursor.description or [])]
            duration_ms = int((time.perf_counter() - started) * 1000)
            rows_payload = [
                {columns[idx]: row[idx] for idx in range(len(columns))}
                for row in rows
            ]
            response = self._build_sql_response(
                run_context=run_context,
                resolved_query=resolved_query,
                execution_plan=execution_plan,
                sql_query=sql_query,
                rows=rows_payload,
                columns=columns,
                duration_ms=duration_ms,
                db_alias=db_alias,
            )
            self._record_event(
                observability=observability,
                event_type="query_sql_assisted_executed",
                source="QueryExecutionPlanner",
                meta={
                    "run_id": run_context.run_id,
                    "trace_id": run_context.trace_id,
                    "db_alias": db_alias,
                    "duration_ms": duration_ms,
                    "domain_code": resolved_query.intent.domain_code,
                    "template_id": resolved_query.intent.template_id,
                    "rowcount": len(rows_payload),
                    "query": sql_query,
                },
            )
            return {"ok": True, "response": response}
        except Exception as exc:
            duration_ms = int((time.perf_counter() - started) * 1000)
            self._record_event(
                observability=observability,
                event_type="query_sql_assisted_error",
                source="QueryExecutionPlanner",
                meta={
                    "run_id": run_context.run_id,
                    "trace_id": run_context.trace_id,
                    "db_alias": db_alias,
                    "duration_ms": duration_ms,
                    "domain_code": resolved_query.intent.domain_code,
                    "template_id": resolved_query.intent.template_id,
                    "query": sql_query,
                    "error": str(exc),
                },
            )
            return {"ok": False, "error": f"sql_execution_error:{exc}"}

    def build_missing_context_response(
        self,
        *,
        run_context: RunContext,
        resolved_query: ResolvedQuerySpec,
        execution_plan: QueryExecutionPlan,
    ) -> dict[str, Any]:
        missing = list(execution_plan.missing_context or [])
        missing_text = ", ".join(missing) if missing else "contexto adicional"
        reply = (
            "Necesito confirmar algunos datos para ejecutar la consulta de forma segura: "
            f"{missing_text}."
        )
        return {
            "session_id": str(run_context.session_id or ""),
            "reply": reply,
            "orchestrator": {
                "intent": str(resolved_query.intent.operation or "query"),
                "domain": str(resolved_query.intent.domain_code or ""),
                "selected_agent": "analista_agent",
                "classifier_source": "query_intelligence_context_request",
                "needs_database": True,
                "output_mode": "summary",
                "used_tools": [],
            },
            "data": {
                "kpis": {},
                "series": [],
                "labels": [],
                "insights": [reply],
                "table": {"columns": [], "rows": [], "rowcount": 0},
            },
            "actions": [
                {
                    "id": f"query-context-{run_context.run_id}",
                    "type": "ask_context",
                    "label": "Completar contexto",
                    "payload": {
                        "missing_context": missing,
                        "domain_code": resolved_query.intent.domain_code,
                    },
                }
            ],
            "data_sources": {
                "query_intelligence": {"ok": True, "mode": "ask_context"},
            },
            "trace": [
                {
                    "phase": "query_intelligence",
                    "status": "partial",
                    "at": datetime.now(timezone.utc).isoformat(),
                    "detail": execution_plan.as_dict(),
                    "active_nodes": ["q", "gpt", "route"],
                }
            ],
            "memory": {
                "used_messages": 0,
                "capacity_messages": 20,
                "usage_ratio": 0.0,
                "trim_events": 0,
                "saturated": False,
            },
            "observability": {
                "enabled": True,
                "duration_ms": 0,
                "tool_latencies_ms": {},
                "tokens_in": 0,
                "tokens_out": 0,
                "estimated_cost_usd": 0.0,
            },
            "active_nodes": ["q", "gpt", "route"],
        }

    def _resolve_capability_id(
        self,
        *,
        domain_code: str,
        template_id: str,
        resolved_query: ResolvedQuerySpec,
    ) -> str | None:
        normalized_domain = str(domain_code or "").strip().lower()
        if normalized_domain in {"empleados", "rrhh"}:
            filters = dict(resolved_query.normalized_filters or {})
            operation = str(resolved_query.intent.operation or "").strip().lower()
            raw_query = str(resolved_query.intent.raw_query or "").strip().lower()
            metrics = [str(item).strip().lower() for item in list(resolved_query.intent.metrics or [])]
            group_by = [str(item).strip().lower() for item in list(resolved_query.intent.group_by or []) if str(item).strip()]
            status_value = self._resolve_status_filter(filters=filters)
            has_employee_identifier = bool(
                str(filters.get("cedula") or "").strip()
                or str(filters.get("movil") or "").strip()
                or str(filters.get("codigo_sap") or "").strip()
                or str(filters.get("search") or "").strip()
            )
            temporal_scope = self._extract_temporal_scope(resolved_query=resolved_query)
            has_temporal_scope = bool(
                temporal_scope.get("column_hint")
                and temporal_scope.get("start_date")
                and temporal_scope.get("end_date")
                and not bool(temporal_scope.get("ambiguous"))
            )
            if "turnover_rate" in metrics or re.search(r"\b(rotacion|rotaciones|turnover)\b", raw_query):
                return "empleados.count.active.v1"
            if template_id == "detail_by_entity_and_period" and has_employee_identifier:
                return "empleados.detail.v1"
            if operation == "count" and status_value in {"ACTIVO", "INACTIVO"}:
                return "empleados.count.active.v1"
            if group_by and status_value in {"ACTIVO", "INACTIVO"} and operation in {"aggregate", "compare", "summary", "count"}:
                return "empleados.count.active.v1"
            if template_id == "count_entities_by_status" and status_value in {"ACTIVO", "INACTIVO"}:
                return "empleados.count.active.v1"
            if template_id == "aggregate_by_group_and_period" and group_by and status_value in {"ACTIVO", "INACTIVO"}:
                return "empleados.count.active.v1"
            if has_temporal_scope and status_value in {"ACTIVO", "INACTIVO"}:
                return "empleados.count.active.v1"
            return None
        if normalized_domain in {"ausentismo", "attendance"}:
            filters = dict(resolved_query.normalized_filters or {})
            raw_query = str(resolved_query.intent.raw_query or "").strip().lower()
            group_by = [str(item).strip().lower() for item in list(resolved_query.intent.group_by or [])]
            has_attendance_reason = bool(
                str(filters.get("justificacion") or "").strip()
                or str(filters.get("motivo_justificacion") or "").strip()
            )
            has_people_scope = bool(
                re.search(r"\b(emplead\w*|colaborador(?:es)?|personal|persona(?:s)?)\b", raw_query)
            )
            has_explicit_grouping = bool(
                re.search(r"\bpor\s+(area|cargo|supervisor|carpeta|labor|tipo de labor|tipo labor|justificacion|motivo|causa)\b", raw_query)
            )
            asks_summary_count = bool(
                re.search(r"\b(cantidad|cuantos|cuantas|total|numero|resumen)\b", raw_query)
            )
            if re.search(r"\b(reincid\w*|recurrent\w*|recurren\w*)\b", raw_query):
                return "attendance.recurrence.grouped.v1"
            if has_attendance_reason and has_people_scope and not group_by and not has_explicit_grouping and not asks_summary_count:
                return "attendance.unjustified.table_with_personal.v1"
            if template_id == "aggregate_by_group_and_period":
                if "supervisor" in group_by:
                    return "attendance.summary.by_supervisor.v1"
                if "area" in group_by:
                    return "attendance.summary.by_area.v1"
                if "cargo" in group_by:
                    return "attendance.summary.by_cargo.v1"
                if group_by:
                    return "attendance.summary.by_attribute.v1"
                return "attendance.unjustified.summary.v1"
            if template_id == "trend_by_period":
                label = str((resolved_query.normalized_period or {}).get("label") or "").lower()
                if any(token in label for token in ("mes", "monthly")):
                    return "attendance.trend.monthly.v1"
                return "attendance.trend.daily.v1"
            if template_id == "detail_by_entity_and_period":
                return "attendance.unjustified.table_with_personal.v1"
            if template_id == "count_records_by_period":
                return "attendance.unjustified.summary.v1"
            return "attendance.unjustified.summary.v1"
        return None

    def _build_constraints(self, *, resolved_query: ResolvedQuerySpec) -> dict[str, Any]:
        filters = dict(resolved_query.normalized_filters or {})
        status_value = self._resolve_status_filter(filters=filters)
        if status_value and "estado" not in filters:
            filters["estado"] = status_value
        period = dict(resolved_query.normalized_period or {})
        group_by = [str(item).strip().lower() for item in list(resolved_query.intent.group_by or []) if str(item).strip()]
        metrics = [str(item).strip().lower() for item in list(resolved_query.intent.metrics or []) if str(item).strip()]
        operation = str(resolved_query.intent.operation or "").strip().lower()
        result_shape = "summary"
        if group_by:
            result_shape = "table"
        elif operation in {"detail"}:
            result_shape = "table"
        elif operation in {"aggregate", "trend", "compare"}:
            result_shape = "table"
        elif operation == "count":
            result_shape = "kpi"

        cedula = str(filters.get("cedula") or "").strip()
        movil = str(filters.get("movil") or "").strip()
        codigo_sap = str(filters.get("codigo_sap") or "").strip()
        search = str(filters.get("search") or "").strip()
        entity_type = ""
        entity_id = ""
        if cedula:
            entity_type = "cedula"
            entity_id = cedula
        elif movil:
            entity_type = "movil"
            entity_id = movil
        elif codigo_sap:
            entity_type = "codigo_sap"
            entity_id = codigo_sap
        elif search:
            entity_type = "search"
            entity_id = search
        entity_scope = {
            "entity_type": entity_type,
            "entity_id": entity_id,
            "has_entity_filter": bool(entity_id),
        }
        period_scope = {
            "label": str(period.get("label") or ""),
            "start_date": str(period.get("start_date") or ""),
            "end_date": str(period.get("end_date") or ""),
        }
        temporal_scope = self._extract_temporal_scope(resolved_query=resolved_query)
        relations_payload = list(
            (dict(resolved_query.semantic_context or {}).get("resolved_semantic") or {}).get("relations") or []
        )
        chart_requested = bool(
            any(metric in {"count", "percentage"} for metric in metrics)
            and (operation in {"trend", "aggregate", "compare"})
        )
        return {
            "entity_scope": entity_scope,
            "filters": filters,
            "period_scope": period_scope,
            "temporal_scope": temporal_scope,
            "group_by": group_by,
            "metrics": metrics or (["count"] if operation == "count" else []),
            "result_shape": result_shape,
            "joins": relations_payload,
            "chart_requested": chart_requested,
            "operation": operation,
            "template_id": str(resolved_query.intent.template_id or ""),
        }

    @staticmethod
    def _resolve_status_filter(*, filters: dict[str, Any]) -> str:
        for key in ("estado", "estado_empleado"):
            status = str((filters or {}).get(key) or "").strip().upper()
            if status in {"ACTIVO", "INACTIVO"}:
                return status
        return ""

    def _build_sql_query(self, *, resolved_query: ResolvedQuerySpec) -> tuple[str, str]:
        template_id = str(resolved_query.intent.template_id or "").strip().lower()
        context = dict(resolved_query.semantic_context or {})
        table = self._resolve_primary_table(context=context)
        if not table:
            return "", "sql_missing_primary_table"

        date_column = self._resolve_date_column(context=context)
        entity_column = self._resolve_entity_column(context=context)
        status_column = self._resolve_status_column(context=context)
        group_column = self._resolve_group_column(resolved_query=resolved_query, context=context)
        start_date = str((resolved_query.normalized_period or {}).get("start_date") or "")
        end_date = str((resolved_query.normalized_period or {}).get("end_date") or "")
        filters = dict(resolved_query.normalized_filters or {})
        limit = self._max_sql_limit()

        if template_id == "count_entities_by_status":
            if not status_column and "estado" in filters:
                return "", "sql_missing_status_column"
            where_parts = []
            if status_column and filters.get("estado"):
                where_parts.append(f"{status_column} = '{self._escape_literal(str(filters.get('estado') or ''))}'")
            where_sql = (" WHERE " + " AND ".join(where_parts)) if where_parts else ""
            query = f"SELECT COUNT(*) AS total_registros FROM {table}{where_sql} LIMIT 1"
            return query, "sql_count_entities_by_status"

        if template_id == "count_records_by_period":
            if start_date and end_date and not date_column:
                return "", "sql_missing_date_column"
            where_parts = self._build_date_where(date_column=date_column, start_date=start_date, end_date=end_date)
            if entity_column and filters.get("cedula"):
                where_parts.append(f"{entity_column} = '{self._escape_literal(str(filters.get('cedula') or ''))}'")
            where_sql = (" WHERE " + " AND ".join(where_parts)) if where_parts else ""
            query = f"SELECT COUNT(*) AS total_registros FROM {table}{where_sql} LIMIT 1"
            return query, "sql_count_records_by_period"

        if template_id == "detail_by_entity_and_period":
            if start_date and end_date and not date_column:
                return "", "sql_missing_date_column"
            select_columns = self._resolve_detail_columns(context=context)
            where_parts = self._build_date_where(date_column=date_column, start_date=start_date, end_date=end_date)
            if entity_column and filters.get("cedula"):
                where_parts.append(f"{entity_column} = '{self._escape_literal(str(filters.get('cedula') or ''))}'")
            where_sql = (" WHERE " + " AND ".join(where_parts)) if where_parts else ""
            order_sql = f" ORDER BY {date_column} DESC" if date_column else ""
            query = f"SELECT {', '.join(select_columns)} FROM {table}{where_sql}{order_sql} LIMIT {limit}"
            return query, "sql_detail_by_entity_and_period"

        if template_id == "aggregate_by_group_and_period":
            if not group_column:
                return "", "sql_missing_group_column"
            if start_date and end_date and not date_column:
                return "", "sql_missing_date_column"
            where_parts = self._build_date_where(date_column=date_column, start_date=start_date, end_date=end_date)
            where_sql = (" WHERE " + " AND ".join(where_parts)) if where_parts else ""
            query = (
                f"SELECT {group_column} AS grupo, COUNT(*) AS total_registros "
                f"FROM {table}{where_sql} "
                f"GROUP BY {group_column} ORDER BY total_registros DESC LIMIT {limit}"
            )
            return query, "sql_aggregate_by_group_and_period"

        if template_id == "trend_by_period":
            if not date_column:
                return "", "sql_missing_date_column"
            where_parts = self._build_date_where(date_column=date_column, start_date=start_date, end_date=end_date)
            where_sql = (" WHERE " + " AND ".join(where_parts)) if where_parts else ""
            query = (
                f"SELECT DATE({date_column}) AS periodo, COUNT(*) AS total_registros "
                f"FROM {table}{where_sql} GROUP BY DATE({date_column}) ORDER BY DATE({date_column}) ASC LIMIT {limit}"
            )
            return query, "sql_trend_by_period"

        return "", "sql_template_not_supported"

    @staticmethod
    def _build_date_where(*, date_column: str, start_date: str, end_date: str) -> list[str]:
        where_parts: list[str] = []
        if date_column and start_date and end_date:
            where_parts.append(f"DATE({date_column}) BETWEEN '{start_date}' AND '{end_date}'")
        return where_parts

    def _resolve_primary_table(self, *, context: dict[str, Any]) -> str:
        tables = list(context.get("tables") or [])
        preferred = None
        for item in tables:
            if not isinstance(item, dict):
                continue
            if bool(item.get("es_principal")) or str(item.get("rol") or "").strip().lower() in {"hechos", "fact"}:
                preferred = item
                break
        if preferred is None and tables:
            preferred = tables[0]
        if not isinstance(preferred, dict):
            return ""
        table_fqn = str(preferred.get("table_fqn") or "").strip()
        table_name = str(preferred.get("table_name") or "").strip()
        if table_fqn and self._is_safe_identifier(table_fqn):
            return table_fqn
        if table_name and self._is_safe_identifier(table_name):
            return table_name
        return ""

    def _resolve_date_column(self, *, context: dict[str, Any]) -> str:
        for profile in list(context.get("column_profiles") or []):
            if not isinstance(profile, dict):
                continue
            if not bool(profile.get("is_date")):
                continue
            physical = str(profile.get("column_name") or "").strip()
            if self._is_safe_identifier(physical):
                return physical
        for item in list(context.get("columns") or []):
            if not isinstance(item, dict):
                continue
            logical = str(item.get("nombre_columna_logico") or "").strip().lower()
            physical = str(item.get("column_name") or "").strip()
            if any(token in logical for token in ("fecha", "periodo", "dia")) and self._is_safe_identifier(physical):
                return physical
        for name in list(context.get("allowed_columns") or []):
            clean = str(name or "").strip()
            if any(token in clean.lower() for token in ("fecha", "periodo")) and self._is_safe_identifier(clean):
                return clean
        return ""

    def _resolve_entity_column(self, *, context: dict[str, Any]) -> str:
        for profile in list(context.get("column_profiles") or []):
            if not isinstance(profile, dict):
                continue
            if not bool(profile.get("is_identifier")):
                continue
            physical = str(profile.get("column_name") or "").strip()
            if self._is_safe_identifier(physical):
                return physical
        for item in list(context.get("columns") or []):
            if not isinstance(item, dict):
                continue
            logical = str(item.get("nombre_columna_logico") or "").strip().lower()
            physical = str(item.get("column_name") or "").strip()
            if ("cedula" in logical or "identificacion" in logical) and self._is_safe_identifier(physical):
                return physical
            if physical.lower() == "cedula":
                return physical
        return "cedula"

    def _resolve_status_column(self, *, context: dict[str, Any]) -> str:
        for profile in list(context.get("column_profiles") or []):
            if not isinstance(profile, dict):
                continue
            allowed = list(profile.get("allowed_values") or [])
            if not allowed:
                continue
            if {"ACTIVO", "INACTIVO"} & {str(item or "").strip().upper() for item in allowed}:
                physical = str(profile.get("column_name") or "").strip()
                if self._is_safe_identifier(physical):
                    return physical
        preferred = ("estado", "status", "activo", "is_active", "estado_empleado")
        for item in list(context.get("columns") or []):
            if not isinstance(item, dict):
                continue
            physical = str(item.get("column_name") or "").strip()
            if physical.lower() in preferred and self._is_safe_identifier(physical):
                return physical
        return ""

    def _resolve_group_column(self, *, resolved_query: ResolvedQuerySpec, context: dict[str, Any]) -> str:
        requested = [str(item).strip().lower() for item in list(resolved_query.intent.group_by or [])]
        if not requested:
            return ""
        profile_by_logical: dict[str, str] = {}
        for profile in list(context.get("column_profiles") or []):
            if not isinstance(profile, dict):
                continue
            logical = str(profile.get("logical_name") or "").strip().lower()
            physical = str(profile.get("column_name") or "").strip()
            if not logical or not physical:
                continue
            if not bool(profile.get("supports_group_by") or profile.get("supports_dimension")):
                continue
            profile_by_logical[logical] = physical
        aliases = dict(context.get("aliases") or {})
        columns = {str(item.get("column_name") or "").strip().lower(): str(item.get("column_name") or "").strip() for item in list(context.get("columns") or []) if isinstance(item, dict)}
        for item in requested:
            mapped = str(aliases.get(item, item)).strip().lower()
            if mapped in profile_by_logical and self._is_safe_identifier(profile_by_logical[mapped]):
                return profile_by_logical[mapped]
            if mapped in columns and self._is_safe_identifier(columns[mapped]):
                return columns[mapped]
            if self._is_safe_identifier(mapped):
                return mapped
        return ""

    @staticmethod
    def _resolve_detail_columns(*, context: dict[str, Any]) -> list[str]:
        preferred = (
            "cedula",
            "nombre",
            "apellido",
            "nombre_completo",
            "fecha_ausentismo",
            "fecha_edit",
            "ausentismo",
            "justificacion",
            "supervisor",
            "area",
            "cargo",
            "carpeta",
        )
        existing: list[str] = []
        column_names = {str(item.get("column_name") or "").strip().lower(): str(item.get("column_name") or "").strip() for item in list(context.get("columns") or []) if isinstance(item, dict)}
        for key in preferred:
            if key in column_names:
                existing.append(column_names[key])
        if existing:
            return existing[:12]
        fallback = [str(item).strip() for item in list(context.get("allowed_columns") or []) if str(item).strip()]
        return fallback[:8] or ["*"]

    def _detect_missing_context(self, *, resolved_query: ResolvedQuerySpec) -> list[str]:
        missing: list[str] = []
        if not list((resolved_query.semantic_context or {}).get("tables") or []):
            missing.append("tablas_registradas_del_dominio")
        if str(resolved_query.intent.template_id or "").strip().lower() == "detail_by_entity_and_period":
            filters = dict(resolved_query.normalized_filters or {})
            if not any(
                str(filters.get(key) or "").strip()
                for key in ("cedula", "movil", "codigo_sap", "search")
            ):
                missing.append("identificador_empleado")
        period = dict(resolved_query.normalized_period or {})
        if not period.get("start_date") or not period.get("end_date"):
            missing.append("periodo_consulta")
        domain_code = str(resolved_query.intent.domain_code or "").strip().lower()
        if domain_code in {"empleados", "rrhh"}:
            temporal_scope = self._extract_temporal_scope(resolved_query=resolved_query)
            if bool(temporal_scope.get("ambiguous")):
                reason = str(temporal_scope.get("reason") or "temporal_scope_ambiguous")
                missing.append(f"temporal_binding:{reason}")
        return missing

    @staticmethod
    def _extract_temporal_scope(*, resolved_query: ResolvedQuerySpec) -> dict[str, Any]:
        context = dict(resolved_query.semantic_context or {})
        direct_scope = dict(context.get("temporal_scope") or {})
        if direct_scope:
            return direct_scope
        resolved_semantic = dict(context.get("resolved_semantic") or {})
        return dict(resolved_semantic.get("temporal_scope") or {})

    def _is_capability_rollout_enabled(self, capability_id: str) -> bool:
        definition = self.catalog.get(capability_id)
        if definition is None or not definition.rollout_flag:
            return definition is not None
        required = [
            str(token).strip()
            for token in str(definition.rollout_flag or "").replace(",", "|").split("|")
            if str(token).strip()
        ]
        if not required:
            return True
        for name in required:
            raw = str(os.getenv(name, "0") or "").strip().lower()
            if raw not in {"1", "true", "yes", "on"}:
                return False
        return True

    @staticmethod
    def _max_sql_limit() -> int:
        raw = str(os.getenv("IA_DEV_QUERY_SQL_ASSISTED_MAX_LIMIT", "500") or "500").strip()
        try:
            value = int(raw)
        except Exception:
            value = 500
        return max(1, min(value, 5000))

    def _build_sql_response(
        self,
        *,
        run_context: RunContext,
        resolved_query: ResolvedQuerySpec,
        execution_plan: QueryExecutionPlan,
        sql_query: str,
        rows: list[dict[str, Any]],
        columns: list[str],
        duration_ms: int,
        db_alias: str,
    ) -> dict[str, Any]:
        template_id = str(resolved_query.intent.template_id or "").strip().lower()
        kpis: dict[str, Any] = {}
        if rows and template_id.startswith("count_"):
            first = rows[0]
            numeric_values = [value for value in first.values() if isinstance(value, (int, float))]
            if numeric_values:
                kpis["total"] = int(numeric_values[0])
        if not kpis:
            kpis["rowcount"] = int(len(rows))

        period = dict(resolved_query.normalized_period or {})
        reply = (
            f"Consulta analitica ejecutada en modo SQL asistido restringido para {resolved_query.intent.domain_code}: "
            f"{len(rows)} filas."
        )
        if period.get("start_date") and period.get("end_date"):
            reply = (
                f"Consulta analitica ejecutada en modo SQL asistido restringido para {resolved_query.intent.domain_code} "
                f"en el periodo {period.get('start_date')} al {period.get('end_date')}: {len(rows)} filas."
            )
        return {
            "session_id": str(run_context.session_id or ""),
            "reply": reply,
            "orchestrator": {
                "intent": str(resolved_query.intent.operation or "query"),
                "domain": str(resolved_query.intent.domain_code or ""),
                "selected_agent": "analista_agent",
                "classifier_source": "query_intelligence_sql_assisted",
                "needs_database": True,
                "output_mode": "table" if rows else "summary",
                "used_tools": ["query_sql_assisted_executor"],
            },
            "data": {
                "kpis": kpis,
                "series": [],
                "labels": [],
                "insights": [
                    "Resultado obtenido con SQL asistido restringido (solo lectura).",
                ],
                "table": {
                    "columns": list(columns or []),
                    "rows": list(rows or []),
                    "rowcount": len(rows),
                },
            },
            "actions": [],
            "data_sources": {
                "query_intelligence": {
                    "ok": True,
                    "strategy": execution_plan.strategy,
                    "query": sql_query,
                    "db_alias": db_alias,
                }
            },
            "trace": [
                {
                    "phase": "query_intelligence_execution",
                    "status": "ok",
                    "at": datetime.now(timezone.utc).isoformat(),
                    "detail": {
                        "execution_plan": execution_plan.as_dict(),
                        "duration_ms": duration_ms,
                        "rowcount": len(rows),
                    },
                    "active_nodes": ["q", "gpt", "route", "sql", "result"],
                }
            ],
            "memory": {
                "used_messages": 0,
                "capacity_messages": 20,
                "usage_ratio": 0.0,
                "trim_events": 0,
                "saturated": False,
            },
            "observability": {
                "enabled": True,
                "duration_ms": int(duration_ms),
                "tool_latencies_ms": {"query_sql_assisted_executor": int(duration_ms)},
                "tokens_in": 0,
                "tokens_out": 0,
                "estimated_cost_usd": 0.0,
            },
            "active_nodes": ["q", "gpt", "route", "sql", "result"],
        }

    @classmethod
    def _is_safe_identifier(cls, value: str) -> bool:
        return bool(cls.SAFE_IDENTIFIER_RE.match(str(value or "").strip()))

    @staticmethod
    def _escape_literal(value: str) -> str:
        return str(value or "").replace("'", "''")

    @staticmethod
    def _record_event(*, observability, event_type: str, source: str, meta: dict[str, Any]) -> None:
        if observability is None or not hasattr(observability, "record_event"):
            return
        observability.record_event(
            event_type=event_type,
            source=source,
            meta=dict(meta or {}),
        )
