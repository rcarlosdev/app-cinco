from __future__ import annotations

import re
from datetime import date
from typing import Any

from apps.ia_dev.application.contracts.query_intelligence_contracts import (
    QueryExecutionPlan,
    ResolvedQuerySpec,
    SatisfactionValidation,
)


class ResultSatisfactionValidator:
    def validate(
        self,
        *,
        message: str,
        response: dict[str, Any],
        resolved_query: ResolvedQuerySpec | None = None,
        execution_plan: QueryExecutionPlan | None = None,
    ) -> SatisfactionValidation:
        normalized_message = self._normalize_text(message)
        data = dict((response or {}).get("data") or {})
        table = dict(data.get("table") or {})
        rows = list(table.get("rows") or [])
        kpis = dict(data.get("kpis") or {})
        labels = list(data.get("labels") or [])
        series = list(data.get("series") or [])
        charts = list(data.get("charts") or [])
        chart = dict(data.get("chart") or {})
        checks: dict[str, Any] = {}
        constraints = dict((execution_plan.constraints if execution_plan else {}) or {})

        expected_filters = self._resolve_expected_filters(
            message=normalized_message,
            resolved_query=resolved_query,
            execution_plan=execution_plan,
        )
        expected_group_by = self._resolve_expected_group_by(
            resolved_query=resolved_query,
            execution_plan=execution_plan,
            message=normalized_message,
        )
        expected_metrics = self._resolve_expected_metrics(
            resolved_query=resolved_query,
            execution_plan=execution_plan,
        )
        expected_shape = self._resolve_expected_shape(
            resolved_query=resolved_query,
            execution_plan=execution_plan,
            message=normalized_message,
        )

        expected_cedula = self._normalize_identifier(str(expected_filters.get("cedula") or ""))
        if not expected_cedula:
            expected_cedula = self._resolve_expected_cedula(normalized_message, resolved_query=resolved_query)
        if expected_cedula:
            row_cedulas = {
                self._normalize_identifier(str(item.get("cedula") or ""))
                for item in rows
                if isinstance(item, dict)
            }
            row_cedulas.discard("")
            checks["expected_cedula"] = expected_cedula
            checks["row_cedulas"] = sorted(row_cedulas)
            if row_cedulas and row_cedulas != {expected_cedula}:
                return SatisfactionValidation(
                    satisfied=False,
                    reason="entity_filter_not_applied_for_cedula",
                    checks=checks,
                )

        asks_count = expected_shape == "kpi" or any(
            token in normalized_message for token in ("cantidad", "cuantos", "cuantas", "total", "numero")
        )
        expected_template = str(((resolved_query.intent.template_id if resolved_query else "") or "")).strip().lower()
        if asks_count or expected_template.startswith("count_") or "count" in expected_metrics:
            has_numeric_kpi = any(isinstance(value, (int, float)) for value in kpis.values())
            if not has_numeric_kpi and rows:
                for row in rows:
                    if not isinstance(row, dict):
                        continue
                    if any(isinstance(value, (int, float)) for value in row.values()):
                        has_numeric_kpi = True
                        break
            checks["has_numeric_kpi"] = has_numeric_kpi
            if not has_numeric_kpi:
                return SatisfactionValidation(
                    satisfied=False,
                    reason="count_requested_without_numeric_kpi",
                    checks=checks,
                )

        asks_grouped_count = asks_count and bool(expected_group_by)
        if asks_grouped_count and rows:
            detail_like = any("fecha_ausentismo" in row and "cedula" in row for row in rows if isinstance(row, dict))
            has_group_metric = self._has_group_metric(rows=rows, expected_group_by=expected_group_by)
            checks["grouped_count"] = {
                "detail_like": detail_like,
                "has_group_metric": has_group_metric,
            }
            if detail_like or not has_group_metric:
                return SatisfactionValidation(
                    satisfied=False,
                    reason="group_count_requested_but_result_is_not_aggregated",
                    checks=checks,
                )

        estado_expected = str(expected_filters.get("estado") or "").strip().upper()
        if estado_expected:
            estado_values = self._collect_row_values(rows=rows, keys=("estado", "estado_empleado", "status"))
            checks["expected_estado"] = estado_expected
            checks["row_estados"] = sorted(estado_values)
            if estado_values and estado_values != {estado_expected}:
                return SatisfactionValidation(
                    satisfied=False,
                    reason="state_filter_not_applied",
                    checks=checks,
                )

        asks_last_year = bool(re.search(r"\b(ultimo|ultimos|ultima|ultimas)\s+ano(s)?\b", normalized_message))
        if asks_last_year:
            period = self._extract_period_from_response(response=response)
            checks["resolved_period"] = period
            if period:
                start, end = period
                if (end - start).days < 330:
                    return SatisfactionValidation(
                        satisfied=False,
                        reason="period_for_last_year_is_too_short",
                        checks=checks,
                    )

        expected_period = self._resolve_expected_period(
            resolved_query=resolved_query,
            execution_plan=execution_plan,
        )
        expected_start = str(expected_period.get("start_date") or "")
        expected_end = str(expected_period.get("end_date") or "")
        if expected_start and expected_end:
            checks["expected_period"] = {"start_date": expected_start, "end_date": expected_end}
            resolved_period = self._extract_period_from_response(response=response)
            checks["resolved_period_from_response"] = resolved_period
            if resolved_period is not None:
                response_start, response_end = resolved_period
                if response_start.isoformat() > expected_start or response_end.isoformat() < expected_end:
                    return SatisfactionValidation(
                        satisfied=False,
                        reason="expected_period_not_fully_covered",
                        checks=checks,
                    )

        if expected_group_by:
            matched_group = self._find_group_dimension_in_rows(rows=rows, expected_group_by=expected_group_by)
            checks["expected_group_by"] = list(expected_group_by)
            checks["matched_group_dimension"] = matched_group
            if rows and not matched_group:
                return SatisfactionValidation(
                    satisfied=False,
                    reason="expected_group_dimension_missing",
                    checks=checks,
                )

        if expected_shape == "trend":
            has_trend = bool(labels and series) or bool(
                rows and any("periodo" in row for row in rows if isinstance(row, dict))
            )
            checks["has_trend_shape"] = has_trend
            if not has_trend:
                return SatisfactionValidation(
                    satisfied=False,
                    reason="trend_shape_missing",
                    checks=checks,
                )

        if bool(constraints.get("chart_requested")):
            has_chart = bool(chart or charts or (labels and series))
            checks["chart_requested"] = True
            checks["has_chart_payload"] = has_chart
            if not has_chart:
                return SatisfactionValidation(
                    satisfied=False,
                    reason="chart_requested_but_missing",
                    checks=checks,
                )

        return SatisfactionValidation(
            satisfied=True,
            reason="ok",
            checks=checks,
        )

    def _resolve_expected_filters(
        self,
        *,
        message: str,
        resolved_query: ResolvedQuerySpec | None,
        execution_plan: QueryExecutionPlan | None,
    ) -> dict[str, Any]:
        filters = dict((execution_plan.constraints if execution_plan else {}).get("filters") or {})
        if resolved_query is not None:
            for key, value in dict(resolved_query.normalized_filters or {}).items():
                filters.setdefault(str(key), value)
        if "cedula" not in filters:
            match = re.search(r"\b\d{6,13}\b", message)
            if match:
                filters["cedula"] = self._normalize_identifier(match.group(0))
        return filters

    @staticmethod
    def _resolve_expected_group_by(
        *,
        resolved_query: ResolvedQuerySpec | None,
        execution_plan: QueryExecutionPlan | None,
        message: str,
    ) -> list[str]:
        plan_constraints = dict((execution_plan.constraints if execution_plan else {}) or {})
        if "group_by" in plan_constraints:
            return [
                str(item).strip().lower()
                for item in list(plan_constraints.get("group_by") or [])
                if str(item).strip()
            ]
        if resolved_query is not None:
            values = [str(item).strip().lower() for item in list(resolved_query.intent.group_by or []) if str(item).strip()]
            if values:
                return values
        inferred = [str(item or "").strip().lower() for item in re.findall(r"\bpor\s+([a-z0-9_]+)", str(message or "").lower()) if str(item or "").strip()]
        return list(dict.fromkeys(inferred))

    @staticmethod
    def _resolve_expected_metrics(
        *,
        resolved_query: ResolvedQuerySpec | None,
        execution_plan: QueryExecutionPlan | None,
    ) -> list[str]:
        values = [str(item).strip().lower() for item in list((execution_plan.constraints if execution_plan else {}).get("metrics") or []) if str(item).strip()]
        if values:
            return values
        if resolved_query is not None:
            return [str(item).strip().lower() for item in list(resolved_query.intent.metrics or []) if str(item).strip()]
        return []

    def _resolve_expected_shape(
        self,
        *,
        resolved_query: ResolvedQuerySpec | None,
        execution_plan: QueryExecutionPlan | None,
        message: str,
    ) -> str:
        plan_shape = str((execution_plan.constraints if execution_plan else {}).get("result_shape") or "").strip().lower()
        if plan_shape in {"kpi", "table", "summary", "trend"}:
            return plan_shape
        if resolved_query is not None:
            operation = str(resolved_query.intent.operation or "").strip().lower()
            template = str(resolved_query.intent.template_id or "").strip().lower()
            if operation == "count" or template.startswith("count_"):
                return "kpi"
            if operation == "trend" or template == "trend_by_period":
                return "trend"
            if operation in {"detail", "aggregate", "compare"}:
                return "table"
        if any(token in message for token in ("tendencia", "evolucion", "historico")):
            return "trend"
        if any(token in message for token in ("cantidad", "cuantos", "cuantas", "total")):
            return "kpi"
        return "summary"

    @staticmethod
    def _resolve_expected_period(
        *,
        resolved_query: ResolvedQuerySpec | None,
        execution_plan: QueryExecutionPlan | None,
    ) -> dict[str, str]:
        period_scope = dict((execution_plan.constraints if execution_plan else {}).get("period_scope") or {})
        if period_scope.get("start_date") and period_scope.get("end_date"):
            return {
                "start_date": str(period_scope.get("start_date") or ""),
                "end_date": str(period_scope.get("end_date") or ""),
            }
        if resolved_query is not None:
            return {
                "start_date": str((resolved_query.normalized_period or {}).get("start_date") or ""),
                "end_date": str((resolved_query.normalized_period or {}).get("end_date") or ""),
            }
        return {"start_date": "", "end_date": ""}

    @staticmethod
    def _collect_row_values(*, rows: list[dict[str, Any]], keys: tuple[str, ...]) -> set[str]:
        values: set[str] = set()
        for row in rows:
            if not isinstance(row, dict):
                continue
            for key in keys:
                raw = str(row.get(key) or "").strip().upper()
                if raw:
                    values.add(raw)
        return values

    @staticmethod
    def _find_group_dimension_in_rows(*, rows: list[dict[str, Any]], expected_group_by: list[str]) -> str:
        if not rows:
            return ""
        aliases = {
            "supervisor": {"supervisor"},
            "area": {"area"},
            "cargo": {"cargo"},
            "birth_month": {"birth_month", "mes", "month"},
            "carpeta": {"carpeta"},
            "justificacion": {"justificacion", "motivo", "causa"},
            "estado": {"estado", "estado_justificacion"},
            "estado_justificacion": {"estado", "estado_justificacion"},
            "periodo": {"periodo", "fecha", "mes"},
        }
        keys = {str(key or "").strip().lower() for row in rows if isinstance(row, dict) for key in row.keys()}
        for requested in expected_group_by:
            options = aliases.get(requested, {requested})
            for option in options:
                if option in keys:
                    return option
        return ""

    @classmethod
    def _has_group_metric(cls, *, rows: list[dict[str, Any]], expected_group_by: list[str]) -> bool:
        group_aliases = set(expected_group_by)
        aliases = {
            "supervisor": {"supervisor"},
            "area": {"area"},
            "cargo": {"cargo"},
            "birth_month": {"birth_month", "mes", "month"},
            "carpeta": {"carpeta"},
            "justificacion": {"justificacion", "motivo", "causa"},
            "estado": {"estado", "estado_justificacion"},
            "estado_justificacion": {"estado", "estado_justificacion"},
            "periodo": {"periodo", "fecha", "mes"},
        }
        for item in list(expected_group_by or []):
            group_aliases.update(aliases.get(str(item or "").strip().lower(), set()))
        for row in rows:
            if not isinstance(row, dict):
                continue
            for key, value in row.items():
                normalized_key = str(key or "").strip().lower()
                if normalized_key in group_aliases or isinstance(value, bool):
                    continue
                if isinstance(value, (int, float)):
                    return True
        return False

    @staticmethod
    def _resolve_expected_cedula(message: str, *, resolved_query: ResolvedQuerySpec | None) -> str:
        if resolved_query is not None:
            value = resolved_query.normalized_filters.get("cedula")
            normalized = ResultSatisfactionValidator._normalize_identifier(str(value or ""))
            if normalized:
                return normalized
        match = re.search(r"\b\d{6,13}\b", str(message or ""))
        if not match:
            return ""
        return ResultSatisfactionValidator._normalize_identifier(match.group(0))

    @staticmethod
    def _extract_period_from_response(*, response: dict[str, Any]) -> tuple[date, date] | None:
        reply = str((response or {}).get("reply") or "").lower()
        match = re.search(r"periodo\s+(\d{4}-\d{2}-\d{2})\s+al\s+(\d{4}-\d{2}-\d{2})", reply)
        if match:
            try:
                return date.fromisoformat(match.group(1)), date.fromisoformat(match.group(2))
            except Exception:
                return None

        table = dict((dict((response or {}).get("data") or {})).get("table") or {})
        rows = list(table.get("rows") or [])
        if rows and isinstance(rows[0], dict):
            first = rows[0]
            if first.get("periodo_inicio") and first.get("periodo_fin"):
                try:
                    return date.fromisoformat(str(first.get("periodo_inicio"))), date.fromisoformat(str(first.get("periodo_fin")))
                except Exception:
                    return None
        return None

    @staticmethod
    def _normalize_identifier(value: str) -> str:
        return "".join(ch for ch in str(value or "") if ch.isdigit())

    @staticmethod
    def _normalize_text(value: str) -> str:
        return str(value or "").strip().lower()
