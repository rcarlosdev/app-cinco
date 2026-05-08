from __future__ import annotations

import copy
import os
import re
import unicodedata
from datetime import date, timedelta
from typing import Any

from apps.ia_dev.application.contracts.query_intelligence_contracts import (
    ResolvedQuerySpec,
    StructuredQueryIntent,
)
from apps.ia_dev.application.delegation.domain_registry import DomainRegistry
from apps.ia_dev.application.semantic.column_semantic_resolver import ColumnSemanticResolver
from apps.ia_dev.application.semantic.query_intent_resolver import QueryIntentResolver
from apps.ia_dev.application.semantic.relation_semantic_resolver import RelationSemanticResolver
from apps.ia_dev.application.semantic.rule_semantic_resolver import RuleSemanticResolver
from apps.ia_dev.application.semantic.synonym_semantic_resolver import SynonymSemanticResolver
from apps.ia_dev.services.ai_dictionary_remediation_service import AIDictionaryRemediationService
from apps.ia_dev.services.dictionary_tool_service import DictionaryToolService
from apps.ia_dev.services.employee_identifier_service import EmployeeIdentifierService
from apps.ia_dev.services.period_service import resolve_period_from_text


class SemanticBusinessResolver:
    """
    Convierte intencion estructurada en especificacion operativa de negocio
    usando ai_dictionary.dd_* como fuente estructural y YAML solo como narrativa.
    """

    DOMAIN_TO_DICTIONARY_CODE = {
        "ausentismo": "ausentismo",
        "attendance": "ausentismo",
        "empleados": "empleados",
        "rrhh": "empleados",
        "transporte": "transport",
        "transport": "transport",
    }
    LEGACY_STRUCTURAL_CATALOGS = (
        "ia_dev_catalogo_*",
        "dd_campos_semantic_profile",
        "dd_capacidades_campo",
    )

    def __init__(
        self,
        *,
        registry: DomainRegistry | None = None,
        dictionary_tool: DictionaryToolService | None = None,
        column_resolver: ColumnSemanticResolver | None = None,
        relation_resolver: RelationSemanticResolver | None = None,
        rule_resolver: RuleSemanticResolver | None = None,
        synonym_resolver: SynonymSemanticResolver | None = None,
    ):
        self.registry = registry or DomainRegistry()
        self.dictionary_tool = dictionary_tool or DictionaryToolService()
        self.column_resolver = column_resolver or ColumnSemanticResolver()
        self.relation_resolver = relation_resolver or RelationSemanticResolver()
        self.rule_resolver = rule_resolver or RuleSemanticResolver()
        self.synonym_resolver = synonym_resolver or SynonymSemanticResolver()

    def build_semantic_context(self, *, domain_code: str, include_dictionary: bool = True) -> dict[str, Any]:
        normalized_domain = self.registry.normalize_domain_code(domain_code)
        domain = self.registry.get_domain(normalized_domain)
        raw = dict((domain.raw_context if domain else {}) or {})
        company_context = self._normalize_company_context(raw_company_context=raw.get("company_context"))
        contexto_agente = dict(raw.get("contexto_agente") or {})
        reglas_negocio = list(raw.get("reglas_negocio") or [])
        ejemplos_consulta = list(raw.get("ejemplos_consulta") or [])
        vocabulario_negocio = list(raw.get("vocabulario_negocio") or [])
        tablas_prioritarias = list(raw.get("tablas_prioritarias") or [])
        columnas_prioritarias = list(raw.get("columnas_prioritarias") or [])
        yaml_structural_inventory = self._extract_yaml_structural_inventory(raw=raw)
        yaml_fields_ignored = self._resolve_yaml_field_list(
            raw=raw,
            explicit_key="yaml_fields_ignored",
            structural_inventory=yaml_structural_inventory,
        )
        yaml_fields_removed = self._resolve_yaml_field_list(
            raw=raw,
            explicit_key="yaml_fields_removed",
            structural_inventory=yaml_structural_inventory,
        )
        capabilities = list(raw.get("capabilities") or raw.get("legacy_capabilities") or [])
        flags = dict(raw.get("flags") or {})

        dictionary_context: dict[str, Any] = {}
        dictionary_seed: dict[str, Any] = {
            "enabled": False,
            "status": "skipped",
            "inserted": 0,
            "skipped": 0,
            "errors": [],
        }
        if include_dictionary:
            dictionary_domain = self.DOMAIN_TO_DICTIONARY_CODE.get(normalized_domain, normalized_domain or "general")
            if dictionary_domain == "empleados":
                dictionary_seed = self._maybe_seed_rrhh_status_synonyms()
            try:
                dictionary_context = self.dictionary_tool.get_domain_context(dictionary_domain, limit=20)
            except Exception:
                dictionary_context = {}
            dictionary_context = self._merge_remediation_dictionary_context(
                normalized_domain=normalized_domain,
                dictionary_context=dictionary_context,
            )

        dictionary_fields = list(dictionary_context.get("fields") or [])
        dictionary_relations = list(dictionary_context.get("relations") or [])
        dictionary_synonyms = list(dictionary_context.get("synonyms") or [])
        dictionary_rules = list(dictionary_context.get("rules") or [])
        dictionary_field_profiles = list(dictionary_context.get("field_profiles") or [])
        dictionary_tables = self._dictionary_tables_from_context(dictionary_context=dictionary_context)
        dictionary_field_profiles.extend(
            self._load_dictionary_table_field_profiles(
                table_names=[
                    str(item.get("table_fqn") or item.get("table_name") or "").strip()
                    for item in dictionary_tables
                    if isinstance(item, dict)
                    and str(item.get("table_fqn") or item.get("table_name") or "").strip()
                ]
            )
        )
        dictionary_field_profiles = self._merge_dictionary_rows(
            rows=dictionary_field_profiles,
            key_builder=lambda row: (
                str((row or {}).get("table_name") or "").strip().lower(),
                str((row or {}).get("campo_logico") or (row or {}).get("logical_name") or "").strip().lower(),
                str((row or {}).get("column_name") or "").strip().lower(),
            ),
        )
        dictionary_relationships = self._dictionary_relationships_from_relations(dictionary_relations=dictionary_relations)
        dictionary_fields, dictionary_field_profiles = self._extend_joined_table_semantics(
            normalized_domain=normalized_domain,
            tables=dictionary_tables,
            relationships=dictionary_relationships,
            dictionary_fields=dictionary_fields,
            dictionary_field_profiles=dictionary_field_profiles,
        )
        tables = self._dictionary_tables_from_context(dictionary_context=dictionary_context)
        columns = self._dictionary_columns_from_fields(
            dictionary_fields=dictionary_fields,
        )
        relationships = self._dictionary_relationships_from_relations(dictionary_relations=dictionary_relations)
        missing_dictionary_metadata = self._find_missing_dictionary_metadata(
            normalized_domain=normalized_domain,
            dictionary_context=dictionary_context,
            dictionary_fields=dictionary_fields,
            dictionary_relations=dictionary_relations,
            yaml_structural_inventory=yaml_structural_inventory,
        )

        column_profiles = self.column_resolver.build_column_profiles(
            runtime_columns=[],
            dictionary_fields=dictionary_fields,
        )
        if dictionary_field_profiles:
            # Prefer perfiles persistidos cuando existan.
            column_profiles = self.column_resolver.build_column_profiles(
                runtime_columns=[],
                dictionary_fields=dictionary_field_profiles + dictionary_fields,
            )

        relation_profiles = self.relation_resolver.build_relation_profiles(
            runtime_relationships=[],
            dictionary_relations=dictionary_relations,
        )

        synonym_index = self.synonym_resolver.build_index(
            dictionary_synonyms=dictionary_synonyms,
            dictionary_fields=dictionary_fields,
            runtime_columns=[],
        )
        company_synonym_index = self._build_company_language_synonym_index(company_context=company_context)
        synonym_index = {**company_synonym_index, **synonym_index}

        allowed_tables = self._collect_allowed_tables(tables=[], dictionary_context=dictionary_context)
        allowed_columns = self._collect_allowed_columns(columns=[], dictionary_fields=dictionary_fields)
        aliases = self._collect_aliases(columns=[], dictionary_fields=dictionary_fields, dictionary_synonyms=dictionary_synonyms)
        aliases = {**synonym_index, **aliases}
        operational_scope = self._build_company_operational_scope(
            normalized_domain=normalized_domain,
            company_context=company_context,
        )
        pilot_sql_assisted_enabled = bool(
            dictionary_fields
            and (
                (
                    normalized_domain in {"ausentismo", "attendance"}
                    and dictionary_relations
                    and any(
                        str(item.get("table_name") or "").strip().lower() == "cinco_base_de_personal"
                        for item in dictionary_fields
                        if isinstance(item, dict)
                    )
                )
                or (
                    normalized_domain in {"empleados", "rrhh"}
                    and any(
                        str(item.get("table_name") or "").strip().lower() == "cinco_base_de_personal"
                        for item in dictionary_fields
                        if isinstance(item, dict)
                    )
                )
            )
        )
        query_hints = self._build_query_hints(
            normalized_domain=normalized_domain,
            tables=tables,
            column_profiles=column_profiles,
            relation_profiles=relation_profiles,
        )
        used_yaml = any(
            [
                bool(contexto_agente),
                bool(reglas_negocio),
                bool(ejemplos_consulta),
                bool(vocabulario_negocio),
                bool(tablas_prioritarias),
                bool(columnas_prioritarias),
                bool(yaml_fields_ignored),
            ]
        )
        runtime_structural_status = "dictionary_runtime_context" if (tables or columns or relationships) else "dictionary_metadata_missing"

        return {
            "domain_code": normalized_domain,
            "domain_status": str(getattr(domain, "domain_status", raw.get("domain_status", "planned")) or "planned"),
            "maturity_level": str(getattr(domain, "maturity_level", raw.get("maturity_level", "initial")) or "initial"),
            "schema_confidence": float(getattr(domain, "schema_confidence", raw.get("schema_confidence", 0.0)) or 0.0),
            "main_entity": str(getattr(domain, "main_entity", raw.get("main_entity", "")) or ""),
            "business_goal": str(getattr(domain, "business_goal", raw.get("business_goal", "")) or ""),
            "tables": tables,
            "columns": columns,
            "relationships": relationships,
            "capabilities": capabilities,
            "flags": flags,
            "dictionary": {
                "fields": dictionary_fields,
                "relations": dictionary_relations,
                "rules": dictionary_rules,
                "synonyms": dictionary_synonyms,
                "field_profiles": dictionary_field_profiles,
            },
            "dictionary_meta": {
                "schema": str(dictionary_context.get("schema") or ""),
                "dictionary_table": str(dictionary_context.get("dictionary_table") or ""),
                "profile_table_name": str(dictionary_context.get("profile_table_name") or ""),
                "domain": dict(dictionary_context.get("domain") or {}),
            },
            "column_profiles": column_profiles,
            "relation_profiles": relation_profiles,
            "synonym_index": synonym_index,
            "allowed_tables": allowed_tables,
            "allowed_columns": allowed_columns,
            "aliases": aliases,
            "supports_sql_assisted": bool(flags.get("sql_asistido_permitido")) or pilot_sql_assisted_enabled,
            "dictionary_seed": dictionary_seed,
            "company_context": company_context,
            "company_operational_scope": operational_scope,
            "query_hints": query_hints,
            "yaml_role": "narrative_only",
            "yaml_fields_ignored": yaml_fields_ignored,
            "yaml_fields_removed": yaml_fields_removed,
            "yaml_structural_inventory": yaml_structural_inventory,
            "missing_dictionary_metadata": missing_dictionary_metadata,
            "source_of_truth": {
                "structural": "ai_dictionary.dd_*",
                "narrative": "yaml_domain_context",
                "structural_authority": "dictionary_first",
                "structural_source": "ai_dictionary",
                "yaml_role": "narrative_only",
                "yaml_structural_ignored": bool(yaml_fields_ignored),
                "yaml_fields_ignored": list(yaml_fields_ignored),
                "yaml_fields_removed": list(yaml_fields_removed),
                "missing_dictionary_metadata": list(missing_dictionary_metadata),
                "pilot_sql_assisted_enabled": pilot_sql_assisted_enabled,
                "used_dictionary": bool(include_dictionary and dictionary_context),
                "used_yaml": used_yaml,
                "runtime_structural_context": {
                    "tables": bool(tables),
                    "columns": bool(columns),
                    "relationships": bool(relationships),
                    "status": runtime_structural_status,
                },
                "legacy_catalogs": [
                    {
                        "pattern": pattern,
                        "status": "deprecated",
                        "mode": "isolated_non_authoritative",
                    }
                    for pattern in self.LEGACY_STRUCTURAL_CATALOGS
                ],
            },
            "contexto_agente": contexto_agente,
            "reglas_negocio": reglas_negocio,
            "ejemplos_consulta": ejemplos_consulta,
            "vocabulario_negocio": vocabulario_negocio,
            "tablas_prioritarias": tablas_prioritarias,
            "columnas_prioritarias": columnas_prioritarias,
        }

    def _merge_remediation_dictionary_context(
        self,
        *,
        normalized_domain: str,
        dictionary_context: dict[str, Any],
    ) -> dict[str, Any]:
        if normalized_domain not in {"empleados", "rrhh"}:
            return dict(dictionary_context or {})
        manifest = self._normalize_remediation_manifest(
            AIDictionaryRemediationService()._build_domain_manifest(domain_code="empleados")
        )
        merged = dict(dictionary_context or {})
        for key, key_builder in (
            (
                "tables",
                lambda row: (
                    str((row or {}).get("schema_name") or "").strip().lower(),
                    str((row or {}).get("table_name") or "").strip().lower(),
                ),
            ),
            (
                "fields",
                lambda row: (
                    str((row or {}).get("table_name") or "").strip().lower(),
                    str((row or {}).get("campo_logico") or "").strip().lower(),
                    str((row or {}).get("column_name") or "").strip().lower(),
                ),
            ),
            (
                "rules",
                lambda row: str((row or {}).get("codigo") or (row or {}).get("nombre") or "").strip().lower(),
            ),
            (
                "synonyms",
                lambda row: (
                    str((row or {}).get("termino") or "").strip().lower(),
                    str((row or {}).get("sinonimo") or "").strip().lower(),
                ),
            ),
        ):
            merged[key] = self._merge_dictionary_rows(
                rows=[*list(merged.get(key) or []), *list(manifest.get(key) or [])],
                key_builder=key_builder,
            )
        return merged

    def _load_dictionary_table_field_profiles(self, *, table_names: list[str]) -> list[dict[str, Any]]:
        requested = [str(item or "").strip() for item in list(table_names or []) if str(item or "").strip()]
        if not requested or not hasattr(self.dictionary_tool, "get_table_field_profiles"):
            return []
        try:
            rows = self.dictionary_tool.get_table_field_profiles(requested, limit=80)
        except Exception:
            return []
        if not isinstance(rows, list):
            return []
        return [dict(row) for row in list(rows or []) if isinstance(row, dict)]

    @staticmethod
    def _merge_dictionary_rows(
        *,
        rows: list[dict[str, Any]],
        key_builder,
    ) -> list[dict[str, Any]]:
        merged: dict[Any, dict[str, Any]] = {}
        for row in rows:
            if not isinstance(row, dict):
                continue
            key = key_builder(row)
            if not key:
                continue
            merged[key] = {**dict(merged.get(key) or {}), **dict(row)}
        return list(merged.values())

    @staticmethod
    def _normalize_remediation_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(manifest or {})
        fields: list[dict[str, Any]] = []
        for item in list(normalized.get("fields") or []):
            if not isinstance(item, dict):
                continue
            capabilities = dict(item.get("capabilities") or {})
            fields.append(
                {
                    **dict(item),
                    "campo_logico": item.get("campo_logico") or item.get("logical_name"),
                    "valores_permitidos": item.get("valores_permitidos") or item.get("allowed_values"),
                    "es_filtro": item.get("es_filtro") if item.get("es_filtro") is not None else capabilities.get("supports_filter"),
                    "es_group_by": item.get("es_group_by") if item.get("es_group_by") is not None else capabilities.get("supports_group_by"),
                    "es_metrica": item.get("es_metrica") if item.get("es_metrica") is not None else capabilities.get("supports_metric"),
                    "es_dimension": item.get("es_dimension") if item.get("es_dimension") is not None else capabilities.get("supports_dimension"),
                }
            )
        normalized["fields"] = fields
        synonyms: list[dict[str, Any]] = []
        for item in list(normalized.get("synonyms") or []):
            if isinstance(item, dict):
                synonyms.append(dict(item))
                continue
            if isinstance(item, tuple) and len(item) == 2:
                synonyms.append({"termino": item[0], "sinonimo": item[1]})
        normalized["synonyms"] = synonyms
        return normalized

    def _extend_joined_table_semantics(
        self,
        *,
        normalized_domain: str,
        tables: list[dict[str, Any]],
        relationships: list[dict[str, Any]],
        dictionary_fields: list[dict[str, Any]],
        dictionary_field_profiles: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        if normalized_domain not in {"ausentismo", "attendance"}:
            return list(dictionary_fields or []), list(dictionary_field_profiles or [])

        joined_table_names = {
            str(item.get("table_fqn") or item.get("table_name") or "").strip().lower()
            for item in list(tables or [])
            if isinstance(item, dict)
            and str(item.get("table_fqn") or item.get("table_name") or "").strip()
        }
        joined_table_names.update(
            {
                "cinco_base_de_personal"
                for item in list(relationships or [])
                if isinstance(item, dict)
                and "cinco_base_de_personal" in str(item.get("condicion") or item.get("condicion_join_sql") or "").strip().lower()
            }
        )
        employee_like_tables = {
            name for name in joined_table_names if name in {"cinco_base_de_personal"}
        }
        if not employee_like_tables:
            return list(dictionary_fields or []), list(dictionary_field_profiles or [])

        extra_profiles = self.dictionary_tool.get_table_field_profiles(
            sorted(employee_like_tables),
            limit=120,
        )
        base_fields = list(dictionary_fields or [])
        base_profiles = list(dictionary_field_profiles or [])
        seen_keys = {
            (
                str(item.get("table_fqn") or item.get("table_name") or "").strip().lower(),
                str(item.get("campo_logico") or item.get("column_name") or "").strip().lower(),
            )
            for item in [*base_fields, *base_profiles]
            if isinstance(item, dict)
        }
        for row in extra_profiles:
            if not isinstance(row, dict):
                continue
            key = (
                str(row.get("table_fqn") or row.get("table_name") or "").strip().lower(),
                str(row.get("campo_logico") or row.get("column_name") or "").strip().lower(),
            )
            if not key[0] or not key[1] or key in seen_keys:
                continue
            seen_keys.add(key)
            payload = dict(row)
            payload.setdefault("semantic_source", "joined_table_profile")
            base_fields.append(payload)
            base_profiles.append(dict(payload))
        return base_fields, base_profiles

    def resolve_query(
        self,
        *,
        message: str,
        intent: StructuredQueryIntent,
        base_classification: dict[str, Any],
        semantic_context_override: dict[str, Any] | None = None,
    ) -> ResolvedQuerySpec:
        domain_code = self.registry.normalize_domain_code(intent.domain_code or base_classification.get("domain"))
        attendance_reason = self._resolve_attendance_reason_from_message(message=message)
        if self._should_rescue_to_attendance(
            message=message,
            domain_code=domain_code,
            intent=intent,
            attendance_reason=attendance_reason,
        ):
            domain_code = "ausentismo"
        if isinstance(semantic_context_override, dict) and semantic_context_override:
            semantic_context = copy.deepcopy(semantic_context_override)
        else:
            semantic_context = self.build_semantic_context(domain_code=domain_code, include_dictionary=True)
        operational_scope = dict(semantic_context.get("company_operational_scope") or {})
        synonym_index = dict(semantic_context.get("synonym_index") or {})
        known_logical_names = {
            str(item.get("logical_name") or item.get("column_name") or "").strip().lower()
            for item in list(semantic_context.get("column_profiles") or [])
            if isinstance(item, dict) and str(item.get("logical_name") or item.get("column_name") or "").strip()
        }

        def canonicalize_term(value: str | None) -> str:
            normalized_value = self._normalize_text(value)
            if normalized_value in known_logical_names:
                return normalized_value
            canonical = self.synonym_resolver.canonicalize(
                term=value,
                synonym_index=synonym_index,
            )
            normalized_canonical = self._normalize_text(canonical)
            if normalized_value in known_logical_names and normalized_canonical not in known_logical_names:
                return normalized_value
            return canonical

        dictionary_rules = list((semantic_context.get("dictionary") or {}).get("rules") or [])
        rule_filters = self.rule_resolver.apply_rule_overrides(
            message=message,
            domain_code=domain_code,
            filters=dict(intent.filters or {}),
            dictionary_rules=dictionary_rules,
        )
        if domain_code in {"ausentismo", "attendance"} and attendance_reason:
            for status_key in ("estado", "estado_empleado"):
                raw_status = str(rule_filters.get(status_key) or "").strip().upper()
                if raw_status and raw_status not in {"ACTIVO", "INACTIVO"}:
                    rule_filters.pop(status_key, None)
            rule_filters["justificacion"] = attendance_reason
        identifier_filter = self.column_resolver.resolve_identifier_filter(
            message=message,
            semantic_context=semantic_context,
        )
        if identifier_filter:
            identifier_key, identifier_value = identifier_filter
            rule_filters.setdefault(identifier_key, identifier_value)
        schema_value_filters, schema_value_resolutions = self.column_resolver.resolve_schema_value_filters(
            message=message,
            semantic_context=semantic_context,
        )
        for key, value in schema_value_filters.items():
            if str(value or "").strip():
                rule_filters.setdefault(str(key), value)
        birthday_month = self._resolve_birthday_filter(message=message, filters=rule_filters)
        if birthday_month:
            rule_filters["fnacimiento_month"] = birthday_month

        normalized_filters, filter_resolutions = self.column_resolver.resolve_filters(
            filters=rule_filters,
            semantic_context=semantic_context,
            canonicalize_term=canonicalize_term,
            normalize_status_value=self.rule_resolver.normalize_status_value,
        )
        filter_resolutions = [*list(schema_value_resolutions or []), *list(filter_resolutions or [])]
        self._apply_executable_filter_aliases(normalized_filters=normalized_filters)
        birthday_month = self._resolve_birthday_filter(message=message, filters=normalized_filters)
        if birthday_month:
            normalized_filters["fnacimiento_month"] = birthday_month
            self._apply_executable_filter_aliases(normalized_filters=normalized_filters)
        status_resolution = self._resolve_status_from_dictionary(
            message=message,
            semantic_context=semantic_context,
            normalized_filters=normalized_filters,
            canonicalize_term=canonicalize_term,
        )
        if status_resolution:
            status_key = str(status_resolution.get("status_key") or "estado").strip().lower() or "estado"
            status_value = str(status_resolution.get("status_value") or "").strip().upper()
            if status_value:
                normalized_filters[status_key] = status_value
                normalized_filters.setdefault("estado", status_value)
        status_value_after_normalization = self._extract_status_value(normalized_filters)
        if status_value_after_normalization and "estado" not in normalized_filters:
            normalized_filters["estado"] = status_value_after_normalization
        elif domain_code in {"empleados", "rrhh"}:
            status_from_message = self._resolve_status_from_message(message=message)
            if status_from_message:
                normalized_filters["estado"] = status_from_message
                normalized_filters["estado_empleado"] = status_from_message
        if domain_code in {"empleados", "rrhh"}:
            dictionary_value_filters = self._resolve_allowed_value_filters_from_dictionary(
                message=message,
                semantic_context=semantic_context,
                normalized_filters=normalized_filters,
            )
            for filter_key, filter_value in dictionary_value_filters.items():
                if not str(filter_value or "").strip():
                    continue
                normalized_filters.setdefault(filter_key, filter_value)
        if domain_code in {"empleados", "rrhh"} and self._is_turnover_query(message):
            normalized_filters["estado"] = "INACTIVO"
            normalized_filters["estado_empleado"] = "INACTIVO"
        if domain_code in {"empleados", "rrhh"}:
            self._apply_default_employee_status(
                semantic_context=semantic_context,
                normalized_filters=normalized_filters,
            )
            self._apply_executable_filter_aliases(normalized_filters=normalized_filters)
            self._prune_missingness_literal_siblings(normalized_filters=normalized_filters)
        normalized_filters = EmployeeIdentifierService.prune_redundant_search_filter(normalized_filters)
        resolved_group_by, group_resolutions = self.column_resolver.resolve_group_by(
            requested_group_by=list(intent.group_by or []),
            message=message,
            semantic_context=semantic_context,
            canonicalize_term=canonicalize_term,
        )
        inferred_group_by = self._infer_group_by_from_query(
            domain_code=domain_code,
            message=message,
            intent=intent,
            semantic_context=semantic_context,
            canonicalize_term=canonicalize_term,
        )
        if inferred_group_by:
            resolved_group_by = list(dict.fromkeys([*list(resolved_group_by or []), *list(inferred_group_by or [])]))
        if (
            domain_code in {"empleados", "rrhh"}
            and QueryIntentResolver._has_missingness_filter(filters=dict(normalized_filters or {}))
            and not re.search(r"\bpor\s+[a-z0-9_]+\b", self._normalize_text(message))
        ):
            resolved_group_by = []
        if domain_code in {"empleados", "rrhh"}:
            resolved_group_by = self._prune_employee_group_by_filters(
                resolved_group_by=resolved_group_by,
                normalized_filters=normalized_filters,
            )
        self._drop_group_dimension_filters(
            resolved_group_by=resolved_group_by,
            normalized_filters=normalized_filters,
        )
        if (
            domain_code in {"empleados", "rrhh"}
            and self._is_birthday_query(message=message, filters=normalized_filters)
            and (
                "birth_month" in list(intent.group_by or [])
                or "birth_month" in list(inferred_group_by or [])
                or "por mes" in self._normalize_text(message)
            )
        ):
            resolved_group_by = list(dict.fromkeys([*list(resolved_group_by or []), "birth_month"]))
        if (
            domain_code in {"empleados", "rrhh"}
            and str(normalized_filters.get("fnacimiento_month") or "").strip()
            and list(resolved_group_by or []) == ["birth_month"]
            and "por mes" not in self._normalize_text(message)
        ):
            resolved_group_by = []
        resolved_metrics, metric_resolutions = self.column_resolver.resolve_metrics(
            requested_metrics=list(intent.metrics or []),
            operation=intent.operation,
            message=message,
            semantic_context=semantic_context,
            canonicalize_term=canonicalize_term,
        )
        normalized_period = self._normalize_period(
            message=message,
            intent=intent,
        )
        temporal_scope = self._resolve_temporal_scope(
            domain_code=domain_code,
            message=message,
            normalized_filters=normalized_filters,
            normalized_period=normalized_period,
        )
        semantic_field_match = self._match_business_concept_field(
            message=message,
            domain_code=domain_code,
            semantic_context=semantic_context,
            normalized_filters=normalized_filters,
            resolved_group_by=resolved_group_by,
        )
        mapped_columns = self._map_filter_columns(
            filters=normalized_filters,
            semantic_context=semantic_context,
        )
        relation_resolutions = self.relation_resolver.resolve_required_relations(
            semantic_context=semantic_context,
            requested_terms=[
                *list(normalized_filters.keys()),
                *list(resolved_group_by),
            ],
        )
        status_value = self._extract_status_value(normalized_filters)
        resolved_operation = str(intent.operation or "").strip().lower()
        resolved_template_id = str(intent.template_id or "").strip().lower()
        is_birthday_query = domain_code in {"empleados", "rrhh"} and self._is_birthday_query(
            message=message,
            filters=normalized_filters,
        )
        if is_birthday_query:
            if resolved_group_by:
                resolved_operation = "aggregate"
                resolved_template_id = "aggregate_by_group_and_period"
            elif str(intent.operation or "").strip().lower() == "count":
                resolved_operation = "count"
                resolved_template_id = "count_records_by_period"
            else:
                resolved_operation = "detail"
                resolved_template_id = "detail_by_entity_and_period"
        if (
            domain_code in {"empleados", "rrhh"}
            and not is_birthday_query
            and not QueryIntentResolver._has_missingness_filter(filters=dict(normalized_filters or {}))
            and status_value
            and (
                str(intent.operation or "").strip().lower() == "count"
                or self._is_general_employee_population_request(
                    message=message,
                    filters=normalized_filters,
                    group_by=resolved_group_by,
                )
            )
        ):
            resolved_operation = "aggregate" if resolved_group_by else "count"
            resolved_template_id = "aggregate_by_group_and_period" if resolved_group_by else "count_entities_by_status"

        resolution_payload = {
            "filters": [item.as_dict() for item in filter_resolutions],
            "group_by": [item.as_dict() for item in group_resolutions],
            "group_by_candidates": self._build_group_by_candidates(
                resolved_group_by=resolved_group_by,
                group_resolutions=group_resolutions,
                semantic_context=semantic_context,
            ),
            "metrics": [item.as_dict() for item in metric_resolutions],
            "relations": [item.as_dict() for item in relation_resolutions],
            "temporal_scope": dict(temporal_scope or {}),
            "field_match": dict(semantic_field_match or {}),
        }
        semantic_context["resolved_semantic"] = resolution_payload
        semantic_context["temporal_scope"] = dict(temporal_scope or {})
        if semantic_field_match:
            semantic_context["semantic_field_match"] = dict(semantic_field_match)
        if (
            operational_scope
            and bool(operational_scope.get("domain_known"))
            and not bool(operational_scope.get("domain_operational", True))
        ):
            semantic_events = list(semantic_context.get("semantic_events") or [])
            semantic_events.append(
                {
                    "event_type": "domain_known_but_not_operational",
                    "domain_code": domain_code,
                    "supported_domains": list(operational_scope.get("supported_domains") or []),
                }
            )
            semantic_context["semantic_events"] = semantic_events
        if status_resolution:
            semantic_events = list(semantic_context.get("semantic_events") or [])
            semantic_events.append(
                {
                    "event_type": "semantic_status_resolved_from_dictionary",
                    "status_value": str(status_resolution.get("status_value") or ""),
                    "status_key": str(status_resolution.get("status_key") or "estado"),
                    "matched_token": str(status_resolution.get("matched_token") or ""),
                    "allowed_values": list(status_resolution.get("allowed_values") or []),
                }
            )
            semantic_context["semantic_events"] = semantic_events
        if temporal_scope:
            semantic_events = list(semantic_context.get("semantic_events") or [])
            if bool(temporal_scope.get("ambiguous")):
                semantic_events.append(
                    {
                        "event_type": "semantic_temporal_scope_ambiguous",
                        "domain_code": domain_code,
                        "reason": str(temporal_scope.get("reason") or ""),
                        "start_date": str(temporal_scope.get("start_date") or ""),
                        "end_date": str(temporal_scope.get("end_date") or ""),
                    }
                )
            else:
                semantic_events.append(
                    {
                        "event_type": "semantic_temporal_scope_bound",
                        "domain_code": domain_code,
                        "column_hint": str(temporal_scope.get("column_hint") or ""),
                        "status_value": str(temporal_scope.get("status_value") or ""),
                        "source": str(temporal_scope.get("source") or ""),
                        "confidence": float(temporal_scope.get("confidence") or 0.0),
                        "start_date": str(temporal_scope.get("start_date") or ""),
                        "end_date": str(temporal_scope.get("end_date") or ""),
                    }
                )
            semantic_context["semantic_events"] = semantic_events

        warnings = self._build_warnings(
            domain_code=domain_code,
            intent=intent,
            normalized_filters=normalized_filters,
            normalized_period=normalized_period,
            temporal_scope=temporal_scope,
            semantic_context=semantic_context,
        )
        return ResolvedQuerySpec(
            intent=StructuredQueryIntent(
                raw_query=intent.raw_query,
                domain_code=domain_code,
                operation=resolved_operation or intent.operation,
                template_id=resolved_template_id or str(intent.template_id or ""),
                entity_type=intent.entity_type,
                entity_value=intent.entity_value,
                filters=dict(normalized_filters or {}),
                period=dict(intent.period or {}),
                group_by=list(resolved_group_by or []),
                metrics=list(resolved_metrics or []),
                confidence=float(intent.confidence or 0.0),
                source=intent.source,
                warnings=list(intent.warnings or []),
            ),
            semantic_context=semantic_context,
            normalized_filters=normalized_filters,
            normalized_period=normalized_period,
            mapped_columns=mapped_columns,
            warnings=warnings,
        )

    @staticmethod
    def _dictionary_tables_from_context(*, dictionary_context: dict[str, Any]) -> list[dict[str, Any]]:
        tables: list[dict[str, Any]] = []
        for item in list(dictionary_context.get("tables") or []):
            if not isinstance(item, dict):
                continue
            schema_name = str(item.get("schema_name") or "").strip()
            table_name = str(item.get("table_name") or "").strip()
            if not table_name:
                continue
            table_fqn = f"{schema_name}.{table_name}" if schema_name else table_name
            tables.append(
                {
                    "schema_name": schema_name,
                    "table_name": table_name,
                    "table_fqn": table_fqn,
                    "nombre_tabla_logico": str(item.get("alias_negocio") or "").strip(),
                    "rol": str(item.get("rol") or "").strip(),
                    "es_principal": bool(item.get("es_principal")),
                }
            )
        return tables

    @staticmethod
    def _dictionary_columns_from_fields(*, dictionary_fields: list[dict[str, Any]]) -> list[dict[str, Any]]:
        columns: list[dict[str, Any]] = []
        for item in list(dictionary_fields or []):
            if not isinstance(item, dict):
                continue
            logical_name = str(item.get("campo_logico") or item.get("logical_name") or "").strip()
            column_name = str(item.get("column_name") or "").strip()
            if not logical_name and not column_name:
                continue
            columns.append(
                {
                    "schema_name": str(item.get("schema_name") or "").strip(),
                    "table_name": str(item.get("table_name") or "").strip(),
                    "table_fqn": str(item.get("table_fqn") or "").strip(),
                    "column_name": column_name,
                    "nombre_columna_logico": logical_name or column_name,
                    "descripcion": str(item.get("definicion_negocio") or "").strip(),
                    "es_filtro": bool(item.get("supports_filter") or item.get("es_filtro")),
                    "es_group_by": bool(item.get("supports_group_by") or item.get("es_group_by")),
                    "es_metrica": bool(item.get("supports_metric") or item.get("es_metrica")),
                    "es_clave": bool(item.get("es_clave")),
                }
            )
        return columns

    @staticmethod
    def _dictionary_relationships_from_relations(*, dictionary_relations: list[dict[str, Any]]) -> list[dict[str, Any]]:
        relationships: list[dict[str, Any]] = []
        for item in list(dictionary_relations or []):
            if not isinstance(item, dict):
                continue
            join_sql = str(item.get("join_sql") or "").strip()
            if not join_sql:
                continue
            relationships.append(
                {
                    "nombre_relacion": str(item.get("nombre_relacion") or "").strip(),
                    "condicion": join_sql,
                    "cardinalidad": str(item.get("cardinalidad") or "").strip(),
                }
            )
        return relationships

    def _extract_yaml_structural_inventory(self, *, raw: dict[str, Any]) -> dict[str, Any]:
        explicit = dict(raw.get("yaml_structural_inventory") or {})
        if explicit:
            return {
                "tables": list(explicit.get("tables") or []),
                "columns": list(explicit.get("columns") or []),
                "relationships": list(explicit.get("relationships") or []),
                "capabilities": list(explicit.get("capabilities") or []),
                "supported_filters": list(explicit.get("supported_filters") or []),
                "supported_group_by": list(explicit.get("supported_group_by") or []),
                "supported_metrics": list(explicit.get("supported_metrics") or []),
            }
        return {
            "tables": list(raw.get("tables") or raw.get("tablas_asociadas") or []),
            "columns": list(raw.get("columns") or raw.get("columnas_clave") or []),
            "relationships": list(raw.get("relationships") or raw.get("joins_conocidos") or []),
            "capabilities": list(raw.get("capabilities") or raw.get("legacy_capabilities") or raw.get("capacidades") or []),
            "supported_filters": list(raw.get("filtros_soportados") or []),
            "supported_group_by": list(raw.get("group_by_soportados") or []),
            "supported_metrics": list(raw.get("metricas_soportadas") or []),
        }

    def _resolve_yaml_field_list(
        self,
        *,
        raw: dict[str, Any],
        explicit_key: str,
        structural_inventory: dict[str, Any],
    ) -> list[str]:
        explicit = [
            str(item or "").strip()
            for item in list(raw.get(explicit_key) or [])
            if str(item or "").strip()
        ]
        if explicit:
            return list(dict.fromkeys(explicit))
        return [
            key
            for key, value in structural_inventory.items()
            if self._has_yaml_structural_payload(value)
        ]

    @staticmethod
    def _has_yaml_structural_payload(value: Any) -> bool:
        if isinstance(value, dict):
            return bool(value)
        if isinstance(value, list):
            return any(item not in (None, "", [], {}) for item in value)
        return value not in (None, "", [], {})

    def _find_missing_dictionary_metadata(
        self,
        *,
        normalized_domain: str,
        dictionary_context: dict[str, Any],
        dictionary_fields: list[dict[str, Any]],
        dictionary_relations: list[dict[str, Any]],
        yaml_structural_inventory: dict[str, Any],
    ) -> list[dict[str, str]]:
        issues: list[dict[str, str]] = []
        matched = bool(dict(dictionary_context.get("domain") or {}).get("matched"))
        if not matched:
            issues.append(
                {
                    "domain": normalized_domain,
                    "type": "dictionary_domain_missing",
                    "value": normalized_domain,
                }
            )
            return issues

        dictionary_tables = {
            str(item.get("table_name") or "").strip().lower()
            for item in list(dictionary_context.get("tables") or [])
            if isinstance(item, dict) and str(item.get("table_name") or "").strip()
        }
        dictionary_columns = {
            str(item.get("campo_logico") or item.get("column_name") or "").strip().lower()
            for item in list(dictionary_fields or [])
            if isinstance(item, dict) and str(item.get("campo_logico") or item.get("column_name") or "").strip()
        }
        dictionary_physical_columns = {
            str(item.get("column_name") or "").strip().lower()
            for item in list(dictionary_fields or [])
            if isinstance(item, dict) and str(item.get("column_name") or "").strip()
        }
        filterable_columns = {
            str(item.get("campo_logico") or item.get("column_name") or "").strip().lower()
            for item in list(dictionary_fields or [])
            if isinstance(item, dict)
            and bool(item.get("supports_filter") or item.get("es_filtro"))
            and str(item.get("campo_logico") or item.get("column_name") or "").strip()
        }
        groupable_columns = {
            str(item.get("campo_logico") or item.get("column_name") or "").strip().lower()
            for item in list(dictionary_fields or [])
            if isinstance(item, dict)
            and bool(item.get("supports_group_by") or item.get("supports_dimension") or item.get("es_group_by"))
            and str(item.get("campo_logico") or item.get("column_name") or "").strip()
        }
        metric_columns = {
            str(item.get("campo_logico") or item.get("column_name") or "").strip().lower()
            for item in list(dictionary_fields or [])
            if isinstance(item, dict)
            and bool(item.get("supports_metric") or item.get("es_metrica"))
            and str(item.get("campo_logico") or item.get("column_name") or "").strip()
        }
        relation_names = {
            str(item.get("nombre_relacion") or "").strip().lower()
            for item in list(dictionary_relations or [])
            if isinstance(item, dict) and str(item.get("nombre_relacion") or "").strip()
        }
        relation_sql = {
            " ".join(str(item.get("join_sql") or "").strip().lower().split())
            for item in list(dictionary_relations or [])
            if isinstance(item, dict) and str(item.get("join_sql") or "").strip()
        }

        for item in list(yaml_structural_inventory.get("tables") or []):
            if not isinstance(item, dict):
                continue
            table_name = str(item.get("table_name") or "").strip().lower()
            if table_name and table_name not in dictionary_tables:
                issues.append({"domain": normalized_domain, "type": "dictionary_table_missing", "value": table_name})
        for item in list(yaml_structural_inventory.get("columns") or []):
            if not isinstance(item, dict):
                continue
            logical_name = str(item.get("nombre_columna_logico") or item.get("campo_logico") or "").strip().lower()
            column_name = str(item.get("column_name") or "").strip().lower()
            if logical_name and logical_name not in dictionary_columns and column_name not in dictionary_physical_columns:
                issues.append(
                    {
                        "domain": normalized_domain,
                        "type": "dictionary_column_missing",
                        "value": logical_name or column_name,
                    }
                )
        for raw_filter in list(yaml_structural_inventory.get("supported_filters") or []):
            token = str(raw_filter or "").strip().lower()
            if token and token not in filterable_columns:
                issues.append({"domain": normalized_domain, "type": "dictionary_filter_metadata_missing", "value": token})
        for raw_group in list(yaml_structural_inventory.get("supported_group_by") or []):
            token = str(raw_group or "").strip().lower()
            if token and token not in groupable_columns:
                issues.append({"domain": normalized_domain, "type": "dictionary_group_by_metadata_missing", "value": token})
        for raw_metric in list(yaml_structural_inventory.get("supported_metrics") or []):
            token = str(raw_metric or "").strip().lower()
            if token and token not in metric_columns:
                issues.append({"domain": normalized_domain, "type": "dictionary_metric_metadata_missing", "value": token})
        for item in list(yaml_structural_inventory.get("relationships") or []):
            if not isinstance(item, dict):
                continue
            relation_name = str(item.get("nombre_relacion") or "").strip().lower()
            join_sql = " ".join(
                str(item.get("condicion") or item.get("condicion_join_sql") or item.get("join_sql") or "").strip().lower().split()
            )
            if join_sql and join_sql not in relation_sql and relation_name not in relation_names:
                issues.append(
                    {
                        "domain": normalized_domain,
                        "type": "dictionary_relation_missing",
                        "value": relation_name or join_sql,
                    }
                )
        deduped: dict[tuple[str, str, str], dict[str, str]] = {}
        for issue in issues:
            key = (
                str(issue.get("domain") or ""),
                str(issue.get("type") or ""),
                str(issue.get("value") or ""),
            )
            deduped[key] = issue
        return list(deduped.values())

    @staticmethod
    def _extract_tables(raw: dict[str, Any]) -> list[dict[str, Any]]:
        values = raw.get("tables") or raw.get("tablas_asociadas") or []
        if not isinstance(values, list):
            return []
        tables: list[dict[str, Any]] = []
        for item in values:
            if isinstance(item, dict):
                schema_name = str(item.get("schema_name") or "").strip()
                table_name = str(item.get("table_name") or "").strip()
                table_fqn = str(item.get("table_fqn") or "").strip()
                if not table_fqn and table_name:
                    table_fqn = f"{schema_name}.{table_name}" if schema_name else table_name
                tables.append(
                    {
                        "schema_name": schema_name,
                        "table_name": table_name,
                        "table_fqn": table_fqn,
                        "nombre_tabla_logico": str(item.get("nombre_tabla_logico") or item.get("alias_negocio") or "").strip(),
                        "rol": str(item.get("rol") or item.get("rol_tabla") or "").strip(),
                        "es_principal": bool(item.get("es_principal")),
                    }
                )
            elif isinstance(item, str):
                clean = str(item).strip()
                schema_name, table_name = SemanticBusinessResolver._split_table_name(clean)
                tables.append(
                    {
                        "schema_name": schema_name or "",
                        "table_name": table_name,
                        "table_fqn": clean,
                        "nombre_tabla_logico": "",
                        "rol": "",
                        "es_principal": False,
                    }
                )
        return tables

    @staticmethod
    def _extract_columns(raw: dict[str, Any]) -> list[dict[str, Any]]:
        values = raw.get("columns") or raw.get("columnas_clave") or []
        if not isinstance(values, list):
            return []
        supported_filters = {
            SemanticBusinessResolver._normalize_text(item)
            for item in list(raw.get("filtros_soportados") or [])
            if str(item or "").strip()
        }
        supported_group_by = {
            SemanticBusinessResolver._normalize_text(item)
            for item in list(raw.get("group_by_soportados") or [])
            if str(item or "").strip()
        }
        supported_metrics = {
            SemanticBusinessResolver._normalize_text(item)
            for item in list(raw.get("metricas_soportadas") or [])
            if str(item or "").strip()
        }
        columns: list[dict[str, Any]] = []
        for item in values:
            if not isinstance(item, dict):
                continue
            logical_name = str(item.get("nombre_columna_logico") or item.get("campo_logico") or "").strip()
            column_name = str(item.get("column_name") or "").strip()
            normalized_names = {
                SemanticBusinessResolver._normalize_text(logical_name),
                SemanticBusinessResolver._normalize_text(column_name),
            }
            columns.append(
                {
                    "table_name": str(item.get("table_name") or "").strip(),
                    "column_name": column_name,
                    "nombre_columna_logico": logical_name,
                    "descripcion": str(item.get("descripcion") or item.get("definicion_negocio") or "").strip(),
                    "es_filtro": bool(item.get("es_filtro")) or bool(normalized_names & supported_filters),
                    "es_group_by": bool(item.get("es_group_by")) or bool(normalized_names & supported_group_by),
                    "es_metrica": bool(item.get("es_metrica")) or bool(normalized_names & supported_metrics),
                    "es_clave": bool(item.get("es_clave")),
                }
            )
        return columns

    @staticmethod
    def _extract_relationships(raw: dict[str, Any]) -> list[dict[str, Any]]:
        values = raw.get("relationships") or raw.get("joins_conocidos") or []
        if not isinstance(values, list):
            return []
        relationships: list[dict[str, Any]] = []
        for item in values:
            if not isinstance(item, dict):
                continue
            relationships.append(
                {
                    "nombre_relacion": str(item.get("nombre_relacion") or "").strip(),
                    "condicion": str(item.get("condicion") or item.get("condicion_join_sql") or "").strip(),
                    "cardinalidad": str(item.get("cardinalidad") or "").strip(),
                }
            )
        return relationships

    @staticmethod
    def _collect_allowed_tables(*, tables: list[dict[str, Any]], dictionary_context: dict[str, Any]) -> list[str]:
        values: list[str] = []
        for item in tables:
            table_name = str(item.get("table_name") or "").strip().lower()
            table_fqn = str(item.get("table_fqn") or "").strip().lower()
            if table_name:
                values.append(table_name)
            if table_fqn:
                values.append(table_fqn)
        for row in list(dictionary_context.get("tables") or []):
            if not isinstance(row, dict):
                continue
            schema_name = str(row.get("schema_name") or "").strip().lower()
            table_name = str(row.get("table_name") or "").strip().lower()
            if table_name:
                values.append(table_name)
                values.append(f"{schema_name}.{table_name}" if schema_name else table_name)
        return sorted({item for item in values if item})

    @staticmethod
    def _collect_allowed_columns(*, columns: list[dict[str, Any]], dictionary_fields: list[dict[str, Any]]) -> list[str]:
        values: set[str] = set()
        for item in columns:
            col = str(item.get("column_name") or "").strip().lower()
            logical = str(item.get("nombre_columna_logico") or "").strip().lower()
            if col:
                values.add(col)
            if logical:
                values.add(logical)
        for row in dictionary_fields:
            if not isinstance(row, dict):
                continue
            col = str(row.get("column_name") or "").strip().lower()
            logical = str(row.get("campo_logico") or "").strip().lower()
            if col:
                values.add(col)
            if logical:
                values.add(logical)
        return sorted(values)

    @staticmethod
    def _collect_aliases(
        *,
        columns: list[dict[str, Any]],
        dictionary_fields: list[dict[str, Any]],
        dictionary_synonyms: list[dict[str, Any]],
    ) -> dict[str, str]:
        aliases: dict[str, str] = {}
        for item in columns:
            logical = str(item.get("nombre_columna_logico") or "").strip().lower()
            physical = str(item.get("column_name") or "").strip().lower()
            if logical and physical:
                aliases[logical] = physical
        for row in dictionary_fields:
            if not isinstance(row, dict):
                continue
            logical = str(row.get("campo_logico") or "").strip().lower()
            physical = str(row.get("column_name") or "").strip().lower()
            if logical and physical:
                aliases[logical] = physical
        for row in dictionary_synonyms:
            if not isinstance(row, dict):
                continue
            term = str(row.get("termino") or "").strip().lower()
            synonym = str(row.get("sinonimo") or "").strip().lower()
            if term and synonym and term in aliases and synonym not in aliases:
                aliases[synonym] = aliases[term]
        return aliases

    def _normalize_company_context(self, *, raw_company_context: Any) -> dict[str, Any]:
        raw = dict(raw_company_context or {}) if isinstance(raw_company_context, dict) else {}

        def as_list(value: Any) -> list[Any]:
            if isinstance(value, list):
                return value
            if isinstance(value, tuple):
                return list(value)
            if isinstance(value, dict):
                return [value]
            return []

        return {
            "codigo_compania": str(raw.get("codigo_compania") or "").strip().upper(),
            "nombre_compania": str(raw.get("nombre_compania") or "").strip(),
            "nombre_comercial": str(raw.get("nombre_comercial") or "").strip(),
            "aliases_compania": as_list(raw.get("aliases_compania")),
            "sector": str(raw.get("sector") or "").strip(),
            "descripcion_negocio": str(raw.get("descripcion_negocio") or "").strip(),
            "areas_activas": as_list(raw.get("areas_activas")),
            "procesos_clave": as_list(raw.get("procesos_clave")),
            "dominios_oficiales": as_list(raw.get("dominios_oficiales")),
            "lenguaje_interno": as_list(raw.get("lenguaje_interno")),
            "sistemas_fuente": as_list(raw.get("sistemas_fuente")),
            "politicas_globales": as_list(raw.get("politicas_globales")),
            "objetivo_orquestador": str(raw.get("objetivo_orquestador") or "").strip(),
            "agentes_oficiales": as_list(raw.get("agentes_oficiales")),
            "restricciones_operativas": as_list(raw.get("restricciones_operativas")),
            "indicadores_clave": as_list(raw.get("indicadores_clave")),
            "dominios_operativos": as_list(raw.get("dominios_operativos")),
            "estado": str(raw.get("estado") or "unknown").strip().lower(),
            "version": int(raw.get("version") or 0),
            "origen": str(raw.get("origen") or ""),
        }

    def _build_company_language_synonym_index(self, *, company_context: dict[str, Any]) -> dict[str, str]:
        index: dict[str, str] = {}
        for row in list(company_context.get("lenguaje_interno") or []):
            if not isinstance(row, dict):
                continue
            canonical = self._normalize_text(str(row.get("termino") or ""))
            if not canonical:
                continue
            index[canonical] = canonical
            for alias in list(row.get("equivalentes") or []):
                normalized_alias = self._normalize_text(str(alias or ""))
                if normalized_alias and normalized_alias not in index:
                    index[normalized_alias] = canonical
        for alias in list(company_context.get("aliases_compania") or []):
            normalized_alias = self._normalize_text(str(alias or ""))
            if normalized_alias:
                index[normalized_alias] = "compania"
        return index

    def _build_company_operational_scope(
        self,
        *,
        normalized_domain: str,
        company_context: dict[str, Any],
    ) -> dict[str, Any]:
        known_domains: set[str] = set()
        supported_domains: set[str] = set()

        for item in list(company_context.get("dominios_oficiales") or []):
            normalized = self.registry.normalize_domain_code(self._normalize_text(str(item or "")))
            if normalized:
                known_domains.add(normalized)
        for item in list(company_context.get("dominios_operativos") or []):
            normalized = self.registry.normalize_domain_code(self._normalize_text(str(item or "")))
            if normalized:
                supported_domains.add(normalized)
                known_domains.add(normalized)

        normalized_current = self.registry.normalize_domain_code(normalized_domain)
        domain_known = bool(normalized_current and (not known_domains or normalized_current in known_domains))
        domain_operational = bool(
            normalized_current
            and (
                not supported_domains
                or normalized_current in supported_domains
            )
        )
        return {
            "domain_code": normalized_current,
            "known_domains": sorted(known_domains),
            "supported_domains": sorted(supported_domains),
            "domain_known": domain_known,
            "domain_operational": domain_operational,
        }

    def _build_query_hints(
        self,
        *,
        normalized_domain: str,
        tables: list[dict[str, Any]],
        column_profiles: list[dict[str, Any]],
        relation_profiles: list[dict[str, Any]],
    ) -> dict[str, Any]:
        candidate_tables: list[dict[str, Any]] = []
        for item in list(tables or [])[:8]:
            if not isinstance(item, dict):
                continue
            table_name = str(item.get("table_name") or "").strip().lower()
            if not table_name:
                continue
            candidate_tables.append(
                {
                    "table_name": table_name,
                    "table_fqn": str(item.get("table_fqn") or "").strip().lower(),
                    "role": str(item.get("rol") or "").strip().lower(),
                    "is_primary": bool(item.get("es_principal")),
                }
            )

        candidate_columns: list[dict[str, Any]] = []
        for profile in list(column_profiles or []):
            if not isinstance(profile, dict):
                continue
            logical_name = str(profile.get("logical_name") or "").strip().lower()
            column_name = str(profile.get("column_name") or "").strip().lower()
            if not logical_name and not column_name:
                continue
            tags: list[str] = []
            if bool(profile.get("supports_filter")):
                tags.append("filter")
            if bool(profile.get("supports_group_by")) or bool(profile.get("supports_dimension")):
                tags.append("group_by")
            if bool(profile.get("supports_metric")):
                tags.append("metric")
            if bool(profile.get("is_identifier")):
                tags.append("identifier")
            if bool(profile.get("is_date")):
                tags.append("date")
            candidate_columns.append(
                {
                    "logical_name": logical_name or column_name,
                    "column_name": column_name or logical_name,
                    "table_name": str(profile.get("table_name") or "").strip().lower(),
                    "tags": tags,
                }
            )
        candidate_columns = candidate_columns[:14]

        candidate_group_dimensions = self._candidate_group_dimensions_from_context(
            domain_code=normalized_domain,
            semantic_context={
                "tables": tables,
                "column_profiles": column_profiles,
                "relation_profiles": relation_profiles,
            },
        )
        candidate_filter_columns = [
            str(profile.get("logical_name") or profile.get("column_name") or "").strip().lower()
            for profile in list(column_profiles or [])
            if isinstance(profile, dict) and bool(profile.get("supports_filter"))
        ]
        default_filters: dict[str, Any] = {}
        if normalized_domain in {"empleados", "rrhh"}:
            default_filters["estado"] = "ACTIVO"

        runtime_rules = ["si la consulta usa 'por <dimension>', interpretar group_by/aggregate"]
        if normalized_domain in {"empleados", "rrhh"}:
            runtime_rules.append("si no se especifica estado en empleados, usar estado=ACTIVO")
        if normalized_domain in {"ausentismo", "attendance"} and any(
            table.get("table_name") == "cinco_base_de_personal" for table in candidate_tables
        ):
            runtime_rules.append("para area/cargo/supervisor/carpeta usar join con cinco_base_de_personal")
        if normalized_domain in {"ausentismo", "attendance"}:
            runtime_rules.append("si aparecen vacaciones/incapacidad/licencia/permiso, usar filtro justificacion")

        join_paths = [
            {
                "relation_name": str(item.get("relation_name") or "").strip().lower(),
                "join_sql": str(item.get("join_sql") or "").strip(),
                "cardinality": str(item.get("cardinality") or "").strip().lower(),
            }
            for item in list(relation_profiles or [])[:6]
            if isinstance(item, dict)
        ]

        return {
            "candidate_tables": candidate_tables,
            "candidate_columns": candidate_columns,
            "candidate_group_dimensions": candidate_group_dimensions,
            "candidate_filter_columns": list(dict.fromkeys([item for item in candidate_filter_columns if item]))[:12],
            "default_filters": default_filters,
            "runtime_rules": runtime_rules,
            "join_paths": join_paths,
        }

    def _normalize_filters(
        self,
        *,
        message: str,
        domain_code: str,
        intent: StructuredQueryIntent,
        semantic_context: dict[str, Any],
    ) -> dict[str, Any]:
        synonym_index = dict(semantic_context.get("synonym_index") or {})
        filters = self.rule_resolver.apply_rule_overrides(
            message=message,
            domain_code=domain_code,
            filters=dict(intent.filters or {}),
            dictionary_rules=list((semantic_context.get("dictionary") or {}).get("rules") or []),
        )
        resolved, _ = self.column_resolver.resolve_filters(
            filters=filters,
            semantic_context=semantic_context,
            canonicalize_term=lambda term: self.synonym_resolver.canonicalize(
                term=term,
                synonym_index=synonym_index,
            ),
            normalize_status_value=self.rule_resolver.normalize_status_value,
        )
        return resolved

    def _infer_group_by_from_query(
        self,
        *,
        domain_code: str,
        message: str,
        intent: StructuredQueryIntent,
        semantic_context: dict[str, Any],
        canonicalize_term,
    ) -> list[str]:
        normalized_message = self._normalize_text(message)
        if (
            domain_code in {"empleados", "rrhh"}
            and QueryIntentResolver._has_missingness_filter(filters=dict(intent.filters or {}))
            and not re.search(r"\bpor\s+[a-z0-9_]+\b", normalized_message)
        ):
            return []
        entity_hint = self._normalize_text(getattr(intent, "entity_type", "") or "")
        candidate_dimensions = self._candidate_group_dimensions_from_context(
            domain_code=domain_code,
            semantic_context=semantic_context,
        )
        if not candidate_dimensions:
            return []

        semantic_variants = QueryIntentResolver._semantic_group_dimension_variants(
            semantic_context=semantic_context,
        )
        resolved: list[str] = []
        for canonical in candidate_dimensions:
            tokens = semantic_variants.get(canonical, (canonical, canonical.replace("_", " ")))
            canonical_terms = {
                canonical,
                self._normalize_text(canonicalize_term(canonical) or canonical),
            }
            if entity_hint and (entity_hint in canonical_terms or entity_hint in tokens):
                resolved.append(canonical)
                continue
            if any(f"por {token}" in normalized_message for token in tokens):
                if canonical == "birth_month" and not self._is_birthday_query(message=message, filters=dict(intent.filters or {})):
                    continue
                resolved.append(canonical)
                continue
            if any(re.search(rf"\b{re.escape(token)}\b", normalized_message) for token in tokens):
                if canonical == "birth_month" and not self._is_birthday_query(message=message, filters=dict(intent.filters or {})):
                    continue
                resolved.append(canonical)
        if any(item in {"estado", "estado_empleado"} for item in resolved):
            explicit_status_group = bool(re.search(r"\bpor\s+(estado|estatus)\b", normalized_message))
            if not explicit_status_group:
                resolved = [item for item in resolved if item not in {"estado", "estado_empleado"}]
        return list(dict.fromkeys(resolved))

    def _candidate_group_dimensions_from_context(
        self,
        *,
        domain_code: str,
        semantic_context: dict[str, Any],
    ) -> list[str]:
        dimensions: list[str] = []
        for profile in list(semantic_context.get("column_profiles") or []):
            if not isinstance(profile, dict):
                continue
            if not (bool(profile.get("supports_group_by")) or bool(profile.get("supports_dimension"))):
                continue
            logical_name = str(profile.get("logical_name") or profile.get("column_name") or "").strip().lower()
            if logical_name:
                dimensions.append(logical_name)

        normalized_domain = self.registry.normalize_domain_code(domain_code)
        has_personal_join = any(
            str(item.get("table_name") or "").strip().lower() == "cinco_base_de_personal"
            for item in list(semantic_context.get("tables") or [])
            if isinstance(item, dict)
        ) or any(
            "cinco_base_de_personal" in str(item.get("join_sql") or "").strip().lower()
            for item in list(semantic_context.get("relation_profiles") or [])
            if isinstance(item, dict)
        )

        default_dimensions: list[str] = []
        if normalized_domain in {"empleados", "rrhh"}:
            default_dimensions.extend(["supervisor", "area", "cargo", "carpeta", "tipo_labor", "movil", "sede", "centro_costo", "birth_month"])
        if normalized_domain in {"ausentismo", "attendance"}:
            default_dimensions.extend(["justificacion", "estado_justificacion"])
            if has_personal_join:
                default_dimensions.extend(["supervisor", "area", "cargo", "carpeta", "tipo_labor", "movil", "sede", "centro_costo"])

        return list(dict.fromkeys([item for item in [*dimensions, *default_dimensions] if item]))

    def _build_group_by_candidates(
        self,
        *,
        resolved_group_by: list[str],
        group_resolutions: list[Any],
        semantic_context: dict[str, Any],
    ) -> list[dict[str, Any]]:
        if not resolved_group_by:
            return []
        profile_index: dict[str, dict[str, Any]] = {}
        for profile in list(semantic_context.get("column_profiles") or []):
            if not isinstance(profile, dict):
                continue
            logical_name = str(profile.get("logical_name") or profile.get("column_name") or "").strip().lower()
            if logical_name:
                profile_index[logical_name] = profile

        requested_index = {
            str(item.canonical_term or "").strip().lower(): str(item.requested_term or "").strip()
            for item in list(group_resolutions or [])
            if getattr(item, "canonical_term", None)
        }
        results: list[dict[str, Any]] = []
        for logical_name in list(resolved_group_by or []):
            normalized = str(logical_name or "").strip().lower()
            if not normalized:
                continue
            if normalized == "birth_month":
                results.append(
                    {
                        "business_name": "birth_month",
                        "physical_column": "fnacimiento",
                        "table": "cinco_base_de_personal",
                        "semantic_role": "calendar_dimension",
                        "allowed_operation": "group_by",
                        "allowed_operations": ["group_by", "date_part"],
                        "requested_term": requested_index.get(normalized, "mes"),
                        "confidence": 0.95,
                    }
                )
                continue
            profile = dict(profile_index.get(normalized) or {})
            semantic_role = str(profile.get("semantic_role") or "").strip().lower() or self._semantic_role_for_profile(
                logical_name=normalized,
                column_name=str(profile.get("column_name") or normalized).strip().lower(),
            )
            allowed_operations = [
                str(item or "").strip().lower()
                for item in list(profile.get("allowed_operations") or [])
                if str(item or "").strip()
            ]
            if "group_by" not in allowed_operations:
                allowed_operations.append("group_by")
            results.append(
                {
                    "business_name": normalized,
                    "physical_column": str(profile.get("column_name") or normalized).strip().lower(),
                    "table": str(profile.get("table_name") or "").strip().lower(),
                    "semantic_role": semantic_role or "organizational_dimension",
                    "allowed_operation": "group_by",
                    "allowed_operations": list(dict.fromkeys(allowed_operations)),
                    "requested_term": requested_index.get(normalized, normalized),
                    "confidence": round(float(profile.get("confidence") or 0.95), 4),
                }
            )
        return results

    @staticmethod
    def _prune_employee_group_by_filters(
        *,
        resolved_group_by: list[str],
        normalized_filters: dict[str, Any],
    ) -> list[str]:
        group_values = [str(item or "").strip().lower() for item in list(resolved_group_by or []) if str(item or "").strip()]
        if len(group_values) <= 1:
            return group_values
        filter_keys = {
            str(key or "").strip().lower()
            for key, value in dict(normalized_filters or {}).items()
            if str(key or "").strip() and str(value or "").strip()
        }
        pruned = [item for item in group_values if item not in filter_keys]
        return pruned or group_values

    @staticmethod
    def _drop_group_dimension_filters(
        *,
        resolved_group_by: list[str],
        normalized_filters: dict[str, Any],
    ) -> None:
        for key in [str(item or "").strip().lower() for item in list(resolved_group_by or []) if str(item or "").strip()]:
            normalized_filters.pop(key, None)

    @staticmethod
    def _prune_missingness_literal_siblings(*, normalized_filters: dict[str, Any]) -> None:
        if not QueryIntentResolver._has_missingness_filter(filters=dict(normalized_filters or {})):
            return
        if isinstance(normalized_filters.get("documento_identidad"), dict):
            for key in ("documento_identidad_lado_a", "documento_identidad_lado_b"):
                if key in normalized_filters and not isinstance(normalized_filters.get(key), dict):
                    normalized_filters.pop(key, None)

    @classmethod
    def _normalize_period(cls, *, message: str, intent: StructuredQueryIntent) -> dict[str, Any]:
        period = dict(intent.period or {})
        if not period.get("start_date") or not period.get("end_date"):
            resolved = resolve_period_from_text(message)
            start = resolved.get("start")
            end = resolved.get("end")
            period = {
                "label": str(resolved.get("label") or ""),
                "start_date": start.isoformat() if hasattr(start, "isoformat") else None,
                "end_date": end.isoformat() if hasattr(end, "isoformat") else None,
            }
        if cls._is_turnover_query(message) and str(period.get("label") or "") == "hoy" and not cls._has_explicit_period(message):
            end = date.today()
            start = end - timedelta(days=29)
            period = {
                "label": "ultimo_mes_30_dias",
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
            }
        return {
            "label": str(period.get("label") or ""),
            "start_date": str(period.get("start_date") or ""),
            "end_date": str(period.get("end_date") or ""),
        }

    @staticmethod
    def _map_filter_columns(*, filters: dict[str, Any], semantic_context: dict[str, Any]) -> dict[str, str]:
        aliases = dict(semantic_context.get("aliases") or {})
        mapped: dict[str, str] = {}
        for key in filters.keys():
            clean = str(key or "").strip().lower()
            if not clean:
                continue
            mapped[clean] = str(aliases.get(clean, clean))
        return mapped

    def _resolve_temporal_scope(
        self,
        *,
        domain_code: str,
        message: str,
        normalized_filters: dict[str, Any],
        normalized_period: dict[str, Any],
    ) -> dict[str, Any]:
        normalized_domain = self.registry.normalize_domain_code(domain_code)
        if normalized_domain not in {"empleados", "rrhh"}:
            return {}
        if self._is_birthday_query(message=message, filters=normalized_filters):
            return {}
        if (
            str((normalized_period or {}).get("label") or "").strip().lower() == "hoy"
            and self._is_general_employee_population_request(
                message=message,
                filters=normalized_filters,
                group_by=[],
            )
            and self._extract_status_value(normalized_filters) == "ACTIVO"
        ):
            return {}
        if not self._has_explicit_period(message):
            return {}
        start_date = str((normalized_period or {}).get("start_date") or "").strip()
        end_date = str((normalized_period or {}).get("end_date") or "").strip()
        if not start_date or not end_date:
            return {
                "start_date": start_date,
                "end_date": end_date,
                "column_hint": "",
                "source": "empleados_temporal_binding_rule",
                "confidence": 0.0,
                "ambiguous": True,
                "reason": "period_not_resolved_for_temporal_binding",
            }
        status_value = self._extract_status_value(normalized_filters)
        if not status_value:
            return {
                "start_date": start_date,
                "end_date": end_date,
                "column_hint": "",
                "source": "empleados_temporal_binding_rule",
                "confidence": 0.0,
                "ambiguous": True,
                "reason": "status_missing_for_temporal_binding",
            }
        if status_value == "INACTIVO":
            column_hint = "fecha_egreso"
            confidence = 0.95
        else:
            column_hint = "fecha_ingreso"
            confidence = 0.74
        return {
            "start_date": start_date,
            "end_date": end_date,
            "column_hint": column_hint,
            "status_value": status_value,
            "source": "empleados_temporal_binding_rule",
            "confidence": float(confidence),
            "ambiguous": False,
            "reason": "",
        }

    @staticmethod
    def _build_warnings(
        *,
        domain_code: str,
        intent: StructuredQueryIntent,
        normalized_filters: dict[str, Any],
        normalized_period: dict[str, Any],
        temporal_scope: dict[str, Any],
        semantic_context: dict[str, Any],
    ) -> list[str]:
        warnings: list[str] = []
        company_scope = dict(semantic_context.get("company_operational_scope") or {})
        if not domain_code:
            warnings.append("domain_not_resolved")
        if (
            bool(company_scope.get("domain_known"))
            and not bool(company_scope.get("domain_operational", True))
        ):
            warnings.append("domain_known_but_not_operational")
        if intent.operation in {"count", "aggregate", "trend", "detail"} and not semantic_context.get("tables"):
            warnings.append("semantic_tables_not_available")
        birthday_month_resolved = bool(
            str((normalized_filters or {}).get("fnacimiento_month") or "").strip()
        )
        if (
            intent.operation in {"count", "detail", "aggregate", "trend"}
            and not normalized_period.get("start_date")
            and not birthday_month_resolved
        ):
            warnings.append("period_not_resolved")
        if "cedula" in normalized_filters and not str(normalized_filters.get("cedula") or "").isdigit():
            warnings.append("cedula_filter_not_normalized")
        if bool((temporal_scope or {}).get("ambiguous")):
            warnings.append("temporal_scope_ambiguous")
        return warnings

    @staticmethod
    def _split_table_name(value: str) -> tuple[str | None, str]:
        clean = str(value or "").strip()
        if "." not in clean:
            return None, clean
        schema, table = clean.split(".", 1)
        return schema, table

    @staticmethod
    def _normalize_text(value: str) -> str:
        lowered = str(value or "").strip().lower()
        normalized = unicodedata.normalize("NFKD", lowered)
        return "".join(ch for ch in normalized if not unicodedata.combining(ch))

    @classmethod
    def _is_birthday_query(cls, *, message: str, filters: dict[str, Any]) -> bool:
        if cls._resolve_birthday_filter(message=message, filters=filters):
            return True
        normalized = cls._normalize_text(message)
        return bool(re.search(r"\b(cumple\w*|nacimiento|edad)\b", normalized))

    @classmethod
    def _resolve_birthday_filter(cls, *, message: str, filters: dict[str, Any]) -> str:
        for key in ("fnacimiento_month", "birth_month", "month_of_birth", "mes_cumpleanos"):
            parsed = cls._parse_month_number((filters or {}).get(key))
            if parsed:
                return parsed
        normalized = cls._normalize_text(message)
        if not re.search(r"\b(cumple\w*|nacimiento|fnacimiento)\b", normalized):
            return ""
        return cls._parse_month_number(normalized)

    @staticmethod
    def _parse_month_number(value: Any) -> str:
        raw = str(value or "").strip().lower()
        if not raw:
            return ""
        if re.fullmatch(r"(?:0?[1-9]|1[0-2])", raw):
            return str(int(raw))
        months = {
            "enero": "1",
            "febrero": "2",
            "marzo": "3",
            "abril": "4",
            "mayo": "5",
            "junio": "6",
            "julio": "7",
            "agosto": "8",
            "septiembre": "9",
            "setiembre": "9",
            "octubre": "10",
            "noviembre": "11",
            "diciembre": "12",
        }
        for name, number in months.items():
            if re.search(rf"\b{re.escape(name)}\b", raw):
                return number
        if re.search(r"\b(este mes|mes actual)\b", raw):
            return str(date.today().month)
        return ""

    def _match_business_concept_field(
        self,
        *,
        message: str,
        domain_code: str,
        semantic_context: dict[str, Any],
        normalized_filters: dict[str, Any],
        resolved_group_by: list[str],
    ) -> dict[str, Any]:
        normalized_domain = str(domain_code or "").strip().lower()
        if normalized_domain not in {"empleados", "rrhh"}:
            return {}
        normalized_message = self._normalize_text(message)
        synonym_index = {
            self._normalize_text(key): self._normalize_text(value)
            for key, value in dict(semantic_context.get("synonym_index") or {}).items()
            if str(key or "").strip() and str(value or "").strip()
        }
        best: dict[str, Any] = {}
        best_score = 0.0
        for profile in list(semantic_context.get("column_profiles") or []):
            if not isinstance(profile, dict):
                continue
            logical_name = self._normalize_text(profile.get("logical_name") or profile.get("column_name"))
            column_name = self._normalize_text(profile.get("column_name"))
            if not logical_name:
                continue
            semantic_role = self._semantic_role_for_profile(
                logical_name=logical_name,
                column_name=column_name,
            )
            aliases = {logical_name, column_name, logical_name.replace("_", " "), column_name.replace("_", " ")}
            aliases.update(
                alias
                for alias, canonical in synonym_index.items()
                if canonical in {logical_name, column_name}
            )
            score = 0.0
            matched_aliases: list[str] = []
            for alias in aliases:
                clean_alias = self._normalize_text(alias)
                if not clean_alias:
                    continue
                if re.search(rf"\b{re.escape(clean_alias)}\b", normalized_message):
                    score += 0.55 + min(len(clean_alias) / 100.0, 0.15)
                    matched_aliases.append(clean_alias)
            if logical_name == "fecha_nacimiento" and str(normalized_filters.get("fnacimiento_month") or "").strip():
                score += 0.65
            if "birth_month" in list(resolved_group_by or []) and logical_name == "fecha_nacimiento":
                score += 0.5
            if semantic_role in {"person_birth_date", "employment_start_date", "employment_end_date"}:
                score += 0.08
            if score <= best_score:
                continue
            best_score = score
            canonical_logical_name = logical_name
            if semantic_role == "person_birth_date":
                canonical_logical_name = "fecha_nacimiento"
            elif semantic_role == "employment_start_date":
                canonical_logical_name = "fecha_ingreso"
            elif semantic_role == "employment_end_date":
                canonical_logical_name = "fecha_egreso"
            best = {
                "matched": True,
                "logical_name": canonical_logical_name,
                "column_name": column_name,
                "table_name": self._normalize_text(profile.get("table_name")),
                "semantic_role": semantic_role,
                "business_concepts": self._business_concepts_for_role(semantic_role),
                "matched_aliases": sorted(dict.fromkeys(matched_aliases)),
                "confidence": round(min(score, 0.98), 4),
                "allowed_operations": self._allowed_operations_for_role(semantic_role),
                "date_granularities": ["month", "day", "year"] if bool(profile.get("is_date")) else [],
            }
        return best

    @staticmethod
    def _semantic_role_for_profile(*, logical_name: str, column_name: str) -> str:
        key = str(logical_name or column_name or "").strip().lower()
        if key in {"fecha_nacimiento", "fnacimiento"}:
            return "person_birth_date"
        if key in {"fecha_ingreso", "fingreso"}:
            return "employment_start_date"
        if key in {"fecha_egreso", "fecha_retiro", "fretiro"}:
            return "employment_end_date"
        if key in {
            "certificado_alturas_fecha_emision",
            "certificado_alturas_fecha_vencimiento",
            "certificado_alturas_estado_vigencia",
        }:
            return "heights_certificate_validity"
        return ""

    @staticmethod
    def _business_concepts_for_role(role: str) -> list[str]:
        mapping = {
            "person_birth_date": ["birthday", "age"],
            "employment_start_date": ["tenure"],
            "employment_end_date": ["turnover"],
            "heights_certificate_validity": ["certificate", "expiration", "compliance"],
        }
        return list(mapping.get(str(role or ""), []))

    @staticmethod
    def _allowed_operations_for_role(role: str) -> list[str]:
        mapping = {
            "person_birth_date": ["list", "count", "group_by_month", "filter_by_month"],
            "employment_start_date": ["list", "count", "group_by_month", "filter_by_month"],
            "employment_end_date": ["list", "count", "group_by_month", "filter_by_month"],
            "heights_certificate_validity": ["count", "detail", "filter", "derive_expiration"],
        }
        return list(mapping.get(str(role or ""), []))

    @classmethod
    def _resolve_attendance_reason_from_message(cls, *, message: str) -> str:
        normalized = cls._normalize_text(message)
        if re.search(r"\bpermiso\s+de\s+trabajo\b", normalized):
            return ""
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

    @classmethod
    def _should_rescue_to_attendance(
        cls,
        *,
        message: str,
        domain_code: str,
        intent: StructuredQueryIntent,
        attendance_reason: str,
    ) -> bool:
        if not attendance_reason:
            return False
        normalized_domain = str(domain_code or "").strip().lower()
        if normalized_domain in {"ausentismo", "attendance"}:
            return False
        if normalized_domain not in {"", "general", "empleados", "rrhh"}:
            return False
        normalized_message = cls._normalize_text(message)
        has_people_scope = bool(
            re.search(r"\b(emplead\w*|colaborador(?:es)?|personal|persona(?:s)?)\b", normalized_message)
        )
        if has_people_scope:
            return True
        for status_key in ("estado", "estado_empleado"):
            raw_value = str((intent.filters or {}).get(status_key) or "").strip().upper()
            if raw_value == attendance_reason:
                return True
        return False

    @staticmethod
    def _normalize_identifier(value: str | None) -> str:
        return "".join(ch for ch in str(value or "") if ch.isdigit())

    @staticmethod
    def _extract_identifier_from_message(message: str) -> str:
        match = re.search(r"\b\d{6,13}\b", str(message or ""))
        if not match:
            return ""
        return "".join(ch for ch in match.group(0) if ch.isdigit())

    @staticmethod
    def _extract_after_keyword(message: str, keyword: str) -> str:
        match = re.search(rf"\b{re.escape(keyword)}\s+([a-z0-9 ._-]{{2,80}})", message)
        if not match:
            return ""
        value = str(match.group(1) or "").strip(" .,-")
        for token in (" y ", " de ", " con ", " para ", " en "):
            if token in value:
                value = value.split(token, 1)[0].strip()
        return value

    @staticmethod
    def parse_iso_date(value: str | None) -> date | None:
        raw = str(value or "").strip()
        if not raw:
            return None
        try:
            return date.fromisoformat(raw)
        except Exception:
            return None

    @staticmethod
    def _extract_status_value(filters: dict[str, Any]) -> str:
        for key in ("estado", "estado_empleado"):
            value = str((filters or {}).get(key) or "").strip().upper()
            if value in {"ACTIVO", "INACTIVO"}:
                return value
        return ""

    def _apply_default_employee_status(
        self,
        *,
        semantic_context: dict[str, Any],
        normalized_filters: dict[str, Any],
    ) -> None:
        if self._extract_status_value(normalized_filters):
            return
        status_profile = self._find_status_profile(semantic_context=semantic_context)
        status_key = str(status_profile.get("logical_name") or status_profile.get("column_name") or "estado").strip().lower()
        if status_key:
            normalized_filters.setdefault(status_key, "ACTIVO")
        normalized_filters.setdefault("estado", "ACTIVO")

    @classmethod
    def _resolve_status_from_message(cls, *, message: str) -> str:
        normalized = cls._normalize_text(message)
        inactive_tokens = (
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
            "desvinculacion",
            "desvinculaciones",
            "desvinculado",
            "desvinculados",
            "baja",
            "bajas",
            "rotacion",
            "rotaciones",
        )
        if any(token in normalized for token in inactive_tokens):
            return "INACTIVO"
        active_tokens = (
            "activo",
            "activos",
            "vigente",
            "vigentes",
            "vinculado",
            "vinculados",
        )
        if any(token in normalized for token in active_tokens):
            return "ACTIVO"
        return ""

    @classmethod
    def _is_general_employee_population_request(
        cls,
        *,
        message: str,
        filters: dict[str, Any],
        group_by: list[str],
    ) -> bool:
        normalized = cls._normalize_text(message)
        if not re.search(r"\b(emplead\w*|colaborador(?:es)?|personal|persona(?:s)?)\b", normalized):
            return False
        if cls._extract_status_value(filters) not in {"ACTIVO", "INACTIVO"}:
            return False
        if any(
            str((filters or {}).get(key) or "").strip()
            for key in (
                "cedula",
                "cedula_empleado",
                "identificacion",
                "documento",
                "id_empleado",
                "movil",
                "codigo_sap",
                "nombre",
                "search",
            )
        ):
            return False
        if cls._is_birthday_query(message=message, filters=filters):
            return False
        if any(token in normalized for token in ("detalle", "informacion", "info", "ficha", "datos")):
            return False
        return bool(group_by) or bool(cls._resolve_status_from_message(message=message))

    @staticmethod
    def _apply_executable_filter_aliases(*, normalized_filters: dict[str, Any]) -> None:
        alias_pairs = (
            ("cedula_empleado", "cedula"),
            ("identificacion", "cedula"),
            ("documento", "cedula"),
            ("id_empleado", "cedula"),
            ("movil_empleado", "movil"),
            ("codigo_sap_empleado", "codigo_sap"),
            ("birth_month", "fnacimiento_month"),
            ("month_of_birth", "fnacimiento_month"),
            ("mes_cumpleanos", "fnacimiento_month"),
        )
        for source, target in alias_pairs:
            raw_value = normalized_filters.get(source)
            has_source = (
                isinstance(raw_value, dict)
                or bool(str(raw_value or "").strip())
            )
            target_value = normalized_filters.get(target)
            has_target = (
                isinstance(target_value, dict)
                or bool(str(target_value or "").strip())
            )
            if has_source and not has_target:
                normalized_filters[target] = raw_value
            if has_source and target in normalized_filters:
                normalized_filters.pop(source, None)

    @classmethod
    def _has_explicit_period(cls, message: str) -> bool:
        normalized = cls._normalize_text(message)
        if re.search(r"\d{4}-\d{2}-\d{2}", normalized):
            return True
        if re.search(r"\b(lunes|martes|miercoles|jueves|viernes|sabado|domingo)\b", normalized):
            return True
        return any(
            token in normalized
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
                "ano",
                "rango",
            )
        )

    @classmethod
    def _is_turnover_query(cls, message: str) -> bool:
        normalized = cls._normalize_text(message)
        return bool(re.search(r"\b(rotacion|rotaciones|turnover)\b", normalized))

    def _resolve_status_from_dictionary(
        self,
        *,
        message: str,
        semantic_context: dict[str, Any],
        normalized_filters: dict[str, Any],
        canonicalize_term,
    ) -> dict[str, Any]:
        if self._extract_status_value(normalized_filters):
            return {}
        status_profile = self._find_status_profile(semantic_context=semantic_context)
        if not status_profile:
            return {}

        status_key = str(status_profile.get("logical_name") or status_profile.get("column_name") or "estado").strip().lower()
        allowed_values = list(status_profile.get("allowed_values") or [])
        if not allowed_values:
            return {}
        allowed_set = {str(item or "").strip().upper() for item in allowed_values if str(item or "").strip()}
        if not allowed_set:
            return {}

        synonym_index = dict(semantic_context.get("synonym_index") or {})
        canonical_tokens = self.synonym_resolver.canonicalize_tokens_from_message(
            message=message,
            synonym_index=synonym_index,
        )
        raw_tokens = re.findall(r"[a-z0-9_]{2,}", self._normalize_text(message))
        tokens = list(dict.fromkeys([*canonical_tokens, *raw_tokens]))
        for token in tokens:
            mapped = str(canonicalize_term(token) or token).strip()
            normalized_value = self.rule_resolver.normalize_status_value(
                raw_value=mapped,
                allowed_values=allowed_values,
            )
            if normalized_value in allowed_set:
                return {
                    "status_key": status_key,
                    "status_value": normalized_value,
                    "matched_token": token,
                    "allowed_values": sorted(allowed_set),
                }
        return {}

    def _resolve_allowed_value_filters_from_dictionary(
        self,
        *,
        message: str,
        semantic_context: dict[str, Any],
        normalized_filters: dict[str, Any],
    ) -> dict[str, str]:
        resolved: dict[str, str] = {}
        normalized_message = self._normalize_text(message)
        if not normalized_message:
            return resolved
        dimension_variants = QueryIntentResolver._semantic_group_dimension_variants(
            semantic_context=semantic_context,
        )
        protected_dimension_tokens = {
            token
            for tokens in dimension_variants.values()
            for token in tokens
            if token and re.search(rf"\b{re.escape(token)}\b", normalized_message)
        }
        synonym_index = {
            self._normalize_text(key): self._normalize_text(value)
            for key, value in dict(semantic_context.get("synonym_index") or {}).items()
            if str(key or "").strip() and str(value or "").strip()
        }
        known_logical_names = {
            self._normalize_text(item.get("logical_name") or item.get("column_name"))
            for item in list(semantic_context.get("column_profiles") or [])
            if isinstance(item, dict) and str(item.get("logical_name") or item.get("column_name") or "").strip()
        }

        for profile in list(semantic_context.get("column_profiles") or []):
            if not isinstance(profile, dict):
                continue
            logical_name = str(profile.get("logical_name") or profile.get("column_name") or "").strip().lower()
            column_name = str(profile.get("column_name") or "").strip().lower()
            if not logical_name or logical_name in {"estado", "estado_empleado"}:
                continue
            if str((normalized_filters or {}).get(logical_name) or "").strip():
                continue
            if not bool(profile.get("supports_filter")):
                continue
            allowed_values = [
                str(item or "").strip().upper()
                for item in list(profile.get("allowed_values") or [])
                if str(item or "").strip()
            ]
            if not allowed_values:
                continue
            logical_markers = {
                self._normalize_text(logical_name),
                self._normalize_text(column_name),
                self._normalize_text(logical_name.replace("_", " ")),
                self._normalize_text(column_name.replace("_", " ")) if column_name else "",
            }
            column_explicitly_named = any(
                marker and re.search(rf"\b{re.escape(marker)}\b", normalized_message)
                for marker in logical_markers
            )
            for candidate in allowed_values:
                normalized_candidate = self._normalize_text(candidate)
                if not normalized_candidate:
                    continue
                if normalized_candidate in {"si", "no"} and not column_explicitly_named:
                    continue
                candidate_aliases = {
                    normalized_candidate,
                    *{
                        alias
                        for alias, canonical in synonym_index.items()
                        if canonical == normalized_candidate
                        and normalized_candidate not in known_logical_names
                    },
                }
                matched_aliases = [
                    alias
                    for alias in candidate_aliases
                    if alias and re.search(rf"\b{re.escape(alias)}\b", normalized_message)
                ]
                if not matched_aliases:
                    continue
                if all(alias in protected_dimension_tokens for alias in matched_aliases):
                    continue
                resolved[logical_name] = candidate
                break
        return resolved

    def _find_status_profile(self, *, semantic_context: dict[str, Any]) -> dict[str, Any]:
        profiles = list(semantic_context.get("column_profiles") or [])
        for profile in profiles:
            if not isinstance(profile, dict):
                continue
            logical_name = str(profile.get("logical_name") or "").strip().lower()
            column_name = str(profile.get("column_name") or "").strip().lower()
            allowed_values = [str(item or "").strip().upper() for item in list(profile.get("allowed_values") or []) if str(item or "").strip()]
            supports_filter = bool(profile.get("supports_filter"))
            if not supports_filter or not allowed_values:
                continue
            if logical_name in {"estado", "estado_empleado"} or column_name == "estado":
                return {
                    **profile,
                    "allowed_values": allowed_values,
                    "logical_name": logical_name or column_name or "estado",
                }
        return {}

    def _maybe_seed_rrhh_status_synonyms(self) -> dict[str, Any]:
        enabled = str(
            os.getenv("IA_DEV_QUERY_INTELLIGENCE_RRHH_SYNONYM_SEED_ENABLED", "0") or "0"
        ).strip().lower() in {"1", "true", "yes", "on"}
        if not enabled:
            return {
                "enabled": False,
                "status": "skipped",
                "inserted": 0,
                "skipped": 0,
                "errors": [],
            }
        result = self.dictionary_tool.ensure_rrhh_status_synonyms_seed()
        payload = dict(result or {})
        payload["enabled"] = True
        payload.setdefault("status", "skipped")
        payload.setdefault("inserted", 0)
        payload.setdefault("skipped", 0)
        payload.setdefault("errors", [])
        return payload
