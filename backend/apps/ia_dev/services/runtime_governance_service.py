from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any

from apps.ia_dev.application.delegation.domain_context_loader import DomainContextLoader
from apps.ia_dev.application.runtime.functional_validation_suite import (
    ValidationCase,
    build_functional_validation_cases,
)
from apps.ia_dev.services.ai_dictionary_deduplication_service import (
    AIDictionaryDeduplicationService,
)
from apps.ia_dev.services.dictionary_tool_service import DictionaryToolService
from apps.ia_dev.services.observability_service import ObservabilityService
from apps.ia_dev.services.sql_store import IADevSqlStore


class RuntimeGovernanceService:
    PHASE9_LAST_FIX_AT = datetime(2026, 5, 2, 0, 0, 0, tzinfo=timezone.utc)

    def __init__(
        self,
        *,
        observability_service: ObservabilityService | None = None,
        dictionary_service: DictionaryToolService | None = None,
        context_loader: DomainContextLoader | None = None,
        deduplication_service: AIDictionaryDeduplicationService | None = None,
        sql_store: IADevSqlStore | None = None,
    ) -> None:
        self.observability_service = observability_service or ObservabilityService()
        self.dictionary_service = dictionary_service or DictionaryToolService()
        self.context_loader = context_loader or DomainContextLoader()
        self.deduplication_service = deduplication_service or AIDictionaryDeduplicationService(
            context_loader=self.context_loader,
        )
        self.sql_store = sql_store or IADevSqlStore()

    def build_monitor_summary(self, *, domain: str, days: int) -> dict[str, Any]:
        normalized_domain = str(domain or "").strip().lower() or "ausentismo"
        safe_days = max(1, min(int(days), 30))
        raw = self.observability_service.summary_filtered(
            window_seconds=safe_days * 86400,
            limit=5000,
            domain_code=normalized_domain,
        )
        runtime = dict(raw.get("runtime_analytics") or {})
        total = int(runtime.get("total_analytics_queries") or 0)
        sql_count = int(runtime.get("sql_assisted_count") or 0)
        handler_count = int(runtime.get("handler_count") or 0)
        runtime_only_fallback_count = int(runtime.get("runtime_only_fallback_count") or 0)
        blocked_legacy_fallback_count = int(runtime.get("blocked_legacy_fallback_count") or 0)
        return {
            "domain": normalized_domain,
            "days": safe_days,
            "volumen_consultas": total,
            "sql_assisted_count": sql_count,
            "sql_assisted_pct": self._safe_pct(sql_count, total),
            "handler_count": handler_count,
            "handler_pct": self._safe_pct(handler_count, total),
            "legacy_count": int(runtime.get("legacy_count") or 0),
            "runtime_only_fallback_count": runtime_only_fallback_count,
            "blocked_legacy_fallback_count": blocked_legacy_fallback_count,
            "unsafe_sql_plan_count": int(runtime.get("unsafe_sql_plan_count") or 0),
            "no_metric_column_declared_count": int(
                runtime.get("no_metric_column_declared_count") or 0
            ),
            "no_allowed_dimension_count": int(
                runtime.get("no_allowed_dimension_count") or 0
            ),
            "missing_dictionary_relation_count": int(
                runtime.get("missing_dictionary_relation_count") or 0
            ),
            "missing_dictionary_column_count": int(
                runtime.get("missing_dictionary_column_count") or 0
            ),
            "satisfaction_review_failed_count": int(
                runtime.get("satisfaction_review_failed_count") or 0
            ),
            "insight_poor_count": int(runtime.get("insight_poor_count") or 0),
            "top_preguntas_fallidas": list(runtime.get("top_failed_questions") or []),
            "top_columnas_usadas": list(runtime.get("top_columns_used") or []),
            "top_relaciones_usadas": list(runtime.get("top_relations_used") or []),
            "recomendaciones": list(runtime.get("improvement_recommendations") or []),
            "raw_summary": raw,
        }

    def build_pilot_report(
        self,
        *,
        domain: str,
        days: int,
        since_fix: bool = False,
        created_after: int | str | None = None,
    ) -> dict[str, Any]:
        normalized_domain = str(domain or "").strip().lower() or "ausentismo"
        safe_days = max(1, min(int(days), 30))
        window_seconds = safe_days * 86400
        fix_cutoff = self._resolve_fix_cutoff(
            domain=normalized_domain,
            since_fix=since_fix,
            created_after=created_after,
        )
        events = list(
            self.observability_service.list_events(
                window_seconds=window_seconds,
                limit=10000,
                event_types=["runtime_response_resolved", "query_sql_assisted_error"],
                created_after=fix_cutoff,
            )
            or []
        )
        runtime_events = [
            event
            for event in events
            if str(event.get("event_type") or "") == "runtime_response_resolved"
        ]
        sql_error_events = [
            event
            for event in events
            if str(event.get("event_type") or "") == "query_sql_assisted_error"
        ]
        pilot_runtime_events = [
            event
            for event in runtime_events
            if self._event_matches_runtime_pilot_scope(event=event, domain=normalized_domain)
        ]
        pilot_sql_errors = [
            event
            for event in sql_error_events
            if self._event_matches_sql_error_scope(event=event, domain=normalized_domain)
        ]

        top_questions = Counter()
        top_failures = Counter()
        columns_used = Counter()
        relations_used = Counter()
        compilers_used = Counter()
        poor_insights: list[dict[str, Any]] = []

        sql_assisted_count = 0
        handler_count = 0
        runtime_only_fallback_count = 0
        legacy_count = 0
        blocked_legacy_count = 0
        satisfaction_review_failed_count = 0

        for event in pilot_runtime_events:
            meta = dict(event.get("meta") or {})
            response_flow = str(meta.get("response_flow") or "").strip().lower()
            question = str(meta.get("original_question") or "").strip()
            fallback_reason = str(
                meta.get("runtime_only_fallback_reason")
                or meta.get("fallback_reason")
                or meta.get("sql_reason")
                or ""
            ).strip().lower()
            insight_quality = str(meta.get("insight_quality") or "").strip().lower()
            compiler_used = str(meta.get("compiler_used") or "").strip().lower()
            if question:
                top_questions[question] += 1
            if response_flow == "sql_assisted":
                sql_assisted_count += 1
            elif response_flow == "handler":
                handler_count += 1
            elif response_flow == "runtime_only_fallback":
                runtime_only_fallback_count += 1
            elif response_flow == "legacy_fallback":
                legacy_count += 1
            if bool(meta.get("blocked_legacy_fallback")):
                blocked_legacy_count += 1
            if not bool(dict(meta.get("satisfaction_review") or {}).get("satisfied", True)):
                satisfaction_review_failed_count += 1
            if fallback_reason:
                top_failures[fallback_reason] += 1
            if insight_quality == "poor":
                top_failures["insight_poor"] += 1
                poor_insights.append(
                    {
                        "question": question or "(sin pregunta)",
                        "response_flow": response_flow or "unknown",
                        "fallback_reason": fallback_reason,
                        "insight_quality": insight_quality,
                    }
                )
            if compiler_used:
                compilers_used[compiler_used] += 1
            for column in list(meta.get("columns_used") or []):
                token = str(column or "").strip().lower()
                if token:
                    columns_used[token] += 1
            for relation in list(meta.get("relations_used") or []):
                token = self._normalize_relation(relation)
                if token:
                    relations_used[token] += 1

        for event in pilot_sql_errors:
            meta = dict(event.get("meta") or {})
            error = str(meta.get("error") or "sql_execution_error").strip().lower()
            if error:
                top_failures[error] += 1

        errores_sql = len(pilot_sql_errors)
        insight_poor_count = len(poor_insights)
        recommendations = self._build_pilot_recommendations(
            top_failures=top_failures,
            poor_insights=poor_insights,
            columns_used=columns_used,
            relations_used=relations_used,
        )
        return {
            "domain": normalized_domain,
            "days": safe_days,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "since_fix": bool(since_fix),
            "created_after": int(fix_cutoff or 0),
            "total_consultas_reales": len(pilot_runtime_events),
            "sql_assisted_count": sql_assisted_count,
            "handler_count": handler_count,
            "runtime_only_fallback_count": runtime_only_fallback_count,
            "legacy_count": legacy_count,
            "blocked_legacy_count": blocked_legacy_count,
            "errores_sql": errores_sql,
            "satisfaction_review_failed_count": satisfaction_review_failed_count,
            "insight_poor_count": insight_poor_count,
            "top_preguntas": self._top_counter(top_questions, label="question"),
            "top_fallos": self._top_counter(top_failures, label="failure"),
            "compiladores_usados": self._top_counter(compilers_used, label="compiler"),
            "columnas_usadas": self._top_counter(columns_used, label="column"),
            "relaciones_usadas": self._top_counter(relations_used, label="relation"),
            "insights_pobres": poor_insights[:10],
            "recomendaciones_ai_dictionary": recommendations,
        }

    def build_pilot_health(
        self,
        *,
        domain: str,
        days: int,
        since_fix: bool = False,
        created_after: int | str | None = None,
    ) -> dict[str, Any]:
        report = self.build_pilot_report(
            domain=domain,
            days=days,
            since_fix=since_fix,
            created_after=created_after,
        )
        checks = {
            "legacy_count": int(report.get("legacy_count") or 0),
            "runtime_only_fallback_count": int(report.get("runtime_only_fallback_count") or 0),
            "blocked_legacy_count": int(report.get("blocked_legacy_count") or 0),
            "errores_sql": int(report.get("errores_sql") or 0),
            "satisfaction_review_failed_count": int(
                report.get("satisfaction_review_failed_count") or 0
            ),
            "insight_poor_count": int(report.get("insight_poor_count") or 0),
        }
        failing_checks = [
            f"{key}={value}"
            for key, value in checks.items()
            if int(value or 0) > 0
        ]
        return {
            "domain": str(report.get("domain") or domain or "ausentismo"),
            "days": int(report.get("days") or days or 1),
            "status": "healthy" if not failing_checks else "unhealthy",
            "checks": checks,
            "failing_checks": failing_checks,
            "report": report,
        }

    def _resolve_fix_cutoff(
        self,
        *,
        domain: str,
        since_fix: bool,
        created_after: int | str | None,
    ) -> int | None:
        explicit_cutoff = self._parse_created_after(created_after)
        if explicit_cutoff > 0:
            return explicit_cutoff
        if not since_fix:
            return None
        fix_cutoff = int(self.sql_store.get_latest_domain_fix_timestamp(domain_code=domain) or 0)
        if fix_cutoff > 0:
            return fix_cutoff
        return int(self.PHASE9_LAST_FIX_AT.timestamp())

    @staticmethod
    def _parse_created_after(value: int | str | None) -> int:
        if value is None:
            return 0
        if isinstance(value, int):
            return max(0, int(value))
        raw = str(value or "").strip()
        if not raw:
            return 0
        if raw.isdigit():
            numeric = int(raw)
            if numeric > 9999999999:
                return int(numeric / 1000)
            return max(0, numeric)
        normalized = raw.replace("T", " ")
        if normalized.endswith("Z"):
            normalized = normalized[:-1] + "+00:00"
        for candidate in (normalized, normalized.replace("/", "-")):
            try:
                parsed = datetime.fromisoformat(candidate)
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                else:
                    parsed = parsed.astimezone(timezone.utc)
                return int(parsed.timestamp())
            except ValueError:
                continue
        return 0

    def audit_dictionary(self, *, domain: str, with_empleados: bool = False) -> dict[str, Any]:
        domains = [str(domain or "").strip().lower() or "ausentismo"]
        if with_empleados and "empleados" not in domains:
            domains.append("empleados")
        contexts = self.context_loader.load_from_files()
        cases = self._cases_for_domains(domains=domains)

        dd_columns: set[str] = set()
        dd_metric_columns: set[str] = set()
        dd_relations: set[str] = set()
        dd_relation_names: set[str] = set()
        dd_synonyms: set[tuple[str, str]] = set()
        dd_rules: set[str] = set()
        domain_reports: list[dict[str, Any]] = []

        for domain_code in domains:
            dictionary_context = self.dictionary_service.get_domain_context(domain_code, limit=250)
            fields = [dict(item) for item in list(dictionary_context.get("fields") or [])]
            relations = [dict(item) for item in list(dictionary_context.get("relations") or [])]
            synonyms = [dict(item) for item in list(dictionary_context.get("synonyms") or [])]
            rules = [dict(item) for item in list(dictionary_context.get("rules") or [])]
            for field in fields:
                logical = self._normalize_key(field.get("campo_logico"))
                column_name = self._normalize_key(field.get("column_name"))
                if logical:
                    dd_columns.add(logical)
                if column_name:
                    dd_columns.add(column_name)
                if bool(field.get("supports_metric") or field.get("es_metrica")) and column_name:
                    dd_metric_columns.add(column_name)
            for relation in relations:
                name = self._normalize_key(relation.get("nombre_relacion"))
                join_sql = self._normalize_relation(relation.get("join_sql"))
                if name:
                    dd_relation_names.add(name)
                if join_sql:
                    dd_relations.add(join_sql)
            for synonym in synonyms:
                term = self._normalize_key(synonym.get("termino"))
                alias = self._normalize_key(synonym.get("sinonimo"))
                if term and alias:
                    dd_synonyms.add((term, alias))
            for rule in rules:
                code = self._normalize_key(rule.get("codigo"))
                name = self._normalize_key(rule.get("nombre"))
                if code:
                    dd_rules.add(code)
                if name:
                    dd_rules.add(name)
            domain_reports.append(
                {
                    "domain": domain_code,
                    "dictionary_context": dictionary_context,
                    "yaml_context": dict(contexts.get(domain_code) or {}),
                }
            )

        required_columns = self._required_columns_from_cases(cases=cases)
        required_metrics = self._required_metrics_from_cases(cases=cases)
        required_relations = self._required_relations_from_cases(cases=cases)
        required_synonyms = self._required_synonyms_from_cases(cases=cases)
        required_rules = self._required_rules_from_yaml(domain_reports=domain_reports)

        yaml_structural_leaks = self._find_yaml_structural_leaks(
            domain_reports=domain_reports,
            dd_columns=dd_columns,
            dd_relations=dd_relations,
            dd_relation_names=dd_relation_names,
            dd_rules=dd_rules,
        )
        duplicated_definitions = self._find_duplicated_definitions(
            domain_reports=domain_reports,
            domains=domains,
        )
        missing_columns = sorted(item for item in required_columns if item not in dd_columns)
        missing_metrics = sorted(item for item in required_metrics if item not in dd_metric_columns)
        missing_relations = sorted(
            item
            for item in required_relations
            if item not in dd_relations and item not in dd_relation_names
        )
        missing_synonyms = sorted(
            f"{term}->{alias}"
            for term, alias in required_synonyms
            if (term, alias) not in dd_synonyms
        )
        missing_rules = sorted(item for item in required_rules if item not in dd_rules)
        missing_dictionary_metadata = [
            *({"type": "column", "value": item} for item in missing_columns),
            *({"type": "metric", "value": item} for item in missing_metrics),
            *({"type": "relation", "value": item} for item in missing_relations),
            *({"type": "synonym", "value": item} for item in missing_synonyms),
            *({"type": "rule", "value": item} for item in missing_rules),
        ]

        return {
            "domains": domains,
            "missing_columns": missing_columns,
            "missing_metrics": missing_metrics,
            "missing_relations": missing_relations,
            "missing_synonyms": missing_synonyms,
            "missing_rules": missing_rules,
            "duplicated_definitions": duplicated_definitions,
            "yaml_structural_leaks": yaml_structural_leaks,
            "yaml_fields_ignored": self._collect_yaml_field_events(
                domain_reports=domain_reports,
                key="yaml_fields_ignored",
                event_type="yaml_field_ignored",
            ),
            "yaml_fields_removed": self._collect_yaml_field_events(
                domain_reports=domain_reports,
                key="yaml_fields_removed",
                event_type="yaml_field_removed",
            ),
            "missing_dictionary_metadata": missing_dictionary_metadata,
        }

    @staticmethod
    def _safe_pct(value: int, total: int) -> float:
        if total <= 0:
            return 0.0
        return round((float(value) / float(total)) * 100.0, 2)

    @staticmethod
    def _normalize_key(value: Any) -> str:
        return str(value or "").strip().lower().replace(" ", "_")

    @staticmethod
    def _normalize_relation(value: Any) -> str:
        return " ".join(str(value or "").strip().lower().split())

    @staticmethod
    def _top_counter(counter: Counter[str], *, label: str) -> list[dict[str, Any]]:
        ordered = sorted(counter.items(), key=lambda item: (-int(item[1]), item[0]))
        return [{label: key, "count": int(value)} for key, value in ordered[:10]]

    @classmethod
    def _event_matches_runtime_pilot_scope(cls, *, event: dict[str, Any], domain: str) -> bool:
        meta = dict(event.get("meta") or {})
        if not bool(meta.get("pilot_enabled")):
            return False
        event_domain = str(meta.get("domain_resolved") or "").strip().lower()
        if event_domain != str(domain or "").strip().lower():
            return False
        return event_domain in {"ausentismo", "attendance", "empleados", "rrhh"}

    @classmethod
    def _event_matches_sql_error_scope(cls, *, event: dict[str, Any], domain: str) -> bool:
        meta = dict(event.get("meta") or {})
        if not bool(meta.get("pilot_enabled")):
            return False
        return str(meta.get("domain_code") or "").strip().lower() == str(domain or "").strip().lower()

    @classmethod
    def _build_pilot_recommendations(
        cls,
        *,
        top_failures: Counter[str],
        poor_insights: list[dict[str, Any]],
        columns_used: Counter[str],
        relations_used: Counter[str],
    ) -> list[str]:
        recommendations: list[str] = []
        if int(top_failures.get("missing_dictionary_relation") or 0) > 0:
            recommendations.append(
                "Registrar o corregir joins en ai_dictionary.dd_relaciones para las consultas auditadas del piloto."
            )
        if any("sql_execution_error" in key for key in top_failures):
            recommendations.append(
                "Revisar SQL compilado y columnas declaradas en ai_dictionary.dd_campos para eliminar errores de ejecucion."
            )
        if int(top_failures.get("unsupported_metric") or 0) > 0:
            recommendations.append(
                "Declarar metricas y capacidades analiticas faltantes en ai_dictionary.dd_campos e ia_dev_capacidades_columna."
            )
        if int(top_failures.get("unsupported_dimension") or 0) > 0:
            recommendations.append(
                "Completar dimensiones seguras y sinonimos en ai_dictionary.dd_campos y ai_dictionary.dd_sinonimos."
            )
        if poor_insights:
            recommendations.append(
                "Refinar reglas narrativas del dominio y enriquecer columnas accionables para reducir insight_quality=poor."
            )
        if not relations_used:
            recommendations.append(
                "Validar que las relaciones de ausentismo y empleados sigan trazables en ai_dictionary antes de ampliar el rollout."
            )
        if columns_used:
            hot_columns = ", ".join(key for key, _ in columns_used.most_common(3))
            recommendations.append(
                f"Priorizar cobertura y sinonimos de las columnas mas usadas del piloto: {hot_columns}."
            )
        if not recommendations:
            recommendations.append(
                "Piloto estable: mantener monitoreo diario y ampliar ejemplos de ai_dictionary sobre consultas reales mas frecuentes."
            )
        return recommendations[:5]

    def _cases_for_domains(self, *, domains: list[str]) -> list[ValidationCase]:
        wanted = set(domains)
        return [
            case
            for case in build_functional_validation_cases()
            if str(case.expected_domain or "").strip().lower() in wanted
        ]

    def _required_columns_from_cases(self, *, cases: list[ValidationCase]) -> set[str]:
        required: set[str] = set()
        for case in cases:
            required.update(
                self._normalize_key(item)
                for item in list(case.required_columns)
                if self._normalize_key(item)
            )
        return required

    def _required_metrics_from_cases(self, *, cases: list[ValidationCase]) -> set[str]:
        required: set[str] = set()
        for case in cases:
            for metric in list(case.resolved_query.intent.metrics or []):
                token = str(metric or "").strip().lower()
                if not token or token == "count":
                    continue
                if ":" in token:
                    token = token.split(":", 1)[1]
                token = self._normalize_key(token)
                if token:
                    required.add(token)
        return required

    def _required_relations_from_cases(self, *, cases: list[ValidationCase]) -> set[str]:
        return {
            self._normalize_relation(item)
            for case in cases
            for item in list(case.required_relations)
            if self._normalize_relation(item)
        }

    def _required_synonyms_from_cases(
        self,
        *,
        cases: list[ValidationCase],
    ) -> set[tuple[str, str]]:
        required: set[tuple[str, str]] = set()
        synonym_map = {
            "area": ("areas",),
            "cargo": ("cargos",),
            "sede": ("sedes",),
            "empleado": ("empleados",),
            "dias_perdidos": ("dias_perdidos", "dias perdidos"),
        }
        for case in cases:
            for group in list(case.resolved_query.intent.group_by or []):
                canonical = self._normalize_key(group)
                for alias in synonym_map.get(canonical, ()):
                    required.add((canonical, self._normalize_key(alias)))
            for metric in list(case.resolved_query.intent.metrics or []):
                token = str(metric or "").strip().lower()
                if ":" in token:
                    token = token.split(":", 1)[1]
                canonical = self._normalize_key(token)
                for alias in synonym_map.get(canonical, ()):
                    required.add((canonical, self._normalize_key(alias)))
        return required

    def _required_rules_from_yaml(self, *, domain_reports: list[dict[str, Any]]) -> set[str]:
        required: set[str] = set()
        for report in domain_reports:
            yaml_context = dict(report.get("yaml_context") or {})
            for rule in list(yaml_context.get("reglas_negocio") or []):
                if isinstance(rule, dict):
                    for key in ("codigo", "nombre", "id"):
                        token = self._normalize_key(rule.get(key))
                        if token:
                            required.add(token)
        return required

    def _yaml_structural_inventory(self, *, yaml_context: dict[str, Any]) -> dict[str, Any]:
        explicit = dict(yaml_context.get("yaml_structural_inventory") or {})
        if explicit:
            return {
                "columns": list(explicit.get("columns") or []),
                "relationships": list(explicit.get("relationships") or []),
            }
        return {
            "columns": list(yaml_context.get("columns") or []),
            "relationships": list(yaml_context.get("relationships") or []),
        }

    def _collect_yaml_field_events(
        self,
        *,
        domain_reports: list[dict[str, Any]],
        key: str,
        event_type: str,
    ) -> list[dict[str, str]]:
        events: list[dict[str, str]] = []
        for report in domain_reports:
            domain_code = str(report.get("domain") or "")
            yaml_context = dict(report.get("yaml_context") or {})
            for field in list(yaml_context.get(key) or []):
                token = self._normalize_key(field)
                if token:
                    events.append({"domain": domain_code, "type": event_type, "value": token})
        return events

    def _find_yaml_structural_leaks(
        self,
        *,
        domain_reports: list[dict[str, Any]],
        dd_columns: set[str],
        dd_relations: set[str],
        dd_relation_names: set[str],
        dd_rules: set[str],
    ) -> list[dict[str, Any]]:
        leaks: list[dict[str, Any]] = []
        for report in domain_reports:
            domain_code = str(report.get("domain") or "")
            yaml_context = dict(report.get("yaml_context") or {})
            yaml_structural_inventory = self._yaml_structural_inventory(yaml_context=yaml_context)
            for column in list(yaml_structural_inventory.get("columns") or []):
                if not isinstance(column, dict):
                    continue
                logical = self._normalize_key(column.get("nombre_columna_logico"))
                physical = self._normalize_key(column.get("column_name"))
                if logical and logical not in dd_columns and physical and physical not in dd_columns:
                    leaks.append(
                        {
                            "domain": domain_code,
                            "type": "yaml_column_not_in_dd_campos",
                            "value": logical or physical,
                        }
                    )
            for relation in list(yaml_structural_inventory.get("relationships") or []):
                if not isinstance(relation, dict):
                    continue
                name = self._normalize_key(relation.get("nombre_relacion"))
                join_sql = self._normalize_relation(
                    relation.get("condicion") or relation.get("join_sql")
                )
                if join_sql and join_sql not in dd_relations and name not in dd_relation_names:
                    leaks.append(
                        {
                            "domain": domain_code,
                            "type": "yaml_relation_not_in_dd_relaciones",
                            "value": name or join_sql,
                        }
                    )
            for rule in list(yaml_context.get("reglas_negocio") or []):
                if not isinstance(rule, dict):
                    continue
                token = self._normalize_key(
                    rule.get("codigo") or rule.get("nombre") or rule.get("id")
                )
                if token and token not in dd_rules:
                    leaks.append(
                        {
                            "domain": domain_code,
                            "type": "yaml_rule_not_in_dd_reglas",
                            "value": token,
                        }
                    )
        return leaks

    def _find_duplicated_definitions(
        self,
        *,
        domain_reports: list[dict[str, Any]],
        domains: list[str],
    ) -> list[dict[str, Any]]:
        analysis = self.deduplication_service.analyze(
            domain=str((domains or ["ausentismo"])[0] or "ausentismo"),
            with_empleados="empleados" in set(domains),
        )
        duplicates = [
            {
                "entity_type": str(item.get("entity_type") or ""),
                "classification": str(item.get("classification") or ""),
                "canonical_record": dict(item.get("canonical_record") or {}),
                "duplicate_record": dict(item.get("duplicate_record") or {}),
                "conflict_reason": str(item.get("conflict_reason") or ""),
                "recommended_action": str(item.get("recommended_action") or ""),
            }
            for item in list(analysis.get("duplicates") or [])
            if str(item.get("classification") or "") == "conflicting"
        ]
        duplicates.sort(
            key=lambda item: (
                str(item.get("entity_type") or ""),
                str(((item.get("canonical_record") or {}).get("id")) or ""),
                str(((item.get("duplicate_record") or {}).get("id")) or ""),
            )
        )
        return duplicates
