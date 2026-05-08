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
from apps.ia_dev.application.semantic.join_aware_sql_service import JoinAwarePilotSqlService


class QueryExecutionPlanner:
    SAFE_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9_\.]+$")
    TRAILING_LIMIT_RE = re.compile(r"\s+LIMIT\s+(\d+)\s*;?\s*$", re.IGNORECASE)
    CLEANUP_PHASE = "phase_7"
    PILOT_PHASE = "phase_9"
    ANALYTICS_ROUTER_DOMAINS = {"ausentismo", "attendance", "empleados", "rrhh"}
    COVERED_ANALYTICS_DOMAINS = {"ausentismo", "attendance", "empleados", "rrhh"}
    MODERN_HANDLER_CAPABILITY_PREFIXES = ("empleados.",)
    PRODUCTIVE_PILOT_DOMAINS = {"ausentismo", "attendance", "empleados", "rrhh"}

    def __init__(
        self,
        *,
        catalog: CapabilityCatalog | None = None,
        query_policy: QueryExecutionPolicy | None = None,
        join_aware_sql_service: JoinAwarePilotSqlService | None = None,
    ):
        self.catalog = catalog or CapabilityCatalog()
        self.query_policy = query_policy or QueryExecutionPolicy()
        self.join_aware_sql_service = join_aware_sql_service or JoinAwarePilotSqlService()

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
        raw_query_fallback_meta = self._resolve_raw_query_fallback_metadata(
            domain_code=domain_code,
            template_id=template_id,
            resolved_query=resolved_query,
        )
        capability_available = bool(capability_id and self._is_capability_rollout_enabled(capability_id))
        pilot_analytics_candidate = self.join_aware_sql_service.should_handle(
            resolved_query=resolved_query
        )
        analytics_router_metadata = self._build_analytics_router_metadata(
            domain_code=domain_code,
            capability_id=capability_id,
            pilot_analytics_candidate=pilot_analytics_candidate,
            decision="legacy",
        )
        sql_policy = self.query_policy.evaluate_sql_assisted(
            run_context=run_context,
            resolved_query=resolved_query,
        )
        sql_reason = ""
        sql_metadata: dict[str, Any] = {}
        if sql_policy.allowed:
            sql_query, sql_reason, sql_metadata = self._build_sql_query(resolved_query=resolved_query)
            if sql_query:
                validation = self.query_policy.validate_sql_query(
                    query=sql_query,
                    allowed_tables=list((resolved_query.semantic_context or {}).get("allowed_tables") or []),
                    allowed_columns=list((resolved_query.semantic_context or {}).get("allowed_columns") or []),
                    allowed_relations=[
                        str(item.get("join_sql") or "").strip()
                        for item in list(((resolved_query.semantic_context or {}).get("dictionary") or {}).get("relations") or [])
                        if isinstance(item, dict) and str(item.get("join_sql") or "").strip()
                    ],
                    declared_columns=list((sql_metadata or {}).get("physical_columns_used") or []),
                    declared_relations=list((sql_metadata or {}).get("relations_used") or []),
                    max_limit=self._max_sql_limit(),
                )
                if validation.allowed:
                    effective_constraints = dict(constraints or {})
                    if str((sql_metadata or {}).get("metric_used") or "") == "certificado_alturas_vigencia":
                        effective_constraints["group_by"] = []
                        effective_constraints["result_shape"] = "kpi"
                        effective_constraints["operation"] = "count"
                        effective_constraints["chart_requested"] = False
                    return QueryExecutionPlan(
                        strategy="sql_assisted",
                        reason=sql_reason,
                        domain_code=domain_code,
                        sql_query=sql_query,
                        constraints=effective_constraints,
                        policy={
                            "allowed": True,
                            "reason": validation.reason,
                            "metadata": validation.metadata,
                        },
                        metadata={
                            "template_id": template_id,
                            "operation": resolved_query.intent.operation,
                            "capability_id": capability_id,
                            **dict(sql_metadata or {}),
                            **raw_query_fallback_meta,
                            **self._build_analytics_router_metadata(
                                domain_code=domain_code,
                                capability_id=capability_id,
                                pilot_analytics_candidate=pilot_analytics_candidate,
                                decision="join_aware_sql",
                            ),
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
                    metadata={
                        "template_id": template_id,
                        **raw_query_fallback_meta,
                        **dict(sql_metadata or {}),
                        **analytics_router_metadata,
                    },
                )
            if self._cleanup_blocks_legacy_analytics_fallback(
                resolved_query=resolved_query,
                pilot_analytics_candidate=pilot_analytics_candidate,
            ):
                runtime_only_reason = self._map_runtime_only_fallback_reason(
                    reason=sql_reason or "compiler_not_applicable"
                )
                cleanup_metadata = self._build_cleanup_metadata(
                    runtime_only_fallback_reason=runtime_only_reason,
                    legacy_fallback_target=capability_id,
                    sql_reason=sql_reason,
                    domain_code=domain_code,
                    pilot_analytics_candidate=pilot_analytics_candidate,
                )
                return QueryExecutionPlan(
                    strategy="fallback",
                    reason=runtime_only_reason,
                    domain_code=domain_code,
                    capability_id=capability_id,
                    constraints=constraints,
                    policy={
                        "allowed": False,
                        "reason": "runtime_only_fallback_phase_7",
                        "metadata": cleanup_metadata,
                    },
                    metadata={
                        "template_id": template_id,
                        **raw_query_fallback_meta,
                        **dict(sql_metadata or {}),
                        **cleanup_metadata,
                    },
                )

        if capability_available:
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
                    **raw_query_fallback_meta,
                    **self._build_analytics_router_metadata(
                        domain_code=domain_code,
                        capability_id=capability_id,
                        pilot_analytics_candidate=pilot_analytics_candidate,
                        decision="handler_modern" if self._is_modern_handler_capability(capability_id) else "legacy",
                    ),
                },
            )

        # General-domain requests are conversational and should continue to legacy/OpenAI reply
        # generation instead of triggering context-collection flows intended for DB analytics.
        if domain_code == "":
            return QueryExecutionPlan(
                strategy="fallback",
                reason="no_domain_resolved",
                domain_code="general",
                capability_id=capability_id,
                constraints=constraints,
                policy={"allowed": False, "reason": "fallback_legacy"},
                metadata={"template_id": template_id, **raw_query_fallback_meta, **analytics_router_metadata},
            )

        if domain_code == "general":
            return QueryExecutionPlan(
                strategy="fallback",
                reason="general_domain_conversational_fallback",
                domain_code=domain_code or "general",
                capability_id=capability_id,
                constraints=constraints,
                policy={"allowed": False, "reason": "fallback_legacy"},
                metadata={"template_id": template_id, **raw_query_fallback_meta, **analytics_router_metadata},
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
                metadata={"template_id": template_id, **raw_query_fallback_meta, **analytics_router_metadata},
            )

        return QueryExecutionPlan(
            strategy="fallback",
            reason=self._normalize_fallback_reason(
                domain_code=domain_code,
                capability_id=capability_id,
                capability_available=capability_available,
                sql_policy_allowed=sql_policy.allowed,
                sql_reason=sql_reason,
            ),
            domain_code=domain_code,
            capability_id=capability_id,
            constraints=constraints,
            policy={"allowed": False, "reason": "fallback_legacy"},
            metadata={
                "template_id": template_id,
                **({"sql_reason": sql_reason} if sql_reason else {}),
                **raw_query_fallback_meta,
                **dict(sql_metadata or {}),
                **analytics_router_metadata,
            },
        )

    def _normalize_fallback_reason(
        self,
        *,
        domain_code: str,
        capability_id: str | None,
        capability_available: bool,
        sql_policy_allowed: bool,
        sql_reason: str,
    ) -> str:
        normalized_domain = str(domain_code or "").strip().lower()
        normalized_sql_reason = str(sql_reason or "").strip().lower()
        if not normalized_domain:
            return "no_domain_resolved"
        if normalized_sql_reason:
            mapped = self._map_sql_reason_to_fallback(reason=normalized_sql_reason)
            if mapped:
                return mapped
        if capability_id and not capability_available:
            return "handler_not_available"
        if sql_policy_allowed:
            return "unsafe_sql_plan"
        return "compiler_not_applicable"

    @staticmethod
    def _flag_enabled(name: str, default: str = "0") -> bool:
        raw = str(os.getenv(name, default) or "").strip().lower()
        return raw in {"1", "true", "yes", "on"}

    def _cleanup_blocks_legacy_analytics_fallback(
        self,
        *,
        resolved_query: ResolvedQuerySpec,
        pilot_analytics_candidate: bool,
    ) -> bool:
        domain_code = str(resolved_query.intent.domain_code or "").strip().lower()
        legacy_fallback_disabled = self._flag_enabled(
            "IA_DEV_DISABLE_LEGACY_ANALYTICS_FALLBACK", "0"
        ) or self._productive_pilot_enabled_for_domain(domain_code=domain_code)
        if not legacy_fallback_disabled:
            return False
        return self._is_covered_analytics_query(
            resolved_query=resolved_query,
            pilot_analytics_candidate=pilot_analytics_candidate,
        )

    @classmethod
    def _productive_pilot_enabled_for_domain(cls, *, domain_code: str) -> bool:
        normalized_domain = str(domain_code or "").strip().lower()
        if normalized_domain not in cls.PRODUCTIVE_PILOT_DOMAINS:
            return False
        return cls._flag_enabled("IA_DEV_ATTENDANCE_EMPLOYEES_PILOT_ENABLED", "0")

    def _build_cleanup_metadata(
        self,
        *,
        runtime_only_fallback_reason: str,
        legacy_fallback_target: str | None,
        sql_reason: str,
        domain_code: str = "ausentismo",
        pilot_analytics_candidate: bool = True,
    ) -> dict[str, Any]:
        metadata = self._build_analytics_router_metadata(
            domain_code=domain_code,
            capability_id=legacy_fallback_target,
            pilot_analytics_candidate=pilot_analytics_candidate,
            decision="runtime_only_fallback",
        )
        metadata.update(
            {
            "legacy_analytics_fallback_disabled": True,
            "blocked_legacy_fallback": True,
            "blocked_tool_ausentismo_service": True,
            "blocked_run_legacy_for_analytics": True,
            "runtime_only_fallback_reason": str(runtime_only_fallback_reason or ""),
            "cleanup_phase": self.CLEANUP_PHASE,
            "legacy_fallback_target": str(legacy_fallback_target or "tool_ausentismo_service"),
            "sql_reason": str(sql_reason or ""),
            "fallback_reason": str(sql_reason or runtime_only_fallback_reason or "unsafe_sql_plan"),
        }
        )
        return metadata

    @classmethod
    def _is_modern_handler_capability(cls, capability_id: str | None) -> bool:
        capability = str(capability_id or "").strip().lower()
        if not capability:
            return False
        return capability.startswith(cls.MODERN_HANDLER_CAPABILITY_PREFIXES)

    @classmethod
    def _is_covered_analytics_query(
        cls,
        *,
        resolved_query: ResolvedQuerySpec,
        pilot_analytics_candidate: bool,
    ) -> bool:
        if not pilot_analytics_candidate:
            return False
        domain_code = str(resolved_query.intent.domain_code or "").strip().lower()
        return domain_code in cls.COVERED_ANALYTICS_DOMAINS

    @classmethod
    def _build_analytics_router_metadata(
        cls,
        *,
        domain_code: str,
        capability_id: str | None,
        pilot_analytics_candidate: bool,
        decision: str,
    ) -> dict[str, Any]:
        normalized_domain = str(domain_code or "").strip().lower()
        normalized_decision = str(decision or "legacy").strip().lower() or "legacy"
        if normalized_domain not in cls.ANALYTICS_ROUTER_DOMAINS:
            return {}
        isolated = bool(
            normalized_decision in {"join_aware_sql", "handler_modern", "runtime_only_fallback"}
            and (
                pilot_analytics_candidate
                or cls._is_modern_handler_capability(capability_id)
                or normalized_decision == "handler_modern"
            )
        )
        metadata = {
            "analytics_router_decision": normalized_decision,
            "legacy_analytics_isolated": isolated,
        }
        if isolated:
            metadata["cleanup_phase"] = cls.CLEANUP_PHASE
        return metadata

    @classmethod
    def _map_runtime_only_fallback_reason(cls, *, reason: str) -> str:
        normalized = str(reason or "").strip().lower()
        if not normalized:
            return "unsafe_sql_plan"
        if normalized in {"no_metric_column_declared", "unsupported_metric"}:
            return "unsupported_metric"
        if normalized in {"no_allowed_dimension", "max_dimensions_exceeded", "unsupported_dimension"}:
            return "unsupported_dimension"
        if "relation" in normalized:
            return "missing_dictionary_relation"
        if any(
            token in normalized
            for token in (
                "column",
                "dimension_missing_or_unsafe",
                "identifier_missing_or_unsafe",
                "missing_status_column",
                "missing_group_column",
                "missing_date_column",
            )
        ):
            return "missing_dictionary_column"
        if "actionable" in normalized:
            return "no_actionable_insight"
        return "unsafe_sql_plan"

    @staticmethod
    def _map_sql_reason_to_fallback(*, reason: str) -> str:
        normalized = str(reason or "").strip().lower()
        if not normalized:
            return ""
        if normalized.startswith("sql_rejected:"):
            validation_reason = normalized.split(":", 1)[1]
            if "unregistered_relation" in validation_reason:
                return "no_declared_relation"
            if "unregistered_column" in validation_reason:
                return "no_allowed_columns"
            return "unsafe_sql_plan"
        if normalized == "no_metric_column_declared":
            return "no_metric_column_declared"
        if normalized == "no_allowed_dimension":
            return "no_allowed_dimension"
        if normalized == "max_dimensions_exceeded":
            return "max_dimensions_exceeded"
        if "relation" in normalized:
            return "no_declared_relation"
        if any(
            token in normalized
            for token in (
                "dimension_missing_or_unsafe",
                "identifier_missing_or_unsafe",
                "missing_status_column",
                "missing_group_column",
                "missing_date_column",
            )
        ):
            return "no_allowed_columns"
        if any(
            token in normalized
            for token in (
                "tables_missing",
                "missing_primary_table",
                "template_not_supported",
            )
        ):
            return "compiler_not_applicable"
        return "unsafe_sql_plan"

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
            result_metadata = self._resolve_sql_result_metadata(
                db_alias=db_alias,
                sql_query=sql_query,
                returned_records=len(rows_payload),
                execution_plan=execution_plan,
            )
            response = self._build_sql_response(
                run_context=run_context,
                resolved_query=resolved_query,
                execution_plan=execution_plan,
                sql_query=sql_query,
                rows=rows_payload,
                columns=columns,
                duration_ms=duration_ms,
                db_alias=db_alias,
                result_metadata=result_metadata,
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
                    "total_records": int(result_metadata.get("total_records") or len(rows_payload)),
                    "returned_records": int(result_metadata.get("returned_records") or len(rows_payload)),
                    "truncated": bool(result_metadata.get("truncated")),
                    "limit": int(result_metadata.get("limit") or 0),
                    "query": sql_query,
                    "pilot_enabled": self._productive_pilot_enabled_for_domain(
                        domain_code=str(resolved_query.intent.domain_code or "")
                    ),
                    "pilot_mode": "productive_pilot"
                    if self._productive_pilot_enabled_for_domain(
                        domain_code=str(resolved_query.intent.domain_code or "")
                    )
                    else "",
                    "pilot_phase": self.PILOT_PHASE,
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
                    "pilot_enabled": self._productive_pilot_enabled_for_domain(
                        domain_code=str(resolved_query.intent.domain_code or "")
                    ),
                    "pilot_mode": "productive_pilot"
                    if self._productive_pilot_enabled_for_domain(
                        domain_code=str(resolved_query.intent.domain_code or "")
                    )
                    else "",
                    "pilot_phase": self.PILOT_PHASE,
                },
            )
            return {"ok": False, "error": f"sql_execution_error:{exc}"}

    def _resolve_sql_result_metadata(
        self,
        *,
        db_alias: str,
        sql_query: str,
        returned_records: int,
        execution_plan: QueryExecutionPlan,
    ) -> dict[str, Any]:
        limit = self._extract_trailing_limit(sql_query)
        result_shape = str((execution_plan.constraints or {}).get("result_shape") or "").strip().lower()
        aggregation = str((execution_plan.metadata or {}).get("aggregation_used") or "").strip().lower()
        should_count_total = bool(
            limit
            and (
                result_shape in {"table", "list", "detail"}
                or aggregation in {"list", "detail"}
            )
            and aggregation in {"list", "detail", ""}
        )
        total_records = int(returned_records)
        count_query = ""
        count_error = ""
        if should_count_total:
            count_query = self._build_limited_detail_count_query(sql_query=sql_query)
            if count_query:
                try:
                    with connections[db_alias].cursor() as cursor:
                        cursor.execute(count_query)
                        row = cursor.fetchone()
                    total_records = int((row or [returned_records])[0] or 0)
                except Exception as exc:
                    count_error = str(exc)
                    total_records = int(returned_records)

        return {
            "total_records": int(total_records),
            "returned_records": int(returned_records),
            "truncated": bool(limit and total_records > returned_records),
            "limit": int(limit or 0),
            "count_query": count_query,
            "count_error": count_error,
        }

    @classmethod
    def _extract_trailing_limit(cls, sql_query: str) -> int:
        match = cls.TRAILING_LIMIT_RE.search(str(sql_query or "").strip())
        if not match:
            return 0
        try:
            return max(0, int(match.group(1)))
        except Exception:
            return 0

    @classmethod
    def _build_limited_detail_count_query(cls, *, sql_query: str) -> str:
        base_query = cls.TRAILING_LIMIT_RE.sub("", str(sql_query or "").strip()).strip().rstrip(";").strip()
        if not base_query:
            return ""
        return f"SELECT COUNT(*) AS total_records FROM ({base_query}) AS sql_assisted_total LIMIT 1"

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
            metrics = [str(item).strip().lower() for item in list(resolved_query.intent.metrics or [])]
            group_by = [str(item).strip().lower() for item in list(resolved_query.intent.group_by or []) if str(item).strip()]
            status_value = self._resolve_status_filter(filters=filters)
            has_employee_identifier = bool(
                self._first_filter_value(
                    filters=filters,
                    keys=("cedula", "cedula_empleado", "identificacion", "documento", "id_empleado"),
                )
                or str(filters.get("movil") or "").strip()
                or str(filters.get("codigo_sap") or "").strip()
                or str(filters.get("search") or "").strip()
            )
            has_employee_detail_filter = self._has_employee_detail_filter(filters=filters)
            temporal_scope = self._extract_temporal_scope(resolved_query=resolved_query)
            has_temporal_scope = bool(
                temporal_scope.get("column_hint")
                and temporal_scope.get("start_date")
                and temporal_scope.get("end_date")
                and not bool(temporal_scope.get("ambiguous"))
            )
            if self._is_employee_population_summary_request(
                filters=filters,
                group_by=group_by,
                status_value=status_value,
                template_id=template_id,
                operation=operation,
                has_employee_identifier=has_employee_identifier,
                has_employee_detail_filter=has_employee_detail_filter,
            ):
                return "empleados.count.active.v1"
            if "turnover_rate" in metrics:
                return "empleados.count.active.v1"
            if (template_id == "detail_by_entity_and_period" or operation == "detail") and (
                has_employee_identifier or has_employee_detail_filter
            ):
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
        if str(resolved_query.intent.domain_code or "").strip().lower() in {"empleados", "rrhh"} and self._is_employee_population_summary_request(
            filters=filters,
            group_by=group_by,
            status_value=status_value,
            template_id=str(resolved_query.intent.template_id or "").strip().lower(),
            operation=operation,
            has_employee_identifier=bool(
                self._first_filter_value(
                    filters=filters,
                    keys=("cedula", "cedula_empleado", "identificacion", "documento", "id_empleado"),
                )
                or str(filters.get("movil") or "").strip()
                or str(filters.get("codigo_sap") or "").strip()
                or str(filters.get("search") or "").strip()
            ),
            has_employee_detail_filter=self._has_employee_detail_filter(filters=filters),
        ):
            operation = "aggregate" if group_by else "count"
        result_shape = "summary"
        if group_by:
            result_shape = "table"
        elif operation in {"detail"}:
            result_shape = "table"
        elif operation in {"aggregate", "trend", "compare"}:
            result_shape = "table"
        elif operation == "count":
            result_shape = "kpi"

        cedula = self._first_filter_value(
            filters=filters,
            keys=("cedula", "cedula_empleado", "identificacion", "documento", "id_empleado"),
        )
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
    def _is_employee_population_summary_request(
        *,
        filters: dict[str, Any],
        group_by: list[str],
        status_value: str,
        template_id: str,
        operation: str,
        has_employee_identifier: bool,
        has_employee_detail_filter: bool,
    ) -> bool:
        if status_value not in {"ACTIVO", "INACTIVO"}:
            return False
        if has_employee_identifier or has_employee_detail_filter:
            return False
        if any(str((filters or {}).get(key) or "").strip() for key in ("fnacimiento_month", "birth_month", "month_of_birth")):
            return False
        return bool(group_by) or str(template_id or "").strip().lower() in {
            "count_entities_by_status",
            "detail_by_entity_and_period",
        } or str(operation or "").strip().lower() == "detail"

    @staticmethod
    def _resolve_status_filter(*, filters: dict[str, Any]) -> str:
        for key in ("estado", "estado_empleado"):
            status = str((filters or {}).get(key) or "").strip().upper()
            if status in {"ACTIVO", "INACTIVO"}:
                return status
        return ""

    def _resolve_raw_query_fallback_metadata(
        self,
        *,
        domain_code: str,
        template_id: str,
        resolved_query: ResolvedQuerySpec,
    ) -> dict[str, Any]:
        normalized_domain = str(domain_code or "").strip().lower()
        metadata = {
            "raw_query_fallback_used": False,
            "raw_query_fallback_reason": "",
        }
        if normalized_domain not in {"ausentismo", "attendance"}:
            return metadata

        raw_query = str(resolved_query.intent.raw_query or "").strip().lower()
        if re.search(r"\b(reincid\w*|recurrent\w*|recurren\w*)\b", raw_query):
            metadata["raw_query_fallback_used"] = True
            metadata["raw_query_fallback_reason"] = "attendance_recurrence_capability_not_structured_yet"
            return metadata

        filters = dict(resolved_query.normalized_filters or {})
        group_by = [str(item).strip().lower() for item in list(resolved_query.intent.group_by or []) if str(item).strip()]
        has_attendance_reason = bool(
            str(filters.get("justificacion") or "").strip()
            or str(filters.get("motivo_justificacion") or "").strip()
        )
        has_people_scope = bool(
            re.search(r"\b(emplead\w*|colaborador(?:es)?|personal|persona(?:s)?)\b", raw_query)
        )
        asks_summary_count = bool(
            re.search(r"\b(cantidad|cuantos|cuantas|total|numero|resumen)\b", raw_query)
        )
        if (
            str(template_id or "").strip().lower() != "aggregate_by_group_and_period"
            and has_attendance_reason
            and has_people_scope
            and not group_by
            and not asks_summary_count
        ):
            metadata["raw_query_fallback_used"] = True
            metadata["raw_query_fallback_reason"] = "attendance_people_scope_detail_fallback"
        return metadata

    def _build_sql_query(self, *, resolved_query: ResolvedQuerySpec) -> tuple[str, str, dict[str, Any]]:
        pilot = self.join_aware_sql_service.compile(
            resolved_query=resolved_query,
            max_limit=self._max_sql_limit(),
        ) if self.join_aware_sql_service.should_handle(resolved_query=resolved_query) else {"ok": False}
        if bool(pilot.get("ok")):
            return (
                str(pilot.get("sql_query") or ""),
                str(pilot.get("reason") or "pilot_join_aware_sql"),
                dict(pilot.get("metadata") or {}),
            )

        template_id = str(resolved_query.intent.template_id or "").strip().lower()
        context = dict(resolved_query.semantic_context or {})
        table = self._resolve_primary_table(context=context)
        if not table:
            return "", "sql_missing_primary_table", {}
        if str(resolved_query.intent.domain_code or "").strip().lower() in {"empleados", "rrhh"}:
            employee_query, employee_reason, employee_metadata = self._build_employee_sql_query(
                resolved_query=resolved_query,
                context=context,
                table=table,
            )
            if employee_query:
                return employee_query, employee_reason, employee_metadata
            if employee_reason not in {"employee_sql_not_applicable", ""}:
                return "", employee_reason, employee_metadata

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
                return "", "sql_missing_status_column", {}
            where_parts = []
            if status_column and filters.get("estado"):
                where_parts.append(f"{status_column} = '{self._escape_literal(str(filters.get('estado') or ''))}'")
            where_sql = (" WHERE " + " AND ".join(where_parts)) if where_parts else ""
            query = f"SELECT COUNT(*) AS total_registros FROM {table}{where_sql} LIMIT 1"
            return query, "sql_count_entities_by_status", self._default_sql_metadata(
                table=table,
                columns=[status_column] if status_column else [],
            )

        if template_id == "count_records_by_period":
            if start_date and end_date and not date_column:
                return "", "sql_missing_date_column", {}
            where_parts = self._build_date_where(date_column=date_column, start_date=start_date, end_date=end_date)
            if entity_column and filters.get("cedula"):
                where_parts.append(f"{entity_column} = '{self._escape_literal(str(filters.get('cedula') or ''))}'")
            where_sql = (" WHERE " + " AND ".join(where_parts)) if where_parts else ""
            query = f"SELECT COUNT(*) AS total_registros FROM {table}{where_sql} LIMIT 1"
            return query, "sql_count_records_by_period", self._default_sql_metadata(
                table=table,
                columns=[date_column, entity_column],
            )

        if template_id == "detail_by_entity_and_period":
            if start_date and end_date and not date_column:
                return "", "sql_missing_date_column", {}
            select_columns = self._resolve_detail_columns(context=context)
            where_parts = self._build_date_where(date_column=date_column, start_date=start_date, end_date=end_date)
            if entity_column and filters.get("cedula"):
                where_parts.append(f"{entity_column} = '{self._escape_literal(str(filters.get('cedula') or ''))}'")
            where_sql = (" WHERE " + " AND ".join(where_parts)) if where_parts else ""
            order_sql = f" ORDER BY {date_column} DESC" if date_column else ""
            query = f"SELECT {', '.join(select_columns)} FROM {table}{where_sql}{order_sql} LIMIT {limit}"
            return query, "sql_detail_by_entity_and_period", self._default_sql_metadata(
                table=table,
                columns=[*select_columns, date_column, entity_column],
            )

        if template_id == "aggregate_by_group_and_period":
            if not group_column:
                return "", "sql_missing_group_column", {}
            if start_date and end_date and not date_column:
                return "", "sql_missing_date_column", {}
            where_parts = self._build_date_where(date_column=date_column, start_date=start_date, end_date=end_date)
            where_sql = (" WHERE " + " AND ".join(where_parts)) if where_parts else ""
            group_alias = str((resolved_query.intent.group_by or ["grupo"])[0] or "grupo").strip().lower() or "grupo"
            query = (
                f"SELECT {group_column} AS {group_alias}, COUNT(*) AS total_registros "
                f"FROM {table}{where_sql} "
                f"GROUP BY {group_column} ORDER BY total_registros DESC LIMIT {limit}"
            )
            return query, "sql_aggregate_by_group_and_period", self._default_sql_metadata(
                table=table,
                columns=[group_column, date_column],
            )

        if template_id == "trend_by_period":
            if not date_column:
                return "", "sql_missing_date_column", {}
            where_parts = self._build_date_where(date_column=date_column, start_date=start_date, end_date=end_date)
            where_sql = (" WHERE " + " AND ".join(where_parts)) if where_parts else ""
            query = (
                f"SELECT DATE({date_column}) AS periodo, COUNT(*) AS total_registros "
                f"FROM {table}{where_sql} GROUP BY DATE({date_column}) ORDER BY DATE({date_column}) ASC LIMIT {limit}"
            )
            return query, "sql_trend_by_period", self._default_sql_metadata(
                table=table,
                columns=[date_column],
            )

        return "", "sql_template_not_supported", {}

    def _build_employee_sql_query(
        self,
        *,
        resolved_query: ResolvedQuerySpec,
        context: dict[str, Any],
        table: str,
    ) -> tuple[str, str, dict[str, Any]]:
        filters = dict(resolved_query.normalized_filters or {})
        group_by = [str(item).strip().lower() for item in list(resolved_query.intent.group_by or []) if str(item).strip()]
        operation = str(resolved_query.intent.operation or "").strip().lower()
        template_id = str(resolved_query.intent.template_id or "").strip().lower()
        status_column = self._resolve_status_column(context=context)
        birthday_column = self._resolve_named_column(
            context=context,
            preferred_terms=("fecha_nacimiento", "fnacimiento", "birth_date"),
        )
        is_birthday_query = bool(
            birthday_column
            and (
                self._resolve_month_filter(filters=filters)
                or "birth_month" in group_by
                or str(((context.get("semantic_field_match") or {}).get("logical_name") or "")).strip().lower() == "fecha_nacimiento"
                or "birthday" in {
                    str(item or "").strip().lower()
                    for item in list(((context.get("resolved_semantic") or {}).get("field_match") or {}).get("business_concepts") or [])
                    if str(item or "").strip()
                }
            )
        )
        if is_birthday_query and not birthday_column:
            return "", "employee_birthday_column_missing", {}

        where_parts: list[str] = []
        month_value = self._resolve_month_filter(filters=filters)
        if month_value and birthday_column:
            where_parts.append(self._build_month_filter_sql(column=birthday_column, month_value=month_value))
        if status_column and self._resolve_status_filter(filters=filters):
            where_parts.append(
                f"{status_column} = '{self._escape_literal(self._resolve_status_filter(filters=filters))}'"
            )
        for logical_name in ("area", "cargo", "sede", "supervisor", "carpeta", "tipo_labor", "movil"):
            raw_value = filters.get(logical_name)
            if isinstance(raw_value, dict):
                continue
            value = str(raw_value or "").strip()
            if not value:
                continue
            physical = self._resolve_named_column(context=context, preferred_terms=(logical_name,))
            if physical:
                where_parts.append(f"{physical} = '{self._escape_literal(value)}'")

        detail_columns = self._resolve_employee_detail_columns(context=context)
        where_sql = (" WHERE " + " AND ".join(where_parts)) if where_parts else ""
        limit = self._max_sql_limit()
        used_columns = [birthday_column, status_column, *detail_columns]
        data_quality_query, data_quality_reason, data_quality_metadata = self._build_employee_data_quality_sql_query(
            resolved_query=resolved_query,
            context=context,
            table=table,
            detail_columns=detail_columns,
            base_where_parts=where_parts,
        )
        if data_quality_query:
            return data_quality_query, data_quality_reason, data_quality_metadata
        if data_quality_reason not in {"employee_data_quality_not_applicable", ""}:
            return "", data_quality_reason, data_quality_metadata
        certificate_query, certificate_reason, certificate_metadata = self._build_employee_certificate_heights_sql_query(
            resolved_query=resolved_query,
            context=context,
            table=table,
            status_column=status_column,
        )
        if certificate_query:
            return certificate_query, certificate_reason, certificate_metadata
        if certificate_reason not in {"employee_heights_certificate_not_applicable", ""}:
            return "", certificate_reason, certificate_metadata

        if template_id == "detail_by_entity_and_period" or operation == "detail":
            order_sql = ""
            if birthday_column and is_birthday_query:
                order_sql = f" ORDER BY MONTH({birthday_column}) ASC, DAY({birthday_column}) ASC"
            query = f"SELECT {', '.join(detail_columns)} FROM {table}{where_sql}{order_sql} LIMIT {limit}"
            return query, "employee_birthdays_detail", self._employee_sql_metadata(
                table=table,
                columns=used_columns,
                metric_used="employees",
                aggregation_used="list",
                dimensions_used=[],
                concept_field="fecha_nacimiento" if is_birthday_query else "employees",
            )

        if group_by or template_id == "aggregate_by_group_and_period" or operation in {"aggregate", "compare", "summary"}:
            group_dimension = self._resolve_employee_group_dimension(
                resolved_query=resolved_query,
                context=context,
            )
            if not group_dimension:
                return "", "employee_group_column_missing", {}
            group_sql = str(group_dimension.get("group_sql") or "")
            select_sql = str(group_dimension.get("select_sql") or "")
            dimension_aliases = [
                str(item or "").strip().lower()
                for item in list(group_dimension.get("dimension_aliases") or [])
                if str(item or "").strip()
            ] or [str(group_dimension.get("alias") or "grupo").strip().lower() or "grupo"]
            query = (
                f"SELECT {select_sql}, COUNT(*) AS total_registros "
                f"FROM {table}{where_sql} GROUP BY {group_sql} "
                f"ORDER BY total_registros DESC LIMIT {limit}"
            )
            return query, "employee_birthdays_aggregate", self._employee_sql_metadata(
                table=table,
                columns=[birthday_column, status_column, *list(group_dimension.get("physical_columns") or [])],
                metric_used="employees",
                aggregation_used="count",
                dimensions_used=dimension_aliases,
                concept_field="fecha_nacimiento" if is_birthday_query else "employees",
            )

        if template_id in {"count_records_by_period", "count_entities_by_status"} or operation == "count":
            query = f"SELECT COUNT(*) AS total_registros FROM {table}{where_sql} LIMIT 1"
            return query, "employee_birthdays_count", self._employee_sql_metadata(
                table=table,
                columns=[birthday_column, status_column],
                metric_used="employees",
                aggregation_used="count",
                dimensions_used=[],
                concept_field="fecha_nacimiento" if is_birthday_query else "employees",
            )

        return "", "employee_sql_not_applicable", {}

    def _build_employee_data_quality_sql_query(
        self,
        *,
        resolved_query: ResolvedQuerySpec,
        context: dict[str, Any],
        table: str,
        detail_columns: list[str],
        base_where_parts: list[str],
    ) -> tuple[str, str, dict[str, Any]]:
        filters = dict(resolved_query.normalized_filters or {})
        targets = self._resolve_data_quality_targets(filters=filters, context=context)
        if not targets:
            return "", "employee_data_quality_not_applicable", {}

        operation = str(resolved_query.intent.operation or "").strip().lower()
        template_id = str(resolved_query.intent.template_id or "").strip().lower()
        group_by = [str(item).strip().lower() for item in list(resolved_query.intent.group_by or []) if str(item).strip()]
        where_parts = list(base_where_parts or [])
        missing_clauses = [str(item.get("where_sql") or "").strip() for item in targets if str(item.get("where_sql") or "").strip()]
        if not missing_clauses:
            return "", "employee_data_quality_target_missing_sql", {}
        where_parts.append(f"({' OR '.join(missing_clauses)})")
        where_sql = " WHERE " + " AND ".join(where_parts)
        limit = self._max_sql_limit()

        target_selects = [
            str(item.get("select_sql") or "").strip()
            for item in targets
            if str(item.get("select_sql") or "").strip() and bool(item.get("include_in_detail_select"))
        ]
        select_columns = list(detail_columns or [])
        for select_sql in target_selects:
            if select_sql not in select_columns:
                select_columns.append(select_sql)
        select_columns = select_columns[:20]

        target_labels = [
            str(item.get("label") or item.get("logical_name") or "").strip()
            for item in targets
            if str(item.get("label") or item.get("logical_name") or "").strip()
        ]
        dimensions_used = list(group_by or [])
        extra_metadata = {
            "response_category": "data_quality",
            "data_quality_operator": "missing_or_incomplete",
            "data_quality_targets": [
                str(item.get("logical_name") or "").strip().lower()
                for item in targets
                if str(item.get("logical_name") or "").strip()
            ],
            "data_quality_target_operators": [
                str(item.get("operator") or "").strip().lower()
                for item in targets
                if str(item.get("operator") or "").strip()
            ],
            "data_quality_target_labels": target_labels,
            "insights": [
                "La consulta se resolvio como revision gobernada de datos faltantes/incompletos.",
            ],
        }
        used_columns = [
            *list(detail_columns or []),
            *[
                str(item.get("source_column") or "").strip()
                for item in targets
                if str(item.get("source_column") or "").strip()
            ],
        ]

        if group_by or template_id == "aggregate_by_group_and_period" or operation in {"aggregate", "compare", "summary"}:
            group_dimension = self._resolve_employee_group_dimension(
                resolved_query=resolved_query,
                context=context,
            )
            if not group_dimension:
                return "", "employee_group_column_missing", {}
            group_sql = str(group_dimension.get("group_sql") or "")
            select_sql = str(group_dimension.get("select_sql") or "")
            query = (
                f"SELECT {select_sql}, COUNT(*) AS total_registros "
                f"FROM {table}{where_sql} GROUP BY {group_sql} "
                f"ORDER BY total_registros DESC LIMIT {limit}"
            )
            dimensions_used = [
                str(item or "").strip().lower()
                for item in list(group_dimension.get("dimension_aliases") or group_by or [])
                if str(item or "").strip()
            ]
            return query, "employee_data_quality_aggregate", self._employee_sql_metadata(
                table=table,
                columns=[*used_columns, *list(group_dimension.get("physical_columns") or [])],
                metric_used="employee_data_quality",
                aggregation_used="count",
                dimensions_used=dimensions_used,
                concept_field="employee_data_quality",
                extra_metadata=extra_metadata,
            )

        if template_id in {"count_records_by_period", "count_entities_by_status"} or operation == "count":
            query = f"SELECT COUNT(*) AS total_registros FROM {table}{where_sql} LIMIT 1"
            return query, "employee_data_quality_count", self._employee_sql_metadata(
                table=table,
                columns=used_columns,
                metric_used="employee_data_quality",
                aggregation_used="count",
                dimensions_used=[],
                concept_field="employee_data_quality",
                extra_metadata=extra_metadata,
            )

        query = f"SELECT {', '.join(select_columns)} FROM {table}{where_sql} LIMIT {limit}"
        return query, "employee_data_quality_detail", self._employee_sql_metadata(
            table=table,
            columns=used_columns,
            metric_used="employee_data_quality",
            aggregation_used="list",
            dimensions_used=[],
            concept_field="employee_data_quality",
            extra_metadata=extra_metadata,
        )

    def _build_employee_certificate_heights_sql_query(
        self,
        *,
        resolved_query: ResolvedQuerySpec,
        context: dict[str, Any],
        table: str,
        status_column: str,
    ) -> tuple[str, str, dict[str, Any]]:
        operation = str(resolved_query.intent.operation or "").strip().lower()
        if operation not in {"count", "summary", "aggregate"}:
            return "", "employee_heights_certificate_not_applicable", {}

        field_match = dict((context.get("resolved_semantic") or {}).get("field_match") or {})
        if not field_match:
            field_match = dict(context.get("semantic_field_match") or {})
        semantic_role = str(field_match.get("semantic_role") or "").strip().lower()
        logical_name = str(field_match.get("logical_name") or "").strip().lower()
        certificate_filter_keys = {
            str(key or "").strip().lower()
            for key in dict(resolved_query.normalized_filters or {}).keys()
            if str(key or "").strip()
        }
        certificate_filter_detected = bool(
            certificate_filter_keys
            & {
                "certificado_alturas_fecha_emision",
                "certificado_alturas_fecha_vencimiento",
                "certificado_alturas_estado_vigencia",
            }
        )
        if (
            semantic_role != "heights_certificate_validity"
            and logical_name
            not in {
                "certificado_alturas_fecha_emision",
                "certificado_alturas_fecha_vencimiento",
                "certificado_alturas_estado_vigencia",
            }
            and not certificate_filter_detected
        ):
            return "", "employee_heights_certificate_not_applicable", {}

        required_rule_sets = (
            ("certificado_alturas_vigencia_18_meses", "certificado_alturas_vigencia_anual"),
            ("certificado_alturas_vencido",),
            ("certificado_alturas_proximo_vencer_45_dias", "certificado_alturas_proximo_vencer_30_dias"),
            ("personal_activo_operativo",),
        )
        missing_rules = [
            "/".join(rule_codes)
            for rule_codes in required_rule_sets
            if not any(self._dictionary_rule_declared(context=context, rule_code=code) for code in rule_codes)
        ]
        if missing_rules:
            return "", "employee_heights_certificate_rules_missing", {"missing_rule_codes": missing_rules}

        status_filter = self._resolve_status_filter(filters=dict(resolved_query.normalized_filters or {})) or "ACTIVO"
        if status_filter != "ACTIVO":
            return "", "employee_heights_certificate_requires_active_scope", {"requested_status": status_filter}
        tipo_labor_value = str((resolved_query.normalized_filters or {}).get("tipo_labor") or "").strip().upper()
        if tipo_labor_value and tipo_labor_value != "OPERATIVO":
            return "", "employee_heights_certificate_requires_operativo_scope", {"requested_tipo_labor": tipo_labor_value}
        tipo_labor_value = "OPERATIVO"

        tipo_labor_column = self._resolve_named_column(context=context, preferred_terms=("tipo_labor",))
        if not status_column:
            return "", "employee_heights_certificate_status_column_missing", {}
        if not tipo_labor_column:
            return "", "employee_heights_certificate_tipo_labor_column_missing", {}

        selected_table = self._resolve_table_for_required_columns(
            context=context,
            required_columns=("datos", "tipo_labor", "estado", "calturas"),
            preferred_table_name="cinco_base_de_personal",
        )
        if selected_table:
            table = selected_table

        source_profile = self._find_context_profile_for_table(
            context=context,
            table_ref=table,
            logical_names=("certificado_alturas_fecha_emision",),
            column_names=("datos",),
        )
        if not source_profile:
            source_profile = self._find_context_profile_for_table(
                context=context,
                table_ref=table,
                logical_names=("certificado_alturas_fecha_emision",),
                column_names=("calturas",),
            )
        if not source_profile:
            return "", "employee_heights_certificate_source_missing", {}
        if not str(source_profile.get("definicion_negocio") or "").strip():
            dictionary_source_profile = self._find_context_profile_for_table(
                context={"column_profiles": [], "dictionary": context.get("dictionary")},
                table_ref=table,
                logical_names=("certificado_alturas_fecha_emision",),
                column_names=("datos",),
            )
            if dictionary_source_profile:
                source_profile = dict(dictionary_source_profile)

        source_metadata = self._parse_semantic_tags(
            text=str(source_profile.get("definicion_negocio") or ""),
        )
        source_column = str(source_profile.get("column_name") or "").strip().lower()
        json_path = str(source_metadata.get("json_path") or "").strip()
        json_filter_tipo = str(source_metadata.get("json_filter_tipo") or "alturas").strip()
        fallback_column = str(source_metadata.get("fallback_column") or "calturas").strip().lower()
        try:
            vigencia_months = max(1, int(str(source_metadata.get("vigencia_months") or "18").strip()))
        except Exception:
            vigencia_months = 18
        try:
            expiry_warning_days = max(1, int(str(source_metadata.get("expiry_warning_days") or "45").strip()))
        except Exception:
            expiry_warning_days = 45

        where_sql = (
            f" WHERE e.{status_column} = 'ACTIVO' AND e.{tipo_labor_column} = 'OPERATIVO'"
        )
        if json_path and source_column == "datos":
            query = (
                "SELECT "
                f"SUM(CASE WHEN DATE_ADD(src.fecha_emision, INTERVAL {vigencia_months} MONTH) < CURRENT_DATE() THEN 1 ELSE 0 END) AS certificados_vencidos, "
                f"SUM(CASE WHEN DATE_ADD(src.fecha_emision, INTERVAL {vigencia_months} MONTH) BETWEEN CURRENT_DATE() AND DATE_ADD(CURRENT_DATE(), INTERVAL {expiry_warning_days} DAY) THEN 1 ELSE 0 END) AS certificados_proximos_vencer "
                "FROM ("
                f"SELECT CAST(jt.fecha AS DATE) AS fecha_emision FROM {table} AS e "
                f"JOIN JSON_TABLE(e.{source_column}, '{json_path}' COLUMNS("
                "tipo VARCHAR(50) PATH '$.tipo', "
                "fecha VARCHAR(20) PATH '$.fecha'"
                f")) AS jt ON jt.tipo = '{self._escape_literal(json_filter_tipo)}'"
                f"{where_sql}"
                ") AS src LIMIT 1"
            )
            return query, "employee_heights_certificate_summary_json", self._employee_sql_metadata(
                table=table,
                columns=[source_column, status_column, tipo_labor_column],
                metric_used="certificado_alturas_vigencia",
                aggregation_used="count_by_validity",
                dimensions_used=[],
                concept_field="certificado_alturas_fecha_emision",
                extra_metadata={
                    "json_path_used": json_path,
                    "json_filter_tipo": json_filter_tipo,
                    "vigencia_months": vigencia_months,
                    "expiry_warning_days": expiry_warning_days,
                    "source_mode": "json_path",
                    "declared_rule_source": "ai_dictionary.dd_reglas",
                    "physical_columns_used": sorted({source_column, status_column, tipo_labor_column}),
                },
            )

        fallback_profile = self._find_context_profile_for_table(
            context=context,
            table_ref=table,
            column_names=(fallback_column,),
        )
        if not fallback_profile:
            fallback_profile = self._find_context_profile_for_table(
                context=context,
                table_ref=table,
                column_names=("calturas",),
            )
        fallback_physical = str((fallback_profile or {}).get("column_name") or fallback_column).strip().lower()
        if fallback_physical != "calturas":
            return "", "employee_heights_certificate_json_path_missing", {"fallback_column": fallback_physical}
        query = (
            "SELECT "
            f"SUM(CASE WHEN DATE_ADD(DATE(e.calturas), INTERVAL {vigencia_months} MONTH) < CURRENT_DATE() THEN 1 ELSE 0 END) AS certificados_vencidos, "
            f"SUM(CASE WHEN DATE_ADD(DATE(e.calturas), INTERVAL {vigencia_months} MONTH) BETWEEN CURRENT_DATE() AND DATE_ADD(CURRENT_DATE(), INTERVAL {expiry_warning_days} DAY) THEN 1 ELSE 0 END) AS certificados_proximos_vencer "
            f"FROM {table} AS e"
            f"{where_sql} AND e.calturas IS NOT NULL LIMIT 1"
        )
        return query, "employee_heights_certificate_summary_fallback", self._employee_sql_metadata(
            table=table,
            columns=["calturas", status_column, tipo_labor_column],
            metric_used="certificado_alturas_vigencia",
            aggregation_used="count_by_validity",
            dimensions_used=[],
            concept_field="certificado_alturas_fecha_emision",
            extra_metadata={
                "source_mode": "fallback_calturas",
                "fallback_reason": "json_path_missing_in_ai_dictionary",
                "vigencia_months": vigencia_months,
                "expiry_warning_days": expiry_warning_days,
                "declared_rule_source": "ai_dictionary.dd_reglas",
                "physical_columns_used": sorted({"calturas", status_column, tipo_labor_column}),
            },
        )

    def _resolve_employee_group_dimension(self, *, resolved_query: ResolvedQuerySpec, context: dict[str, Any]) -> dict[str, Any]:
        group_by = [str(item).strip().lower() for item in list(resolved_query.intent.group_by or []) if str(item).strip()]
        if not group_by:
            return {}

        resolved_dimensions: list[dict[str, str]] = []
        for target in group_by:
            if target == "birth_month":
                birthday_column = self._resolve_named_column(
                    context=context,
                    preferred_terms=("fecha_nacimiento", "fnacimiento", "birth_date"),
                )
                if not birthday_column:
                    return {}
                resolved_dimensions.append(
                    {
                        "alias": "birth_month",
                        "group_sql": f"MONTH({birthday_column})",
                        "select_sql": f"MONTH({birthday_column}) AS birth_month",
                        "physical_column": birthday_column,
                    }
                )
                continue

            physical = self._resolve_group_column_by_target(
                target=target,
                resolved_query=resolved_query,
                context=context,
            )
            if not physical:
                return {}
            resolved_dimensions.append(
                {
                    "alias": target,
                    "group_sql": physical,
                    "select_sql": f"{physical} AS {target}",
                    "physical_column": physical,
                }
            )

        return {
            "alias": str(resolved_dimensions[0].get("alias") or "grupo"),
            "group_sql": ", ".join(str(item.get("group_sql") or "") for item in resolved_dimensions),
            "select_sql": ", ".join(str(item.get("select_sql") or "") for item in resolved_dimensions),
            "physical_columns": [
                str(item.get("physical_column") or "").strip()
                for item in resolved_dimensions
                if str(item.get("physical_column") or "").strip()
            ],
            "dimension_aliases": [
                str(item.get("alias") or "").strip().lower()
                for item in resolved_dimensions
                if str(item.get("alias") or "").strip()
            ],
        }

    def _resolve_named_column(self, *, context: dict[str, Any], preferred_terms: tuple[str, ...]) -> str:
        preferred = {str(item or "").strip().lower() for item in preferred_terms if str(item or "").strip()}
        for profile in list(context.get("column_profiles") or []):
            if not isinstance(profile, dict):
                continue
            logical = str(profile.get("logical_name") or "").strip().lower()
            column = str(profile.get("column_name") or "").strip()
            if logical in preferred or str(column).strip().lower() in preferred:
                if self._is_safe_identifier(column):
                    return column
        for item in list(context.get("columns") or []):
            if not isinstance(item, dict):
                continue
            logical = str(item.get("nombre_columna_logico") or "").strip().lower()
            column = str(item.get("column_name") or "").strip()
            if logical in preferred or str(column).strip().lower() in preferred:
                if self._is_safe_identifier(column):
                    return column
        return ""

    @staticmethod
    def _resolve_month_filter(*, filters: dict[str, Any]) -> str:
        for key in ("fnacimiento_month", "birth_month", "month_of_birth", "mes_cumpleanos"):
            value = str((filters or {}).get(key) or "").strip()
            if value:
                return value
        return ""

    @staticmethod
    def _build_month_filter_sql(*, column: str, month_value: str) -> str:
        return f"MONTH({column}) = {int(month_value)}"

    def _resolve_employee_detail_columns(self, *, context: dict[str, Any]) -> list[str]:
        preferred = (
            "cedula",
            "nombre",
            "apellido",
            "fnacimiento",
            "estado",
            "area",
            "cargo",
            "zona_nodo",
            "supervisor",
        )
        selected: list[str] = []
        for token in preferred:
            physical = self._resolve_named_column(context=context, preferred_terms=(token,))
            if physical and physical not in selected:
                selected.append(physical)
        return selected[:10] or self._resolve_detail_columns(context=context)

    def _resolve_data_quality_targets(
        self,
        *,
        filters: dict[str, Any],
        context: dict[str, Any],
    ) -> list[dict[str, Any]]:
        targets: list[dict[str, Any]] = []
        for logical_name, raw_value in dict(filters or {}).items():
            if not self._is_data_quality_filter_spec(raw_value):
                continue
            logical_target = str(logical_name or "").strip().lower()
            operator = self._normalize_data_quality_operator(raw_value)
            if logical_target == "documento_identidad":
                for document_side in ("documento_identidad_lado_a", "documento_identidad_lado_b"):
                    profile = self._find_context_profile(
                        context=context,
                        logical_names=(document_side,),
                    )
                    target = self._build_data_quality_target(
                        logical_name=document_side,
                        operator=operator,
                        profile=profile,
                        context=context,
                    )
                    if target:
                        targets.append(target)
                continue
            profile = self._find_context_profile(
                context=context,
                logical_names=(logical_target,),
            )
            target = self._build_data_quality_target(
                logical_name=logical_target,
                operator=operator,
                profile=profile,
                context=context,
            )
            if target:
                targets.append(target)
        return targets

    @staticmethod
    def _is_data_quality_filter_spec(value: Any) -> bool:
        if not isinstance(value, dict):
            return False
        operator = str(value.get("operator") or "").strip().lower()
        return operator in {
            "is_missing",
            "is_incomplete",
            "missing",
            "empty",
            "incomplete",
            "not_registered",
            "not_available",
            "no_tiene",
            "sin",
        }

    @staticmethod
    def _normalize_data_quality_operator(value: Any) -> str:
        if not isinstance(value, dict):
            return ""
        operator = str(value.get("operator") or "").strip().lower()
        if operator in {"is_incomplete", "incomplete"}:
            return "incomplete"
        if operator in {"empty"}:
            return "empty"
        if operator in {"not_registered"}:
            return "not_registered"
        if operator in {"not_available"}:
            return "not_available"
        if operator in {"no_tiene"}:
            return "no_tiene"
        if operator in {"sin"}:
            return "sin"
        return "missing"

    def _build_data_quality_target(
        self,
        *,
        logical_name: str,
        operator: str,
        profile: dict[str, Any] | None,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        if not profile:
            return {}
        definition = str(
            profile.get("definicion_negocio")
            or profile.get("definition")
            or profile.get("descripcion")
            or ""
        ).strip()
        semantic_tags = self._parse_semantic_tags(text=definition)
        source_column = str(profile.get("column_name") or "").strip().lower()
        if not source_column:
            return {}
        json_path = str(profile.get("json_path") or semantic_tags.get("json_path") or "").strip()
        privacy = str(profile.get("privacy") or semantic_tags.get("privacy") or "").strip().lower()
        empty_equivalent_values = self._normalize_semantic_list(
            profile.get("empty_equivalent_values") or semantic_tags.get("empty_equivalent_values")
        )
        fallback_fields = self._normalize_semantic_list(
            profile.get("missing_fallback_fields") or semantic_tags.get("missing_fallback_fields")
        )
        select_sql = ""
        where_sql = self._build_missingness_where_sql(
            source_column=source_column,
            json_path=json_path,
            empty_equivalent_values=empty_equivalent_values,
            fallback_fields=fallback_fields,
            context=context,
        )
        if not where_sql:
            return {}
        if json_path and privacy not in {"high"}:
            select_sql = (
                f"JSON_UNQUOTE(JSON_EXTRACT({source_column}, '{self._escape_literal(json_path)}')) "
                f"AS {str(logical_name).strip().lower()}"
            )
        return {
            "logical_name": str(logical_name or "").strip().lower(),
            "source_column": source_column,
            "select_sql": select_sql,
            "where_sql": where_sql,
            "label": self._data_quality_label(logical_name=str(logical_name or "").strip().lower()),
            "operator": str(operator or "missing"),
            "include_in_detail_select": False,
        }

    def _build_missingness_where_sql(
        self,
        *,
        source_column: str,
        json_path: str,
        empty_equivalent_values: list[str],
        fallback_fields: list[str],
        context: dict[str, Any],
    ) -> str:
        primary_clause = self._missing_expression_clause(
            source_column=source_column,
            json_path=json_path,
            empty_equivalent_values=empty_equivalent_values,
        )
        if not primary_clause:
            return ""
        fallback_clauses: list[str] = []
        for fallback_logical in list(fallback_fields or []):
            profile = self._find_context_profile(
                context=context,
                logical_names=(str(fallback_logical or "").strip().lower(),),
            )
            if not profile:
                continue
            fallback_definition = str(
                profile.get("definicion_negocio")
                or profile.get("definition")
                or profile.get("descripcion")
                or ""
            ).strip()
            fallback_tags = self._parse_semantic_tags(text=fallback_definition)
            fallback_source = str(profile.get("column_name") or "").strip().lower()
            if not fallback_source:
                continue
            clause = self._missing_expression_clause(
                source_column=fallback_source,
                json_path=str(profile.get("json_path") or fallback_tags.get("json_path") or "").strip(),
                empty_equivalent_values=self._normalize_semantic_list(
                    profile.get("empty_equivalent_values") or fallback_tags.get("empty_equivalent_values")
                ),
            )
            if clause:
                fallback_clauses.append(f"({clause})")
        if not fallback_clauses:
            return primary_clause
        return f"(({primary_clause}) AND {' AND '.join(fallback_clauses)})"

    def _missing_expression_clause(
        self,
        *,
        source_column: str,
        json_path: str,
        empty_equivalent_values: list[str],
    ) -> str:
        expression = (
            f"JSON_UNQUOTE(JSON_EXTRACT({source_column}, '{self._escape_literal(json_path)}'))"
            if json_path
            else source_column
        )
        conditions = [
            f"{expression} IS NULL",
            f"TRIM({expression}) = ''",
        ]
        for token in list(empty_equivalent_values or []):
            clean = str(token or "").strip()
            if clean:
                conditions.append(f"{expression} = '{self._escape_literal(clean)}'")
        return " OR ".join(conditions)

    @staticmethod
    def _normalize_semantic_list(value: Any) -> list[str]:
        if isinstance(value, list):
            return [str(item or "").strip() for item in value if str(item or "").strip()]
        text = str(value or "").strip()
        if not text:
            return []
        normalized = text
        for separator in (";", ","):
            normalized = normalized.replace(separator, "|")
        return [str(item or "").strip() for item in normalized.split("|") if str(item or "").strip()]

    @staticmethod
    def _data_quality_label(*, logical_name: str) -> str:
        labels = {
            "supervisor": "supervisor",
            "correo_corporativo": "correo corporativo",
            "celular_personal": "celular personal",
            "eps": "EPS",
            "arl": "ARL",
            "permiso_trabajo": "permiso de trabajo",
            "talla_botas": "tallas",
            "talla_camisa": "tallas",
            "talla_chaqueta": "tallas",
            "talla_guerrera": "tallas",
            "talla_pantalon": "tallas",
            "documento_identidad_lado_a": "documento de identidad",
            "documento_identidad_lado_b": "documento de identidad",
        }
        return str(labels.get(str(logical_name or "").strip().lower()) or logical_name)

    @staticmethod
    def _data_quality_risk_text(*, targets: list[str]) -> str:
        normalized = {str(item or "").strip().lower() for item in list(targets or []) if str(item or "").strip()}
        if "supervisor" in normalized:
            return "La falta de jefe directo limita escalamiento, control y seguimiento de la operacion."
        if "correo corporativo" in normalized:
            return "La ausencia de correo corporativo afecta notificaciones formales y trazabilidad de comunicaciones."
        if "celular personal" in normalized:
            return "La ausencia de celular personal dificulta contacto operativo y actualizacion de datos del colaborador."
        if normalized & {"eps", "arl"}:
            return "La falta de EPS o ARL expone riesgos de cumplimiento laboral y cobertura del personal."
        if "permiso de trabajo" in normalized:
            return "La ausencia de permiso de trabajo expone riesgos legales, migratorios y de continuidad contractual."
        if "tallas" in normalized:
            return "La informacion de tallas incompleta afecta planeacion, compra y entrega correcta de dotacion."
        if "documento de identidad" in normalized:
            return "La documentacion de identidad incompleta afecta validacion administrativa, trazabilidad y soportes de auditoria."
        return "La informacion faltante reduce control operativo y confiabilidad del maestro de personal."

    @staticmethod
    def _data_quality_recommendation_text(*, targets: list[str]) -> str:
        normalized = {str(item or "").strip().lower() for item in list(targets or []) if str(item or "").strip()}
        if "supervisor" in normalized:
            return "Asignar responsable de actualizacion jerarquica y depurar empleados activos sin jefe directo."
        if "correo corporativo" in normalized:
            return "Completar el correo corporativo oficial y validar el proceso de provisionamiento de cuentas."
        if "celular personal" in normalized:
            return "Actualizar el celular personal principal y reforzar la captura obligatoria del dato."
        if normalized & {"eps", "arl"}:
            return "Regularizar EPS y ARL faltantes con validacion documental y seguimiento de cumplimiento."
        if "permiso de trabajo" in normalized:
            return "Validar autorizacion de consulta y completar el soporte legal o migratorio faltante."
        if "tallas" in normalized:
            return "Completar tallas oficiales desde datos.tallas antes de programar dotacion o reposiciones."
        if "documento de identidad" in normalized:
            return "Completar ambos lados del documento de identidad sin exponer URLs completas en la salida operativa."
        return "Depurar el dato faltante y establecer responsables de calidad por area."

    def _employee_sql_metadata(
        self,
        *,
        table: str,
        columns: list[str],
        metric_used: str,
        aggregation_used: str,
        dimensions_used: list[str],
        concept_field: str,
        extra_metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        physical_columns = [item for item in columns if item and "(" not in str(item)]
        metadata = self._default_sql_metadata(table=table, columns=physical_columns)
        metadata.update(
            {
                "compiler": "employee_semantic_sql",
                "compiler_used": "employee_semantic_sql",
                "metric_used": metric_used,
                "aggregation_used": aggregation_used,
                "dimensions_used": list(dimensions_used or []),
                "concept_field": concept_field,
                "declared_metric_source": "ai_dictionary.dd_campos",
                "declared_dimensions_source": "ai_dictionary.dd_campos",
                "insights": [
                    "La consulta se resolvio por inferencia semantica validada contra ai_dictionary.",
                ],
            }
        )
        if extra_metadata:
            metadata.update(dict(extra_metadata or {}))
        return metadata

    @staticmethod
    def _parse_semantic_tags(*, text: str) -> dict[str, str]:
        payload: dict[str, str] = {}
        for key, value in re.findall(r"\[([a-zA-Z0-9_]+)=(.*?)\](?=\[|$)", str(text or "")):
            clean_key = str(key or "").strip().lower()
            clean_value = str(value or "").strip()
            if clean_key and clean_value:
                payload[clean_key] = clean_value
        return payload

    @staticmethod
    def _find_context_profile(
        *,
        context: dict[str, Any],
        logical_names: tuple[str, ...] = (),
        column_names: tuple[str, ...] = (),
    ) -> dict[str, Any]:
        logical_set = {str(item or "").strip().lower() for item in logical_names if str(item or "").strip()}
        column_set = {str(item or "").strip().lower() for item in column_names if str(item or "").strip()}
        profile_sources = [
            profile
            for profile in list(context.get("column_profiles") or [])
            if isinstance(profile, dict)
        ]
        profile_sources.extend(
            [
                field
                for field in list((context.get("dictionary") or {}).get("fields") or [])
                if isinstance(field, dict)
            ]
        )
        if logical_set:
            for profile in profile_sources:
                logical_name = str(profile.get("logical_name") or profile.get("campo_logico") or "").strip().lower()
                if logical_name in logical_set:
                    return profile
        if column_set:
            for profile in profile_sources:
                column_name = str(profile.get("column_name") or "").strip().lower()
                if column_name in column_set:
                    return profile
        return {}

    @staticmethod
    def _dictionary_rule_declared(*, context: dict[str, Any], rule_code: str) -> bool:
        target = str(rule_code or "").strip().lower()
        if not target:
            return False
        for rule in list((context.get("dictionary") or {}).get("rules") or []):
            if not isinstance(rule, dict):
                continue
            if str(rule.get("codigo") or "").strip().lower() == target:
                return True
        return False

    @staticmethod
    def _build_date_where(*, date_column: str, start_date: str, end_date: str) -> list[str]:
        where_parts: list[str] = []
        if date_column and start_date and end_date:
            where_parts.append(f"DATE({date_column}) BETWEEN '{start_date}' AND '{end_date}'")
        return where_parts

    @staticmethod
    def _default_sql_metadata(*, table: str, columns: list[str]) -> dict[str, Any]:
        normalized_columns = []
        for value in columns:
            token = str(value or "").strip()
            if not token or token == "*":
                continue
            normalized_columns.append(token.split(".")[-1])
        table_name = str(table or "").strip().split(".")[-1]
        return {
            "compiler": "default_sql_builder",
            "compiler_used": "default_sql_builder",
            "tables_detected": [table_name] if table_name else [],
            "columns_detected": sorted(set(normalized_columns)),
            "physical_columns_used": sorted(set(normalized_columns)),
            "relations_used": [],
        }

    @staticmethod
    def _table_key(*, schema_name: str = "", table_name: str = "", table_fqn: str = "") -> str:
        if str(table_fqn or "").strip():
            return str(table_fqn).strip().lower()
        clean_table = str(table_name or "").strip().lower()
        clean_schema = str(schema_name or "").strip().lower()
        if clean_schema and clean_table:
            return f"{clean_schema}.{clean_table}"
        return clean_table

    @classmethod
    def _profile_matches_table(cls, *, profile: dict[str, Any], table: dict[str, Any]) -> bool:
        profile_key = cls._table_key(
            schema_name=str(profile.get("schema_name") or ""),
            table_name=str(profile.get("table_name") or ""),
            table_fqn=str(profile.get("table_fqn") or ""),
        )
        table_key = cls._table_key(
            schema_name=str(table.get("schema_name") or ""),
            table_name=str(table.get("table_name") or ""),
            table_fqn=str(table.get("table_fqn") or ""),
        )
        if profile_key and table_key:
            return profile_key == table_key
        return (
            str(profile.get("table_name") or "").strip().lower()
            == str(table.get("table_name") or "").strip().lower()
        )

    @classmethod
    def _profile_columns_for_table(cls, *, context: dict[str, Any], table: dict[str, Any]) -> set[str]:
        columns: set[str] = set()
        profile_sources = [
            profile
            for profile in list(context.get("column_profiles") or [])
            if isinstance(profile, dict)
        ]
        profile_sources.extend(
            [
                field
                for field in list((context.get("dictionary") or {}).get("fields") or [])
                if isinstance(field, dict)
            ]
        )
        for profile in profile_sources:
            if not cls._profile_matches_table(profile=profile, table=table):
                continue
            column_name = str(profile.get("column_name") or "").strip().lower()
            if column_name:
                columns.add(column_name)
        return columns

    def _resolve_table_for_required_columns(
        self,
        *,
        context: dict[str, Any],
        required_columns: tuple[str, ...],
        preferred_table_name: str = "",
    ) -> str:
        candidates = [
            item
            for item in list(context.get("tables") or [])
            if isinstance(item, dict)
        ]
        if not candidates:
            return ""
        required = {
            str(item or "").strip().lower()
            for item in required_columns
            if str(item or "").strip()
        }
        preferred_name = str(preferred_table_name or "").strip().lower()
        best_table = ""
        best_score = -1
        for candidate in candidates:
            table_name = str(candidate.get("table_name") or "").strip().lower()
            if preferred_name and table_name and table_name != preferred_name:
                continue
            available = self._profile_columns_for_table(context=context, table=candidate)
            score = len(required & available)
            if score <= best_score:
                continue
            table_ref = self._table_key(
                schema_name=str(candidate.get("schema_name") or ""),
                table_name=str(candidate.get("table_name") or ""),
                table_fqn=str(candidate.get("table_fqn") or ""),
            )
            if not table_ref or not self._is_safe_identifier(table_ref):
                continue
            best_score = score
            best_table = table_ref
            if score == len(required):
                break
        return best_table

    @classmethod
    def _find_context_profile_for_table(
        cls,
        *,
        context: dict[str, Any],
        table_ref: str,
        logical_names: tuple[str, ...] = (),
        column_names: tuple[str, ...] = (),
    ) -> dict[str, Any]:
        base = cls._find_context_profile(
            context=context,
            logical_names=logical_names,
            column_names=column_names,
        )
        if not table_ref:
            return base
        logical_set = {str(item or "").strip().lower() for item in logical_names if str(item or "").strip()}
        column_set = {str(item or "").strip().lower() for item in column_names if str(item or "").strip()}
        profile_sources = [
            profile
            for profile in list(context.get("column_profiles") or [])
            if isinstance(profile, dict)
        ]
        profile_sources.extend(
            [
                field
                for field in list((context.get("dictionary") or {}).get("fields") or [])
                if isinstance(field, dict)
            ]
        )
        table = {"table_fqn": table_ref}
        best_profile: dict[str, Any] = {}
        best_score = -1
        for profile in profile_sources:
            if not cls._profile_matches_table(profile=profile, table=table):
                continue
            logical_name = str(profile.get("logical_name") or profile.get("campo_logico") or "").strip().lower()
            column_name = str(profile.get("column_name") or "").strip().lower()
            logical_match = logical_name in logical_set if logical_set else False
            column_match = column_name in column_set if column_set else False
            if logical_set and not logical_match and not column_match:
                continue
            if column_set and not logical_set and not column_match:
                continue
            score = 0
            if logical_match:
                score += 2
            if column_match:
                score += 3
            if score > best_score:
                best_score = score
                best_profile = profile
        return best_profile or base

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
        return self._resolve_group_column_by_target(target=requested[0], resolved_query=resolved_query, context=context)

    def _resolve_group_column_by_target(
        self,
        *,
        target: str,
        resolved_query: ResolvedQuerySpec,
        context: dict[str, Any],
    ) -> str:
        requested = [str(item).strip().lower() for item in list(resolved_query.intent.group_by or [])]
        if not requested:
            return ""
        profile_by_logical: dict[str, str] = {}
        profile_by_physical: dict[str, str] = {}
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
            profile_by_physical[physical.strip().lower()] = physical
        aliases = dict(context.get("aliases") or {})
        columns = {str(item.get("column_name") or "").strip().lower(): str(item.get("column_name") or "").strip() for item in list(context.get("columns") or []) if isinstance(item, dict)}
        mapped = str(aliases.get(target, target)).strip().lower()
        for candidate in (target, mapped):
            if candidate in profile_by_logical and self._is_safe_identifier(profile_by_logical[candidate]):
                return profile_by_logical[candidate]
            if candidate in profile_by_physical and self._is_safe_identifier(profile_by_physical[candidate]):
                return profile_by_physical[candidate]
            if candidate in columns and self._is_safe_identifier(columns[candidate]):
                return columns[candidate]
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
                for key in self._EMPLOYEE_DETAIL_FILTER_KEYS
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

    @staticmethod
    def _first_filter_value(*, filters: dict[str, Any], keys: tuple[str, ...]) -> str:
        for key in keys:
            value = str((filters or {}).get(key) or "").strip()
            if value:
                return value
        return ""

    _EMPLOYEE_DETAIL_FILTER_KEYS = (
        "cedula",
        "cedula_empleado",
        "identificacion",
        "documento",
        "id_empleado",
        "movil",
        "codigo_sap",
        "codigo_sap_empleado",
        "nombre",
        "area",
        "cargo",
        "tipo_labor",
        "supervisor",
        "carpeta",
        "fnacimiento_month",
        "birth_month",
        "month_of_birth",
        "search",
    )

    @classmethod
    def _has_employee_detail_filter(cls, *, filters: dict[str, Any]) -> bool:
        return any(str((filters or {}).get(key) or "").strip() for key in cls._EMPLOYEE_DETAIL_FILTER_KEYS)

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
        result_metadata: dict[str, Any] | None = None,
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
        metadata = dict(execution_plan.metadata or {})
        result_meta = {
            "total_records": int((result_metadata or {}).get("total_records") or len(rows)),
            "returned_records": int((result_metadata or {}).get("returned_records") or len(rows)),
            "truncated": bool((result_metadata or {}).get("truncated")),
            "limit": int((result_metadata or {}).get("limit") or 0),
        }
        kpis.setdefault("returned_records", result_meta["returned_records"])
        kpis.setdefault("total_records", result_meta["total_records"])
        compiler = str(metadata.get("compiler") or "default_sql_builder")
        metric_used = str(metadata.get("metric_used") or "")
        relations_used = list(metadata.get("relations_used") or [])
        insights = [
            "Resultado obtenido con SQL asistido restringido (solo lectura).",
        ]
        insights.extend([str(item) for item in list(metadata.get("insights") or []) if str(item).strip()])

        labels: list[str] = []
        series: list[dict[str, Any]] = []
        if rows and len(columns) >= 2:
            first_dimension = str(columns[0] or "")
            first_metric = next(
                (
                    str(name)
                    for name in columns[1:]
                    if str(name).lower().startswith("total")
                    and all(isinstance((row or {}).get(str(name)), (int, float)) for row in rows[:20])
                ),
                "",
            )
            if first_metric:
                labels = [str((row or {}).get(first_dimension) or "N/D") for row in rows[:20]]
                values = [int((row or {}).get(first_metric) or 0) for row in rows[:20]]
                if any(labels) and values:
                    series = [{"name": first_metric, "data": values}]

        period = dict(resolved_query.normalized_period or {})
        domain_code = str(resolved_query.intent.domain_code or "").strip().lower()
        reply = (
            f"Consulta analitica ejecutada en modo SQL asistido restringido para {resolved_query.intent.domain_code}: "
            f"{len(rows)} filas."
        )
        if period.get("start_date") and period.get("end_date"):
            reply = (
                f"Consulta analitica ejecutada en modo SQL asistido restringido para {resolved_query.intent.domain_code} "
                f"en el periodo {period.get('start_date')} al {period.get('end_date')}: {len(rows)} filas."
            )
        month_value = self._resolve_month_filter(filters=dict(resolved_query.normalized_filters or {}))
        if domain_code in {"empleados", "rrhh"} and month_value:
            if str(resolved_query.intent.operation or "").strip().lower() == "count":
                total = int(kpis.get("total") or kpis.get("rowcount") or 0)
                reply = f"Se encontraron {total} empleados que cumplen anos en el mes {month_value}."
            else:
                reply = f"Se listan {len(rows)} empleados con cumpleanos en el mes {month_value}."
        business_response: dict[str, Any] | None = None
        response_category = str(metadata.get("response_category") or "").strip().lower()
        findings = [
            {
                "title": "Top hallazgo",
                "detail": (
                    f"Se obtuvieron {len(rows)} filas usando {compiler}."
                    if domain_code not in {"empleados", "rrhh"} or not month_value
                    else f"El campo semantico fecha_nacimiento permitio resolver cumpleanos del mes {month_value}."
                ),
            }
        ]
        actions = [
            {
                "id": f"task-followup-{run_context.run_id}",
                "type": "followup",
                "label": "Profundizar analisis",
                "payload": {
                    "suggested_dimensions": ["sede", "area", "cargo"],
                    "current_strategy": "sql_assisted",
                },
            }
        ]
        if response_category == "data_quality":
            target_labels = [
                str(item or "").strip()
                for item in list(metadata.get("data_quality_target_labels") or [])
                if str(item or "").strip()
            ]
            distinct_labels = list(dict.fromkeys(target_labels))
            label_text = " o ".join(distinct_labels[:2]) if len(distinct_labels) <= 2 else ", ".join(distinct_labels[:-1]) + f" y {distinct_labels[-1]}"
            total = int(result_meta.get("total_records") or kpis.get("total") or kpis.get("rowcount") or len(rows) or 0)
            returned = int(result_meta.get("returned_records") or len(rows) or 0)
            truncated = bool(result_meta.get("truncated"))
            limit = int(result_meta.get("limit") or 0)
            operation = str(resolved_query.intent.operation or "").strip().lower()
            missing_phrase = (
                f"sin {label_text}"
                if len(distinct_labels) == 1 and label_text.lower() != "tallas"
                else f"con {label_text} faltante o incompleto"
            )
            if operation == "count":
                reply = f"Se identificaron {total} empleados activos {missing_phrase}."
            else:
                reply = f"Se identificaron {total} empleados activos {missing_phrase}."
                if truncated:
                    reply += f" Estoy mostrando los primeros {returned} registros debido al limite operativo de {limit}."
                else:
                    reply += f" Se muestran {returned} registros."
            hallazgo = f"Hay empleados activos con informacion faltante o incompleta en {label_text}."
            if truncated:
                hallazgo += f" El detalle esta truncado: {returned} de {total} registros encontrados."
            riesgo = self._data_quality_risk_text(targets=distinct_labels)
            recomendacion = self._data_quality_recommendation_text(targets=distinct_labels)
            if truncated:
                recomendacion = (
                    f"{recomendacion} Segmenta por sede, area, supervisor, movil o tipo_labor para reducir el volumen."
                ).strip()
            insights = [
                f"Dato principal: {total} empleados activos con {label_text} faltante o incompleto.",
                *(
                    [f"Truncamiento: se muestran {returned} de {total} registros por limite operativo."]
                    if truncated
                    else []
                ),
                f"Riesgo: {riesgo}",
                f"Recomendacion: {recomendacion}",
            ]
            findings = [{"title": "Alerta de calidad de datos", "detail": hallazgo}]
            business_response = {
                "dato": f"{total} empleados activos con {label_text} faltante o incompleto.",
                "hallazgo": hallazgo,
                "interpretacion": "La consulta evidencia brechas de calidad de dato sobre atributos operativos y administrativos del personal activo.",
                "riesgo": riesgo,
                "recomendacion": recomendacion,
                "siguiente_accion": (
                    "Filtra por sede, area, supervisor, movil o tipo_labor para reducir el volumen."
                    if truncated
                    else "Priorizar depuracion del dato y asignar responsables por area o supervisor."
                ),
            }
            actions = [
                {
                    "id": f"task-followup-{run_context.run_id}",
                    "type": "followup",
                    "label": "Muestrame el resumen por area, cargo o supervisor.",
                    "payload": {
                        "suggested_dimensions": ["area", "cargo", "supervisor"],
                        "current_strategy": "sql_assisted",
                        "metric_used": metric_used,
                    },
                }
            ]
        if metric_used == "certificado_alturas_vigencia" and rows:
            first_row = dict(rows[0] or {})
            vencidos = int(first_row.get("certificados_vencidos") or 0)
            proximos = int(first_row.get("certificados_proximos_vencer") or 0)
            reply = (
                f"{vencidos} certificados de alturas vencidos y {proximos} proximos a vencer "
                "en personal activo de labor operativa."
            )
            findings = [
                {
                    "title": "Riesgo documental operativo",
                    "detail": (
                        "El personal operativo activo tiene riesgo documental si hay certificados vencidos."
                    ),
                }
            ]
            insights = [
                f"Dato principal: {vencidos} certificados de alturas vencidos y {proximos} proximos a vencer.",
                "Riesgo: tecnicos con certificado vencido no deberian ser asignados a trabajos en alturas.",
                "Recomendacion: priorizar renovacion de vencidos y programar renovacion de proximos a vencer.",
            ]
            actions = [
                {
                    "id": f"task-followup-{run_context.run_id}",
                    "type": "followup",
                    "label": "Muestrame el detalle por empleado, area, supervisor o movil.",
                    "payload": {
                        "suggested_dimensions": ["empleado", "area", "supervisor", "movil"],
                        "current_strategy": "sql_assisted",
                        "metric_used": metric_used,
                    },
                }
            ]
            kpis = {
                "certificados_vencidos": vencidos,
                "certificados_proximos_vencer": proximos,
            }
            business_response = {
                "dato": f"{vencidos} certificados de alturas vencidos y {proximos} proximos a vencer.",
                "hallazgo": "El personal operativo activo tiene riesgo documental si hay certificados vencidos.",
                "interpretacion": "La vigencia de 18 meses del certificado de alturas impacta la habilitacion operativa del personal de campo.",
                "riesgo": "Tecnicos con certificado vencido no deberian ser asignados a trabajos en alturas.",
                "recomendacion": "Priorizar renovacion de vencidos y programar renovacion de proximos a vencer.",
                "siguiente_accion": "Muestrame el detalle por empleado, area, supervisor o movil.",
            }
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
                "response_flow": "sql_assisted",
            },
            "data": {
                "kpis": kpis,
                "series": series,
                "labels": labels,
                "insights": insights,
                "table": {
                    "columns": list(columns or []),
                    "rows": list(rows or []),
                    "rowcount": len(rows),
                    "total_records": result_meta["total_records"],
                    "returned_records": result_meta["returned_records"],
                    "truncated": result_meta["truncated"],
                    "limit": result_meta["limit"],
                },
                "meta": {
                    "result_set": dict(result_meta),
                },
                "charts": (
                    [
                        {
                            "type": "bar" if str(columns[0] or "").lower() != "fecha" else "line",
                            "title": "Distribucion analitica",
                            "labels": labels,
                            "series": series,
                        }
                    ]
                    if labels and series
                    else []
                ),
                "findings": [
                    *findings
                ],
                **({"business_response": business_response} if business_response else {}),
            },
            "actions": actions,
            "data_sources": {
                "query_intelligence": {
                    "ok": True,
                    "strategy": execution_plan.strategy,
                    "query": sql_query,
                    "db_alias": db_alias,
                    "compiler": compiler,
                    "relations_used": relations_used,
                    "metric_used": metric_used,
                    "aggregation_used": str(metadata.get("aggregation_used") or ""),
                    "dimensions_used": list(metadata.get("dimensions_used") or []),
                    "result_set": dict(result_meta),
                    "total_records": result_meta["total_records"],
                    "returned_records": result_meta["returned_records"],
                    "truncated": result_meta["truncated"],
                    "limit": result_meta["limit"],
                    "declared_metric_source": str(metadata.get("declared_metric_source") or ""),
                    "declared_dimensions_source": str(metadata.get("declared_dimensions_source") or ""),
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
                        "result_set": dict(result_meta),
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
