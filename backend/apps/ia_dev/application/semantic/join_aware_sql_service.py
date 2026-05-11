from __future__ import annotations

import re
from typing import Any

from apps.ia_dev.application.contracts.query_intelligence_contracts import ResolvedQuerySpec
from apps.ia_dev.application.semantic.synonym_semantic_resolver import SynonymSemanticResolver


class JoinAwarePilotSqlService:
    SUPPORTED_DOMAIN_CODES = {"ausentismo", "attendance"}
    SUPPORTED_DIMENSIONS = {"area", "cargo", "sede", "fecha", "empleado", "justificacion"}
    MAX_DIMENSIONS = 3

    def __init__(self):
        self.synonyms = SynonymSemanticResolver()

    def is_enabled(self, *, semantic_context: dict[str, Any]) -> bool:
        meta = dict(semantic_context.get("source_of_truth") or {})
        return bool(meta.get("pilot_sql_assisted_enabled"))

    def should_handle(self, *, resolved_query: ResolvedQuerySpec) -> bool:
        domain_code = str(resolved_query.intent.domain_code or "").strip().lower()
        if domain_code not in self.SUPPORTED_DOMAIN_CODES:
            return False
        context = dict(resolved_query.semantic_context or {})
        if not self.is_enabled(semantic_context=context):
            return False

        raw_query = self._normalize_text(resolved_query.intent.raw_query)
        group_by = [self._canonical_term(item, context=context) for item in list(resolved_query.intent.group_by or [])]
        if any(item in {"area", "cargo", "sede", "fecha", "empleado"} for item in group_by):
            return True
        return any(
            token in raw_query
            for token in (
                "riesgo",
                "incapacidad",
                "incapacidades",
                "patron",
                "patrones",
                "sede",
                "areas",
                "cargos",
                "repetitiv",
                "recurrent",
                "recurren",
                "empleados",
            )
        )

    def compile(self, *, resolved_query: ResolvedQuerySpec, max_limit: int) -> dict[str, Any]:
        context = dict(resolved_query.semantic_context or {})
        alias_map = {"gestionh_ausentismo": "a", "cinco_base_de_personal": "e"}
        tables = self._table_index(context=context)
        relation = self._resolve_relation(context=context)
        if not relation:
            return self._compile_error(reason="pilot_relation_missing")

        attendance_table = tables.get("gestionh_ausentismo")
        employee_table = tables.get("cinco_base_de_personal")
        if not attendance_table or not employee_table:
            return self._compile_error(reason="pilot_tables_missing")

        dimensions_result = self._resolve_dimensions(resolved_query=resolved_query, context=context)
        if not dimensions_result.get("ok"):
            return self._compile_error(
                reason=str(dimensions_result.get("reason") or "pilot_dimension_missing_or_unsafe"),
                metadata={
                    "dimensions_used": list(dimensions_result.get("dimensions_used") or []),
                    "declared_dimensions_source": str(
                        dimensions_result.get("declared_dimensions_source") or "ai_dictionary.dd_campos"
                    ),
                },
            )
        dimensions = list(dimensions_result.get("dimensions") or [])
        if not dimensions:
            return self._compile_error(reason="pilot_dimension_missing_or_unsafe")

        metric_result = self._resolve_metric(resolved_query=resolved_query, context=context)
        if not metric_result.get("ok"):
            return self._compile_error(
                reason=str(metric_result.get("reason") or "no_metric_column_declared"),
                metadata={
                    "metric_used": str(metric_result.get("metric_used") or ""),
                    "aggregation_used": str(metric_result.get("aggregation_used") or ""),
                    "declared_metric_source": str(
                        metric_result.get("declared_metric_source") or "ai_dictionary.dd_campos"
                    ),
                },
            )

        select_dimension = ", ".join(str(item.get("sql") or "") for item in dimensions)
        group_dimension = ", ".join(str(item.get("group_sql") or "") for item in dimensions)
        output_alias = str((dimensions[0] or {}).get("alias") or "dimension")
        physical_columns_used = []
        for dimension in dimensions:
            physical_columns_used.extend(list(dimension.get("physical_columns") or []))
        physical_columns_used.extend(list(metric_result.get("physical_columns") or []))
        dimensions_used = [str(item.get("alias") or "") for item in dimensions if str(item.get("alias") or "").strip()]

        justification_column = self._resolve_column(
            context=context,
            preferred_terms=("justificacion", "motivo_justificacion"),
            preferred_tables=("gestionh_ausentismo",),
        )
        employee_name_column = self._resolve_column(
            context=context,
            preferred_terms=("nombre_completo", "nombre", "nombre_empleado"),
            preferred_tables=("cinco_base_de_personal",),
        )
        employee_last_name_column = self._resolve_column(
            context=context,
            preferred_terms=("apellido", "apellido_empleado"),
            preferred_tables=("cinco_base_de_personal",),
        )
        date_column = self._resolve_column(
            context=context,
            preferred_terms=("fecha_ausentismo", "fecha_edit", "fecha"),
            preferred_tables=("gestionh_ausentismo",),
        )
        physical_columns_used.extend(
            self._physical_column_name(item)
            for item in [justification_column, employee_name_column, employee_last_name_column, date_column]
            if self._physical_column_name(item)
        )

        where_parts = []
        period = dict(resolved_query.normalized_period or {})
        if date_column and period.get("start_date") and period.get("end_date"):
            where_parts.append(
                f"DATE({date_column}) BETWEEN '{self._escape(period.get('start_date'))}' AND '{self._escape(period.get('end_date'))}'"
            )

        raw_query = self._normalize_text(resolved_query.intent.raw_query)
        detected_filters: list[str] = []
        if justification_column and any(token in raw_query for token in ("incapacidad", "incapacidades")):
            where_parts.append(f"UPPER(COALESCE({justification_column}, '')) LIKE '%INCAPAC%'")
            detected_filters.append("incapacidad")

        limit = max(1, min(int(max_limit or 50), 100))
        metric_sql = str(metric_result.get("sql") or "COUNT(*) AS total_ausentismos")
        risk_sql = ""
        order_sql = str(metric_result.get("order_alias") or "total_ausentismos") + " DESC"
        insights = ["Piloto SQL assisted join-aware ejecutado con joins validados desde ai_dictionary.dd_relaciones."]

        if output_alias == "empleado" and len(dimensions) == 1:
            employee_id_column = self._resolve_column(
                context=context,
                preferred_terms=("cedula", "cedula_empleado", "identificacion"),
                preferred_tables=("cinco_base_de_personal",),
            )
            if not employee_id_column:
                return self._compile_error(reason="pilot_employee_identifier_missing_or_unsafe")
            display_name = employee_name_column or employee_id_column
            if employee_last_name_column and employee_name_column and employee_last_name_column != employee_name_column:
                display_name = (
                    f"TRIM(CONCAT(COALESCE({employee_name_column}, ''), ' ', COALESCE({employee_last_name_column}, '')))"
                )
            select_dimension = f"{display_name} AS empleado, {employee_id_column} AS cedula"
            group_dimension = f"{display_name}, {employee_id_column}"
            physical_columns_used.append(self._physical_column_name(employee_id_column))
            risk_sql = (
                ", CASE "
                "WHEN COUNT(*) >= 6 THEN 'alto' "
                "WHEN COUNT(*) >= 3 THEN 'medio' "
                "ELSE 'bajo' END AS nivel_riesgo"
            )
            insights.append("El nivel de riesgo se estima por frecuencia observada de ausentismos en el periodo consultado.")

        if output_alias == "fecha" and str(metric_result.get("aggregation_used") or "") == "count":
            order_sql = "fecha ASC"
            insights.append("La salida por fecha permite detectar patrones temporales y picos de ausentismo.")

        from_sql = (
            f"FROM {attendance_table} AS a "
            f"JOIN {employee_table} AS e ON {self._alias_join_sql(relation, alias_map=alias_map)}"
        )
        where_sql = f" WHERE {' AND '.join(where_parts)}" if where_parts else ""
        query = (
            f"SELECT {select_dimension}, {metric_sql}{risk_sql} "
            f"{from_sql}{where_sql} "
            f"GROUP BY {group_dimension} "
            f"ORDER BY {order_sql} LIMIT {limit}"
        )
        return {
            "ok": True,
            "sql_query": query,
            "reason": f"pilot_join_aware_{output_alias}",
            "metadata": {
                "compiler": "join_aware_pilot",
                "compiler_used": "join_aware_pilot",
                "tables_detected": ["gestionh_ausentismo", "cinco_base_de_personal"],
                "columns_detected": sorted({item for item in physical_columns_used if item}),
                "physical_columns_used": sorted({item for item in physical_columns_used if item}),
                "relations_used": [relation],
                "safe_dimensions": sorted(self.SUPPORTED_DIMENSIONS),
                "filters_applied": detected_filters,
                "metric_used": str(metric_result.get("metric_used") or ""),
                "aggregation_used": str(metric_result.get("aggregation_used") or ""),
                "dimensions_used": dimensions_used,
                "declared_metric_source": str(metric_result.get("declared_metric_source") or "ai_dictionary.dd_campos"),
                "declared_dimensions_source": str(
                    dimensions_result.get("declared_dimensions_source") or "ai_dictionary.dd_campos"
                ),
                "insights": insights,
            },
        }

    def _resolve_dimensions(self, *, resolved_query: ResolvedQuerySpec, context: dict[str, Any]) -> dict[str, Any]:
        raw_query = self._normalize_text(resolved_query.intent.raw_query)
        requested = [self._canonical_term(item, context=context) for item in list(resolved_query.intent.group_by or [])]
        requested = [item for item in requested if item]
        if "riesgo" in raw_query and "empleado" not in requested:
            requested.insert(0, "empleado")
        if any(token in raw_query for token in ("patron", "patrones")) and not requested:
            for candidate in ("area", "cargo", "sede", "fecha"):
                if candidate in raw_query:
                    requested.append(candidate)
        if not requested:
            for candidate in ("area", "cargo", "sede", "fecha", "empleado"):
                if candidate in raw_query or f"{candidate}s" in raw_query:
                    requested.append(candidate)

        requested = list(dict.fromkeys(requested))
        if len(requested) > self.MAX_DIMENSIONS:
            return {
                "ok": False,
                "reason": "max_dimensions_exceeded",
                "dimensions_used": requested[: self.MAX_DIMENSIONS + 1],
                "declared_dimensions_source": "ai_dictionary.dd_campos",
            }

        resolved_dimensions: list[dict[str, Any]] = []
        declared_source = "ai_dictionary.dd_campos"
        for item in requested:
            if item not in self.SUPPORTED_DIMENSIONS:
                return {
                    "ok": False,
                    "reason": "no_allowed_dimension",
                    "dimensions_used": requested,
                    "declared_dimensions_source": declared_source,
                }
            if item == "fecha":
                date_column = self._resolve_column(
                    context=context,
                    preferred_terms=("fecha_ausentismo", "fecha_edit", "fecha"),
                    preferred_tables=("gestionh_ausentismo",),
                )
                if date_column:
                    resolved_dimensions.append(
                        {
                            "sql": f"DATE({date_column}) AS fecha",
                            "group_sql": f"DATE({date_column})",
                            "alias": "fecha",
                            "physical_columns": [self._physical_column_name(date_column)],
                        }
                    )
                    continue
                return {
                    "ok": False,
                    "reason": "no_allowed_dimension",
                    "dimensions_used": requested,
                    "declared_dimensions_source": declared_source,
                }
            if item == "empleado":
                employee_id_column = self._resolve_column(
                    context=context,
                    preferred_terms=("cedula", "cedula_empleado", "identificacion"),
                    preferred_tables=("cinco_base_de_personal",),
                )
                if employee_id_column:
                    resolved_dimensions.append(
                        {
                            "sql": employee_id_column,
                            "group_sql": employee_id_column,
                            "alias": "empleado",
                            "physical_columns": [self._physical_column_name(employee_id_column)],
                        }
                    )
                    continue
                return {
                    "ok": False,
                    "reason": "no_allowed_dimension",
                    "dimensions_used": requested,
                    "declared_dimensions_source": declared_source,
                }
            column = self._resolve_column(
                context=context,
                preferred_terms=(item,),
                preferred_tables=("cinco_base_de_personal", "gestionh_ausentismo"),
            )
            if column:
                canonical_requested = next(
                    (
                        str(raw).strip().lower()
                        for raw in list(resolved_query.intent.group_by or [])
                        if self._canonical_term(str(raw), context=context) == item
                    ),
                    item,
                )
                if canonical_requested != item:
                    declared_source = "ai_dictionary.dd_sinonimos+dd_campos"
                resolved_dimensions.append(
                    {
                        "sql": f"{column} AS {item}",
                        "group_sql": column,
                        "alias": item,
                        "physical_columns": [self._physical_column_name(column)],
                    }
                )
                continue
            return {
                "ok": False,
                "reason": "no_allowed_dimension",
                "dimensions_used": requested,
                "declared_dimensions_source": declared_source,
            }
        if not resolved_dimensions:
            return {"ok": False, "reason": "pilot_dimension_missing_or_unsafe"}
        return {
            "ok": True,
            "dimensions": resolved_dimensions,
            "dimensions_used": [str(item.get("alias") or "") for item in resolved_dimensions],
            "declared_dimensions_source": declared_source,
        }

    def _resolve_metric(self, *, resolved_query: ResolvedQuerySpec, context: dict[str, Any]) -> dict[str, Any]:
        raw_query = self._normalize_text(resolved_query.intent.raw_query)
        requested_metrics = [str(item or "").strip() for item in list(resolved_query.intent.metrics or []) if str(item or "").strip()]
        if not requested_metrics and "dias perdidos" in raw_query:
            requested_metrics = ["sum:dias_perdidos"]
        if not requested_metrics:
            requested_metrics = ["count"]

        for token in requested_metrics:
            parsed = self._parse_metric_token(token=token, context=context)
            aggregation = str(parsed.get("aggregation") or "count")
            metric_name = str(parsed.get("metric") or "")
            metric_source = str(parsed.get("declared_metric_source") or "ai_dictionary.dd_campos")
            if aggregation == "count":
                return {
                    "ok": True,
                    "sql": "COUNT(*) AS total_ausentismos",
                    "order_alias": "total_ausentismos",
                    "metric_used": metric_name or "ausencias",
                    "aggregation_used": "count",
                    "declared_metric_source": metric_source,
                    "physical_columns": [],
                }
            if aggregation != "sum" or not metric_name:
                continue
            metric_column = self._resolve_metric_column(context=context, metric_name=metric_name)
            if not metric_column:
                return {
                    "ok": False,
                    "reason": "no_metric_column_declared",
                    "metric_used": metric_name,
                    "aggregation_used": aggregation,
                    "declared_metric_source": metric_source,
                }
            return {
                "ok": True,
                "sql": f"SUM(COALESCE({metric_column}, 0)) AS total_dias_perdidos",
                "order_alias": "total_dias_perdidos",
                "metric_used": metric_name,
                "aggregation_used": aggregation,
                "declared_metric_source": metric_source,
                "physical_columns": [self._physical_column_name(metric_column)],
            }
        return {
            "ok": False,
            "reason": "no_metric_column_declared",
            "metric_used": requested_metrics[0] if requested_metrics else "",
            "aggregation_used": "",
            "declared_metric_source": "ai_dictionary.dd_campos",
        }

    def _parse_metric_token(self, *, token: str, context: dict[str, Any]) -> dict[str, str]:
        clean = self._normalize_text(token)
        if clean in {"count", "conteo"}:
            return {
                "aggregation": "count",
                "metric": "ausencias",
                "declared_metric_source": "ai_dictionary.dd_campos",
            }
        if ":" in clean:
            aggregation, metric = clean.split(":", 1)
            canonical_metric = self._canonical_term(metric, context=context)
            source = "ai_dictionary.dd_sinonimos+dd_campos" if canonical_metric != metric else "ai_dictionary.dd_campos"
            return {
                "aggregation": aggregation.strip(),
                "metric": canonical_metric.strip(),
                "declared_metric_source": source,
            }
        canonical_metric = self._canonical_term(clean, context=context)
        source = "ai_dictionary.dd_sinonimos+dd_campos" if canonical_metric != clean else "ai_dictionary.dd_campos"
        aggregation = "sum" if canonical_metric in {"dias_perdidos", "dias perdidos"} else ""
        return {
            "aggregation": aggregation,
            "metric": canonical_metric,
            "declared_metric_source": source,
        }

    def _resolve_metric_column(self, *, context: dict[str, Any], metric_name: str) -> str:
        profiles = [dict(item) for item in list(context.get("column_profiles") or []) if isinstance(item, dict)]
        allowed_columns = {
            str(item or "").strip().lower()
            for item in list(context.get("allowed_columns") or [])
            if str(item or "").strip()
        }
        canonical_metric = self._canonical_term(metric_name, context=context)
        for profile in profiles:
            logical_name = str(profile.get("logical_name") or "").strip().lower()
            column_name = str(profile.get("column_name") or "").strip().lower()
            if canonical_metric not in {logical_name, column_name}:
                continue
            if not bool(profile.get("supports_metric")):
                continue
            if column_name not in allowed_columns:
                continue
            table_name = str(profile.get("table_name") or "").strip().lower()
            alias = "e" if table_name == "cinco_base_de_personal" else "a"
            return f"{alias}.{column_name}"
        return ""

    @staticmethod
    def _compile_error(*, reason: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = dict(metadata or {})
        payload["fallback_reason"] = str(reason or "")
        return {"ok": False, "reason": str(reason or ""), "metadata": payload}

    def _resolve_relation(self, *, context: dict[str, Any]) -> str:
        relation_candidates = list((context.get("dictionary") or {}).get("relations") or [])
        for row in relation_candidates:
            if not isinstance(row, dict):
                continue
            join_sql = str(row.get("join_sql") or "").strip()
            normalized = join_sql.lower()
            if "gestionh_ausentismo" in normalized and "cinco_base_de_personal" in normalized:
                return join_sql
        return ""

    def _resolve_column(
        self,
        *,
        context: dict[str, Any],
        preferred_terms: tuple[str, ...],
        preferred_tables: tuple[str, ...],
    ) -> str:
        profiles = [dict(item) for item in list(context.get("column_profiles") or []) if isinstance(item, dict)]
        aliases = dict(context.get("aliases") or {})
        allowed_columns = {
            str(item or "").strip().lower()
            for item in list(context.get("allowed_columns") or [])
            if str(item or "").strip()
        }
        normalized_terms = {
            self._canonical_term(item, context=context)
            for item in preferred_terms
            if self._canonical_term(item, context=context)
        }
        normalized_terms.update(
            {
                self._canonical_term(str(aliases.get(item) or item), context=context)
                for item in preferred_terms
            }
        )
        for profile in profiles:
            table_name = str(profile.get("table_name") or "").strip().lower()
            logical_name = str(profile.get("logical_name") or profile.get("campo_logico") or "").strip().lower()
            column_name = str(profile.get("column_name") or "").strip().lower()
            if preferred_tables and table_name not in preferred_tables:
                continue
            if logical_name not in normalized_terms and column_name not in normalized_terms:
                continue
            if column_name not in allowed_columns:
                continue
            alias = "e" if table_name == "cinco_base_de_personal" else "a"
            return f"{alias}.{column_name}"
        return ""

    @staticmethod
    def _table_index(*, context: dict[str, Any]) -> dict[str, str]:
        index: dict[str, str] = {}
        for row in list(context.get("tables") or []):
            if not isinstance(row, dict):
                continue
            table_name = str(row.get("table_name") or "").strip().lower()
            schema_name = str(row.get("schema_name") or "").strip()
            if not table_name:
                continue
            index[table_name] = f"{schema_name}.{table_name}" if schema_name else table_name
        return index

    @staticmethod
    def _alias_join_sql(join_sql: str, *, alias_map: dict[str, str]) -> str:
        aliased = str(join_sql or "").strip()
        for table_name, alias in alias_map.items():
            aliased = re.sub(rf"\b{re.escape(table_name)}\.", f"{alias}.", aliased, flags=re.IGNORECASE)
        return aliased

    def _canonical_term(self, value: str | None, *, context: dict[str, Any]) -> str:
        return self.synonyms.canonicalize(
            term=value,
            synonym_index=dict(context.get("synonym_index") or {}),
        )

    @staticmethod
    def _normalize_text(value: str | None) -> str:
        return str(value or "").strip().lower()

    @staticmethod
    def _escape(value: Any) -> str:
        return str(value or "").replace("'", "''")

    @staticmethod
    def _physical_column_name(value: str | None) -> str:
        token = str(value or "").strip()
        if "." not in token:
            return token.lower()
        return token.split(".")[-1].strip().lower()
