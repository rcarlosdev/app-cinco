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
from apps.ia_dev.domains.inventario_logistica.response_assembler import (
    build_inventory_business_response,
)


class QueryExecutionPlanner:
    SAFE_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9_\.]+$")
    TRAILING_LIMIT_RE = re.compile(r"\s+LIMIT\s+(\d+)\s*;?\s*$", re.IGNORECASE)
    CLEANUP_PHASE = "phase_7"
    PILOT_PHASE = "phase_9"
    ANALYTICS_ROUTER_DOMAINS = {"ausentismo", "attendance", "empleados", "rrhh", "inventario_logistica"}
    COVERED_ANALYTICS_DOMAINS = {"ausentismo", "attendance", "empleados", "rrhh", "inventario_logistica"}
    MODERN_HANDLER_CAPABILITY_PREFIXES = ("empleados.",)
    PRODUCTIVE_PILOT_DOMAINS = {"ausentismo", "attendance", "empleados", "rrhh", "inventario_logistica"}
    INVENTORY_QUANTITY_NUMERIC_RE = r"^-?[0-9]+([.][0-9]+)?$"

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
        semantic_trace = self._semantic_trace_payload(resolved_query=resolved_query)

        capability_id = self._resolve_capability_id(
            domain_code=domain_code,
            template_id=template_id,
            resolved_query=resolved_query,
        )
        normalized_template_id = self._normalize_inventory_template_alignment(
            domain_code=domain_code,
            template_id=template_id,
            capability_id=capability_id,
            resolved_query=resolved_query,
            constraints=constraints,
        )
        if normalized_template_id != template_id:
            template_id = normalized_template_id
            resolved_query.intent.template_id = normalized_template_id
            constraints = self._build_constraints(resolved_query=resolved_query)
            semantic_trace = self._semantic_trace_payload(resolved_query=resolved_query)
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
                        capability_id=capability_id,
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
                            "semantic_trace": semantic_trace,
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
                        "semantic_trace": semantic_trace,
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
                        "semantic_trace": semantic_trace,
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
                    "semantic_trace": semantic_trace,
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
                metadata={"template_id": template_id, "semantic_trace": semantic_trace, **raw_query_fallback_meta, **analytics_router_metadata},
            )

        if domain_code == "general":
            return QueryExecutionPlan(
                strategy="fallback",
                reason="general_domain_conversational_fallback",
                domain_code=domain_code or "general",
                capability_id=capability_id,
                constraints=constraints,
                policy={"allowed": False, "reason": "fallback_legacy"},
                metadata={"template_id": template_id, "semantic_trace": semantic_trace, **raw_query_fallback_meta, **analytics_router_metadata},
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
                metadata={"template_id": template_id, "semantic_trace": semantic_trace, **raw_query_fallback_meta, **analytics_router_metadata},
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
                "semantic_trace": semantic_trace,
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
        if normalized_domain == "inventario_logistica":
            return cls._flag_enabled("IA_DEV_QUERY_SQL_ASSISTED_ENABLED", "0")
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
            domain_code = str(resolved_query.intent.domain_code or "").strip().lower()
            if domain_code == "inventario_logistica":
                return True
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
        if normalized == "inventory_stock_requires_db_validation":
            return "inventory_stock_requires_db_validation"
        if normalized == "inventory_stock_requires_business_validation":
            return "inventory_stock_requires_business_validation"
        if normalized in {"no_allowed_dimension", "max_dimensions_exceeded", "unsupported_dimension"}:
            return "unsupported_dimension"
        if "relation" in normalized:
            return "missing_dictionary_relation"
        if any(
            token in normalized
            for token in (
                "column",
                "inventory_table_not_audited",
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
        if normalized == "inventory_stock_requires_business_validation":
            return "inventory_stock_requires_business_validation"
        if normalized == "inventory_stock_requires_db_validation":
            return "inventory_stock_requires_db_validation"
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

        db_alias = str(
            (execution_plan.metadata or {}).get("db_alias")
            or os.getenv("IA_DEV_DB_READONLY_ALIAS", os.getenv("IA_DEV_DB_ALIAS", "default"))
            or "default"
        ).strip()
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
            export_rows_payload = self._resolve_sql_export_rows(
                db_alias=db_alias,
                sql_query=sql_query,
                rows_payload=rows_payload,
                result_metadata=result_metadata,
            )
            supplemental_tables = self._execute_supplemental_inventory_queries(
                db_alias=db_alias,
                execution_plan=execution_plan,
            )
            response = self._build_sql_response(
                run_context=run_context,
                resolved_query=resolved_query,
                execution_plan=execution_plan,
                sql_query=sql_query,
                rows=rows_payload,
                export_rows=export_rows_payload,
                columns=columns,
                duration_ms=duration_ms,
                db_alias=db_alias,
                result_metadata=result_metadata,
                supplemental_tables=supplemental_tables,
            )
            if supplemental_tables:
                response.setdefault("data_sources", {}).setdefault("query_intelligence", {})["supplemental_queries"] = [
                    {
                        "name": str(item.get("name") or ""),
                        "query": str(item.get("query") or ""),
                        "rowcount": int(item.get("rowcount") or 0),
                        "skipped": bool(item.get("skipped")),
                        "reason": str(item.get("reason") or ""),
                    }
                    for item in supplemental_tables
                ]
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

    def _execute_supplemental_inventory_queries(
        self,
        *,
        db_alias: str,
        execution_plan: QueryExecutionPlan,
    ) -> list[dict[str, Any]]:
        supplemental_queries = list((execution_plan.metadata or {}).get("supplemental_queries") or [])
        if not supplemental_queries:
            return []
        results: list[dict[str, Any]] = []
        for item in supplemental_queries:
            if not isinstance(item, dict):
                continue
            if bool(item.get("skipped")) or not str(item.get("query") or "").strip():
                results.append(
                    {
                        "name": str(item.get("name") or ""),
                        "query": str(item.get("query") or ""),
                        "columns": list(item.get("columns") or []),
                        "rows": [],
                        "rowcount": 0,
                        "skipped": True,
                        "reason": str(item.get("reason") or ""),
                        "metadata": dict(item.get("metadata") or {}),
                    }
                )
                continue
            query = str(item.get("query") or "").strip()
            with connections[db_alias].cursor() as cursor:
                cursor.execute(query)
                rows = cursor.fetchall()
                columns = [str(getattr(col, "name", col[0]) or "") for col in (cursor.description or [])]
            rows_payload = [{columns[idx]: row[idx] for idx in range(len(columns))} for row in rows]
            results.append(
                {
                    "name": str(item.get("name") or ""),
                    "query": query,
                    "columns": columns,
                    "rows": rows_payload,
                    "rowcount": len(rows_payload),
                    "skipped": False,
                    "reason": str(item.get("reason") or ""),
                    "metadata": dict(item.get("metadata") or {}),
                }
            )
        return results

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

    @staticmethod
    def _max_sql_export_rows() -> int:
        raw = str(os.getenv("IA_DEV_QUERY_SQL_ASSISTED_EXPORT_MAX_ROWS", "20000") or "20000").strip()
        try:
            value = int(raw)
        except Exception:
            value = 20000
        return max(1, min(value, 100000))

    @classmethod
    def _build_export_rows_query(cls, *, sql_query: str, limit: int) -> str:
        base_query = cls.TRAILING_LIMIT_RE.sub("", str(sql_query or "").strip()).strip().rstrip(";").strip()
        if not base_query:
            return ""
        return f"SELECT * FROM ({base_query}) AS sql_assisted_export LIMIT {max(1, int(limit))}"

    def _resolve_sql_export_rows(
        self,
        *,
        db_alias: str,
        sql_query: str,
        rows_payload: list[dict[str, Any]],
        result_metadata: dict[str, Any],
    ) -> list[dict[str, Any]]:
        total_records = int((result_metadata or {}).get("total_records") or len(rows_payload))
        returned_records = int((result_metadata or {}).get("returned_records") or len(rows_payload))
        export_limit = self._max_sql_export_rows()

        if total_records <= returned_records or total_records <= len(rows_payload):
            return rows_payload

        query = self._build_export_rows_query(
            sql_query=sql_query,
            limit=min(total_records, export_limit),
        )
        if not query:
            return rows_payload

        try:
            with connections[db_alias].cursor() as cursor:
                cursor.execute(query)
                rows = cursor.fetchall()
                columns = [str(getattr(col, "name", col[0]) or "") for col in (cursor.description or [])]
        except Exception:
            return rows_payload

        return [
            {columns[idx]: row[idx] for idx in range(len(columns))}
            for row in rows
        ]

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

    @staticmethod
    def _normalize_inventory_template_alignment(
        *,
        domain_code: str,
        template_id: str,
        capability_id: str,
        resolved_query: ResolvedQuerySpec,
        constraints: dict[str, Any],
    ) -> str:
        if str(domain_code or "").strip().lower() != "inventario_logistica":
            return str(template_id or "").strip().lower()
        normalized_template = str(template_id or "").strip().lower()
        if str(capability_id or "").strip().lower() == "inventory_serial_stock_by_family_grouped_dimension":
            filters = dict((constraints or {}).get("filters") or resolved_query.normalized_filters or {})
            grouping_dimension = str(filters.get("grouping_dimension") or "").strip().lower()
            group_by = {
                str(item or "").strip().lower()
                for item in list((constraints or {}).get("group_by") or resolved_query.intent.group_by or [])
                if str(item or "").strip()
            }
            has_grouped_dimension = grouping_dimension in {"movil", "cedula", "bodega"} or bool(
                group_by & {"movil", "cedula", "bodega"}
            )
            if has_grouped_dimension and str(filters.get("material_family") or "").strip():
                return "inventory_serial_stock_by_family_grouped_dimension"
        if str(capability_id or "").strip().lower() != "inventory_stock_balance_by_material_dimension":
            return normalized_template
        filters = dict((constraints or {}).get("filters") or resolved_query.normalized_filters or {})
        grouping_dimension = str(filters.get("grouping_dimension") or "").strip().lower()
        group_by = {
            str(item or "").strip().lower()
            for item in list((constraints or {}).get("group_by") or resolved_query.intent.group_by or [])
            if str(item or "").strip()
        }
        has_grouped_dimension = grouping_dimension in {"movil", "cedula", "bodega"} or bool(
            group_by & {"movil", "cedula", "bodega"}
        )
        if not has_grouped_dimension:
            return normalized_template
        if any(str(filters.get(key) or "").strip() for key in ("movil", "cedula")):
            return normalized_template
        if not any(str(filters.get(key) or "").strip() for key in ("codigo", "descripcion", "tipo", "material_family")):
            return normalized_template
        return "inventory_material_stock_grouped_dimension"

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
        if normalized_domain == "inventario_logistica":
            semantic_context = dict(resolved_query.semantic_context or {})
            resolved_semantic = dict(semantic_context.get("resolved_semantic") or {})
            binding = dict(
                semantic_context.get("semantic_capability_registry")
                or resolved_semantic.get("semantic_capability_registry")
                or {}
            )
            binding_capability = str(
                binding.get("candidate_capability")
                or resolved_semantic.get("candidate_capability")
                or (((semantic_context.get("business_query_semantic_plan") or {}).get("candidate_capability")))
                or ""
            ).strip()
            if binding_capability:
                return binding_capability
            if self._should_route_kardex_codigo_employee_to_employee(
                domain_code=normalized_domain,
                template_id=template_id,
                resolved_query=resolved_query,
            ):
                return "inventory_kardex_by_employee"
            if template_id == "inventory_material_stock_by_warehouse":
                return "inventory_stock_balance_by_warehouse"
            if template_id == "inventory_material_stock_mobile":
                return "inventory_stock_balance_by_mobile"
            if template_id == "inventory_material_stock_grouped_dimension":
                return "inventory_stock_balance_by_material_dimension"
            if template_id == "inventory_material_critical_by_employee":
                return "inventory_stock_balance_by_mobile"
            if template_id == "inventory_material_stock_balance":
                return "inventory_stock_balance"
            if template_id == "inventory_traceability_by_serial":
                return "inventory_traceability_by_serial"
            if template_id == "inventory_serial_by_operational_holder":
                return "inventory_serial_by_operational_holder"
            if template_id == "inventory_risk_consumo_movil_sin_validar":
                return "inventory_risk_consumo_movil_sin_validar"
            if template_id == "inventory_consumption_top":
                return "inventory_consumption_top"
            if template_id == "inventory_consumption_by_dimension":
                return "inventory_consumption_by_dimension"
            if template_id == "inventory_transfer_warehouse":
                return "inventory_transfer_warehouse"
            if template_id == "inventory_transfer_other_ally":
                return "inventory_transfer_other_ally"
            if template_id == "inventory_serial_association_departures":
                return "inventory_serial_association_departures"
            if template_id == "inventory_entries_by_month":
                return "inventory_entries_by_month"
            if template_id == "inventory_movement_detail":
                return "inventory_movement_detail"
            if template_id == "inventory_kardex_by_employee":
                return "inventory_kardex_by_employee"
            if template_id == "inventory_kardex_consolidated":
                return "inventory_kardex_consolidated"
            if template_id == "inventory_consumption_billing_operacion_hfc":
                return "inventory_consumption_billing_operacion_hfc"
            if template_id == "inventory_semantic_report":
                return "inventory_semantic_report"
            if template_id == "inventory_document_generation_pending":
                return "inventory_document_generation_pending"
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
        if str(resolved_query.intent.domain_code or "").strip().lower() == "inventario_logistica":
            template_id = str(resolved_query.intent.template_id or "").strip().lower()
            if template_id in {
                "inventory_material_stock_mobile",
                "inventory_material_stock_grouped_dimension",
                "inventory_material_stock_balance",
                "inventory_material_stock_by_warehouse",
                "inventory_material_critical_by_employee",
                "inventory_serial_stock_by_family_grouped_dimension",
                "inventory_serial_stock_by_dimension",
                "inventory_serial_employee_balance",
            }:
                metrics = [metric for metric in metrics if metric not in {"count", "percentage"}]
                chart_requested = False
            if template_id in {"inventory_kardex_by_employee", "inventory_kardex_consolidated"}:
                result_shape = "table"
                chart_requested = False
            if template_id in {"inventory_consumption_top", "inventory_consumption_by_dimension"}:
                chart_requested = False
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
    def _semantic_trace_payload(*, resolved_query: ResolvedQuerySpec) -> dict[str, Any]:
        semantic_context = dict(resolved_query.semantic_context or {})
        resolved_semantic = dict(semantic_context.get("resolved_semantic") or {})
        return {
            "original_query": str(resolved_query.intent.raw_query or ""),
            "semantic_plan": dict(
                semantic_context.get("business_query_semantic_plan")
                or semantic_context.get("inventory_semantic_plan")
                or {}
            ),
            "semantic_binding": dict(
                semantic_context.get("semantic_capability_registry")
                or resolved_semantic.get("semantic_capability_registry")
                or {}
            ),
            "rules_applied": list(resolved_semantic.get("rules_applied") or []),
            "consulted_sources": list(resolved_semantic.get("consulted_sources") or []),
            "memory_keys_used": list(resolved_semantic.get("memory_keys_used") or []),
            "final_filters": dict(resolved_semantic.get("final_filters") or resolved_query.normalized_filters or {}),
            "candidate_capability": str(resolved_semantic.get("candidate_capability") or ""),
            "blocked_reasons": list(resolved_semantic.get("limitations") or []),
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
        if str(resolved_query.intent.domain_code or "").strip().lower() == "inventario_logistica":
            inventory_query, inventory_reason, inventory_metadata = self._build_inventory_sql_query(
                resolved_query=resolved_query,
                context=context,
            )
            if inventory_query:
                return inventory_query, inventory_reason, inventory_metadata
            if inventory_reason not in {"inventory_sql_not_applicable", ""}:
                return "", inventory_reason, inventory_metadata

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

    def _build_inventory_sql_query(
        self,
        *,
        resolved_query: ResolvedQuerySpec,
        context: dict[str, Any],
    ) -> tuple[str, str, dict[str, Any]]:
        template_id = str(resolved_query.intent.template_id or "").strip().lower()
        filters = dict(resolved_query.normalized_filters or {})
        month_value = str(filters.get("month") or "").strip()
        limit = self._max_sql_limit()

        if template_id == "inventory_stock_balance_pending_validation":
            return "", "inventory_stock_requires_db_validation", {
                "compiler": "inventory_semantic_sql",
                "compiler_used": "inventory_semantic_sql",
                "limitations": ["stock_calculation_business_rule_confirmed_pending_db_validation"],
                "requires_business_validation": False,
                "requires_db_validation": True,
                "fallback_reason": "inventory_stock_requires_db_validation",
                "db_alias": "logistica_cinco",
            }

        if template_id in {
            "inventory_material_stock_balance",
            "inventory_material_stock_by_warehouse",
            "inventory_material_stock_mobile",
            "inventory_material_stock_grouped_dimension",
            "inventory_material_critical_by_employee",
        }:
            return self._build_inventory_material_stock_sql(
                resolved_query=resolved_query,
                template_id=template_id,
                context=context,
                filters=filters,
                limit=min(limit, 1000),
            )

        if template_id in {"inventory_transfer_warehouse", "inventory_transfer_other_ally"}:
            return self._build_inventory_transfer_sql(
                template_id=template_id,
                context=context,
                limit=min(limit, 1000),
            )

        if template_id == "inventory_transfer_destination_not_available":
            return "", "inventory_transfer_destination_missing_physical_column", {
                "compiler": "inventory_semantic_sql",
                "compiler_used": "inventory_semantic_sql",
                "limitations": ["missing_physical_column:bodega_destino"],
                "fallback_reason": "inventory_transfer_destination_missing_physical_column",
                "db_alias": "logistica_cinco",
            }

        if template_id == "inventory_kardex_by_employee":
            return self._build_inventory_kardex_by_employee_sql(
                resolved_query=resolved_query,
                context=context,
                limit=min(limit, 1000),
            )

        if template_id == "inventory_kardex_consolidated":
            if self._should_route_kardex_codigo_employee_to_employee(
                domain_code=str(resolved_query.intent.domain_code or "").strip().lower(),
                template_id=template_id,
                resolved_query=resolved_query,
            ):
                return self._build_inventory_kardex_by_employee_sql(
                    resolved_query=resolved_query,
                    context=context,
                    limit=min(limit, 1000),
                )
            return self._build_inventory_kardex_sql(
                resolved_query=resolved_query,
                context=context,
                limit=min(limit, 1000),
            )

        if template_id == "inventory_consumption_billing_operacion_hfc":
            return self._build_inventory_consumption_billing_sql(
                context=context,
                limit=min(limit, 1000),
            )

        if template_id == "inventory_serial_stock_by_family_grouped_dimension":
            return self._build_inventory_serial_family_grouped_dimension_sql(
                context=context,
                filters=filters,
                group_by=list(resolved_query.intent.group_by or []),
                limit=min(limit, 1000),
            )

        if template_id == "inventory_serial_stock_by_dimension":
            table = self._resolve_table_for_required_columns(
                context=context,
                required_columns=("estado",),
                preferred_table_name="logistica_base_seriales",
            )
            group_by = [
                str(item or "").strip().lower()
                for item in list(resolved_query.intent.group_by or [])
                if str(item or "").strip()
            ]
            dimension_name = group_by[0] if group_by else "estado"
            if dimension_name not in {"estado", "bodega", "ubicacion", "codigo"}:
                return "", "inventory_serial_stock_dimension_not_validated", {
                    "compiler": "inventory_semantic_sql",
                    "compiler_used": "inventory_semantic_sql",
                    "fallback_reason": "inventory_serial_stock_dimension_not_validated",
                    "db_alias": "logistica_cinco",
                }
            dimension_column = str(
                (
                    self._find_context_profile_for_table(
                        context=context,
                        table_ref=table,
                        logical_names=(dimension_name,),
                        column_names=(dimension_name,),
                    )
                    or {}
                ).get("column_name")
                or ""
            ).strip()
            serial_column = str(
                (
                    self._find_context_profile_for_table(
                        context=context,
                        table_ref=table,
                        logical_names=("serial",),
                        column_names=("numero_serial", "serial"),
                    )
                    or {}
                ).get("column_name")
                or ""
            ).strip()
            if not table or not dimension_column or not self._is_safe_identifier(dimension_column):
                return "", "inventory_serial_stock_missing_dictionary_column", {}
            metric_sql = f"COUNT(DISTINCT {serial_column})" if self._is_safe_identifier(serial_column) else "COUNT(*)"
            query = (
                f"SELECT {dimension_column} AS {dimension_name}, {metric_sql} AS total_seriales "
                f"FROM {table} GROUP BY {dimension_column} "
                f"ORDER BY total_seriales DESC LIMIT {limit}"
            )
            return query, "inventory_serial_stock_by_dimension", self._inventory_sql_metadata(
                table=table,
                columns=[dimension_column, serial_column],
                metric_used="serial_count",
                aggregation_used="count_distinct" if serial_column else "count",
                dimensions_used=[dimension_name],
                concept_field="stock_serializado_estado_actual",
            )

        if template_id == "inventory_traceability_by_serial":
            table = self._resolve_table_for_required_columns(
                context=context,
                required_columns=("serial", "codigo"),
                preferred_table_name="logistica_base_seriales",
            )
            serial_column = self._resolve_named_column(context=context, preferred_terms=("serial", "numero_serial"))
            if not table or not serial_column or not str(filters.get("serial") or "").strip():
                return "", "inventory_traceability_missing_serial_metadata", {}
            detail_columns = self._resolve_inventory_detail_columns(
                context=context,
                preferred=("serial", "codigo", "estado", "ubicacion", "fecha"),
            )
            date_column = self._resolve_inventory_date_column(context=context, table_ref=table)
            order_column = date_column or serial_column
            query = (
                f"SELECT {', '.join(detail_columns)} FROM {table} "
                f"WHERE {serial_column} = '{self._escape_literal(str(filters.get('serial') or ''))}' "
                f"ORDER BY {order_column} DESC LIMIT {limit}"
            )
            return query, "inventory_traceability_by_serial", self._inventory_sql_metadata(
                table=table,
                columns=detail_columns,
                metric_used="traceability",
                aggregation_used="detail",
                dimensions_used=[],
                concept_field="serial",
            )

        if template_id == "inventory_serial_by_operational_holder":
            table = self._resolve_table_for_required_columns(
                context=context,
                required_columns=("codigo", "estado", "cedula"),
                preferred_table_name="logistica_base_seriales",
            )
            if not table:
                return "", "inventory_serial_holder_missing_dictionary_column", {}
            holder_where = self._inventory_operational_filter_clause(
                context=context,
                table_ref=table,
                filters=filters,
                table_alias="s",
            )
            if not holder_where:
                return "", "inventory_serial_holder_missing_filter", {}
            detail_columns = self._resolve_inventory_serial_holder_columns(context=context, table_ref=table)
            qualified_detail_columns = [f"s.{column} AS {column}" for column in detail_columns]
            query = (
                f"SELECT {', '.join(qualified_detail_columns)} FROM {table} AS s "
                f"WHERE {holder_where} LIMIT {limit}"
            )
            metadata = self._inventory_sql_metadata(
                table=table,
                columns=detail_columns,
                metric_used="serial_holder_detail",
                aggregation_used="detail",
                dimensions_used=[],
                concept_field="seriales_por_operador",
            )
            metadata["serial_source_columns"] = list(detail_columns)
            return query, "inventory_serial_by_operational_holder", metadata

        if template_id == "inventory_risk_consumo_movil_sin_validar":
            table = self._resolve_table_for_required_columns(
                context=context,
                required_columns=("movimiento", "validado"),
                preferred_table_name="logistica_base_seriales",
            )
            movimiento_column = self._resolve_named_column(context=context, preferred_terms=("movimiento",))
            validado_column = self._resolve_named_column(context=context, preferred_terms=("validado",))
            if not table or not movimiento_column or not validado_column:
                return "", "inventory_risk_missing_dictionary_column", {}
            detail_columns = self._resolve_inventory_detail_columns(
                context=context,
                preferred=("serial", "codigo", "movimiento", "validado", "fecha", "responsable"),
            )
            query = (
                f"SELECT {', '.join(detail_columns)} FROM {table} "
                f"WHERE {movimiento_column} = 'consumo_movil' "
                f"AND ({validado_column} = 0 OR LOWER(COALESCE(CAST({validado_column} AS CHAR), 'false')) IN ('false', '0', 'no')) "
                f"LIMIT {limit}"
            )
            return query, "inventory_risk_consumo_movil_sin_validar", self._inventory_sql_metadata(
                table=table,
                columns=detail_columns,
                metric_used="pending_validation",
                aggregation_used="detail",
                dimensions_used=[],
                concept_field="consumo_movil_sin_validar",
            )

        if template_id in {"inventory_consumption_top", "inventory_consumption_by_dimension"}:
            table = self._resolve_table_for_required_columns(
                context=context,
                required_columns=("codigo", "cantidad"),
                preferred_table_name="logistica_movimientos_consumo",
            )
            codigo_column = self._resolve_named_column(context=context, preferred_terms=("codigo",))
            cantidad_column = self._resolve_named_column(context=context, preferred_terms=("cantidad",))
            fecha_column = self._resolve_inventory_date_column(context=context, table_ref=table)
            if not table or not codigo_column or not cantidad_column:
                return "", "inventory_consumption_missing_dictionary_column", {}
            where_parts: list[str] = []
            if month_value and fecha_column:
                where_parts.append(f"MONTH({fecha_column}) = {int(month_value)}")
            day_value = str(filters.get("day") or "").strip()
            if day_value.isdigit() and fecha_column:
                where_parts.append(f"DAY({fecha_column}) = {int(day_value)}")
            holder_where = self._inventory_operational_filter_clause(
                context=context,
                table_ref=table,
                filters=filters,
            )
            if holder_where:
                where_parts.append(holder_where)
            where_sql = (" WHERE " + " AND ".join(where_parts)) if where_parts else ""
            safe_cantidad = self._inventory_safe_quantity_sql(cantidad_column)
            invalid_cantidad = self._inventory_invalid_quantity_sql(cantidad_column)
            query = (
                f"SELECT {codigo_column} AS material, SUM({safe_cantidad}) AS total_consumido, "
                f"SUM({invalid_cantidad}) AS registros_cantidad_invalida "
                f"FROM {table}{where_sql} GROUP BY {codigo_column} "
                f"ORDER BY total_consumido DESC LIMIT {limit}"
            )
            return query, "inventory_consumption_top", self._inventory_sql_metadata(
                table=table,
                columns=[codigo_column, cantidad_column, fecha_column],
                metric_used="cantidad",
                aggregation_used="sum",
                dimensions_used=["material"],
                concept_field="materiales_mas_consumidos",
            )

        if template_id == "inventory_transfer_group_by_destination":
            return "", "inventory_transfer_destination_missing_physical_column", {
                "compiler": "inventory_semantic_sql",
                "compiler_used": "inventory_semantic_sql",
                "limitations": ["missing_physical_column:bodega_destino"],
                "fallback_reason": "inventory_transfer_destination_missing_physical_column",
                "db_alias": "logistica_cinco",
            }

        if template_id == "inventory_serial_association_departures":
            table = self._resolve_table_for_required_columns(
                context=context,
                required_columns=("serial", "bodega_salida"),
                preferred_table_name="logistica_seriales_asociados",
            )
            bodega_salida = self._resolve_named_column(context=context, preferred_terms=("bodega_salida",))
            if not table or not bodega_salida:
                return "", "inventory_association_missing_dictionary_column", {}
            detail_columns = self._resolve_inventory_detail_columns(
                context=context,
                preferred=("serial", "codigo", "fecha_asociacion", "asociado_a", "bodega_salida", "estado_asociacion"),
            )
            query = (
                f"SELECT {', '.join(detail_columns)} FROM {table} "
                f"WHERE {bodega_salida} IS NOT NULL LIMIT {limit}"
            )
            return query, "inventory_serial_association_departures", self._inventory_sql_metadata(
                table=table,
                columns=detail_columns,
                metric_used="association_departure",
                aggregation_used="detail",
                dimensions_used=[],
                concept_field="salidas_de_bodega_serializados",
            )

        if template_id == "inventory_entries_by_month":
            table = self._resolve_table_for_required_columns(
                context=context,
                required_columns=("fecha", "cantidad"),
                preferred_table_name="logistica_movimientos_entrada",
            )
            fecha_column = self._resolve_inventory_date_column(context=context, table_ref=table)
            cantidad_column = self._resolve_named_column(context=context, preferred_terms=("cantidad",))
            if not table or not fecha_column:
                return "", "inventory_entries_missing_dictionary_column", {}
            metric_sql = f"SUM({self._inventory_safe_quantity_sql(cantidad_column)})" if cantidad_column else "COUNT(*)"
            query = (
                f"SELECT MONTH({fecha_column}) AS mes, {metric_sql} AS total_entradas "
                f"{', SUM(' + self._inventory_invalid_quantity_sql(cantidad_column) + ') AS registros_cantidad_invalida' if cantidad_column else ''} "
                f"FROM {table} GROUP BY MONTH({fecha_column}) ORDER BY mes ASC LIMIT {limit}"
            )
            return query, "inventory_entries_by_month", self._inventory_sql_metadata(
                table=table,
                columns=[fecha_column, cantidad_column],
                metric_used="cantidad" if cantidad_column else "count",
                aggregation_used="sum" if cantidad_column else "count",
                dimensions_used=["mes"],
                concept_field="entradas",
            )

        if template_id == "inventory_movement_detail":
            filters = dict(resolved_query.normalized_filters or {})
            if str(filters.get("estado") or "").strip():
                table = self._resolve_table_for_required_columns(
                    context=context,
                    required_columns=("estado",),
                    preferred_table_name="logistica_base_seriales",
                )
                estado_column = self._resolve_named_column(context=context, preferred_terms=("estado",))
                if not table or not estado_column:
                    return "", "inventory_movement_missing_status_column", {}
                detail_columns = self._resolve_inventory_detail_columns(
                    context=context,
                    preferred=("serial", "codigo", "estado", "ubicacion", "fecha"),
                )
                date_column = self._resolve_inventory_date_column(context=context, table_ref=table)
                order_sql = f" ORDER BY {date_column} DESC" if date_column else ""
                query = (
                    f"SELECT {', '.join(detail_columns)} FROM {table} "
                    f"WHERE {estado_column} = '{self._escape_literal(str(filters.get('estado') or ''))}'"
                    f"{order_sql} LIMIT {limit}"
                )
                return (
                    query,
                    "inventory_movement_detail",
                    self._inventory_sql_metadata(
                        table=table,
                        columns=detail_columns,
                        metric_used="movement_detail",
                        aggregation_used="detail",
                        dimensions_used=[],
                        concept_field="movimientos_por_estado",
                    ),
                )
            table = self._resolve_primary_table(context=context)
            if not table:
                return "", "inventory_movement_missing_primary_table", {}
            detail_columns = self._resolve_inventory_detail_columns(
                context=context,
                preferred=("codigo", "cantidad", "fecha", "bodega", "responsable"),
            )
            codigo_column = self._resolve_named_column(context=context, preferred_terms=("codigo",))
            where_parts: list[str] = []
            if codigo_column and str(filters.get("codigo") or "").strip():
                where_parts.append(f"{codigo_column} = '{self._escape_literal(str(filters.get('codigo') or ''))}'")
            where_sql = (" WHERE " + " AND ".join(where_parts)) if where_parts else ""
            return (
                f"SELECT {', '.join(detail_columns)} FROM {table}{where_sql} LIMIT {limit}",
                "inventory_movement_detail",
                self._inventory_sql_metadata(
                    table=table,
                    columns=detail_columns,
                    metric_used="movement_detail",
                    aggregation_used="detail",
                    dimensions_used=[],
                    concept_field="movimientos",
                ),
            )

        return "", "inventory_sql_not_applicable", {}

    def _build_inventory_material_stock_sql(
        self,
        *,
        resolved_query: ResolvedQuerySpec,
        template_id: str,
        context: dict[str, Any],
        filters: dict[str, Any] | None = None,
        limit: int,
    ) -> tuple[str, str, dict[str, Any]]:
        catalog = self._inventory_table_mapping(
            context=context,
            table_name="base_codigos",
            required_columns=("codigo", "descripcion", "tipo"),
        )
        if not catalog.get("ok"):
            return "", str(catalog.get("reason") or "inventory_catalog_missing_dictionary_column"), dict(catalog.get("metadata") or {})

        if template_id == "inventory_material_critical_by_employee":
            return self._build_inventory_critical_materials_sql(
                resolved_query=resolved_query,
                context=context,
                filters=filters or {},
                limit=limit,
                catalog=catalog,
            )

        if template_id == "inventory_material_stock_grouped_dimension":
            return self._build_inventory_grouped_dimension_balance_sql(
                resolved_query=resolved_query,
                context=context,
                filters=filters or {},
                limit=limit,
            )

        if template_id == "inventory_material_stock_mobile" and self._inventory_should_group_balance_by_employee(
            resolved_query=resolved_query,
            filters=filters or {},
        ):
            query, reason, metadata = self._build_inventory_mobile_employee_balance_sql(
                resolved_query=resolved_query,
                context=context,
                filters=filters or {},
                limit=limit,
            )
            supplemental = self._inventory_build_unspecified_family_supplemental_queries(
                resolved_query=resolved_query,
                context=context,
                filters=filters or {},
                limit=limit,
            )
            if supplemental:
                metadata["supplemental_queries"] = supplemental
            return query, reason, metadata

        if template_id == "inventory_material_stock_mobile":
            movement = self._inventory_mobile_stock_subqueries(context=context, filters=filters or {})
            saldo_alias = "saldo_movil"
            concept = "stock_movil"
            dimensions: list[str] = []
        else:
            movement = self._inventory_material_stock_subqueries(
                context=context,
                by_warehouse=template_id == "inventory_material_stock_by_warehouse",
            )
            saldo_alias = "saldo_bodega" if template_id == "inventory_material_stock_by_warehouse" else "saldo_material"
            concept = "stock_bodega" if template_id == "inventory_material_stock_by_warehouse" else "stock_actual"
            dimensions = ["bodega"] if template_id == "inventory_material_stock_by_warehouse" else []
        if not movement.get("ok"):
            return "", str(movement.get("reason") or "inventory_stock_missing_dictionary_column"), dict(movement.get("metadata") or {})

        catalog_table = str(catalog["table"])
        catalog_cols = dict(catalog["columns"])
        codigo_catalog = str(catalog_cols["codigo"])
        descripcion_catalog = str(catalog_cols["descripcion"])
        tipo_catalog = str(catalog_cols["tipo"])
        dimension_select = "mov.bodega AS bodega, " if "bodega" in dimensions else ""
        dimension_group = "mov.bodega, " if "bodega" in dimensions else ""
        warehouse_filter = str((filters or {}).get("bodega") or "").strip()
        tipo_filter_sql = self._inventory_tipo_filter_sql(
            filters=filters or {},
            column_sql=f"cat.{tipo_catalog}",
        )
        where_parts: list[str] = []
        if warehouse_filter and "bodega" in dimensions:
            where_parts.append(f"mov.bodega = '{self._escape_literal(warehouse_filter)}'")
        if tipo_filter_sql:
            where_parts.append(tipo_filter_sql)
        where_sql = f"WHERE {' AND '.join(where_parts)} " if where_parts else ""
        query = (
            f"SELECT {dimension_select}mov.codigo AS codigo, "
            f"COALESCE(MAX(cat.{descripcion_catalog}), '') AS descripcion, "
            f"COALESCE(MAX(cat.{tipo_catalog}), '') AS tipo, "
            f"{self._inventory_employee_select_prefix(context=context, filters=filters or {})}"
            f"SUM(mov.entradas) AS entradas, "
            f"SUM(mov.entregas) AS entregas, "
            f"SUM(mov.devoluciones) AS devoluciones, "
            f"SUM(mov.consumos) AS consumos, "
            f"SUM(mov.cobros) AS cobros, "
            f"SUM(mov.traslados_otro_aliado) AS traslados_otro_aliado, "
            f"SUM(mov.traslados_bodega) AS traslados_bodega, "
            f"SUM(mov.entradas - mov.entregas + mov.devoluciones - mov.consumos - mov.cobros - mov.traslados_otro_aliado - mov.traslados_bodega) AS {saldo_alias}, "
            f"SUM(mov.registros_cantidad_invalida) AS registros_cantidad_invalida "
            f"FROM ({movement['sql']}) AS mov "
            f"LEFT JOIN {catalog_table} AS cat ON cat.{codigo_catalog} = mov.codigo "
            f"{self._inventory_employee_join_clause(context=context, filters=filters or {})}"
            f"{where_sql}"
            f"GROUP BY {dimension_group}mov.codigo "
            f"HAVING {saldo_alias} <> 0 OR registros_cantidad_invalida > 0 "
            f"ORDER BY {saldo_alias} ASC LIMIT {limit}"
        )
        columns = [
            *list(movement.get("columns") or []),
            codigo_catalog,
            descripcion_catalog,
            tipo_catalog,
        ]
        metadata = self._inventory_sql_metadata(
            table=str(movement.get("primary_table") or ""),
            columns=columns,
            metric_used=saldo_alias,
            aggregation_used="sum_movement_balance",
            dimensions_used=dimensions or ["codigo"],
            concept_field=concept,
        )
        metadata.update(
            {
                "tables_detected": sorted(set([*list(movement.get("tables") or []), catalog_table.split(".")[-1]])),
                "quantity_cast_policy": "case_when_regexp_then_cast_else_zero_report_invalid",
                "result_overflow_policy": "if_result_exceeds_1000_request_filter_grouping_or_export",
                "formula_used": (
                    "entregas - devoluciones - consumos - cobros"
                    if template_id == "inventory_material_stock_mobile"
                    else (
                        "entradas - entregas + devoluciones - cobros - traslados_otro_aliado +/- traslados_bodega"
                        if template_id == "inventory_material_stock_by_warehouse"
                        else "entradas_no_traslado_bodega - entregas + devoluciones - cobros - traslados_otro_aliado"
                    )
                ),
                "filters_applied": {
                    key: value
                    for key, value in {
                        "bodega": warehouse_filter if warehouse_filter and "bodega" in dimensions else "",
                        "tipo": (filters or {}).get("tipo"),
                    }.items()
                    if value not in ("", None, [], ())
                },
            }
        )
        enrichment_metadata = self._inventory_employee_enrichment_metadata(context=context, filters=filters or {})
        if enrichment_metadata:
            metadata["tables_detected"] = sorted(set([*list(metadata.get("tables_detected") or []), *list(enrichment_metadata.get("tables_detected") or [])]))
            metadata["columns_detected"] = sorted(set([*list(metadata.get("columns_detected") or []), *list(enrichment_metadata.get("columns_detected") or [])]))
            metadata["physical_columns_used"] = sorted(set([*list(metadata.get("physical_columns_used") or []), *list(enrichment_metadata.get("physical_columns_used") or [])]))
            metadata["relations_used"] = list(dict.fromkeys([*list(metadata.get("relations_used") or []), *list(enrichment_metadata.get("relations_used") or [])]))
            metadata["joins_used"] = list(dict.fromkeys([*list(metadata.get("joins_used") or []), *list(enrichment_metadata.get("joins_used") or [])]))
            metadata["employee_enrichment"] = dict(enrichment_metadata.get("employee_enrichment") or {})
        return query, template_id, metadata

    def _inventory_should_group_balance_by_employee(
        self,
        *,
        resolved_query: ResolvedQuerySpec,
        filters: dict[str, Any],
    ) -> bool:
        raw_query = str(resolved_query.intent.raw_query or "").strip().lower()
        group_by = {
            str(item or "").strip().lower()
            for item in list(resolved_query.intent.group_by or [])
            if str(item or "").strip()
        }
        has_specific_holder_filter = bool(str(filters.get("movil") or "").strip()) or bool(
            self._first_filter_value(
                filters=filters,
                keys=("cedula", "cedula_empleado", "identificacion", "documento", "id_empleado"),
            )
        )
        if any(token in raw_query for token in ("materiales criticos", "materiales críticos")):
            return True
        if any(
            token in raw_query
            for token in (
                "saldo por tecnico",
                "saldo por técnico",
                "saldo por empleado",
                "saldo por cedula",
                "inventario por cuadrilla",
                "inventario por brigada",
                "inventario por movil",
                "inventario por móvil",
            )
        ):
            return True
        if has_specific_holder_filter and "datos del empleado" in raw_query:
            return True
        if has_specific_holder_filter and not any(
            token in raw_query for token in ("saldo total", "total de materiales", "saldo total de materiales")
        ):
            return any(token in raw_query for token in ("inventario", "saldo"))
        if has_specific_holder_filter and any(token in raw_query for token in ("inventario", "saldo")):
            return True
        return bool(group_by & {"cedula", "movil"}) and bool(str(filters.get("bodega") or "").strip())

    @staticmethod
    def _inventory_has_explicit_material_family(raw_query: str) -> bool:
        normalized = str(raw_query or "").strip().lower()
        return any(
            token in normalized
            for token in ("materiales", "material ", "ferretero", "ferreteria", "seriales", "equipos", "equipo", "cpe", "imei", "mac")
        )

    def _inventory_requires_dual_inventory_blocks(
        self,
        *,
        resolved_query: ResolvedQuerySpec,
        filters: dict[str, Any],
    ) -> bool:
        raw_query = str(resolved_query.intent.raw_query or "").strip().lower()
        if not any(token in raw_query for token in ("inventario", "saldo")):
            return False
        if self._inventory_has_explicit_material_family(raw_query):
            return False
        has_holder_scope = bool(str(filters.get("movil") or "").strip()) or bool(
            self._first_filter_value(
                filters=filters,
                keys=("cedula", "cedula_empleado", "identificacion", "documento", "id_empleado"),
            )
        )
        group_by = {
            str(item or "").strip().lower()
            for item in list(resolved_query.intent.group_by or [])
            if str(item or "").strip()
        }
        return has_holder_scope or bool(group_by & {"movil", "cedula"})

    def _inventory_build_unspecified_family_supplemental_queries(
        self,
        *,
        resolved_query: ResolvedQuerySpec,
        context: dict[str, Any],
        filters: dict[str, Any],
        limit: int,
    ) -> list[dict[str, Any]]:
        if not self._inventory_requires_dual_inventory_blocks(
            resolved_query=resolved_query,
            filters=filters,
        ):
            return []
        query, reason, metadata = self._build_inventory_serial_employee_balance_sql(
            context=context,
            filters=filters,
            limit=limit,
        )
        if not query:
            return [
                {
                    "name": "serializados_equipos",
                    "reason": reason,
                    "skipped": True,
                    "metadata": metadata,
                }
            ]
        return [
            {
                "name": "serializados_equipos",
                "query": query,
                "reason": reason,
                "columns": [
                    "serial",
                    "codigo",
                    "descripcion",
                    "familia",
                    "estado",
                    "cedula",
                    "nombre",
                    "empleado",
                    "movil",
                    "estado_empleado",
                    "en_movil",
                    "en_base",
                    "cobros",
                    "saldo",
                ],
                "metadata": metadata,
            }
        ]

    def _build_inventory_mobile_employee_balance_sql(
        self,
        *,
        resolved_query: ResolvedQuerySpec,
        context: dict[str, Any],
        filters: dict[str, Any],
        limit: int,
    ) -> tuple[str, str, dict[str, Any]]:
        movement = self._inventory_mobile_employee_stock_subqueries(context=context, filters=filters)
        if not movement.get("ok"):
            return "", str(movement.get("reason") or "inventory_stock_missing_dictionary_column"), dict(movement.get("metadata") or {})
        personal = self._inventory_employee_mapping(context=context)
        catalog = self._inventory_table_mapping(
            context=context,
            table_name="base_codigos",
            required_columns=("codigo", "descripcion", "tipo"),
        )
        if not personal:
            return "", "inventory_employee_mapping_missing_dictionary_column", {}
        if not catalog.get("ok"):
            return "", str(catalog.get("reason") or "inventory_catalog_missing_dictionary_column"), dict(catalog.get("metadata") or {})
        cols = dict(personal.get("columns") or {})
        employee_table = str(personal.get("table") or "").strip()
        catalog_table = str(catalog.get("table") or "").strip()
        catalog_cols = dict(catalog.get("columns") or {})
        if not employee_table:
            return "", "inventory_employee_mapping_missing_dictionary_column", {}
        if not catalog_table:
            return "", "inventory_catalog_missing_dictionary_column", {}
        saldo_alias = "saldo"
        employee_where = self._inventory_employee_filter_clause(context=context, table_alias="p", filters=filters)
        employee_where_sql = f" WHERE {employee_where}" if employee_where else ""
        employee_label = self._inventory_employee_label_sql(
            nombre_sql="emp.nombre",
            apellido_sql="emp.apellido",
        )
        employee_subquery = (
            "SELECT "
            f"p.{cols['cedula']} AS cedula, "
            f"COALESCE(MAX(p.{cols['movil']}), '') AS movil, "
            f"COALESCE(MAX(p.{cols['nombre']}), '') AS nombre, "
            f"COALESCE(MAX(p.{cols['apellido']}), '') AS apellido, "
            f"COALESCE(MAX(p.{cols['estado']}), '') AS estado_empleado "
            f"FROM {employee_table} AS p"
            f"{employee_where_sql} "
            f"GROUP BY p.{cols['cedula']}"
        )
        tipo_filter_sql = self._inventory_tipo_filter_sql(
            filters=filters,
            column_sql=f"cat.{catalog_cols['tipo']}",
        )
        where_sql = f" WHERE {tipo_filter_sql} " if tipo_filter_sql else ""
        query = (
            "SELECT "
            "mov.codigo AS codigo, "
            f"COALESCE(MAX(cat.{catalog_cols['descripcion']}), '') AS descripcion, "
            f"COALESCE(MAX(cat.{catalog_cols['tipo']}), '') AS tipo, "
            f"mov.cedula AS cedula, "
            "COALESCE(MAX(emp.nombre), '') AS nombre, "
            f"{employee_label} AS empleado, "
            "COALESCE(MAX(emp.movil), '') AS movil, "
            "COALESCE(MAX(emp.estado_empleado), '') AS estado_empleado, "
            "SUM(mov.entregas) AS entregas, "
            "SUM(mov.devoluciones) AS devoluciones, "
            "SUM(mov.consumos) AS consumos, "
            "SUM(mov.cobros) AS cobros, "
            f"SUM(mov.entregas - mov.devoluciones - mov.consumos - mov.cobros) AS {saldo_alias}, "
            f"SUM(mov.registros_cantidad_invalida) AS registros_cantidad_invalida "
            f"FROM ({movement['sql']}) AS mov "
            f"LEFT JOIN ({employee_subquery}) AS emp ON emp.cedula = mov.cedula "
            f"LEFT JOIN {catalog_table} AS cat ON cat.{catalog_cols['codigo']} = mov.codigo "
            f"{where_sql}"
            "GROUP BY mov.codigo, mov.cedula, COALESCE(emp.movil, '') "
            f"ORDER BY movil ASC, mov.cedula ASC, mov.codigo ASC LIMIT {limit}"
        )
        metadata = self._inventory_sql_metadata(
            table=str(movement.get("primary_table") or ""),
            columns=[*list(movement.get("columns") or []), *list(cols.values()), *list(catalog_cols.values())],
            metric_used=saldo_alias,
            aggregation_used="sum_movement_balance_by_employee_code",
            dimensions_used=["movil", "cedula", "codigo"],
            concept_field="stock_movil",
        )
        metadata.update(
            {
                "tables_detected": sorted(
                    set([*list(movement.get("tables") or []), employee_table.split(".")[-1], catalog_table.split(".")[-1]])
                ),
                "quantity_cast_policy": "case_when_regexp_then_cast_else_zero_report_invalid",
                "formula_used": "saldo = entregas - devoluciones - consumos - cobros",
                "balance_filter_policy": "include_positive_zero_negative",
                "filters_applied": {
                    key: value
                    for key, value in {
                        "bodega": str(filters.get("bodega") or "").strip(),
                        "movil": str(filters.get("movil") or "").strip(),
                        "cedula": self._first_filter_value(
                            filters=filters,
                            keys=("cedula", "cedula_empleado", "identificacion", "documento", "id_empleado"),
                        ),
                        "tipo": filters.get("tipo"),
                    }.items()
                    if value not in ("", None, [], ())
                },
                "employee_stock_detail": True,
            }
        )
        metadata["joins_used"] = list(
            dict.fromkeys(
                [
                    *list(metadata.get("joins_used") or []),
                    "employee_detail_by_cedula",
                    "catalog_by_codigo",
                ]
            )
        )
        return query, "inventory_material_stock_mobile", metadata

    def _build_inventory_grouped_dimension_balance_sql(
        self,
        *,
        resolved_query: ResolvedQuerySpec,
        context: dict[str, Any],
        filters: dict[str, Any],
        limit: int,
    ) -> tuple[str, str, dict[str, Any]]:
        grouping_dimension = str(
            filters.get("grouping_dimension")
            or next(
                (
                    item
                    for item in list(resolved_query.intent.group_by or [])
                    if str(item or "").strip().lower() in {"movil", "cedula", "bodega"}
                ),
                "",
            )
            or ""
        ).strip().lower()
        if grouping_dimension in {"cuadrilla", "brigada"}:
            grouping_dimension = "movil"
        if grouping_dimension == "bodega":
            return self._build_inventory_grouped_warehouse_balance_sql(
                context=context,
                filters=filters,
                limit=limit,
            )
        return self._build_inventory_grouped_holder_dimension_balance_sql(
            context=context,
            filters=filters,
            grouping_dimension=grouping_dimension or "movil",
            limit=limit,
        )

    def _build_inventory_grouped_holder_dimension_balance_sql(
        self,
        *,
        context: dict[str, Any],
        filters: dict[str, Any],
        grouping_dimension: str,
        limit: int,
    ) -> tuple[str, str, dict[str, Any]]:
        movement = self._inventory_mobile_employee_stock_subqueries(context=context, filters={})
        if not movement.get("ok"):
            return "", str(movement.get("reason") or "inventory_stock_missing_dictionary_column"), dict(movement.get("metadata") or {})
        personal = self._inventory_employee_mapping(context=context)
        catalog = self._inventory_table_mapping(
            context=context,
            table_name="base_codigos",
            required_columns=("codigo", "descripcion", "tipo"),
        )
        if not personal:
            return "", "inventory_employee_mapping_missing_dictionary_column", {}
        if not catalog.get("ok"):
            return "", str(catalog.get("reason") or "inventory_catalog_missing_dictionary_column"), dict(catalog.get("metadata") or {})

        cols = dict(personal.get("columns") or {})
        employee_table = str(personal.get("table") or "").strip()
        catalog_table = str(catalog.get("table") or "").strip()
        catalog_cols = dict(catalog.get("columns") or {})
        employee_label = self._inventory_employee_label_sql(
            nombre_sql="emp.nombre",
            apellido_sql="emp.apellido",
        )
        employee_subquery = (
            "SELECT "
            f"p.{cols['cedula']} AS cedula, "
            f"COALESCE(MAX(p.{cols['movil']}), '') AS movil, "
            f"COALESCE(MAX(p.{cols['nombre']}), '') AS nombre, "
            f"COALESCE(MAX(p.{cols['apellido']}), '') AS apellido, "
            f"COALESCE(MAX(p.{cols['estado']}), '') AS estado_empleado "
            f"FROM {employee_table} AS p "
            f"GROUP BY p.{cols['cedula']}"
        )

        dimension_select = "COALESCE(MAX(emp.movil), '')"
        dimension_group = "COALESCE(emp.movil, '')"
        extra_dimension_columns = (
            "'' AS cedula, '' AS nombre, '' AS empleado, COALESCE(MAX(emp.movil), '') AS movil, '' AS bodega, "
        )
        if grouping_dimension == "cedula":
            dimension_select = "mov.cedula"
            dimension_group = "mov.cedula"
            extra_dimension_columns = (
                "mov.cedula AS cedula, "
                "COALESCE(MAX(emp.nombre), '') AS nombre, "
                f"{employee_label} AS empleado, "
                "COALESCE(MAX(emp.movil), '') AS movil, "
                "'' AS bodega, "
            )

        where_parts: list[str] = []
        tipo_filter_sql = self._inventory_tipo_filter_sql(
            filters=filters,
            column_sql=f"cat.{catalog_cols['tipo']}",
        )
        if tipo_filter_sql:
            where_parts.append(tipo_filter_sql)
        codigo_value = self._first_filter_value(
            filters=filters,
            keys=("codigo", "codigo_material", "material_codigo"),
        )
        if codigo_value:
            where_parts.append(f"mov.codigo = '{self._escape_literal(codigo_value)}'")
        description_filter_sql = self._inventory_catalog_description_filter_sql(
            filters=filters,
            column_sql=f"cat.{catalog_cols['descripcion']}",
        )
        if description_filter_sql:
            where_parts.append(description_filter_sql)
        where_sql = f" WHERE {' AND '.join(where_parts)} " if where_parts else ""

        query = (
            "SELECT "
            f"{dimension_select} AS dimension, "
            f"{extra_dimension_columns}"
            "mov.codigo AS codigo, "
            f"COALESCE(MAX(cat.{catalog_cols['descripcion']}), '') AS descripcion, "
            f"COALESCE(MAX(cat.{catalog_cols['tipo']}), '') AS tipo, "
            "SUM(mov.entregas) AS entregas, "
            "SUM(mov.devoluciones) AS devoluciones, "
            "SUM(mov.consumos) AS consumos, "
            "SUM(mov.cobros) AS cobros, "
            "SUM(mov.entregas - mov.devoluciones - mov.consumos - mov.cobros) AS saldo, "
            "SUM(mov.registros_cantidad_invalida) AS registros_cantidad_invalida "
            f"FROM ({movement['sql']}) AS mov "
            f"LEFT JOIN ({employee_subquery}) AS emp ON emp.cedula = mov.cedula "
            f"LEFT JOIN {catalog_table} AS cat ON cat.{catalog_cols['codigo']} = mov.codigo "
            f"{where_sql}"
            f"GROUP BY {dimension_group}, mov.codigo "
            "ORDER BY dimension ASC, saldo DESC, mov.codigo ASC "
            f"LIMIT {limit}"
        )
        metadata = self._inventory_sql_metadata(
            table=str(movement.get("primary_table") or ""),
            columns=[*list(movement.get("columns") or []), *list(cols.values()), *list(catalog_cols.values())],
            metric_used="saldo",
            aggregation_used=f"sum_movement_balance_by_{grouping_dimension}_code",
            dimensions_used=[grouping_dimension, "codigo"],
            concept_field=f"stock_agrupado_por_{grouping_dimension}",
        )
        metadata.update(
            {
                "tables_detected": sorted(
                    set([*list(movement.get("tables") or []), employee_table.split(".")[-1], catalog_table.split(".")[-1]])
                ),
                "quantity_cast_policy": "case_when_regexp_then_cast_else_zero_report_invalid",
                "formula_used": "saldo = entregas - devoluciones - consumos - cobros",
                "balance_filter_policy": "include_positive_zero_negative",
                "filters_applied": {
                    key: value
                    for key, value in {
                        "codigo": codigo_value,
                        "descripcion": str(filters.get("descripcion") or "").strip(),
                        "tipo": filters.get("tipo"),
                        "grouping_dimension": grouping_dimension,
                    }.items()
                    if value not in ("", None, [], ())
                },
                "grouped_dimension_balance": True,
                "grouping_dimension": grouping_dimension,
            }
        )
        metadata["joins_used"] = list(
            dict.fromkeys(
                [
                    *list(metadata.get("joins_used") or []),
                    "employee_detail_by_cedula",
                    "catalog_by_codigo",
                ]
            )
        )
        return query, "inventory_material_stock_grouped_dimension", metadata

    def _build_inventory_grouped_warehouse_balance_sql(
        self,
        *,
        context: dict[str, Any],
        filters: dict[str, Any],
        limit: int,
    ) -> tuple[str, str, dict[str, Any]]:
        movement = self._inventory_material_stock_subqueries(context=context, by_warehouse=True)
        if not movement.get("ok"):
            return "", str(movement.get("reason") or "inventory_stock_missing_dictionary_column"), dict(movement.get("metadata") or {})
        catalog = self._inventory_table_mapping(
            context=context,
            table_name="base_codigos",
            required_columns=("codigo", "descripcion", "tipo"),
        )
        if not catalog.get("ok"):
            return "", str(catalog.get("reason") or "inventory_catalog_missing_dictionary_column"), dict(catalog.get("metadata") or {})

        catalog_table = str(catalog["table"])
        catalog_cols = dict(catalog["columns"])
        where_parts: list[str] = []
        tipo_filter_sql = self._inventory_tipo_filter_sql(
            filters=filters,
            column_sql=f"cat.{catalog_cols['tipo']}",
        )
        if tipo_filter_sql:
            where_parts.append(tipo_filter_sql)
        codigo_value = self._first_filter_value(
            filters=filters,
            keys=("codigo", "codigo_material", "material_codigo"),
        )
        if codigo_value:
            where_parts.append(f"mov.codigo = '{self._escape_literal(codigo_value)}'")
        description_filter_sql = self._inventory_catalog_description_filter_sql(
            filters=filters,
            column_sql=f"cat.{catalog_cols['descripcion']}",
        )
        if description_filter_sql:
            where_parts.append(description_filter_sql)
        where_sql = f"WHERE {' AND '.join(where_parts)} " if where_parts else ""
        query = (
            "SELECT "
            "mov.bodega AS dimension, "
            "'' AS cedula, '' AS nombre, '' AS empleado, '' AS movil, mov.bodega AS bodega, "
            "mov.codigo AS codigo, "
            f"COALESCE(MAX(cat.{catalog_cols['descripcion']}), '') AS descripcion, "
            f"COALESCE(MAX(cat.{catalog_cols['tipo']}), '') AS tipo, "
            "SUM(mov.entregas) AS entregas, "
            "SUM(mov.devoluciones) AS devoluciones, "
            "SUM(mov.consumos) AS consumos, "
            "SUM(mov.cobros) AS cobros, "
            "SUM(mov.entradas - mov.entregas + mov.devoluciones - mov.consumos - mov.cobros - mov.traslados_otro_aliado - mov.traslados_bodega) AS saldo, "
            "SUM(mov.registros_cantidad_invalida) AS registros_cantidad_invalida "
            f"FROM ({movement['sql']}) AS mov "
            f"LEFT JOIN {catalog_table} AS cat ON cat.{catalog_cols['codigo']} = mov.codigo "
            f"{where_sql}"
            "GROUP BY mov.bodega, mov.codigo "
            "ORDER BY dimension ASC, saldo DESC, mov.codigo ASC "
            f"LIMIT {limit}"
        )
        metadata = self._inventory_sql_metadata(
            table=str(movement.get("primary_table") or ""),
            columns=[*list(movement.get("columns") or []), *list(catalog_cols.values())],
            metric_used="saldo",
            aggregation_used="sum_movement_balance_by_bodega_code",
            dimensions_used=["bodega", "codigo"],
            concept_field="stock_agrupado_por_bodega",
        )
        metadata.update(
            {
                "tables_detected": sorted(set([*list(movement.get("tables") or []), catalog_table.split(".")[-1]])),
                "quantity_cast_policy": "case_when_regexp_then_cast_else_zero_report_invalid",
                "formula_used": "entradas - entregas + devoluciones - consumos - cobros - traslados_otro_aliado - traslados_bodega",
                "balance_filter_policy": "include_positive_zero_negative",
                "filters_applied": {
                    key: value
                    for key, value in {
                        "codigo": codigo_value,
                        "descripcion": str(filters.get("descripcion") or "").strip(),
                        "tipo": filters.get("tipo"),
                        "grouping_dimension": "bodega",
                    }.items()
                    if value not in ("", None, [], ())
                },
                "grouped_dimension_balance": True,
                "grouping_dimension": "bodega",
            }
        )
        return query, "inventory_material_stock_grouped_dimension", metadata

    def _inventory_catalog_description_filter_sql(
        self,
        *,
        filters: dict[str, Any],
        column_sql: str,
    ) -> str:
        description_value = str(filters.get("descripcion") or "").strip()
        if not description_value:
            return ""
        return f"UPPER(COALESCE({column_sql}, '')) LIKE '%{self._escape_literal(description_value.upper())}%'"

    def _inventory_serial_family_filter_sql(
        self,
        *,
        filters: dict[str, Any],
        column_sql: str,
    ) -> str:
        family_value = str(filters.get("material_family") or "").strip()
        if not family_value:
            return ""
        match_mode = str(filters.get("material_family_match_mode") or "contains").strip().lower()
        normalized_column = f"UPPER(TRIM(COALESCE({column_sql}, '')))"
        escaped_value = self._escape_literal(family_value.upper())
        if match_mode == "exact":
            return f"{normalized_column} = '{escaped_value}'"
        return f"{normalized_column} LIKE '%{escaped_value}%'"

    def _build_inventory_serial_employee_balance_sql(
        self,
        *,
        context: dict[str, Any],
        filters: dict[str, Any],
        limit: int,
    ) -> tuple[str, str, dict[str, Any]]:
        serial_mapping = self._inventory_table_mapping(
            context=context,
            table_name="logistica_base_seriales",
            required_columns=("numero_serial", "codigo", "estado", "cedula"),
        )
        personal = self._inventory_employee_mapping(context=context)
        catalog = self._inventory_table_mapping(
            context=context,
            table_name="base_codigo_seriales",
            required_columns=("codigo", "descripcion", "familia"),
        )
        if not serial_mapping.get("ok"):
            return "", str(serial_mapping.get("reason") or "inventory_serial_holder_missing_dictionary_column"), dict(serial_mapping.get("metadata") or {})
        if not personal:
            return "", "inventory_employee_mapping_missing_dictionary_column", {}
        if not catalog.get("ok"):
            return "", str(catalog.get("reason") or "inventory_serial_catalog_missing_dictionary_column"), dict(catalog.get("metadata") or {})
        serial_cols = dict(serial_mapping.get("columns") or {})
        employee_cols = dict(personal.get("columns") or {})
        catalog_cols = dict(catalog.get("columns") or {})
        serial_edit_col = self._inventory_optional_table_column(
            context=context,
            table_name="logistica_base_seriales",
            logical_names=("edit",),
            column_names=("edit",),
        )
        serial_table = str(serial_mapping.get("table") or "").strip()
        employee_table = str(personal.get("table") or "").strip()
        catalog_table = str(catalog.get("table") or "").strip()
        if not serial_table or not employee_table or not catalog_table:
            return "", "inventory_serial_holder_missing_dictionary_column", {}
        serial_where = self._inventory_operational_filter_clause(
            context=context,
            table_ref=serial_table,
            filters=filters,
            table_alias="s",
        )
        warehouse_filter = str(filters.get("bodega") or "").strip()
        where_parts: list[str] = []
        if serial_where:
            where_parts.append(serial_where)
        if warehouse_filter and serial_cols.get("bodega"):
            where_parts.append(f"s.{serial_cols['bodega']} = '{self._escape_literal(warehouse_filter)}'")
        where_sql = f"WHERE {' AND '.join(where_parts)} " if where_parts else ""
        employee_where = self._inventory_employee_filter_clause(context=context, table_alias="p", filters=filters)
        employee_where_sql = f" WHERE {employee_where}" if employee_where else ""
        employee_subquery = (
            "SELECT "
            f"p.{employee_cols['cedula']} AS cedula, "
            f"COALESCE(MAX(p.{employee_cols['movil']}), '') AS movil, "
            f"COALESCE(MAX(p.{employee_cols['nombre']}), '') AS nombre, "
            f"COALESCE(MAX(p.{employee_cols['apellido']}), '') AS apellido, "
            f"COALESCE(MAX(p.{employee_cols['estado']}), '') AS estado_empleado "
            f"FROM {employee_table} AS p"
            f"{employee_where_sql} "
            f"GROUP BY p.{employee_cols['cedula']}"
        )
        fallback_join_sql = (
            f"LEFT JOIN ({employee_subquery}) AS emp_edit ON emp_edit.cedula = s.{serial_edit_col} "
            if serial_edit_col
            else ""
        )
        resolved_nombre_sql = (
            "COALESCE(MAX(emp.nombre), MAX(emp_edit.nombre), '')"
            if serial_edit_col
            else "COALESCE(MAX(emp.nombre), '')"
        )
        resolved_dimension_movil_sql = (
            "COALESCE(emp.movil, emp_edit.movil, '')"
            if serial_edit_col
            else "COALESCE(emp.movil, '')"
        )
        resolved_apellido_sql = (
            "COALESCE(MAX(emp.apellido), MAX(emp_edit.apellido), '')"
            if serial_edit_col
            else "COALESCE(MAX(emp.apellido), '')"
        )
        resolved_movil_sql = (
            "COALESCE(MAX(emp.movil), MAX(emp_edit.movil), '')"
            if serial_edit_col
            else "COALESCE(MAX(emp.movil), '')"
        )
        resolved_estado_sql = (
            "COALESCE(MAX(emp.estado_empleado), MAX(emp_edit.estado_empleado), '')"
            if serial_edit_col
            else "COALESCE(MAX(emp.estado_empleado), '')"
        )
        employee_label = self._inventory_employee_label_sql(
            nombre_sql=resolved_nombre_sql,
            apellido_sql=resolved_apellido_sql,
        )
        estado_expr = f"UPPER(COALESCE(s.{serial_cols['estado']}, ''))"
        en_movil_sql = f"CASE WHEN {estado_expr} LIKE '%MOVIL%' THEN 1 ELSE 0 END"
        en_base_sql = f"CASE WHEN {estado_expr} LIKE '%BASE%' OR {estado_expr} LIKE '%BODEGA%' THEN 1 ELSE 0 END"
        cobro_sql = f"CASE WHEN {estado_expr} LIKE '%COBRO%' THEN 1 ELSE 0 END"
        query = (
            "SELECT "
            f"s.{serial_cols['numero_serial']} AS serial, "
            f"s.{serial_cols['codigo']} AS codigo, "
            f"COALESCE(MAX(cat.{catalog_cols['descripcion']}), '') AS descripcion, "
            f"COALESCE(MAX(cat.{catalog_cols['familia']}), '') AS familia, "
            f"COALESCE(MAX(s.{serial_cols['estado']}), '') AS estado, "
            f"s.{serial_cols['cedula']} AS cedula, "
            f"{resolved_nombre_sql} AS nombre, "
            f"{employee_label} AS empleado, "
            f"{resolved_movil_sql} AS movil, "
            f"{resolved_estado_sql} AS estado_empleado, "
            f"SUM({en_movil_sql}) AS en_movil, "
            f"SUM({en_base_sql}) AS en_base, "
            f"SUM({cobro_sql}) AS cobros, "
            f"SUM({en_movil_sql} + {en_base_sql} - {cobro_sql}) AS saldo "
            f"FROM {serial_table} AS s "
            f"LEFT JOIN ({employee_subquery}) AS emp ON emp.cedula = s.{serial_cols['cedula']} "
            f"{fallback_join_sql}"
            f"LEFT JOIN {catalog_table} AS cat ON cat.{catalog_cols['codigo']} = s.{serial_cols['codigo']} "
            f"{where_sql}"
            f"GROUP BY s.{serial_cols['numero_serial']}, s.{serial_cols['codigo']}, s.{serial_cols['cedula']}, {resolved_dimension_movil_sql} "
            "ORDER BY movil ASC, cedula ASC, codigo ASC, serial ASC "
            f"LIMIT {limit}"
        )
        metadata = self._inventory_sql_metadata(
            table=serial_table,
            columns=[
                *list(serial_cols.values()),
                *list(employee_cols.values()),
                *list(catalog_cols.values()),
            ],
            metric_used="saldo",
            aggregation_used="serial_state_balance_by_employee_serial",
            dimensions_used=["movil", "cedula", "codigo", "serial"],
            concept_field="stock_serializado",
        )
        metadata.update(
            {
                "tables_detected": sorted(
                    set([serial_table.split(".")[-1], employee_table.split(".")[-1], catalog_table.split(".")[-1]])
                ),
                "formula_used": "saldo = en_movil + en_base - cobros",
                "balance_filter_policy": "include_positive_zero_negative",
                "serial_rules": {
                    "en_movil": "estado contiene MOVIL",
                    "en_base": "estado contiene BASE o BODEGA",
                    "cobros": "estado contiene COBRO",
                },
                "filters_applied": {
                    key: value
                    for key, value in {
                        "bodega": warehouse_filter,
                        "movil": str(filters.get("movil") or "").strip(),
                        "cedula": self._first_filter_value(
                            filters=filters,
                            keys=("cedula", "cedula_empleado", "identificacion", "documento", "id_empleado"),
                        ),
                    }.items()
                    if value
                },
                "employee_stock_detail": True,
                "state_employee_included": True,
                "employee_enrichment_fallback_by_edit": bool(serial_edit_col),
            }
        )
        metadata["joins_used"] = [
            "employee_detail_by_cedula",
            *([ "employee_detail_by_edit_fallback" ] if serial_edit_col else []),
            "serial_catalog_by_codigo",
        ]
        return query, "inventory_serial_employee_balance", metadata

    def _build_inventory_serial_family_grouped_dimension_sql(
        self,
        *,
        context: dict[str, Any],
        filters: dict[str, Any],
        group_by: list[str],
        limit: int,
    ) -> tuple[str, str, dict[str, Any]]:
        serial_mapping = self._inventory_table_mapping(
            context=context,
            table_name="logistica_base_seriales",
            required_columns=("numero_serial", "codigo", "estado", "cedula", "bodega"),
        )
        personal = self._inventory_employee_mapping(context=context)
        catalog = self._inventory_table_mapping(
            context=context,
            table_name="base_codigo_seriales",
            required_columns=("codigo", "descripcion", "familia"),
        )
        if not serial_mapping.get("ok"):
            return "", str(serial_mapping.get("reason") or "inventory_serial_holder_missing_dictionary_column"), dict(serial_mapping.get("metadata") or {})
        if not personal:
            return "", "inventory_employee_mapping_missing_dictionary_column", {}
        if not catalog.get("ok"):
            return "", str(catalog.get("reason") or "inventory_serial_catalog_missing_dictionary_column"), dict(catalog.get("metadata") or {})
        family_value = str(filters.get("material_family") or "").strip().upper()
        if not family_value:
            return "", "inventory_serial_family_missing_filter", {}
        serial_cols = dict(serial_mapping.get("columns") or {})
        employee_cols = dict(personal.get("columns") or {})
        catalog_cols = dict(catalog.get("columns") or {})
        serial_edit_col = self._inventory_optional_table_column(
            context=context,
            table_name="logistica_base_seriales",
            logical_names=("edit",),
            column_names=("edit",),
        )
        serial_table = str(serial_mapping.get("table") or "").strip()
        employee_table = str(personal.get("table") or "").strip()
        catalog_table = str(catalog.get("table") or "").strip()
        if not serial_table or not employee_table or not catalog_table:
            return "", "inventory_serial_holder_missing_dictionary_column", {}

        dimension_name = next(
            (
                str(item or "").strip().lower()
                for item in group_by
                if str(item or "").strip().lower() in {"movil", "cedula", "bodega"}
            ),
            str(filters.get("grouping_dimension") or "").strip().lower() or "movil",
        )
        if dimension_name not in {"movil", "cedula", "bodega"}:
            return "", "inventory_serial_stock_dimension_not_validated", {
                "compiler": "inventory_semantic_sql",
                "compiler_used": "inventory_semantic_sql",
                "fallback_reason": "inventory_serial_stock_dimension_not_validated",
                "db_alias": "logistica_cinco",
            }

        employee_subquery = (
            "SELECT "
            f"p.{employee_cols['cedula']} AS cedula, "
            f"COALESCE(MAX(p.{employee_cols['movil']}), '') AS movil, "
            f"COALESCE(MAX(p.{employee_cols['nombre']}), '') AS nombre, "
            f"COALESCE(MAX(p.{employee_cols['apellido']}), '') AS apellido, "
            f"COALESCE(MAX(p.{employee_cols['estado']}), '') AS estado_empleado "
            f"FROM {employee_table} AS p "
            f"GROUP BY p.{employee_cols['cedula']}"
        )
        fallback_join_sql = (
            f"LEFT JOIN ({employee_subquery}) AS emp_edit ON emp_edit.cedula = s.{serial_edit_col} "
            if serial_edit_col
            else ""
        )
        resolved_dimension_movil_sql = (
            "COALESCE(emp.movil, emp_edit.movil, '')" if serial_edit_col else "COALESCE(emp.movil, '')"
        )
        resolved_cedula_sql = (
            f"COALESCE(emp.cedula, emp_edit.cedula, CAST(s.{serial_cols['cedula']} AS CHAR), CAST(s.{serial_edit_col} AS CHAR), '')"
            if serial_edit_col
            else f"CAST(s.{serial_cols['cedula']} AS CHAR)"
        )
        resolved_nombre_sql = (
            "COALESCE(MAX(emp.nombre), MAX(emp_edit.nombre), '')"
            if serial_edit_col
            else "COALESCE(MAX(emp.nombre), '')"
        )
        resolved_apellido_sql = (
            "COALESCE(MAX(emp.apellido), MAX(emp_edit.apellido), '')"
            if serial_edit_col
            else "COALESCE(MAX(emp.apellido), '')"
        )
        resolved_estado_sql = (
            "COALESCE(MAX(emp.estado_empleado), MAX(emp_edit.estado_empleado), '')"
            if serial_edit_col
            else "COALESCE(MAX(emp.estado_empleado), '')"
        )
        employee_label = self._inventory_employee_label_sql(
            nombre_sql=resolved_nombre_sql,
            apellido_sql=resolved_apellido_sql,
        )
        if dimension_name == "movil":
            dimension_sql = resolved_dimension_movil_sql
            cedula_sql = resolved_cedula_sql
            empleado_sql = employee_label
            movil_sql = resolved_dimension_movil_sql
            bodega_sql = "''"
        elif dimension_name == "cedula":
            dimension_sql = resolved_cedula_sql
            cedula_sql = resolved_cedula_sql
            empleado_sql = employee_label
            movil_sql = resolved_dimension_movil_sql
            bodega_sql = "''"
        else:
            dimension_sql = f"COALESCE(s.{serial_cols['bodega']}, '')"
            cedula_sql = "''"
            empleado_sql = "''"
            movil_sql = "''"
            bodega_sql = f"COALESCE(s.{serial_cols['bodega']}, '')"

        estado_expr = f"UPPER(COALESCE(s.{serial_cols['estado']}, ''))"
        en_movil_sql = f"CASE WHEN {estado_expr} LIKE '%MOVIL%' THEN 1 ELSE 0 END"
        en_base_sql = f"CASE WHEN {estado_expr} LIKE '%BASE%' OR {estado_expr} LIKE '%BODEGA%' THEN 1 ELSE 0 END"
        cobro_sql = f"CASE WHEN {estado_expr} LIKE '%COBRO%' THEN 1 ELSE 0 END"
        serial_column = f"s.{serial_cols['numero_serial']}"
        family_filter_sql = self._inventory_serial_family_filter_sql(
            filters=filters,
            column_sql=f"cat.{catalog_cols['familia']}",
        )
        where_parts = [family_filter_sql] if family_filter_sql else []
        where_parts.append(f"UPPER(TRIM(COALESCE(s.{serial_cols['estado']}, ''))) LIKE '%MOVIL%'")
        where_sql = f"WHERE {' AND '.join(where_parts)} " if where_parts else ""
        group_by_sql = (
            f"{dimension_sql}, {resolved_cedula_sql}, {resolved_dimension_movil_sql}, "
            f"s.{serial_cols['codigo']}, cat.{catalog_cols['descripcion']}, cat.{catalog_cols['familia']}"
            if dimension_name in {"movil", "cedula"}
            else f"{dimension_sql}, s.{serial_cols['codigo']}, cat.{catalog_cols['descripcion']}, cat.{catalog_cols['familia']}"
        )
        query = (
            "SELECT "
            f"{dimension_sql} AS dimension, "
            f"{cedula_sql} AS cedula, "
            f"{resolved_nombre_sql} AS nombre, "
            f"{resolved_apellido_sql} AS apellido, "
            f"{empleado_sql} AS empleado, "
            f"{movil_sql} AS movil, "
            f"{resolved_estado_sql} AS estado_empleado, "
            f"{bodega_sql} AS bodega, "
            f"s.{serial_cols['codigo']} AS codigo, "
            f"COALESCE(MAX(cat.{catalog_cols['descripcion']}), '') AS descripcion, "
            f"COALESCE(MAX(cat.{catalog_cols['familia']}), '') AS familia, "
            f"COUNT(DISTINCT {serial_column}) AS seriales_total, "
            f"GROUP_CONCAT(DISTINCT {resolved_cedula_sql} ORDER BY {resolved_cedula_sql} SEPARATOR '; ') AS cedulas_asociadas, "
            f"SUM({en_movil_sql}) AS en_movil, "
            f"SUM({en_base_sql}) AS en_base, "
            f"SUM({cobro_sql}) AS cobros, "
            f"SUM({en_movil_sql} + {en_base_sql} - {cobro_sql}) AS saldo "
            f"FROM {serial_table} AS s "
            f"LEFT JOIN ({employee_subquery}) AS emp ON emp.cedula = s.{serial_cols['cedula']} "
            f"{fallback_join_sql}"
            f"LEFT JOIN {catalog_table} AS cat ON cat.{catalog_cols['codigo']} = s.{serial_cols['codigo']} "
            f"{where_sql}"
            f"GROUP BY {group_by_sql} "
            "ORDER BY movil ASC, cedula ASC, codigo ASC "
            f"LIMIT {limit}"
        )
        metadata = self._inventory_sql_metadata(
            table=serial_table,
            columns=[
                *list(serial_cols.values()),
                *list(employee_cols.values()),
                *list(catalog_cols.values()),
            ],
            metric_used="saldo_serializado",
            aggregation_used="serial_family_balance_by_dimension_and_code",
            dimensions_used=[dimension_name, "codigo", "familia"],
            concept_field="stock_serializado_familia_dimension",
        )
        metadata.update(
            {
                "tables_detected": sorted(
                    set([serial_table.split(".")[-1], employee_table.split(".")[-1], catalog_table.split(".")[-1]])
                ),
                "formula_used": "saldo = en_movil + en_base - cobros",
                "balance_filter_policy": "include_positive_zero_negative",
                "serial_rules": {
                    "en_movil": "estado contiene MOVIL",
                    "en_base": "estado contiene BASE o BODEGA",
                    "cobros": "estado contiene COBRO",
                },
                "filters_applied": {
                    "material_family": family_value,
                    "material_family_match_mode": str(filters.get("material_family_match_mode") or "contains"),
                    "grouping_dimension": dimension_name,
                    "estado": "MOVIL",
                },
                "grouping_dimension": dimension_name,
                "catalog_family_exists": True,
                "catalog_family_column": "base_codigo_seriales.familia",
                "catalog_family_match_mode": str(filters.get("material_family_match_mode") or "contains"),
                "serial_state_filter": "MOVIL",
                "employee_enrichment_fallback_by_edit": bool(serial_edit_col),
            }
        )
        metadata["joins_used"] = [
            "employee_detail_by_cedula",
            *([ "employee_detail_by_edit_fallback" ] if serial_edit_col else []),
            "serial_catalog_by_codigo",
        ]
        return query, "inventory_serial_stock_by_family_grouped_dimension", metadata

    def _build_inventory_critical_materials_sql(
        self,
        *,
        resolved_query: ResolvedQuerySpec,
        context: dict[str, Any],
        filters: dict[str, Any],
        limit: int,
        catalog: dict[str, Any],
    ) -> tuple[str, str, dict[str, Any]]:
        movement = self._inventory_mobile_employee_stock_subqueries(context=context, filters=filters)
        if not movement.get("ok"):
            return "", str(movement.get("reason") or "inventory_stock_missing_dictionary_column"), dict(movement.get("metadata") or {})
        recent_consumption = self._inventory_recent_consumption_subquery(context=context, filters=filters)
        if not recent_consumption.get("ok"):
            return "", str(recent_consumption.get("reason") or "inventory_recent_consumption_missing_dictionary_column"), dict(recent_consumption.get("metadata") or {})
        personal = self._inventory_employee_mapping(context=context)
        if not personal:
            return "", "inventory_employee_mapping_missing_dictionary_column", {}
        cols = dict(personal.get("columns") or {})
        employee_table = str(personal.get("table") or "").strip()
        if not employee_table:
            return "", "inventory_employee_mapping_missing_dictionary_column", {}
        catalog_table = str(catalog["table"])
        catalog_cols = dict(catalog["columns"])
        employee_scope_join = self._inventory_employee_scope_join_clause(
            context=context,
            table_alias="p",
            filters=filters,
            movement_cedula_reference="bal.cedula",
        )
        employee_label = self._inventory_employee_label_sql(
            nombre_sql=f"COALESCE(MAX(p.{cols['nombre']}), '')",
            apellido_sql=f"COALESCE(MAX(p.{cols['apellido']}), '')",
        )
        tipo_filter_sql = self._inventory_tipo_filter_sql(
            filters=filters,
            column_sql=f"cat.{catalog_cols['tipo']}",
        )
        query = (
            "SELECT "
            "bal.cedula AS cedula, "
            f"COALESCE(MAX(p.{cols['movil']}), '') AS movil, "
            f"COALESCE(MAX(p.{cols['nombre']}), '') AS nombre, "
            f"COALESCE(MAX(p.{cols['apellido']}), '') AS apellido, "
            f"COALESCE(MAX(p.{cols['estado']}), '') AS estado_empleado, "
            f"{employee_label} AS empleado, "
            "bal.codigo AS codigo, "
            f"COALESCE(MAX(cat.{catalog_cols['descripcion']}), '') AS descripcion, "
            f"COALESCE(MAX(cat.{catalog_cols['tipo']}), '') AS tipo, "
            "COALESCE(cons.consumo_ultimos_8_dias, 0) AS consumo_ultimos_8_dias, "
            "ROUND(COALESCE(cons.consumo_ultimos_8_dias, 0) / 8, 4) AS promedio_dia, "
            "bal.saldo_actual AS saldo_actual, "
            "ROUND((COALESCE(cons.consumo_ultimos_8_dias, 0) / 8) * 3, 4) AS umbral_3_dias, "
            "'CRITICO' AS estado_critico "
            "FROM ("
            "SELECT mov.cedula AS cedula, mov.codigo AS codigo, "
            "SUM(mov.entregas - mov.devoluciones - mov.consumos - mov.cobros) AS saldo_actual, "
            "SUM(mov.registros_cantidad_invalida) AS registros_cantidad_invalida "
            f"FROM ({movement['sql']}) AS mov "
            "GROUP BY mov.cedula, mov.codigo"
            ") AS bal "
            f"INNER JOIN ({recent_consumption['sql']}) AS cons "
            "ON cons.cedula = bal.cedula AND cons.codigo = bal.codigo "
            f"LEFT JOIN {employee_table} AS p ON p.{cols['cedula']} = bal.cedula{employee_scope_join} "
            f"LEFT JOIN {catalog_table} AS cat ON cat.{catalog_cols['codigo']} = bal.codigo "
            "WHERE COALESCE(cons.consumo_ultimos_8_dias, 0) > 0 "
            "AND bal.saldo_actual < ((COALESCE(cons.consumo_ultimos_8_dias, 0) / 8) * 3) "
            f"{f'AND {tipo_filter_sql} ' if tipo_filter_sql else ''}"
            f"GROUP BY bal.cedula, COALESCE(p.{cols['movil']}, ''), bal.codigo, bal.saldo_actual, cons.consumo_ultimos_8_dias "
            "ORDER BY (umbral_3_dias - saldo_actual) DESC, movil ASC, bal.cedula ASC, bal.codigo ASC "
            f"LIMIT {limit}"
        )
        metadata = self._inventory_sql_metadata(
            table=str(movement.get("primary_table") or ""),
            columns=[
                *list(movement.get("columns") or []),
                *list(recent_consumption.get("columns") or []),
                *list(cols.values()),
                *list(catalog_cols.values()),
            ],
            metric_used="materiales_criticos_por_empleado",
            aggregation_used="critical_material_threshold",
            dimensions_used=["movil", "cedula", "codigo"],
            concept_field="materiales_criticos_por_empleado",
        )
        metadata.update(
            {
                "tables_detected": sorted(
                    set(
                        [
                            *list(movement.get("tables") or []),
                            *list(recent_consumption.get("tables") or []),
                            employee_table.split(".")[-1],
                            catalog_table.split(".")[-1],
                        ]
                    )
                ),
                "quantity_cast_policy": "case_when_regexp_then_cast_else_zero_report_invalid",
                "filters_applied": {
                    key: value
                    for key, value in {
                        "bodega": str(filters.get("bodega") or "").strip(),
                        "movil": str(filters.get("movil") or "").strip(),
                        "cedula": self._first_filter_value(
                            filters=filters,
                            keys=("cedula", "cedula_empleado", "identificacion", "documento", "id_empleado"),
                        ),
                        "tipo": filters.get("tipo"),
                    }.items()
                    if value not in ("", None, [], ())
                },
                "critical_rule": "saldo_actual < ((consumo_ultimos_8_dias / 8) * 3)",
                "critical_window_days": 8,
                "critical_threshold_days": 3,
                "formula_used": "saldo_actual = entregas - devoluciones - consumos - cobros",
            }
        )
        return query, "inventory_material_critical_by_employee", metadata

    def _inventory_recent_consumption_subquery(self, *, context: dict[str, Any], filters: dict[str, Any]) -> dict[str, Any]:
        consumo = self._inventory_table_mapping(
            context=context,
            table_name="logistica_movimientos_consumo",
            required_columns=("codigo", "cantidad", "f_consumo", "cedula", "bodega"),
        )
        if not consumo.get("ok"):
            return consumo
        cols = dict(consumo["columns"])
        where_parts: list[str] = []
        holder_where = self._inventory_operational_filter_clause(
            context=context,
            table_ref=str(consumo["table"]),
            filters=filters,
        )
        if holder_where:
            where_parts.append(holder_where)
        warehouse_filter = str(filters.get("bodega") or "").strip()
        if warehouse_filter:
            where_parts.append(f"{cols['bodega']} = '{self._escape_literal(warehouse_filter)}'")
        where_parts.append(f"DATE({cols['f_consumo']}) >= DATE_SUB(CURDATE(), INTERVAL 8 DAY)")
        where_sql = " AND ".join(where_parts)
        return {
            "ok": True,
            "sql": (
                f"SELECT {cols['cedula']} AS cedula, {cols['codigo']} AS codigo, "
                f"SUM({self._inventory_safe_quantity_sql(cols['cantidad'])}) AS consumo_ultimos_8_dias "
                f"FROM {consumo['table']} "
                f"WHERE {where_sql} "
                f"GROUP BY {cols['cedula']}, {cols['codigo']}"
            ),
            "tables": [str(consumo["table"]).split(".")[-1]],
            "columns": sorted(set(cols.values())),
            "primary_table": str(consumo["table"]),
        }

    def _build_inventory_transfer_sql(
        self,
        *,
        template_id: str,
        context: dict[str, Any],
        limit: int,
    ) -> tuple[str, str, dict[str, Any]]:
        transfer = self._inventory_table_mapping(
            context=context,
            table_name="logistica_movimientos_traslado",
            required_columns=("codigo", "cantidad", "f_consumo", "bodega", "movimiento"),
        )
        catalog = self._inventory_table_mapping(
            context=context,
            table_name="base_codigos",
            required_columns=("codigo", "descripcion", "tipo"),
        )
        if not transfer.get("ok"):
            return "", str(transfer.get("reason") or "inventory_transfer_missing_dictionary_column"), dict(transfer.get("metadata") or {})
        if not catalog.get("ok"):
            return "", str(catalog.get("reason") or "inventory_catalog_missing_dictionary_column"), dict(catalog.get("metadata") or {})
        cols = dict(transfer["columns"])
        cat_cols = dict(catalog["columns"])
        movement_value = "TRASLADOS_OTRO_ALIADO" if template_id == "inventory_transfer_other_ally" else "TRASLADO_BODEGA"
        metric_alias = "salida_otro_aliado" if template_id == "inventory_transfer_other_ally" else "salida_traslado_bodega"
        qty = self._inventory_safe_quantity_sql(cols["cantidad"])
        invalid = self._inventory_invalid_quantity_sql(cols["cantidad"])
        query = (
            f"SELECT t.{cols['bodega']} AS bodega_origen, t.{cols['codigo']} AS codigo, "
            f"COALESCE(MAX(cat.{cat_cols['descripcion']}), '') AS descripcion, "
            f"COALESCE(MAX(cat.{cat_cols['tipo']}), '') AS familia, "
            f"SUM({qty}) AS {metric_alias}, SUM({invalid}) AS registros_cantidad_invalida "
            f"FROM {transfer['table']} AS t "
            f"LEFT JOIN {catalog['table']} AS cat ON cat.{cat_cols['codigo']} = t.{cols['codigo']} "
            f"WHERE t.{cols['movimiento']} = '{movement_value}' "
            f"GROUP BY t.{cols['bodega']}, t.{cols['codigo']} "
            f"ORDER BY {metric_alias} DESC LIMIT {limit}"
        )
        metadata = self._inventory_sql_metadata(
            table=str(transfer["table"]),
            columns=[*list(cols.values()), *list(cat_cols.values())],
            metric_used=metric_alias,
            aggregation_used="sum",
            dimensions_used=["bodega_origen", "codigo"],
            concept_field="traslado_otro_aliado" if template_id == "inventory_transfer_other_ally" else "traslado_bodega_doble_registro",
        )
        metadata.update(
            {
                "tables_detected": sorted({str(transfer["table"]).split(".")[-1], str(catalog["table"]).split(".")[-1]}),
                "quantity_cast_policy": "case_when_regexp_then_cast_else_zero_report_invalid",
                "blocked_columns": ["bodega_destino"],
            }
        )
        return query, template_id, metadata

    def _build_inventory_kardex_sql(
        self,
        *,
        resolved_query: ResolvedQuerySpec,
        context: dict[str, Any],
        limit: int,
    ) -> tuple[str, str, dict[str, Any]]:
        codigo_value = str((resolved_query.normalized_filters or {}).get("codigo") or "").strip()
        if not codigo_value:
            return "", "inventory_kardex_requires_codigo_filter", {
                "compiler": "inventory_semantic_sql",
                "compiler_used": "inventory_semantic_sql",
                "fallback_reason": "inventory_kardex_requires_codigo_filter",
                "result_overflow_policy": "if_result_exceeds_1000_request_filter_grouping_or_export",
                "db_alias": "logistica_cinco",
            }
        movement = self._inventory_kardex_subqueries(context=context, codigo_value=codigo_value)
        catalog = self._inventory_table_mapping(
            context=context,
            table_name="base_codigos",
            required_columns=("codigo", "descripcion", "tipo"),
        )
        if not movement.get("ok"):
            return "", str(movement.get("reason") or "inventory_kardex_missing_dictionary_column"), dict(movement.get("metadata") or {})
        if not catalog.get("ok"):
            return "", str(catalog.get("reason") or "inventory_catalog_missing_dictionary_column"), dict(catalog.get("metadata") or {})
        cat_cols = dict(catalog["columns"])
        query = (
            f"SELECT kardex.fecha AS fecha, kardex.movimiento AS movimiento, kardex.codigo AS codigo, "
            f"COALESCE(cat.{cat_cols['descripcion']}, '') AS descripcion, "
            f"COALESCE(cat.{cat_cols['tipo']}, '') AS familia, "
            f"kardex.entrada AS entrada, kardex.salida AS salida, "
            f"SUM(kardex.entrada - kardex.salida) OVER (PARTITION BY kardex.codigo ORDER BY kardex.fecha ASC, kardex.movimiento_id ASC) AS saldo "
            f"FROM ({movement['sql']}) AS kardex "
            f"LEFT JOIN {catalog['table']} AS cat ON cat.{cat_cols['codigo']} = kardex.codigo "
            f"ORDER BY kardex.fecha DESC, kardex.movimiento_id DESC LIMIT {limit}"
        )
        metadata = self._inventory_sql_metadata(
            table=str(movement.get("primary_table") or ""),
            columns=[*list(movement.get("columns") or []), *list(cat_cols.values())],
            metric_used="saldo",
            aggregation_used="running_sum",
            dimensions_used=["codigo"],
            concept_field="kardex_consolidado",
        )
        metadata.update(
            {
                "tables_detected": sorted(set([*list(movement.get("tables") or []), str(catalog["table"]).split(".")[-1]])),
                "quantity_cast_policy": "case_when_regexp_then_cast_else_zero_report_invalid",
                "formula_used": "entrega suma como entrada; devolucion, consumo, cobro y traslado restan como salida",
                "result_overflow_policy": "requires_codigo_filter_or_export_when_result_exceeds_1000",
            }
        )
        return query, "inventory_kardex_consolidated", metadata

    def _build_inventory_kardex_by_employee_sql(
        self,
        *,
        resolved_query: ResolvedQuerySpec,
        context: dict[str, Any],
        limit: int,
    ) -> tuple[str, str, dict[str, Any]]:
        filters = dict(resolved_query.normalized_filters or {})
        cedula_value = self._first_filter_value(
            filters=filters,
            keys=("cedula", "cedula_empleado", "identificacion", "documento", "id_empleado"),
        )
        if not cedula_value:
            return "", "inventory_kardex_by_employee_requires_cedula_filter", {
                "compiler": "inventory_semantic_sql",
                "compiler_used": "inventory_semantic_sql",
                "fallback_reason": "inventory_kardex_by_employee_requires_cedula_filter",
                "db_alias": "logistica_cinco",
            }
        movement = self._inventory_kardex_employee_subqueries(context=context, filters=filters)
        personal = self._inventory_employee_mapping(context=context)
        catalog = self._inventory_table_mapping(
            context=context,
            table_name="base_codigos",
            required_columns=("codigo", "descripcion", "tipo"),
        )
        if not movement.get("ok"):
            return "", str(movement.get("reason") or "inventory_kardex_by_employee_missing_dictionary_column"), dict(movement.get("metadata") or {})
        if not personal:
            return "", "inventory_employee_mapping_missing_dictionary_column", {}
        if not catalog.get("ok"):
            return "", str(catalog.get("reason") or "inventory_catalog_missing_dictionary_column"), dict(catalog.get("metadata") or {})
        employee_cols = dict(personal.get("columns") or {})
        catalog_cols = dict(catalog.get("columns") or {})
        employee_table = str(personal.get("table") or "").strip()
        catalog_table = str(catalog.get("table") or "").strip()
        if not employee_table or not catalog_table:
            return "", "inventory_kardex_by_employee_missing_dictionary_column", {}
        employee_where = self._inventory_employee_filter_clause(context=context, table_alias="p", filters=filters)
        employee_where_sql = f" WHERE {employee_where}" if employee_where else ""
        employee_label = self._inventory_employee_label_sql(
            nombre_sql="emp.nombre",
            apellido_sql="emp.apellido",
        )
        employee_subquery = (
            "SELECT "
            f"p.{employee_cols['cedula']} AS cedula, "
            f"COALESCE(MAX(p.{employee_cols['movil']}), '') AS movil, "
            f"COALESCE(MAX(p.{employee_cols['nombre']}), '') AS nombre, "
            f"COALESCE(MAX(p.{employee_cols['apellido']}), '') AS apellido, "
            f"COALESCE(MAX(p.{employee_cols['estado']}), '') AS estado_empleado "
            f"FROM {employee_table} AS p"
            f"{employee_where_sql} "
            f"GROUP BY p.{employee_cols['cedula']}"
        )
        tipo_filter_sql = self._inventory_tipo_filter_sql(
            filters=filters,
            column_sql=f"cat.{catalog_cols['tipo']}",
        )
        where_sql = f" WHERE {tipo_filter_sql} " if tipo_filter_sql else ""
        optional_select_parts: list[str] = []
        if bool(movement.get("has_orden_trabajo")):
            optional_select_parts.append("k.orden_trabajo AS orden_trabajo, ")
        if bool(movement.get("has_ticket")):
            optional_select_parts.append("k.ticket AS ticket, ")
        entrada_case_sql = "CASE WHEN k.tipo_movimiento = 'entrega' THEN k.cantidad ELSE 0 END"
        salida_case_sql = (
            "CASE WHEN k.tipo_movimiento IN ('devolucion', 'consumo', 'cobro') "
            "THEN k.cantidad ELSE 0 END"
        )
        query = (
            "SELECT "
            "k.fecha AS fecha, "
            "k.tipo_movimiento AS tipo_movimiento, "
            "k.codigo AS codigo, "
            f"COALESCE(cat.{catalog_cols['descripcion']}, '') AS descripcion, "
            f"COALESCE(cat.{catalog_cols['tipo']}, '') AS tipo, "
            "k.cedula AS cedula, "
            f"{employee_label} AS empleado, "
            "COALESCE(emp.movil, '') AS movil, "
            "COALESCE(emp.estado_empleado, '') AS estado_empleado, "
            "k.bodega AS bodega, "
            f"{''.join(optional_select_parts)}"
            f"{entrada_case_sql} AS entrada, "
            f"{salida_case_sql} AS salida, "
            "k.cantidad AS cantidad, "
            "k.efecto AS efecto, "
            "SUM(k.saldo_delta) OVER (PARTITION BY k.codigo, k.cedula ORDER BY k.fecha ASC, k.movimiento_id ASC) AS saldo_movimiento "
            f"FROM ({movement['sql']}) AS k "
            f"LEFT JOIN ({employee_subquery}) AS emp ON emp.cedula = k.cedula "
            f"LEFT JOIN {catalog_table} AS cat ON cat.{catalog_cols['codigo']} = k.codigo "
            f"{where_sql}"
            f"ORDER BY k.fecha DESC, k.movimiento_id DESC LIMIT {limit}"
        )
        metadata = self._inventory_sql_metadata(
            table=str(movement.get("primary_table") or ""),
            columns=[*list(movement.get("columns") or []), *list(employee_cols.values()), *list(catalog_cols.values())],
            metric_used="saldo_movimiento",
            aggregation_used="running_sum_by_employee_code",
            dimensions_used=["fecha", "cedula", "codigo"],
            concept_field="kardex_operativo_por_empleado",
        )
        metadata.update(
            {
                "tables_detected": sorted(
                    set([*list(movement.get("tables") or []), employee_table.split(".")[-1], catalog_table.split(".")[-1]])
                ),
                "quantity_cast_policy": "case_when_regexp_then_cast_else_zero_report_invalid",
                "formula_used": "entrega suma como entrada; devolucion, consumo y cobro restan como salida sobre el saldo por codigo",
                "balance_filter_policy": "include_positive_zero_negative",
                "filters_applied": {
                    key: value
                    for key, value in {
                        "cedula": cedula_value,
                        "codigo": filters.get("codigo"),
                        "tipo": filters.get("tipo"),
                    }.items()
                    if value not in ("", None, [], ())
                },
                "limitations": ["serializados_employee_kardex_not_available"],
                "insights": [
                    "Kardex por empleado/tecnico resuelto por cedula usando movimientos auditados de materiales y ferretero.",
                    "No se incluyo kardex serializado porque las tablas disponibles no exponen una trazabilidad cronologica confiable por cedula.",
                ],
                "employee_stock_detail": True,
            }
        )
        metadata["joins_used"] = list(
            dict.fromkeys(
                [
                    *list(metadata.get("joins_used") or []),
                    "employee_detail_by_cedula",
                    "catalog_by_codigo",
                ]
            )
        )
        return query, "inventory_kardex_by_employee", metadata

    def _build_inventory_consumption_billing_sql(
        self,
        *,
        context: dict[str, Any],
        limit: int,
    ) -> tuple[str, str, dict[str, Any]]:
        consumo = self._inventory_table_mapping(
            context=context,
            table_name="logistica_movimientos_consumo",
            required_columns=("codigo", "cantidad", "orden_trabajo", "tipo", "bodega", "estado"),
        )
        promedios = self._inventory_table_mapping(
            context=context,
            table_name="a_promedios_consumo",
            required_columns=("codigo", "codigo_facturacion", "promedio"),
        )
        facturacion = self._inventory_table_mapping(
            context=context,
            table_name="facturacion_facturado_wfm",
            required_columns=("idorden_de_trabajo", "codigo", "cantidad_actividad"),
        )
        catalog = self._inventory_table_mapping(
            context=context,
            table_name="base_codigos",
            required_columns=("codigo", "descripcion", "tipo"),
        )
        for payload in (consumo, promedios, facturacion, catalog):
            if not payload.get("ok"):
                return "", str(payload.get("reason") or "inventory_consumption_billing_missing_dictionary_column"), dict(payload.get("metadata") or {})
        ccols = dict(consumo["columns"])
        pcols = dict(promedios["columns"])
        fcols = dict(facturacion["columns"])
        cat_cols = dict(catalog["columns"])
        qty = self._inventory_safe_quantity_sql(ccols["cantidad"])
        invalid = self._inventory_invalid_quantity_sql(ccols["cantidad"])
        activity_qty = (
            f"CASE WHEN COALESCE(f.{fcols['cantidad_actividad']}, 0) = 0 "
            f"THEN 1 ELSE f.{fcols['cantidad_actividad']} END"
        )
        query = (
            f"SELECT c.orden_trabajo AS orden_trabajo, c.codigo AS codigo, "
            f"COALESCE(MAX(cat.{cat_cols['descripcion']}), '') AS descripcion, "
            f"COALESCE(MAX(cat.{cat_cols['tipo']}), '') AS familia, "
            f"SUM(c.cantidad_consumida) AS cantidad_consumida, "
            f"COALESCE(SUM(p.{pcols['promedio']} * {activity_qty}), 0) AS cantidad_promedio_facturada, "
            f"SUM(c.registros_cantidad_invalida) AS registros_cantidad_invalida, "
            f"CASE WHEN COUNT(f.{fcols['idorden_de_trabajo']}) = 0 THEN 'consumo_sin_facturacion' "
            f"WHEN SUM(c.cantidad_consumida) > COALESCE(SUM(p.{pcols['promedio']} * {activity_qty}), 0) THEN 'consumo_mayor_a_promedio' "
            f"ELSE 'ok' END AS estado_alerta "
            f"FROM ("
            f"SELECT {ccols['orden_trabajo']} AS orden_trabajo, {ccols['codigo']} AS codigo, {ccols['tipo']} AS tipo, "
            f"SUM({qty}) AS cantidad_consumida, SUM({invalid}) AS registros_cantidad_invalida "
            f"FROM {consumo['table']} "
            f"WHERE {ccols['bodega']} = 'operacion_hfc' AND {ccols['estado']} = 'CERRADO' "
            f"GROUP BY {ccols['orden_trabajo']}, {ccols['codigo']}, {ccols['tipo']}"
            f") AS c "
            f"LEFT JOIN {facturacion['table']} AS f ON CAST(f.{fcols['idorden_de_trabajo']} AS CHAR) = c.orden_trabajo "
            f"LEFT JOIN {promedios['table']} AS p ON CAST(p.{pcols['codigo']} AS CHAR) = c.codigo "
            f"AND p.{pcols['codigo_facturacion']} = f.{fcols['codigo']} "
            f"LEFT JOIN {catalog['table']} AS cat ON cat.{cat_cols['codigo']} = c.codigo "
            f"GROUP BY c.orden_trabajo, c.codigo "
            f"HAVING estado_alerta <> 'ok' OR registros_cantidad_invalida > 0 "
            f"ORDER BY cantidad_consumida DESC LIMIT {limit}"
        )
        metadata = self._inventory_sql_metadata(
            table=str(consumo["table"]),
            columns=[*list(ccols.values()), *list(pcols.values()), *list(fcols.values()), *list(cat_cols.values())],
            metric_used="consumo_vs_promedio_facturado",
            aggregation_used="sum_by_orden_trabajo_codigo",
            dimensions_used=["orden_trabajo", "codigo"],
            concept_field="consumo_vs_facturacion",
        )
        metadata.update(
            {
                "tables_detected": sorted(
                    {
                        str(consumo["table"]).split(".")[-1],
                        str(promedios["table"]).split(".")[-1],
                        str(facturacion["table"]).split(".")[-1],
                        str(catalog["table"]).split(".")[-1],
                    }
                ),
                "scope": "operacion_hfc",
                "not_inventory_discount": ["facturacion_facturado_wfm"],
                "warnings_supported": ["consumo_mayor_a_promedio", "consumo_sin_facturacion"],
                "warnings_pending": ["facturacion_sin_consumo_full_outer"],
                "quantity_cast_policy": "case_when_regexp_then_cast_else_zero_report_invalid",
            }
        )
        return query, "inventory_consumption_billing_operacion_hfc", metadata

    def _inventory_table_mapping(
        self,
        *,
        context: dict[str, Any],
        table_name: str,
        required_columns: tuple[str, ...],
    ) -> dict[str, Any]:
        table = self._resolve_table_for_required_columns(
            context=context,
            required_columns=required_columns,
            preferred_table_name=table_name,
        )
        if not table:
            return {
                "ok": False,
                "reason": "inventory_table_not_audited_or_missing_dictionary_columns",
                "metadata": {
                    "compiler": "inventory_semantic_sql",
                    "compiler_used": "inventory_semantic_sql",
                    "table": table_name,
                    "missing_table": table_name,
                    "missing_columns": list(required_columns),
                    "required_columns": list(required_columns),
                    "capability_blocked": "inventory_stock_balance_by_warehouse",
                    "planner_block_reason_specific": f"missing_table:{table_name}",
                    "fallback_reason": "inventory_table_not_audited_or_missing_dictionary_columns",
                    "db_alias": "logistica_cinco",
                },
            }
        columns: dict[str, str] = {}
        missing: list[str] = []
        for column in required_columns:
            profile = self._find_context_profile_for_table(
                context=context,
                table_ref=table,
                logical_names=(column,),
                column_names=(column,),
            )
            physical = str((profile or {}).get("column_name") or "").strip()
            if physical and self._is_safe_identifier(physical):
                columns[column] = physical
            else:
                missing.append(column)
        if missing:
            return {
                "ok": False,
                "reason": "inventory_missing_dictionary_column",
                "metadata": {
                    "compiler": "inventory_semantic_sql",
                    "compiler_used": "inventory_semantic_sql",
                    "table": table_name,
                    "missing_columns": missing,
                    "capability_blocked": "inventory_stock_balance_by_warehouse",
                    "planner_block_reason_specific": f"missing_columns:{table_name}:{','.join(missing)}",
                    "fallback_reason": "inventory_missing_dictionary_column",
                    "db_alias": "logistica_cinco",
                },
            }
        return {"ok": True, "table": table, "columns": columns}

    def _inventory_optional_table_column(
        self,
        *,
        context: dict[str, Any],
        table_name: str,
        logical_names: tuple[str, ...] = (),
        column_names: tuple[str, ...] = (),
    ) -> str:
        table = self._resolve_table_for_required_columns(
            context=context,
            required_columns=(),
            preferred_table_name=table_name,
        )
        if not table:
            return ""
        profile = self._find_context_profile_for_table(
            context=context,
            table_ref=table,
            logical_names=logical_names,
            column_names=column_names,
        )
        physical = str((profile or {}).get("column_name") or "").strip()
        if physical and self._is_safe_identifier(physical):
            return physical
        return ""

    def _inventory_material_stock_subqueries(self, *, context: dict[str, Any], by_warehouse: bool) -> dict[str, Any]:
        required_by_table = {
            "logistica_movimientos_entrada": ("codigo", "cantidad", "f_consumo", "bodega", "estado"),
            "logistica_movimientos_entrega": ("codigo", "cantidad", "f_consumo", "bodega"),
            "logistica_movimientos_devolucion": ("codigo", "cantidad", "f_consumo", "bodega"),
            "logistica_movimientos_cobro": ("codigo", "cantidad", "f_consumo", "bodega"),
            "logistica_movimientos_traslado": ("codigo", "cantidad", "f_consumo", "bodega", "movimiento"),
        }
        mappings: dict[str, dict[str, Any]] = {}
        for table_name, columns in required_by_table.items():
            mapping = self._inventory_table_mapping(context=context, table_name=table_name, required_columns=columns)
            if not mapping.get("ok"):
                return mapping
            mappings[table_name] = mapping

        subqueries: list[str] = []
        tables_used: list[str] = []
        columns_used: list[str] = []

        def dimension(cols: dict[str, str]) -> str:
            return cols["bodega"] if by_warehouse else "''"

        entrada = mappings["logistica_movimientos_entrada"]
        ecols = dict(entrada["columns"])
        subqueries.append(
            self._inventory_balance_subquery(
                table=str(entrada["table"]),
                cols=ecols,
                dimension_sql=dimension(ecols),
                entradas=self._inventory_safe_quantity_sql(ecols["cantidad"]),
                where=f"COALESCE({ecols['estado']}, '') <> 'traslado_bodega'" if not by_warehouse else "",
            )
        )

        for table_name, metric in (
            ("logistica_movimientos_entrega", "entregas"),
            ("logistica_movimientos_devolucion", "devoluciones"),
            ("logistica_movimientos_cobro", "cobros"),
        ):
            mapping = mappings[table_name]
            cols = dict(mapping["columns"])
            subqueries.append(
                self._inventory_balance_subquery(
                    table=str(mapping["table"]),
                    cols=cols,
                    dimension_sql=dimension(cols),
                    **{metric: self._inventory_safe_quantity_sql(cols["cantidad"])},
                )
            )

        traslado = mappings["logistica_movimientos_traslado"]
        tcols = dict(traslado["columns"])
        if by_warehouse:
            subqueries.append(
                self._inventory_balance_subquery(
                    table=str(traslado["table"]),
                    cols=tcols,
                    dimension_sql=dimension(tcols),
                    traslados_bodega=self._inventory_safe_quantity_sql(tcols["cantidad"]),
                    where=f"{tcols['movimiento']} = 'TRASLADO_BODEGA'",
                )
            )
        subqueries.append(
            self._inventory_balance_subquery(
                table=str(traslado["table"]),
                cols=tcols,
                dimension_sql=dimension(tcols),
                traslados_otro_aliado=self._inventory_safe_quantity_sql(tcols["cantidad"]),
                where=f"{tcols['movimiento']} = 'TRASLADOS_OTRO_ALIADO'",
            )
        )

        for mapping in mappings.values():
            tables_used.append(str(mapping["table"]).split(".")[-1])
            columns_used.extend(list(dict(mapping["columns"]).values()))
        return {
            "ok": True,
            "sql": " UNION ALL ".join(subqueries),
            "tables": tables_used,
            "columns": sorted(set(columns_used)),
            "primary_table": str(mappings["logistica_movimientos_entrada"]["table"]),
        }

    def _inventory_mobile_stock_subqueries(self, *, context: dict[str, Any], filters: dict[str, Any]) -> dict[str, Any]:
        required_by_table = {
            "logistica_movimientos_entrega": ("codigo", "cantidad", "f_consumo", "cedula"),
            "logistica_movimientos_consumo": ("codigo", "cantidad", "f_consumo", "cedula"),
            "logistica_movimientos_cobro": ("codigo", "cantidad", "f_consumo", "cedula"),
            "logistica_movimientos_devolucion": ("codigo", "cantidad", "f_consumo", "cedula"),
        }
        omitted_tables: list[str] = []
        filtered_tables: list[str] = []
        mappings: dict[str, dict[str, Any]] = {}
        for table_name, columns in required_by_table.items():
            mapping = self._inventory_table_mapping(context=context, table_name=table_name, required_columns=columns)
            if not mapping.get("ok"):
                return mapping
            mappings[table_name] = mapping
        subqueries: list[str] = []
        identifier_values = {
            "cedula": self._first_filter_value(
                filters=filters,
                keys=("cedula", "cedula_empleado", "identificacion", "documento", "id_empleado"),
            ),
            "movil": str(filters.get("movil") or "").strip(),
        }
        active_identifier_filter = any(identifier_values.values())
        for table_name, metric in (
            ("logistica_movimientos_entrega", "entregas"),
            ("logistica_movimientos_consumo", "consumos"),
            ("logistica_movimientos_cobro", "cobros"),
            ("logistica_movimientos_devolucion", "devoluciones"),
        ):
            mapping = mappings[table_name]
            cols = dict(mapping["columns"])
            where_clause = ""
            if active_identifier_filter:
                where_clause = self._inventory_operational_filter_clause(
                    context=context,
                    table_ref=str(mapping["table"]),
                    filters=filters,
                )
                if not where_clause:
                    omitted_tables.append(table_name)
                    continue
                filtered_tables.append(table_name)
            subqueries.append(
                self._inventory_balance_subquery(
                    table=str(mapping["table"]),
                    cols=cols,
                    dimension_sql="''",
                    where=where_clause,
                    **{metric: self._inventory_safe_quantity_sql(cols["cantidad"])},
                )
            )
        if active_identifier_filter and not subqueries:
            return {
                "ok": False,
                "reason": "inventory_mobile_filter_not_audited",
                "metadata": {
                    "compiler": "inventory_semantic_sql",
                    "compiler_used": "inventory_semantic_sql",
                    "planner_block_reason_specific": "missing_inventory_operational_filter_columns",
                    "fallback_reason": "inventory_mobile_filter_not_audited",
                    "requested_filters": {key: value for key, value in identifier_values.items() if value},
                    "omitted_tables": list(required_by_table.keys()),
                    "db_alias": "logistica_cinco",
                },
            }
        return {
            "ok": True,
            "sql": " UNION ALL ".join(subqueries),
            "tables": [str(item["table"]).split(".")[-1] for item in mappings.values()],
            "columns": sorted({col for item in mappings.values() for col in dict(item["columns"]).values()}),
            "primary_table": str(mappings["logistica_movimientos_entrega"]["table"]),
            "filtered_tables": filtered_tables,
            "omitted_tables": omitted_tables,
            "identifier_filters": {key: value for key, value in identifier_values.items() if value},
        }

    def _inventory_mobile_employee_stock_subqueries(self, *, context: dict[str, Any], filters: dict[str, Any]) -> dict[str, Any]:
        required_by_table = {
            "logistica_movimientos_entrega": ("codigo", "cantidad", "f_consumo", "cedula", "bodega"),
            "logistica_movimientos_consumo": ("codigo", "cantidad", "f_consumo", "cedula", "bodega"),
            "logistica_movimientos_cobro": ("codigo", "cantidad", "f_consumo", "cedula", "bodega"),
            "logistica_movimientos_devolucion": ("codigo", "cantidad", "f_consumo", "cedula", "bodega"),
        }
        mappings: dict[str, dict[str, Any]] = {}
        for table_name, columns in required_by_table.items():
            mapping = self._inventory_table_mapping(context=context, table_name=table_name, required_columns=columns)
            if not mapping.get("ok"):
                return mapping
            mappings[table_name] = mapping
        warehouse_filter = str(filters.get("bodega") or "").strip()
        subqueries: list[str] = []
        for table_name, metric in (
            ("logistica_movimientos_entrega", "entregas"),
            ("logistica_movimientos_consumo", "consumos"),
            ("logistica_movimientos_cobro", "cobros"),
            ("logistica_movimientos_devolucion", "devoluciones"),
        ):
            mapping = mappings[table_name]
            cols = dict(mapping["columns"])
            where_parts: list[str] = []
            holder_where = self._inventory_operational_filter_clause(
                context=context,
                table_ref=str(mapping["table"]),
                filters=filters,
            )
            if holder_where:
                where_parts.append(holder_where)
            if warehouse_filter:
                where_parts.append(f"{cols['bodega']} = '{self._escape_literal(warehouse_filter)}'")
            subqueries.append(
                self._inventory_balance_subquery(
                    table=str(mapping["table"]),
                    cols=cols,
                    dimension_sql=cols["cedula"],
                    dimension_alias="cedula",
                    where=" AND ".join(where_parts),
                    **{metric: self._inventory_safe_quantity_sql(cols["cantidad"])},
                )
            )
        return {
            "ok": True,
            "sql": " UNION ALL ".join(subqueries),
            "tables": [str(item["table"]).split(".")[-1] for item in mappings.values()],
            "columns": sorted({col for item in mappings.values() for col in dict(item["columns"]).values()}),
            "primary_table": str(mappings["logistica_movimientos_entrega"]["table"]),
        }

    def _inventory_operational_filter_clause(
        self,
        *,
        context: dict[str, Any],
        table_ref: str,
        filters: dict[str, Any],
        table_alias: str = "",
    ) -> str:
        cedula = self._first_filter_value(
            filters=filters,
            keys=("cedula", "cedula_empleado", "identificacion", "documento", "id_empleado"),
        )
        movil = str(filters.get("movil") or "").strip()
        candidates: list[tuple[str, str, str]] = []
        if cedula:
            candidates.append(("cedula", cedula, "exact"))
        if movil:
            if self._is_inventory_numeric_identifier(movil):
                if not cedula:
                    candidates.append(("cedula", movil, "exact"))
            else:
                candidates.append(("movil", movil, "exact"))
        seen: set[tuple[str, str, str]] = set()
        exact_clauses: list[str] = []
        fallback_clauses: list[str] = []
        movement_cedula_profile = self._find_context_profile_for_table(
            context=context,
            table_ref=table_ref,
            logical_names=("cedula",),
            column_names=("cedula",),
        )
        movement_cedula_column = str((movement_cedula_profile or {}).get("column_name") or "").strip()
        movement_cedula_reference = self._qualify_inventory_column(
            table_alias=table_alias,
            column_name=movement_cedula_column,
        )
        for logical_name, value, mode in candidates:
            pair = (logical_name, value, mode)
            if pair in seen or not value:
                continue
            seen.add(pair)
            if logical_name == "movil":
                bridge_clause = self._inventory_employee_bridge_filter_clause(
                    context=context,
                    movement_cedula_reference=movement_cedula_reference,
                    logical_name=logical_name,
                    value=value,
                )
                if bridge_clause:
                    if mode == "fallback_or":
                        fallback_clauses.append(bridge_clause)
                    else:
                        exact_clauses.append(bridge_clause)
                    continue
            profile = self._find_context_profile_for_table(
                context=context,
                table_ref=table_ref,
                logical_names=(logical_name,),
                column_names=(logical_name,),
            )
            physical = str((profile or {}).get("column_name") or "").strip()
            if physical and self._is_safe_identifier(physical):
                qualified_physical = self._qualify_inventory_column(
                    table_alias=table_alias,
                    column_name=physical,
                )
                clause = f"{qualified_physical} = '{self._escape_literal(value)}'"
                if mode == "fallback_or":
                    fallback_clauses.append(clause)
                else:
                    exact_clauses.append(clause)
                continue
            bridge_clause = self._inventory_employee_bridge_filter_clause(
                context=context,
                movement_cedula_reference=movement_cedula_reference,
                logical_name=logical_name,
                value=value,
            )
            if bridge_clause:
                if mode == "fallback_or":
                    fallback_clauses.append(bridge_clause)
                else:
                    exact_clauses.append(bridge_clause)
        if exact_clauses and fallback_clauses:
            return "(" + " OR ".join([*exact_clauses, *fallback_clauses]) + ")"
        if exact_clauses:
            return exact_clauses[0] if len(exact_clauses) == 1 else "(" + " OR ".join(exact_clauses) + ")"
        if fallback_clauses:
            return fallback_clauses[0] if len(fallback_clauses) == 1 else "(" + " OR ".join(fallback_clauses) + ")"
        return ""

    @staticmethod
    def _is_inventory_numeric_identifier(value: str) -> bool:
        return bool(re.fullmatch(r"\d{5,15}", str(value or "").strip()))

    def _inventory_employee_mapping(self, *, context: dict[str, Any]) -> dict[str, Any]:
        personal = self._inventory_table_mapping(
            context=context,
            table_name="cinco_base_de_personal",
            required_columns=("cedula", "nombre", "apellido", "movil", "area", "carpeta", "cargo", "tipo_labor", "estado"),
        )
        return personal if bool(personal.get("ok")) else {}

    def _inventory_employee_filter_clause(self, *, context: dict[str, Any], table_alias: str, filters: dict[str, Any]) -> str:
        mapping = self._inventory_employee_mapping(context=context)
        if not mapping:
            return ""
        cols = dict(mapping.get("columns") or {})
        cedula = self._first_filter_value(
            filters=filters,
            keys=("cedula", "cedula_empleado", "identificacion", "documento", "id_empleado"),
        )
        movil = str(filters.get("movil") or "").strip()
        clauses: list[str] = []
        if cedula and cols.get("cedula"):
            clauses.append(f"{table_alias}.{cols['cedula']} = '{self._escape_literal(cedula)}'")
        if movil and cols.get("movil") and not self._is_inventory_numeric_identifier(movil):
            clauses.append(f"{table_alias}.{cols['movil']} = '{self._escape_literal(movil)}'")
        elif movil and cols.get("movil") and self._is_inventory_numeric_identifier(movil) and not cedula:
            clauses.append(f"{table_alias}.{cols['movil']} = '{self._escape_literal(movil)}'")
        if not clauses:
            return ""
        return " OR ".join(dict.fromkeys(clauses))

    def _inventory_employee_bridge_filter_clause(
        self,
        *,
        context: dict[str, Any],
        movement_cedula_reference: str,
        logical_name: str,
        value: str,
    ) -> str:
        if logical_name not in {"movil", "cedula"}:
            return ""
        if not movement_cedula_reference:
            return ""
        mapping = self._inventory_employee_mapping(context=context)
        if not mapping:
            return ""
        cols = dict(mapping.get("columns") or {})
        employee_table = str(mapping.get("table") or "").strip()
        employee_cedula = str(cols.get("cedula") or "").strip()
        employee_target = str(cols.get(logical_name) or "").strip()
        if not employee_table or not employee_cedula or not employee_target:
            return ""
        match_clause = f"p.{employee_target} = '{self._escape_literal(value)}'"
        return (
            "EXISTS ("
            f"SELECT 1 FROM {employee_table} AS p "
            f"WHERE p.{employee_cedula} = {movement_cedula_reference} AND {match_clause}"
            ")"
        )

    @staticmethod
    def _qualify_inventory_column(*, table_alias: str, column_name: str) -> str:
        clean_column = str(column_name or "").strip()
        if not clean_column:
            return ""
        clean_alias = str(table_alias or "").strip()
        if not clean_alias:
            return clean_column
        return f"{clean_alias}.{clean_column}"

    def _inventory_employee_active_clause(self, *, context: dict[str, Any], table_alias: str) -> str:
        mapping = self._inventory_employee_mapping(context=context)
        if not mapping:
            return ""
        cols = dict(mapping.get("columns") or {})
        estado_column = str(cols.get("estado") or "").strip()
        if not estado_column:
            return ""
        return f"UPPER(COALESCE({table_alias}.{estado_column}, '')) = 'ACTIVO'"

    def _inventory_employee_scope_join_clause(
        self,
        *,
        context: dict[str, Any],
        table_alias: str,
        filters: dict[str, Any],
        movement_cedula_reference: str,
    ) -> str:
        mapping = self._inventory_employee_mapping(context=context)
        if not mapping:
            return ""
        cols = dict(mapping.get("columns") or {})
        where_clause = self._inventory_employee_filter_clause(context=context, table_alias=table_alias, filters=filters)
        if not where_clause:
            return ""
        return f" AND ({where_clause})"

    @staticmethod
    def _inventory_employee_label_sql(*, nombre_sql: str, apellido_sql: str) -> str:
        return (
            "TRIM(CONCAT("
            f"SUBSTRING_INDEX(TRIM({nombre_sql}), ' ', 1), "
            f"CASE WHEN TRIM({apellido_sql}) = '' THEN '' "
            f"ELSE CONCAT(' ', SUBSTRING_INDEX(TRIM({apellido_sql}), ' ', 1)) END"
            "))"
        )

    def _inventory_employee_select_prefix(self, *, context: dict[str, Any], filters: dict[str, Any]) -> str:
        if not self._inventory_employee_filter_clause(context=context, table_alias="emp", filters=filters):
            return ""
        return (
            "COALESCE(MAX(emp.cedulas_relacionadas), '') AS cedulas_relacionadas, "
            "COALESCE(MAX(emp.nombres_relacionados), '') AS nombres_relacionados, "
            "COALESCE(MAX(emp.apellidos_relacionados), '') AS apellidos_relacionados, "
            "COALESCE(MAX(emp.areas_relacionadas), '') AS areas_relacionadas, "
            "COALESCE(MAX(emp.carpetas_relacionadas), '') AS carpetas_relacionadas, "
            "COALESCE(MAX(emp.cargos_relacionados), '') AS cargos_relacionados, "
            "COALESCE(MAX(emp.tipos_labor_relacionados), '') AS tipos_labor_relacionados, "
            "COALESCE(MAX(emp.estados_relacionados), '') AS estados_relacionados, "
            "COALESCE(MAX(emp.moviles_relacionados), '') AS moviles_relacionados, "
        )

    def _inventory_employee_join_clause(self, *, context: dict[str, Any], filters: dict[str, Any]) -> str:
        mapping = self._inventory_employee_mapping(context=context)
        if not mapping:
            return ""
        where_clause = self._inventory_employee_filter_clause(context=context, table_alias="p", filters=filters)
        if not where_clause:
            return ""
        table = str(mapping.get("table") or "")
        cols = dict(mapping.get("columns") or {})
        return (
            "LEFT JOIN ("
            f"SELECT 1 AS scope_key, "
            f"GROUP_CONCAT(DISTINCT CAST(p.{cols['cedula']} AS CHAR) ORDER BY p.{cols['cedula']} SEPARATOR '; ') AS cedulas_relacionadas, "
            f"GROUP_CONCAT(DISTINCT p.{cols['nombre']} ORDER BY p.{cols['nombre']} SEPARATOR '; ') AS nombres_relacionados, "
            f"GROUP_CONCAT(DISTINCT p.{cols['apellido']} ORDER BY p.{cols['apellido']} SEPARATOR '; ') AS apellidos_relacionados, "
            f"GROUP_CONCAT(DISTINCT p.{cols['area']} ORDER BY p.{cols['area']} SEPARATOR '; ') AS areas_relacionadas, "
            f"GROUP_CONCAT(DISTINCT p.{cols['carpeta']} ORDER BY p.{cols['carpeta']} SEPARATOR '; ') AS carpetas_relacionadas, "
            f"GROUP_CONCAT(DISTINCT p.{cols['cargo']} ORDER BY p.{cols['cargo']} SEPARATOR '; ') AS cargos_relacionados, "
            f"GROUP_CONCAT(DISTINCT p.{cols['tipo_labor']} ORDER BY p.{cols['tipo_labor']} SEPARATOR '; ') AS tipos_labor_relacionados, "
            f"GROUP_CONCAT(DISTINCT p.{cols['estado']} ORDER BY p.{cols['estado']} SEPARATOR '; ') AS estados_relacionados, "
            f"GROUP_CONCAT(DISTINCT p.{cols['movil']} ORDER BY p.{cols['movil']} SEPARATOR '; ') AS moviles_relacionados "
            f"FROM {table} AS p WHERE {where_clause}"
            ") AS emp ON emp.scope_key = 1 "
        )

    def _inventory_employee_enrichment_metadata(self, *, context: dict[str, Any], filters: dict[str, Any]) -> dict[str, Any]:
        mapping = self._inventory_employee_mapping(context=context)
        if not mapping:
            return {}
        where_clause = self._inventory_employee_filter_clause(context=context, table_alias="p", filters=filters)
        if not where_clause:
            return {}
        cols = dict(mapping.get("columns") or {})
        return {
            "tables_detected": [str(mapping.get("table") or "").split(".")[-1]],
            "columns_detected": list(cols.values()),
            "physical_columns_used": list(cols.values()),
            "relations_used": [],
            "joins_used": [f"employee_enrichment:{where_clause}"],
            "employee_enrichment": {
                "table": str(mapping.get("table") or ""),
                "filter_scope": {
                    key: value
                    for key, value in {
                        "cedula": self._first_filter_value(
                            filters=filters,
                            keys=("cedula", "cedula_empleado", "identificacion", "documento", "id_empleado"),
                        ),
                        "movil": str(filters.get("movil") or "").strip(),
                    }.items()
                    if value
                },
            },
        }

    def _inventory_serial_catalog_join_clause(self, *, context: dict[str, Any], serial_table: str) -> str:
        serial_mapping = self._inventory_table_mapping(
            context=context,
            table_name="logistica_base_seriales",
            required_columns=("codigo",),
        )
        catalog_mapping = self._inventory_table_mapping(
            context=context,
            table_name="base_codigo_seriales",
            required_columns=("codigo",),
        )
        if not serial_mapping.get("ok") or not catalog_mapping.get("ok"):
            return ""
        scol = dict(serial_mapping.get("columns") or {})
        ccol = dict(catalog_mapping.get("columns") or {})
        catalog_table = str(catalog_mapping.get("table") or "")
        serial_code = str(scol.get("codigo") or "")
        catalog_code = str(ccol.get("codigo") or "")
        if not catalog_table or not serial_code or not catalog_code:
            return ""
        return f"LEFT JOIN {catalog_table} AS cat ON cat.{catalog_code} = s.{serial_code} "

    def _inventory_kardex_subqueries(self, *, context: dict[str, Any], codigo_value: str) -> dict[str, Any]:
        specs = [
            ("logistica_movimientos_entrada", "ingreso", "entrada", ("codigo", "cantidad", "f_consumo", "id", "estado"), "COALESCE({estado}, '') <> 'traslado_bodega'"),
            ("logistica_movimientos_entrega", "entrega", "entrada", ("codigo", "cantidad", "f_consumo", "id"), ""),
            ("logistica_movimientos_devolucion", "devolucion", "salida", ("codigo", "cantidad", "f_consumo", "id"), ""),
            ("logistica_movimientos_consumo", "consumo", "salida", ("codigo", "cantidad", "f_consumo", "id"), ""),
            ("logistica_movimientos_cobro", "cobro", "salida", ("codigo", "cantidad", "f_consumo", "id"), ""),
            ("logistica_movimientos_traslado", "traslado", "salida", ("codigo", "cantidad", "f_consumo", "id", "movimiento"), "{movimiento} IN ('TRASLADO_BODEGA', 'TRASLADOS_OTRO_ALIADO')"),
        ]
        subqueries: list[str] = []
        tables_used: list[str] = []
        columns_used: list[str] = []
        escaped_codigo = self._escape_literal(codigo_value)
        for table_name, movement_label, direction, required, where_template in specs:
            mapping = self._inventory_table_mapping(context=context, table_name=table_name, required_columns=required)
            if not mapping.get("ok"):
                return mapping
            cols = dict(mapping["columns"])
            qty = self._inventory_safe_quantity_sql(cols["cantidad"])
            entrada = qty if direction == "entrada" else "0"
            salida = qty if direction == "salida" else "0"
            where_parts = [f"{cols['codigo']} = '{escaped_codigo}'"]
            if where_template:
                where_parts.append(where_template.format(**cols))
            subqueries.append(
                f"SELECT {cols['f_consumo']} AS fecha, '{movement_label}' AS movimiento, "
                f"{cols['codigo']} AS codigo, {entrada} AS entrada, {salida} AS salida, {cols['id']} AS movimiento_id "
                f"FROM {mapping['table']} WHERE {' AND '.join(where_parts)}"
            )
            tables_used.append(str(mapping["table"]).split(".")[-1])
            columns_used.extend(list(cols.values()))
        return {
            "ok": True,
            "sql": " UNION ALL ".join(subqueries),
            "tables": tables_used,
            "columns": sorted(set(columns_used)),
            "primary_table": "logistica_movimientos_entrada",
        }

    def _inventory_kardex_employee_subqueries(self, *, context: dict[str, Any], filters: dict[str, Any]) -> dict[str, Any]:
        required_by_table = {
            "logistica_movimientos_entrega": ("id", "codigo", "cantidad", "f_consumo", "cedula", "bodega"),
            "logistica_movimientos_devolucion": ("id", "codigo", "cantidad", "f_consumo", "cedula", "bodega"),
            "logistica_movimientos_consumo": ("id", "codigo", "cantidad", "f_consumo", "cedula", "bodega"),
            "logistica_movimientos_cobro": ("id", "codigo", "cantidad", "f_consumo", "cedula", "bodega"),
        }
        mappings: dict[str, dict[str, Any]] = {}
        for table_name, columns in required_by_table.items():
            mapping = self._inventory_table_mapping(context=context, table_name=table_name, required_columns=columns)
            if not mapping.get("ok"):
                return mapping
            mappings[table_name] = mapping

        def optional_column_sql(*, table_ref: str, column_aliases: tuple[str, ...], table_alias: str) -> str:
            profile = self._find_context_profile_for_table(
                context=context,
                table_ref=table_ref,
                logical_names=column_aliases,
                column_names=column_aliases,
            )
            column_name = str((profile or {}).get("column_name") or "").strip()
            if column_name and self._is_safe_identifier(column_name):
                return f"{table_alias}.{column_name}"
            return "''"

        subqueries: list[str] = []
        columns_used: set[str] = set()
        tables_used: list[str] = []
        codigo_value = self._first_filter_value(
            filters=filters,
            keys=("codigo", "codigo_material", "material_codigo"),
        )
        optional_profiles: dict[str, dict[str, dict[str, Any]]] = {}
        for table_name, mapping in mappings.items():
            table_ref = str(mapping["table"])
            optional_profiles[table_name] = {
                "orden_trabajo": self._find_context_profile_for_table(
                    context=context,
                    table_ref=table_ref,
                    logical_names=("orden_trabajo", "ot", "idorden_de_trabajo"),
                    column_names=("orden_trabajo", "ot", "idorden_de_trabajo"),
                ),
                "ticket": self._find_context_profile_for_table(
                    context=context,
                    table_ref=table_ref,
                    logical_names=("ticket",),
                    column_names=("ticket",),
                ),
            }
        has_orden_trabajo = any(
            str((profile_map.get("orden_trabajo") or {}).get("column_name") or "").strip()
            for profile_map in optional_profiles.values()
        )
        has_ticket = any(
            str((profile_map.get("ticket") or {}).get("column_name") or "").strip()
            for profile_map in optional_profiles.values()
        )
        for table_name, movement_label, effect_label, sign, direction in (
            ("logistica_movimientos_entrega", "entrega", "suma", 1, "entrada"),
            ("logistica_movimientos_devolucion", "devolucion", "resta", -1, "salida"),
            ("logistica_movimientos_consumo", "consumo", "resta", -1, "salida"),
            ("logistica_movimientos_cobro", "cobro", "resta", -1, "salida"),
        ):
            mapping = mappings[table_name]
            table_ref = str(mapping["table"])
            cols = dict(mapping["columns"])
            where_clause = self._inventory_operational_filter_clause(
                context=context,
                table_ref=table_ref,
                filters=filters,
                table_alias="src",
            )
            if not where_clause:
                return {
                    "ok": False,
                    "reason": "inventory_kardex_by_employee_filter_not_audited",
                    "metadata": {
                        "compiler": "inventory_semantic_sql",
                        "compiler_used": "inventory_semantic_sql",
                        "fallback_reason": "inventory_kardex_by_employee_filter_not_audited",
                        "db_alias": "logistica_cinco",
                    },
                }
            if codigo_value:
                codigo_profile = self._find_context_profile_for_table(
                    context=context,
                    table_ref=table_ref,
                    logical_names=("codigo",),
                    column_names=("codigo",),
                )
                codigo_column = str((codigo_profile or {}).get("column_name") or "").strip()
                qualified_codigo = self._qualify_inventory_column(
                    table_alias="src",
                    column_name=codigo_column,
                )
                if qualified_codigo:
                    where_clause = (
                        f"({where_clause}) AND {qualified_codigo} = '{self._escape_literal(codigo_value)}'"
                    )
            quantity_sql = self._inventory_safe_quantity_sql(cols["cantidad"])
            optional_select_sql = ""
            if has_orden_trabajo:
                orden_trabajo_sql = optional_column_sql(
                    table_ref=table_ref,
                    column_aliases=("orden_trabajo", "ot", "idorden_de_trabajo"),
                    table_alias="src",
                )
                optional_select_sql += f"{orden_trabajo_sql} AS orden_trabajo, "
            if has_ticket:
                ticket_sql = optional_column_sql(
                    table_ref=table_ref,
                    column_aliases=("ticket",),
                    table_alias="src",
                )
                optional_select_sql += f"{ticket_sql} AS ticket, "
            subqueries.append(
                "SELECT "
                f"src.{cols['f_consumo']} AS fecha, "
                f"'{movement_label}' AS tipo_movimiento, "
                f"src.{cols['codigo']} AS codigo, "
                f"src.{cols['cedula']} AS cedula, "
                f"src.{cols['bodega']} AS bodega, "
                f"{optional_select_sql}"
                f"{quantity_sql} AS cantidad, "
                f"'{effect_label}' AS efecto, "
                f"({sign} * ({quantity_sql})) AS saldo_delta, "
                f"src.{cols['id']} AS movimiento_id "
                f"FROM {table_ref} AS src WHERE {where_clause}"
            )
            columns_used.update(cols.values())
            tables_used.append(table_ref.split(".")[-1])
        return {
            "ok": True,
            "sql": " UNION ALL ".join(subqueries),
            "tables": tables_used,
            "columns": sorted(
                columns_used
                | ({"orden_trabajo"} if has_orden_trabajo else set())
                | ({"ticket"} if has_ticket else set())
            ),
            "has_orden_trabajo": has_orden_trabajo,
            "has_ticket": has_ticket,
            "primary_table": str(mappings["logistica_movimientos_entrega"]["table"]),
        }

    def _should_route_kardex_codigo_employee_to_employee(
        self,
        *,
        domain_code: str,
        template_id: str,
        resolved_query: ResolvedQuerySpec,
    ) -> bool:
        if str(domain_code or "").strip().lower() != "inventario_logistica":
            return False
        if str(template_id or "").strip().lower() != "inventory_kardex_consolidated":
            return False
        filters = dict(resolved_query.normalized_filters or {})
        cedula_value = self._first_filter_value(
            filters=filters,
            keys=("cedula", "cedula_empleado", "identificacion", "documento", "id_empleado"),
        )
        codigo_value = self._first_filter_value(
            filters=filters,
            keys=("codigo", "codigo_material", "material_codigo"),
        )
        raw_query = str(resolved_query.intent.raw_query or "").strip().lower()
        mentions_employee_scope = any(token in raw_query for token in ("empleado", "tecnico", "cedula"))
        return bool(cedula_value and codigo_value and mentions_employee_scope)

    def _inventory_balance_subquery(
        self,
        *,
        table: str,
        cols: dict[str, str],
        dimension_sql: str,
        dimension_alias: str = "bodega",
        entradas: str = "0",
        entregas: str = "0",
        devoluciones: str = "0",
        consumos: str = "0",
        cobros: str = "0",
        traslados_otro_aliado: str = "0",
        traslados_bodega: str = "0",
        where: str = "",
    ) -> str:
        where_sql = f" WHERE {where}" if str(where or "").strip() else ""
        group_by = f"{cols['codigo']}, {dimension_sql}"
        return (
            f"SELECT {cols['codigo']} AS codigo, {dimension_sql} AS {dimension_alias}, "
            f"SUM({entradas}) AS entradas, SUM({entregas}) AS entregas, "
            f"SUM({devoluciones}) AS devoluciones, SUM({consumos}) AS consumos, "
            f"SUM({cobros}) AS cobros, SUM({traslados_otro_aliado}) AS traslados_otro_aliado, "
            f"SUM({traslados_bodega}) AS traslados_bodega, "
            f"SUM({self._inventory_invalid_quantity_sql(cols['cantidad'])}) AS registros_cantidad_invalida "
            f"FROM {table}{where_sql} GROUP BY {group_by}"
        )

    def _inventory_safe_quantity_sql(self, column_name: str) -> str:
        return (
            f"CASE WHEN TRIM(COALESCE({column_name}, '')) REGEXP '{self.INVENTORY_QUANTITY_NUMERIC_RE}' "
            f"THEN CAST({column_name} AS DECIMAL(18,4)) ELSE 0 END"
        )

    def _inventory_invalid_quantity_sql(self, column_name: str) -> str:
        return (
            f"CASE WHEN TRIM(COALESCE({column_name}, '')) REGEXP '{self.INVENTORY_QUANTITY_NUMERIC_RE}' "
            f"THEN 0 ELSE 1 END"
        )

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
            (
                "certificado_alturas_proximo_vencer_45_dias",
                "certificado_alturas_proximo_vencer_30_dias",
            ),
            ("personal_activo_operativo",),
        )
        missing_rules = [
            "/".join(rule_group)
            for rule_group in required_rule_sets
            if not any(self._dictionary_rule_declared(context=context, rule_code=code) for code in rule_group)
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

    def _inventory_sql_metadata(
        self,
        *,
        table: str,
        columns: list[str],
        metric_used: str,
        aggregation_used: str,
        dimensions_used: list[str],
        concept_field: str,
    ) -> dict[str, Any]:
        metadata = self._default_sql_metadata(table=table, columns=columns)
        metadata.update(
            {
                "compiler": "inventory_semantic_sql",
                "compiler_used": "inventory_semantic_sql",
                "metric_used": metric_used,
                "aggregation_used": aggregation_used,
                "dimensions_used": list(dimensions_used or []),
                "concept_field": concept_field,
                "declared_metric_source": "ai_dictionary.dd_campos",
                "declared_dimensions_source": "ai_dictionary.dd_campos",
                "insights": [
                    "La consulta de inventario se resolvio con SQL asistido validado contra ai_dictionary.",
                ],
                "db_alias": "logistica_cinco",
            }
        )
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
        profile_table_name = (
            str(profile.get("table_name") or "").strip().lower()
            or str(profile.get("table_fqn") or "").strip().lower().split(".")[-1]
        )
        table_table_name = (
            str(table.get("table_name") or "").strip().lower()
            or str(table.get("table_fqn") or "").strip().lower().split(".")[-1]
        )
        profile_key = cls._table_key(
            schema_name=str(profile.get("schema_name") or ""),
            table_name=profile_table_name,
            table_fqn=str(profile.get("table_fqn") or ""),
        )
        table_key = cls._table_key(
            schema_name=str(table.get("schema_name") or ""),
            table_name=table_table_name,
            table_fqn=str(table.get("table_fqn") or ""),
        )
        if profile_key and table_key:
            if profile_key == table_key:
                return True
            profile_is_specific = bool(
                str(profile.get("table_fqn") or "").strip()
                or str(profile.get("schema_name") or "").strip()
            )
            table_is_specific = bool(
                str(table.get("table_fqn") or "").strip()
                or str(table.get("schema_name") or "").strip()
            )
            if profile_is_specific and table_is_specific:
                return False
        return profile_table_name != "" and profile_table_name == table_table_name

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
        return best_profile or {}

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

    def _resolve_inventory_date_column(self, *, context: dict[str, Any], table_ref: str = "") -> str:
        preferred = self._find_context_profile_for_table(
            context=context,
            table_ref=table_ref,
            logical_names=("fecha", "fecha_asociacion"),
            column_names=("fecha", "fecha_asociacion", "f_consumo"),
        )
        column_name = str((preferred or {}).get("column_name") or "").strip()
        if column_name and self._is_safe_identifier(column_name):
            return column_name
        return self._resolve_date_column(context=context)

    def _resolve_inventory_detail_columns(self, *, context: dict[str, Any], preferred: tuple[str, ...]) -> list[str]:
        selected: list[str] = []
        for token in preferred:
            physical = self._resolve_named_column(context=context, preferred_terms=(token,))
            if physical and physical not in selected:
                selected.append(physical)
        return selected[:12] or self._resolve_detail_columns(context=context)

    def _resolve_inventory_serial_holder_columns(self, *, context: dict[str, Any], table_ref: str) -> list[str]:
        preferred_pairs = (
            (("serial",), ("numero_serial", "serial")),
            (("codigo",), ("codigo",)),
            (("estado",), ("estado",)),
            (("cedula",), ("cedula",)),
            (("fecha_ingreso", "fecha"), ("fecha_ingreso",)),
            (("ticket",), ("ticket",)),
            (("fecha_edit", "fecha"), ("fecha_edit",)),
        )
        selected: list[str] = []
        for logical_names, column_names in preferred_pairs:
            profile = self._find_context_profile_for_table(
                context=context,
                table_ref=table_ref,
                logical_names=logical_names,
                column_names=column_names,
            )
            physical = str((profile or {}).get("column_name") or "").strip()
            if physical and self._is_safe_identifier(physical) and physical not in selected:
                selected.append(physical)
        return selected

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
        domain_code = str(resolved_query.intent.domain_code or "").strip().lower()
        template_id = str(resolved_query.intent.template_id or "").strip().lower()
        if not list((resolved_query.semantic_context or {}).get("tables") or []):
            missing.append("tablas_registradas_del_dominio")
        if template_id == "detail_by_entity_and_period":
            filters = dict(resolved_query.normalized_filters or {})
            if not any(
                str(filters.get(key) or "").strip()
                for key in self._EMPLOYEE_DETAIL_FILTER_KEYS
            ):
                missing.append("identificador_empleado")
        period = dict(resolved_query.normalized_period or {})
        requires_period = template_id in {
            "count_records_by_period",
            "detail_by_entity_and_period",
            "aggregate_by_group_and_period",
            "trend_by_period",
        }
        if requires_period and (not period.get("start_date") or not period.get("end_date")):
            missing.append("periodo_consulta")
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

    @staticmethod
    def _inventory_grouped_dimension_value(
        row: dict[str, Any],
        *,
        dimension_field: str,
    ) -> str:
        for key in (
            dimension_field,
            "dimension",
            "movil",
            "cedula",
            "bodega",
        ):
            value = str((row or {}).get(key) or "").strip()
            if value:
                return value
        return "SIN_DATO"

    def _build_inventory_serial_dimension_subtotal_table(
        self,
        *,
        rows: list[dict[str, Any]],
        dimension_field: str,
        result_meta: dict[str, Any],
    ) -> dict[str, Any] | None:
        if not rows:
            return None

        aggregated: dict[str, dict[str, Any]] = {}
        for row in rows:
            if not isinstance(row, dict):
                continue
            dimension_value = self._inventory_grouped_dimension_value(
                row,
                dimension_field=dimension_field,
            )
            bucket = aggregated.setdefault(
                dimension_value,
                {
                    dimension_field: dimension_value,
                    "codigos_distintos": set(),
                    "seriales_total": 0.0,
                    "en_movil": 0.0,
                    "en_base": 0.0,
                    "cobros": 0.0,
                    "saldo": 0.0,
                },
            )
            codigo = str(row.get("codigo") or "").strip()
            if codigo:
                bucket["codigos_distintos"].add(codigo)
            for key in ("seriales_total", "en_movil", "en_base", "cobros", "saldo"):
                bucket[key] = float(bucket.get(key) or 0) + float(row.get(key) or 0)

        subtotal_rows = [
            {
                dimension_field: key,
                "codigos_distintos": len(value["codigos_distintos"]),
                "seriales_total": value["seriales_total"],
                "en_movil": value["en_movil"],
                "en_base": value["en_base"],
                "cobros": value["cobros"],
                "saldo": value["saldo"],
            }
            for key, value in aggregated.items()
        ]
        subtotal_rows.sort(
            key=lambda item: (
                -float(item.get("saldo") or 0),
                str(item.get(dimension_field) or ""),
            )
        )

        total_records = len(subtotal_rows)
        returned_records = total_records
        truncated = False
        if bool(result_meta.get("truncated")):
            truncated = True

        return {
            "name": f"subtotales_serializados_por_{dimension_field}",
            "title": f"Subtotales por {dimension_field}",
            "columns": [
                dimension_field,
                "codigos_distintos",
                "seriales_total",
                "en_movil",
                "en_base",
                "cobros",
                "saldo",
            ],
            "rows": subtotal_rows,
            "export_rows": subtotal_rows,
            "rowcount": total_records,
            "total_records": total_records,
            "returned_records": returned_records,
            "export_records": total_records,
            "export_truncated": False,
            "export_limit": total_records,
            "truncated": truncated,
            "limit": total_records,
            "meta": {
                "derived_from_result_set": True,
                "partial_due_to_result_truncation": truncated,
                "dimension_field": dimension_field,
            },
        }

    def _extend_inventory_supplemental_tables(
        self,
        *,
        response_profile_id: str,
        rows: list[dict[str, Any]],
        result_meta: dict[str, Any],
        business_response: dict[str, Any] | None,
        supplemental_tables: list[dict[str, Any]] | None,
    ) -> list[dict[str, Any]]:
        tables = [dict(item) for item in list(supplemental_tables or []) if isinstance(item, dict)]
        if response_profile_id != "inventory.serial.stock.dimension.detail":
            return tables

        grouping_dimension = str(
            dict((business_response or {}).get("metadata") or {}).get("filters", {}).get("grouping_dimension")
            or ""
        ).strip().lower()
        dimension_field = grouping_dimension if grouping_dimension in {"movil", "cedula", "bodega"} else "dimension"
        subtotal_table = self._build_inventory_serial_dimension_subtotal_table(
            rows=rows,
            dimension_field=dimension_field,
            result_meta=result_meta,
        )
        if subtotal_table:
            tables.append(subtotal_table)
        return tables

    def _build_sql_response(
        self,
        *,
        run_context: RunContext,
        resolved_query: ResolvedQuerySpec,
        execution_plan: QueryExecutionPlan,
        sql_query: str,
        rows: list[dict[str, Any]],
        export_rows: list[dict[str, Any]] | None,
        columns: list[str],
        duration_ms: int,
        db_alias: str,
        result_metadata: dict[str, Any] | None = None,
        supplemental_tables: list[dict[str, Any]] | None = None,
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
        export_rows = list(export_rows or rows or [])
        export_rowcount = len(export_rows)
        export_limit = self._max_sql_export_rows()
        export_truncated = result_meta["total_records"] > export_rowcount
        kpis.setdefault("returned_records", result_meta["returned_records"])
        kpis.setdefault("total_records", result_meta["total_records"])
        compiler = str(metadata.get("compiler") or "default_sql_builder")
        metric_used = str(metadata.get("metric_used") or "")
        response_category = str(metadata.get("response_category") or "").strip().lower()
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
        if domain_code == "inventario_logistica":
            business_response = build_inventory_business_response(
                resolved_query=resolved_query.as_dict(),
                rows=rows,
                limitations=list(metadata.get("limitations") or []),
                supplemental_tables=supplemental_tables,
                result_set=dict(result_meta),
                execution_metadata=metadata,
            )
            if str(business_response.get("dato") or "").strip():
                reply = str(business_response.get("dato") or "").strip()
            if str(business_response.get("hallazgo") or "").strip():
                findings = [{"title": "Alertas", "detail": str(business_response.get("hallazgo") or "").strip()}]
            response_profile_id = str(
                (dict(business_response.get("response_profile") or {})).get("id")
                or (dict(business_response.get("metadata") or {})).get("response_profile_usado")
                or ""
            ).strip()
            supplemental_tables = self._extend_inventory_supplemental_tables(
                response_profile_id=response_profile_id,
                rows=rows,
                result_meta=result_meta,
                business_response=business_response,
                supplemental_tables=supplemental_tables,
            )
            business_response = build_inventory_business_response(
                resolved_query=resolved_query.as_dict(),
                rows=rows,
                limitations=list(metadata.get("limitations") or []),
                supplemental_tables=supplemental_tables,
                result_set=dict(result_meta),
                execution_metadata=metadata,
            )
            if str(business_response.get("dato") or "").strip():
                reply = str(business_response.get("dato") or "").strip()
            if str(business_response.get("hallazgo") or "").strip():
                findings = [{"title": "Alertas", "detail": str(business_response.get("hallazgo") or "").strip()}]
            if response_profile_id == "inventory.stock.dimension.summary":
                grouping_dimension = str(
                    (dict(business_response.get("metadata") or {})).get("filters", {}).get("grouping_dimension")
                    or ""
                ).strip().lower()
                dimension_field = grouping_dimension if grouping_dimension in {"movil", "cedula", "bodega"} else "dimension"
                total_saldo = sum(float((row or {}).get("saldo") or 0) for row in rows if isinstance(row, dict))
                distinct_dimensions = {
                    str(
                        (row or {}).get(dimension_field)
                        or (row or {}).get("dimension")
                        or (row or {}).get("movil")
                        or (row or {}).get("cedula")
                        or (row or {}).get("bodega")
                        or ""
                    ).strip()
                    for row in rows
                    if isinstance(row, dict)
                }
                distinct_dimensions.discard("")
                matching_codes = {
                    str((row or {}).get("codigo") or "").strip()
                    for row in rows
                    if isinstance(row, dict) and str((row or {}).get("codigo") or "").strip()
                }
                kpis.update(
                    {
                        "total_saldo": total_saldo,
                        "dimensiones_con_saldo": len(distinct_dimensions),
                        "registros_evidencia": int(result_meta.get("returned_records") or len(rows)),
                        "codigos_coincidentes": len(matching_codes),
                    }
                )
            if response_profile_id == "inventory.serial.stock.dimension.detail":
                grouping_dimension = str(
                    (dict(business_response.get("metadata") or {})).get("filters", {}).get("grouping_dimension")
                    or ""
                ).strip().lower()
                dimension_field = grouping_dimension if grouping_dimension in {"movil", "cedula", "bodega"} else "dimension"
                total_saldo = sum(float((row or {}).get("saldo") or 0) for row in rows if isinstance(row, dict))
                total_seriales = sum(
                    float((row or {}).get("seriales_total") or 0) for row in rows if isinstance(row, dict)
                )
                distinct_dimensions = {
                    self._inventory_grouped_dimension_value(
                        row or {},
                        dimension_field=dimension_field,
                    )
                    for row in rows
                    if isinstance(row, dict)
                }
                distinct_dimensions.discard("SIN_DATO")
                matching_codes = {
                    str((row or {}).get("codigo") or "").strip()
                    for row in rows
                    if isinstance(row, dict) and str((row or {}).get("codigo") or "").strip()
                }
                kpis.update(
                    {
                        "total_saldo": total_saldo,
                        "seriales_total": total_seriales,
                        "dimensiones_con_saldo": len(distinct_dimensions),
                        "codigos_coincidentes": len(matching_codes),
                        "registros_evidencia": int(result_meta.get("returned_records") or len(rows)),
                    }
                )
                if dimension_field == "movil":
                    kpis["moviles_con_saldo"] = len(distinct_dimensions)
                elif dimension_field == "cedula":
                    kpis["tecnicos_con_saldo"] = len(distinct_dimensions)
                elif dimension_field == "bodega":
                    kpis["bodegas_con_saldo"] = len(distinct_dimensions)
            inventory_insights = [
                str(business_response.get(key) or "").strip()
                for key in ("hallazgo", "riesgo", "recomendacion")
                if str(business_response.get(key) or "").strip()
            ]
            if inventory_insights:
                insights = inventory_insights
        supplemental_tables = list(supplemental_tables or [])
        findings = locals().get("findings") or [
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
                    "export_rows": export_rows,
                    "rowcount": result_meta["total_records"],
                    "total_records": result_meta["total_records"],
                    "returned_records": result_meta["returned_records"],
                    "export_records": export_rowcount,
                    "export_truncated": export_truncated,
                    "export_limit": export_limit,
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
                **({"extra_tables": supplemental_tables} if supplemental_tables else {}),
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

    def _inventory_tipo_filter_sql(self, *, filters: dict[str, Any], column_sql: str) -> str:
        raw_tipo = filters.get("tipo")
        normalized_values: list[str] = []
        if isinstance(raw_tipo, (list, tuple, set)):
            normalized_values = [
                str(value or "").strip().lower()
                for value in raw_tipo
                if str(value or "").strip()
            ]
        elif str(raw_tipo or "").strip():
            normalized_values = [str(raw_tipo or "").strip().lower()]
        normalized_values = list(dict.fromkeys(normalized_values))
        if not normalized_values:
            return ""
        escaped_values = [f"'{self._escape_literal(value)}'" for value in normalized_values]
        normalized_column = f"LOWER(COALESCE({column_sql}, ''))"
        if len(escaped_values) == 1:
            return f"{normalized_column} = {escaped_values[0]}"
        return f"{normalized_column} IN ({', '.join(escaped_values)})"

    @staticmethod
    def _record_event(*, observability, event_type: str, source: str, meta: dict[str, Any]) -> None:
        if observability is None or not hasattr(observability, "record_event"):
            return
        observability.record_event(
            event_type=event_type,
            source=source,
            meta=dict(meta or {}),
        )
