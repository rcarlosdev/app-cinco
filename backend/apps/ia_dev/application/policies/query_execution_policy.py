from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any

from apps.ia_dev.application.context.run_context import RunContext
from apps.ia_dev.application.contracts.query_intelligence_contracts import ResolvedQuerySpec
from apps.ia_dev.application.policies.policy_runtime import PolicyRuntime


@dataclass(slots=True, frozen=True)
class QueryExecutionPolicyDecision:
    allowed: bool
    reason: str
    metadata: dict[str, Any]


class QueryExecutionPolicy:
    FORBIDDEN_SQL_TOKENS = (
        " insert ",
        " update ",
        " delete ",
        " alter ",
        " drop ",
        " create ",
        " truncate ",
        " merge ",
        " grant ",
        " revoke ",
    )

    TABLE_REF_RE = re.compile(r"\b(?:from|join)\s+([a-zA-Z0-9_.`]+)\b", re.IGNORECASE)
    FILTER_COLUMN_RE = re.compile(
        r"\b([a-zA-Z_][a-zA-Z0-9_]*)\s*(?:=|>=|<=|<>|!=|>|<|like|in|between)\b",
        re.IGNORECASE,
    )
    SQL_TABLE_FUNCTIONS = {"json_table"}

    def __init__(self, *, runtime: PolicyRuntime | None = None):
        self.runtime = runtime or PolicyRuntime()

    @staticmethod
    def _flag_enabled(name: str, default: str = "0") -> bool:
        raw = str(os.getenv(name, default) or "").strip().lower()
        return raw in {"1", "true", "yes", "on"}

    def evaluate_sql_assisted(
        self,
        *,
        run_context: RunContext,
        resolved_query: ResolvedQuerySpec,
    ) -> QueryExecutionPolicyDecision:
        domain_status = str((resolved_query.semantic_context or {}).get("domain_status") or "planned").strip().lower()
        pilot_enabled = bool((resolved_query.semantic_context or {}).get("source_of_truth", {}).get("pilot_sql_assisted_enabled"))
        runtime_context = {
            "execution_strategy": "sql_assisted",
            "requires_context": False,
            "domain_status": domain_status,
        }
        runtime = self.runtime.evaluate(
            policy_name="query_execution_policy.yaml",
            context=runtime_context,
            fallback_action="allow",
            fallback_policy_id="query_execution_policy.fallback",
            fallback_reason="query_execution_policy_runtime_fallback",
        )
        runtime_action = str(runtime.action or "allow").strip().lower()
        runtime_policy_id = str(runtime.policy_id or "").strip().lower()
        runtime_reason = str(runtime.reason or "").strip()
        if (
            pilot_enabled
            and runtime_action in {"deny", "require_approval"}
            and runtime_policy_id == "query_sql_assisted.domain_status_not_allowed"
            and domain_status == "active"
        ):
            runtime_action = "allow"
        if runtime_action in {"deny", "require_approval"}:
            return QueryExecutionPolicyDecision(
                allowed=False,
                reason=runtime_reason or "query_execution_policy_runtime_denied",
                metadata={
                    "policy_id": str(runtime.policy_id or ""),
                    "runtime_action": runtime_action,
                    "runtime_metadata": dict(runtime.metadata or {}),
                },
            )

        if not self._flag_enabled("IA_DEV_QUERY_SQL_ASSISTED_ENABLED", "0"):
            return QueryExecutionPolicyDecision(
                allowed=False,
                reason="sql_assisted_disabled_by_flag",
                metadata={"flag": "IA_DEV_QUERY_SQL_ASSISTED_ENABLED"},
            )
        if not self._flag_enabled("IA_DEV_QUERY_INTELLIGENCE_ENABLED", "0"):
            return QueryExecutionPolicyDecision(
                allowed=False,
                reason="query_intelligence_disabled",
                metadata={"flag": "IA_DEV_QUERY_INTELLIGENCE_ENABLED"},
            )

        if domain_status not in {"planned", "partial"} and not pilot_enabled:
            return QueryExecutionPolicyDecision(
                allowed=False,
                reason="sql_assisted_only_for_planned_or_partial",
                metadata={"domain_status": domain_status, "pilot_enabled": pilot_enabled},
            )

        if not bool((resolved_query.semantic_context or {}).get("supports_sql_assisted")):
            return QueryExecutionPolicyDecision(
                allowed=False,
                reason="domain_sql_assisted_not_allowed",
                metadata={"domain_code": (resolved_query.intent.domain_code or "")},
            )

        return QueryExecutionPolicyDecision(
            allowed=True,
            reason="sql_assisted_allowed",
            metadata={
                "routing_mode": run_context.routing_mode,
                "domain_code": resolved_query.intent.domain_code,
                "domain_status": domain_status,
            },
        )

    def validate_sql_query(
        self,
        *,
        query: str,
        allowed_tables: list[str],
        allowed_columns: list[str],
        allowed_relations: list[str] | None = None,
        declared_columns: list[str] | None = None,
        declared_relations: list[str] | None = None,
        max_limit: int = 500,
    ) -> QueryExecutionPolicyDecision:
        normalized = re.sub(r"\s+", " ", str(query or "").strip(), flags=re.MULTILINE).strip().lower()
        if not normalized.startswith("select "):
            return QueryExecutionPolicyDecision(False, "sql_must_start_with_select", {})

        padded = f" {normalized} "
        if any(token in padded for token in self.FORBIDDEN_SQL_TOKENS):
            return QueryExecutionPolicyDecision(False, "sql_contains_forbidden_operation", {})

        limit_match = re.search(r"\blimit\s+(\d+)\b", normalized)
        if not limit_match:
            return QueryExecutionPolicyDecision(False, "sql_limit_required", {})
        limit_value = int(limit_match.group(1))
        if limit_value > int(max_limit):
            return QueryExecutionPolicyDecision(
                False,
                "sql_limit_exceeds_max",
                {"limit": limit_value, "max_limit": int(max_limit)},
            )

        declared_tables = self._extract_declared_tables(normalized)
        allowed_table_set = {self._normalize_identifier(item) for item in list(allowed_tables or []) if item}
        if declared_tables and allowed_table_set:
            for table_name in declared_tables:
                normalized_table = self._normalize_identifier(table_name)
                if normalized_table not in allowed_table_set:
                    return QueryExecutionPolicyDecision(
                        False,
                        "sql_uses_unregistered_table",
                        {"table": table_name},
                    )

        column_set = {self._normalize_identifier(item) for item in list(allowed_columns or []) if item}
        query_columns = [
            self._normalize_identifier(item)
            for item in list(declared_columns or self._extract_relevant_columns(normalized))
            if str(item or "").strip()
        ]
        if query_columns and column_set:
            for column in query_columns:
                if self._normalize_identifier(column) not in column_set:
                    return QueryExecutionPolicyDecision(
                        False,
                        "sql_uses_unregistered_column",
                        {"column": column},
                    )

        allowed_relation_set = {
            self._normalize_relation(item)
            for item in list(allowed_relations or [])
            if str(item or "").strip()
        }
        query_relations = [
            self._normalize_relation(item)
            for item in list(declared_relations or [])
            if str(item or "").strip()
        ]
        if query_relations and allowed_relation_set:
            for relation in query_relations:
                if relation not in allowed_relation_set:
                    return QueryExecutionPolicyDecision(
                        False,
                        "sql_uses_unregistered_relation",
                        {"relation": relation},
                    )

        return QueryExecutionPolicyDecision(
            True,
            "sql_validated",
            {
                "declared_tables": declared_tables,
                "declared_columns_count": len(query_columns),
                "declared_relations_count": len(query_relations),
                "limit": limit_value,
            },
        )

    @classmethod
    def _extract_declared_tables(cls, query: str) -> list[str]:
        values: list[str] = []
        for match in cls.TABLE_REF_RE.finditer(query):
            token = str(match.group(1) or "").strip().strip("`")
            if token and token.lower() not in cls.SQL_TABLE_FUNCTIONS:
                values.append(token.lower())
        return values

    @classmethod
    def _extract_relevant_columns(cls, query: str) -> list[str]:
        values: list[str] = []
        for match in cls.FILTER_COLUMN_RE.finditer(query):
            token = str(match.group(1) or "").strip().lower()
            if token:
                values.append(token)

        group_match = re.search(r"\bgroup by\s+([a-zA-Z0-9_,\s`\.]+)", query, re.IGNORECASE)
        if group_match:
            for token in str(group_match.group(1) or "").split(","):
                clean = str(token or "").strip().lower().strip("`")
                if clean:
                    values.append(clean.split(".")[-1])

        order_match = re.search(r"\border by\s+([a-zA-Z0-9_,\s`\.]+)", query, re.IGNORECASE)
        if order_match:
            for token in str(order_match.group(1) or "").split(","):
                clean = str(token or "").strip().lower().strip("`")
                if clean:
                    values.append(clean.split(" ")[0].split(".")[-1])

        return values

    @staticmethod
    def _normalize_identifier(value: str) -> str:
        return str(value or "").strip().lower().strip("`")

    @staticmethod
    def _normalize_relation(value: str) -> str:
        return re.sub(r"\s+", " ", str(value or "").strip().lower())
