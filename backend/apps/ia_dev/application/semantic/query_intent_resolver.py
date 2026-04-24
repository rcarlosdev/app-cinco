from __future__ import annotations

import json
import os
import re
import unicodedata
from datetime import date
from typing import Any

from apps.ia_dev.application.contracts.query_intelligence_contracts import StructuredQueryIntent
from apps.ia_dev.application.taxonomia_dominios import (
    normalizar_codigo_dominio,
    normalizar_dominio_operativo,
)
from apps.ia_dev.services.employee_identifier_service import EmployeeIdentifierService
from apps.ia_dev.services.period_service import resolve_period_from_text


class QueryIntentResolver:
    """
    Traduce lenguaje natural a intencion estructurada.
    Prioriza reglas; opcionalmente refina con OpenAI usando contexto semantico.
    """

    _EMPLOYEE_INACTIVE_SIGNAL_RE = re.compile(
        r"\b("
        r"inactivo|inactivos|"
        r"egreso|egresos|egresado|egresados|"
        r"retiro|retiros|retirado|retirados|"
        r"desvinculacion|desvinculaciones|desvinculado|desvinculados|"
        r"baja|bajas|rotacion|rotaciones"
        r")\b"
    )
    _EMPLOYEE_ACTIVE_SIGNAL_RE = re.compile(
        r"\b(activo|activa|activos|activas|vigente|vigentes|habilitado|habilitados|vinculado|vinculados)\b"
    )
    _TEMPORAL_REFERENCE_RE = re.compile(
        r"\b(hoy|ayer|esta\s+semana|semana\s+actual|semana\s+pasad[ao]|semana\s+anterior|"
        r"ultima\s+semana|ultim[oa]s?\s+\d+\s+(?:dias|semanas|meses)|rolling(?:\s+de)?\s+\d+\s+"
        r"(?:dias|semanas|meses)|este\s+mes|mes\s+actual|mes\s+pasado|mes\s+anterior|"
        r"este\s+ano|ano\s+actual|ano\s+pasado|\d{4}-\d{2}-\d{2})\b"
    )

    def __init__(self):
        self.model = str(os.getenv("IA_DEV_QUERY_INTENT_MODEL", os.getenv("IA_DEV_MODEL", "gpt-5-nano")) or "gpt-5-nano")

    @staticmethod
    def _get_openai_api_key() -> str:
        return str(os.getenv("OPENAI_API_KEY") or os.getenv("IA_DEV_OPENAI_API_KEY") or "").strip()

    @staticmethod
    def _openai_enabled() -> bool:
        return str(os.getenv("IA_DEV_QUERY_INTELLIGENCE_OPENAI_ENABLED", "1") or "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

    def resolve(
        self,
        *,
        message: str,
        base_classification: dict[str, Any],
        semantic_context: dict[str, Any] | None = None,
        memory_hints: dict[str, Any] | None = None,
    ) -> StructuredQueryIntent:
        rules = self._resolve_rules(
            message=message,
            base_classification=base_classification,
            semantic_context=semantic_context or {},
        )
        pattern_guided = self._apply_query_pattern_hints(
            message=message,
            fallback=rules,
            memory_hints=memory_hints or {},
        )
        if self._query_pattern_fastpath_enabled() and str(pattern_guided.source or "").strip().lower() == "memory_pattern":
            return pattern_guided
        if not self._openai_enabled():
            return pattern_guided

        api_key = self._get_openai_api_key()
        if not api_key:
            return pattern_guided

        try:
            llm = self._resolve_openai(
                message=message,
                api_key=api_key,
                fallback=pattern_guided,
                semantic_context=semantic_context or {},
                memory_hints=memory_hints or {},
            )
            return self._merge_intents(fallback=pattern_guided, llm=llm)
        except Exception:
            return pattern_guided

    def match_query_pattern(
        self,
        *,
        message: str,
        base_classification: dict[str, Any],
        semantic_context: dict[str, Any] | None = None,
        memory_hints: dict[str, Any] | None = None,
    ) -> StructuredQueryIntent | None:
        rules = self._resolve_rules(
            message=message,
            base_classification=base_classification,
            semantic_context=semantic_context or {},
        )
        matched = self._apply_query_pattern_hints(
            message=message,
            fallback=rules,
            memory_hints=memory_hints or {},
        )
        if str(matched.source or "").strip().lower() == "memory_pattern":
            return matched
        return None

    def _resolve_rules(
        self,
        *,
        message: str,
        base_classification: dict[str, Any],
        semantic_context: dict[str, Any] | None = None,
    ) -> StructuredQueryIntent:
        normalized = self._normalize_text(message)
        domain = self._resolve_domain(
            normalized=normalized,
            base_domain=str(base_classification.get("domain") or "").strip().lower(),
            semantic_context=semantic_context or {},
        )

        operation = "summary"
        has_grouping_signal = self._has_explicit_grouping_phrase(normalized) or self._has_aggregate_signal(normalized)
        if any(token in normalized for token in ("cantidad", "cuantos", "cuantas", "total", "numero")):
            operation = "count"
        elif self._has_employee_status_metric_signal(normalized) and not has_grouping_signal:
            operation = "count"
        elif any(token in normalized for token in ("compar", "vs", "versus")):
            operation = "compare"
        elif self._has_explicit_grouping_phrase(normalized):
            operation = "aggregate"
        elif self._has_aggregate_signal(normalized):
            operation = "aggregate"
        elif any(token in normalized for token in ("tendencia", "historico", "evolucion", "trend")):
            operation = "trend"
        elif domain in {"empleados", "rrhh"} and self._has_identifier_signal(normalized):
            operation = "detail"
        elif self._looks_like_attendance_person_detail(normalized=normalized, domain=domain):
            operation = "detail"
        elif any(token in normalized for token in ("detalle", "tabla", "mostrar", "lista", "informacion", "info", "ficha", "datos")):
            operation = "detail"

        template_id = self._resolve_template_id(
            normalized=normalized,
            domain_code=domain,
            operation=operation,
        )
        entity_type, entity_value = self._extract_entity(message=message, normalized=normalized)
        filters = self._extract_filters(normalized=normalized)
        if entity_type == "cedula" and entity_value:
            filters.setdefault("cedula", entity_value)
        elif entity_type == "movil" and entity_value:
            filters.setdefault("movil", entity_value)

        period = self._resolve_period_payload(message=message)
        if self._is_turnover_query(normalized) and str(period.get("label") or "") == "hoy" and not self._has_temporal_reference(normalized):
            from datetime import timedelta

            end = date.today()
            start = end - timedelta(days=29)
            period = {
                "label": "ultimo_mes_30_dias",
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
            }
        group_by = self._extract_group_by(normalized=normalized)
        metrics = self._extract_metrics(normalized=normalized, operation=operation)

        return StructuredQueryIntent(
            raw_query=message,
            domain_code=domain,
            operation=operation,
            template_id=template_id,
            entity_type=entity_type,
            entity_value=entity_value,
            filters=filters,
            period=period,
            group_by=group_by,
            metrics=metrics,
            confidence=0.72,
            source="rules",
            warnings=[],
        )

    def _resolve_openai(
        self,
        *,
        message: str,
        api_key: str,
        fallback: StructuredQueryIntent,
        semantic_context: dict[str, Any],
        memory_hints: dict[str, Any],
    ) -> StructuredQueryIntent:
        from openai import OpenAI

        context_payload = self._compact_semantic_context(semantic_context=semantic_context)
        memory_patterns = self._compact_query_patterns(memory_hints=memory_hints)
        client = OpenAI(api_key=api_key)
        response = client.responses.create(
            model=self.model,
            input=[
                {
                    "role": "system",
                    "content": (
                        "Eres un resolver de intencion estructurada para analytics empresarial.\n"
                        "Devuelve SOLO JSON con llaves: domain_code, operation, template_id, entity_type, entity_value, "
                        "filters, period, group_by, metrics, confidence.\n"
                        "template_id permitido: count_entities_by_status, count_records_by_period, "
                        "detail_by_entity_and_period, aggregate_by_group_and_period, trend_by_period.\n"
                        "operation permitido: count, detail, aggregate, trend, compare, summary.\n"
                        "Usa SIEMPRE ambas capas del contexto semantico: YAML de negocio y metadata estructurada de DB.\n"
                        "Prioriza reglas_negocio, contexto_agente y ejemplos_consulta para interpretar el negocio.\n"
                        "Usa tables, columns, relationships, synonyms y query_hints para validar tablas, columnas y joins candidatos.\n"
                        "No generes SQL, no agregues texto fuera del JSON."
                    ),
                },
                {
                    "role": "system",
                    "content": (
                        "Contexto semantico disponible (usar solo esta estructura para interpretar negocio):\n"
                        f"{json.dumps(context_payload, ensure_ascii=False)}"
                    ),
                },
                {
                    "role": "system",
                    "content": (
                        "Patrones de consultas satisfactorias previamente aprobados/reusables:\n"
                        f"{json.dumps(memory_patterns, ensure_ascii=False)}"
                    ),
                },
                {"role": "user", "content": message},
            ],
        )
        raw_text = str(getattr(response, "output_text", "") or "").strip()
        payload = self._safe_json(raw_text)
        return StructuredQueryIntent(
            raw_query=message,
            domain_code=str(payload.get("domain_code") or fallback.domain_code or "").strip().lower(),
            operation=str(payload.get("operation") or fallback.operation or "summary").strip().lower(),
            template_id=str(payload.get("template_id") or fallback.template_id or "").strip().lower(),
            entity_type=str(payload.get("entity_type") or fallback.entity_type or "").strip().lower(),
            entity_value=str(payload.get("entity_value") or fallback.entity_value or "").strip(),
            filters=payload.get("filters") if isinstance(payload.get("filters"), dict) else dict(fallback.filters or {}),
            period=payload.get("period") if isinstance(payload.get("period"), dict) else dict(fallback.period or {}),
            group_by=payload.get("group_by") if isinstance(payload.get("group_by"), list) else list(fallback.group_by or []),
            metrics=payload.get("metrics") if isinstance(payload.get("metrics"), list) else list(fallback.metrics or []),
            confidence=float(payload.get("confidence") or fallback.confidence or 0.0),
            source="openai",
            warnings=[],
        )

    @staticmethod
    def _merge_intents(*, fallback: StructuredQueryIntent, llm: StructuredQueryIntent) -> StructuredQueryIntent:
        llm_filters = dict(llm.filters or {})
        fallback_filters = dict(fallback.filters or {})
        merged_filters = dict(fallback_filters)
        for key, value in llm_filters.items():
            if value in (None, ""):
                continue
            merged_filters[str(key)] = value
        merged_filters = EmployeeIdentifierService.prune_redundant_search_filter(merged_filters)
        llm_period = dict(llm.period or {})
        fallback_period = dict(fallback.period or {})
        llm_group_by = [str(item).strip().lower() for item in list(llm.group_by or []) if str(item).strip()]
        fallback_group_by = [str(item).strip().lower() for item in list(fallback.group_by or []) if str(item).strip()]
        merged_group_by = list(dict.fromkeys([*llm_group_by, *fallback_group_by]))
        llm_domain = normalizar_codigo_dominio(llm.domain_code)
        fallback_domain = normalizar_codigo_dominio(fallback.domain_code)
        normalized_raw_query = QueryIntentResolver._normalize_text(fallback.raw_query)

        operation = str(llm.operation or fallback.operation or "summary").strip().lower()
        template_id = str(llm.template_id or fallback.template_id or "").strip().lower()
        has_entity = bool(str(llm.entity_value or fallback.entity_value or "").strip()) or bool(
            str(merged_filters.get("cedula") or "").strip()
            or str(merged_filters.get("movil") or "").strip()
        )
        resolved_domain = llm_domain or fallback_domain
        if llm_domain in {"", "general"} and fallback_domain not in {"", "general"} and has_entity:
            resolved_domain = fallback_domain
        if operation == "detail" and not has_entity and str(fallback.operation or "").strip().lower() != "detail":
            operation = str(fallback.operation or "summary").strip().lower()
        if template_id == "detail_by_entity_and_period" and not has_entity and str(fallback.template_id or "").strip():
            template_id = str(fallback.template_id or "").strip().lower()
        if (
            fallback_domain == "ausentismo"
            and str(fallback.operation or "").strip().lower() == "detail"
            and QueryIntentResolver._looks_like_attendance_person_detail(
                normalized=normalized_raw_query,
                domain=fallback_domain,
            )
            and not merged_group_by
        ):
            operation = "detail"
            template_id = "detail_by_entity_and_period"
            resolved_domain = fallback_domain

        llm_start = str(llm_period.get("start_date") or "").strip()
        llm_end = str(llm_period.get("end_date") or "").strip()
        fallback_start = str(fallback_period.get("start_date") or "").strip()
        fallback_end = str(fallback_period.get("end_date") or "").strip()
        llm_label = str(llm_period.get("label") or "").strip().lower()
        fallback_label = str(fallback_period.get("label") or "").strip().lower()
        if (
            fallback_start
            and fallback_end
            and fallback_label not in {"", "hoy"}
            and (
                not llm_start
                or not llm_end
                or (llm_label == "hoy" and llm_start == llm_end)
            )
        ):
            llm_period = fallback_period

        merged_metrics = list(dict.fromkeys([*list(llm.metrics or []), *list(fallback.metrics or [])]))
        if QueryIntentResolver._is_turnover_query(normalized_raw_query):
            operation = "aggregate" if merged_group_by else "count"
            template_id = "aggregate_by_group_and_period" if merged_group_by else "count_entities_by_status"
            resolved_domain = "empleados"
            merged_filters["estado"] = "INACTIVO"
            merged_filters["estado_empleado"] = "INACTIVO"
            if "turnover_rate" not in merged_metrics:
                merged_metrics.insert(0, "turnover_rate")

        return StructuredQueryIntent(
            raw_query=fallback.raw_query,
            domain_code=resolved_domain,
            operation=operation,
            template_id=template_id,
            entity_type=str(llm.entity_type or fallback.entity_type or "").strip().lower(),
            entity_value=str(llm.entity_value or fallback.entity_value or "").strip(),
            filters=merged_filters or fallback_filters,
            period=llm_period or fallback_period,
            group_by=merged_group_by,
            metrics=merged_metrics,
            confidence=float(llm.confidence or fallback.confidence or 0.0),
            source=str(llm.source or "openai"),
            warnings=list(llm.warnings or []),
        )

    @staticmethod
    def _resolve_template_id(*, normalized: str, domain_code: str, operation: str) -> str:
        if (
            domain_code in {"empleados", "rrhh"}
            and operation == "count"
            and (
                "activo" in normalized
                or QueryIntentResolver._has_employee_inactive_signal(normalized)
                or QueryIntentResolver._has_employee_active_signal(normalized)
            )
        ):
            return "count_entities_by_status"
        if normalizar_codigo_dominio(domain_code) == "ausentismo" and operation == "detail":
            return "detail_by_entity_and_period"
        if operation == "trend":
            return "trend_by_period"
        if operation == "detail" and QueryIntentResolver._has_identifier_signal(normalized):
            return "detail_by_entity_and_period"
        if QueryIntentResolver._has_group_dimension_signal(normalized):
            return "aggregate_by_group_and_period"
        if operation in {"aggregate", "compare", "summary"} and QueryIntentResolver._has_group_dimension_signal(normalized):
            return "aggregate_by_group_and_period"
        if operation == "count":
            return "count_records_by_period"
        if operation == "detail":
            return "detail_by_entity_and_period"
        return "aggregate_by_group_and_period"

    @staticmethod
    def _extract_entity(*, message: str, normalized: str) -> tuple[str, str]:
        match = re.search(r"\b\d{6,13}\b", normalized)
        if match:
            return "cedula", "".join(ch for ch in match.group(0) if ch.isdigit())
        movil = EmployeeIdentifierService.extract_movil_identifier(message or normalized)
        if movil:
            return "movil", movil
        return "", ""

    @staticmethod
    def _extract_filters(*, normalized: str) -> dict[str, Any]:
        filters: dict[str, Any] = {}
        estado_match = re.search(
            r"\bestado(?:\s+del?\s+\w+)?\s+(?:es\s+)?([a-z_]+)\b",
            str(normalized or ""),
        )
        if estado_match:
            filters["estado"] = str(estado_match.group(1) or "").strip().upper()
        elif QueryIntentResolver._has_employee_inactive_signal(normalized):
            filters["estado"] = "INACTIVO"
        attendance_reason = QueryIntentResolver._extract_attendance_reason_filter(normalized=normalized)
        if attendance_reason:
            filters["justificacion"] = attendance_reason
        return filters

    @staticmethod
    def _extract_group_by(*, normalized: str) -> list[str]:
        values: list[tuple[int, str]] = []
        variants = {
            "supervisor": ("supervisor", "supervisores", "jefe", "jefes", "lider", "lideres"),
            "area": ("area", "areas"),
            "cargo": ("cargo", "cargos"),
            "carpeta": ("carpeta", "carpetas"),
            "tipo_labor": ("labor", "labores", "tipo_labor", "tipo labor", "tipo de labor"),
            "centro_costo": ("centro costo", "centro de costo", "centros de costo", "cc"),
        }
        for canonical, tokens in variants.items():
            first_pos = None
            for token in tokens:
                explicit_match = re.search(rf"\bpor\s+{re.escape(token)}\b", normalized)
                generic_match = re.search(rf"\b{re.escape(token)}\b", normalized)
                match = explicit_match or generic_match
                if match is None:
                    continue
                pos = int(match.start())
                if first_pos is None or pos < first_pos:
                    first_pos = pos
            if first_pos is not None:
                values.append((first_pos, canonical))
        ordered = [canonical for _, canonical in sorted(values, key=lambda item: (item[0], item[1]))]
        return list(dict.fromkeys(ordered))

    @staticmethod
    def _extract_metrics(*, normalized: str, operation: str) -> list[str]:
        metrics: list[str] = []
        if any(token in normalized for token in ("rotacion", "rotaciones", "turnover")):
            metrics.append("turnover_rate")
        if operation == "count" or any(token in normalized for token in ("cantidad", "total", "cuantos", "cuantas")):
            metrics.append("count")
        if any(token in normalized for token in ("porcentaje", "participacion")):
            metrics.append("percentage")
        return metrics or ["count"]

    @staticmethod
    def _resolve_period_payload(*, message: str) -> dict[str, Any]:
        resolved = resolve_period_from_text(message)
        start = resolved.get("start")
        end = resolved.get("end")
        payload = {
            "label": str(resolved.get("label") or ""),
            "start_date": start.isoformat() if isinstance(start, date) else "",
            "end_date": end.isoformat() if isinstance(end, date) else "",
        }
        return payload

    @staticmethod
    def _compact_semantic_context(*, semantic_context: dict[str, Any]) -> dict[str, Any]:
        tables = []
        for item in list(semantic_context.get("tables") or [])[:6]:
            if not isinstance(item, dict):
                continue
            tables.append(
                {
                    "table_fqn": item.get("table_fqn"),
                    "table_name": item.get("table_name"),
                    "logical_name": item.get("nombre_tabla_logico"),
                    "role": item.get("rol"),
                }
            )
        columns = []
        for item in list(semantic_context.get("columns") or [])[:20]:
            if not isinstance(item, dict):
                continue
            columns.append(
                {
                    "table_name": item.get("table_name"),
                    "column_name": item.get("column_name"),
                    "logical_name": item.get("nombre_columna_logico"),
                }
            )
        relations = []
        for item in list(semantic_context.get("relationships") or [])[:10]:
            if not isinstance(item, dict):
                continue
            relations.append(
                {
                    "nombre_relacion": item.get("nombre_relacion"),
                    "condicion": item.get("condicion"),
                }
            )
        synonyms = []
        dictionary = dict(semantic_context.get("dictionary") or {})
        for item in list(dictionary.get("synonyms") or [])[:20]:
            if not isinstance(item, dict):
                continue
            synonyms.append(
                {
                    "termino": item.get("termino"),
                    "sinonimo": item.get("sinonimo"),
                }
            )
        company_raw = dict(semantic_context.get("company_context") or {})
        company_context = {
            "codigo_compania": company_raw.get("codigo_compania"),
            "nombre_compania": company_raw.get("nombre_compania"),
            "nombre_comercial": company_raw.get("nombre_comercial"),
            "sector": company_raw.get("sector"),
            "descripcion_negocio": company_raw.get("descripcion_negocio"),
            "objetivo_orquestador": company_raw.get("objetivo_orquestador"),
            "areas_activas": list(company_raw.get("areas_activas") or [])[:12],
            "procesos_clave": list(company_raw.get("procesos_clave") or [])[:12],
            "dominios_oficiales": list(company_raw.get("dominios_oficiales") or [])[:12],
            "lenguaje_interno": list(company_raw.get("lenguaje_interno") or [])[:16],
            "sistemas_fuente": list(company_raw.get("sistemas_fuente") or [])[:12],
            "politicas_globales": list(company_raw.get("politicas_globales") or [])[:12],
            "agentes_oficiales": list(company_raw.get("agentes_oficiales") or [])[:12],
            "restricciones_operativas": list(company_raw.get("restricciones_operativas") or [])[:16],
            "indicadores_clave": list(company_raw.get("indicadores_clave") or [])[:12],
            "dominios_operativos": list(company_raw.get("dominios_operativos") or [])[:12],
        }
        company_scope = dict(semantic_context.get("company_operational_scope") or {})
        query_hints_raw = dict(semantic_context.get("query_hints") or {})
        query_hints = {
            "candidate_tables": list(query_hints_raw.get("candidate_tables") or [])[:8],
            "candidate_columns": list(query_hints_raw.get("candidate_columns") or [])[:14],
            "candidate_group_dimensions": list(query_hints_raw.get("candidate_group_dimensions") or [])[:10],
            "candidate_filter_columns": list(query_hints_raw.get("candidate_filter_columns") or [])[:10],
            "default_filters": dict(query_hints_raw.get("default_filters") or {}),
            "runtime_rules": list(query_hints_raw.get("runtime_rules") or [])[:8],
            "join_paths": list(query_hints_raw.get("join_paths") or [])[:6],
        }
        contexto_agente_raw = dict(semantic_context.get("contexto_agente") or {})
        reglas_negocio = []
        for item in list(semantic_context.get("reglas_negocio") or [])[:6]:
            if not isinstance(item, dict):
                continue
            reglas_negocio.append(
                {
                    "codigo": item.get("codigo"),
                    "descripcion": item.get("descripcion"),
                    "prioridad": item.get("prioridad"),
                }
            )
        ejemplos_consulta = []
        for item in list(semantic_context.get("ejemplos_consulta") or [])[:4]:
            if not isinstance(item, dict):
                continue
            ejemplos_consulta.append(
                {
                    "consulta": item.get("consulta"),
                    "interpretacion": item.get("interpretacion"),
                    "capacidad_esperada": item.get("capacidad_esperada"),
                }
            )
        semantic_contract = {
            "source_of_truth": str(semantic_context.get("source_of_truth") or "").strip().lower() or "hybrid",
            "use_yaml_business_context": True,
            "use_db_structured_metadata": True,
            "yaml_context_layers": ["contexto_agente", "reglas_negocio", "ejemplos_consulta"],
            "db_context_layers": ["tables", "columns", "relationships", "synonyms", "query_hints"],
        }
        return {
            "domain_code": semantic_context.get("domain_code"),
            "domain_status": semantic_context.get("domain_status"),
            "main_entity": semantic_context.get("main_entity"),
            "semantic_contract": semantic_contract,
            "tables": tables,
            "columns": columns,
            "relationships": relations,
            "synonyms": synonyms,
            "allowed_tables": list(semantic_context.get("allowed_tables") or []),
            "allowed_columns": list(semantic_context.get("allowed_columns") or []),
            "flags": dict(semantic_context.get("flags") or {}),
            "company_context": company_context,
            "company_operational_scope": company_scope,
            "query_hints": query_hints,
            "contexto_agente": {
                "descripcion": contexto_agente_raw.get("descripcion"),
                "criterio_principal": contexto_agente_raw.get("criterio_principal"),
                "defaults_negocio": list(contexto_agente_raw.get("defaults_negocio") or [])[:8],
            },
            "vocabulario_negocio": list(semantic_context.get("vocabulario_negocio") or [])[:24],
            "tablas_prioritarias": list(semantic_context.get("tablas_prioritarias") or [])[:8],
            "columnas_prioritarias": list(semantic_context.get("columnas_prioritarias") or [])[:18],
            "reglas_negocio": reglas_negocio,
            "ejemplos_consulta": ejemplos_consulta,
        }

    @staticmethod
    def _query_pattern_fastpath_enabled() -> bool:
        return str(os.getenv("IA_DEV_QUERY_PATTERN_FASTPATH_ENABLED", "1") or "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

    @classmethod
    def _apply_query_pattern_hints(
        cls,
        *,
        message: str,
        fallback: StructuredQueryIntent,
        memory_hints: dict[str, Any],
    ) -> StructuredQueryIntent:
        patterns = [item for item in list((memory_hints or {}).get("query_patterns") or []) if isinstance(item, dict)]
        if not patterns:
            return fallback
        current_shape = cls._build_query_shape_key(message)
        matched = None
        for item in patterns:
            shape = str(item.get("query_shape_key") or "").strip().lower()
            if shape and shape == current_shape:
                matched = item
                break
        if matched is None:
            return fallback

        domain_code = str(matched.get("domain_code") or fallback.domain_code or "").strip().lower()
        operation = str(matched.get("operation") or fallback.operation or "").strip().lower()
        template_id = str(matched.get("template_id") or fallback.template_id or "").strip().lower()
        group_by = [str(item).strip().lower() for item in list(matched.get("group_by") or fallback.group_by or []) if str(item).strip()]
        metrics = [str(item).strip().lower() for item in list(matched.get("metrics") or fallback.metrics or []) if str(item).strip()]
        filters = dict(fallback.filters or {})
        for key, value in dict(matched.get("filters") or {}).items():
            clean_key = str(key or "").strip().lower()
            if clean_key in {"cedula", "identificacion", "documento", "id_empleado", "nombre", "movil", "search"}:
                continue
            if clean_key not in filters and value not in (None, ""):
                filters[clean_key] = value

        return StructuredQueryIntent(
            raw_query=fallback.raw_query,
            domain_code=domain_code or fallback.domain_code,
            operation=operation or fallback.operation,
            template_id=template_id or fallback.template_id,
            entity_type=str(fallback.entity_type or "").strip().lower(),
            entity_value=str(fallback.entity_value or "").strip(),
            filters=filters,
            period=dict(fallback.period or {}),
            group_by=group_by,
            metrics=metrics or list(fallback.metrics or []),
            confidence=max(float(fallback.confidence or 0.0), float(matched.get("score") or 0.0), 0.91),
            source="memory_pattern",
            warnings=list(fallback.warnings or []),
        )

    @staticmethod
    def _compact_query_patterns(*, memory_hints: dict[str, Any]) -> list[dict[str, Any]]:
        compacted: list[dict[str, Any]] = []
        for item in list((memory_hints or {}).get("query_patterns") or [])[:4]:
            if not isinstance(item, dict):
                continue
            compacted.append(
                {
                    "domain_code": str(item.get("domain_code") or "").strip().lower(),
                    "template_id": str(item.get("template_id") or "").strip().lower(),
                    "operation": str(item.get("operation") or "").strip().lower(),
                    "capability_id": str(item.get("capability_id") or "").strip(),
                    "group_by": [str(token).strip().lower() for token in list(item.get("group_by") or []) if str(token).strip()],
                    "metrics": [str(token).strip().lower() for token in list(item.get("metrics") or []) if str(token).strip()],
                    "filters": dict(item.get("filters") or {}),
                    "query_shape_key": str(item.get("query_shape_key") or "").strip().lower(),
                    "score": float(item.get("score") or 0.0),
                }
            )
        return compacted

    @staticmethod
    def _build_query_shape_key(value: str) -> str:
        normalized = QueryIntentResolver._normalize_text(value)
        normalized = re.sub(r"\b\d{4}-\d{2}-\d{2}\b", "<fecha>", normalized)
        normalized = re.sub(r"\b\d{6,13}\b", "<cedula>", normalized)
        normalized = re.sub(r"\b[a-z][a-z0-9_-]*\d+[a-z0-9_-]*\b", "<codigo>", normalized)
        normalized = re.sub(r"\s+", " ", normalized).strip()
        return normalized

    @staticmethod
    def _safe_json(raw_text: str) -> dict[str, Any]:
        if not raw_text:
            return {}
        json_match = re.search(r"\{.*\}", raw_text, re.DOTALL)
        raw = json_match.group(0) if json_match else raw_text
        try:
            payload = json.loads(raw)
            return payload if isinstance(payload, dict) else {}
        except Exception:
            return {}

    @staticmethod
    def _normalize_text(value: str) -> str:
        lowered = str(value or "").strip().lower()
        normalized = unicodedata.normalize("NFKD", lowered)
        clean = "".join(ch for ch in normalized if not unicodedata.combining(ch))
        return QueryIntentResolver._apply_common_business_typos(clean)

    @staticmethod
    def _resolve_domain(*, normalized: str, base_domain: str, semantic_context: dict[str, Any] | None = None) -> str:
        domain = normalizar_codigo_dominio(base_domain)
        rrhh_match = bool(
            re.search(
                r"\b(colaborador(?:es)?|personal|emplead\w*|cedula|rrhh|movil|tipo_labor|tipo\s+labor|tipo\s+de\s+labor|labor(?:es)?|area(?:s)?|cargo(?:s)?|supervisor(?:es)?|jefe(?:s)?|lider(?:es)?|carpeta(?:s)?|sede(?:s)?|egreso(?:s)?|retiro(?:s)?|retirad\w*|desvinculad\w*|baja(?:s)?|rotacion(?:es)?)\b",
                str(normalized or ""),
            )
        )
        generic_employee_lookup = bool(
            EmployeeIdentifierService.has_movil_identifier(normalized)
            or
            re.search(r"\b(?:info|informacion|detalle|datos|ficha)\s+de\s+[a-z0-9_-]{3,40}\b", str(normalized or ""))
            or re.search(r"^\s*(?:info|informacion|detalle|datos|ficha)\s+[a-z0-9_-]{3,40}\s*$", str(normalized or ""))
        )
        attendance_reason_match = bool(QueryIntentResolver._extract_attendance_reason_filter(normalized=normalized))
        attendance_match = any(token in normalized for token in ("ausent", "asistencia", "injustific")) or attendance_reason_match
        if domain == "ausentismo":
            return domain
        if domain in {"empleados", "rrhh"} and attendance_match:
            return "ausentismo"
        if domain == "empleados":
            return domain
        if attendance_match and (rrhh_match or generic_employee_lookup) and domain in {"", "general"}:
            return "ausentismo"
        if (rrhh_match or generic_employee_lookup) and domain in {"", "general"}:
            return "empleados"

        if attendance_match:
            return "ausentismo"
        semantic_query_hints = dict((semantic_context or {}).get("query_hints") or {})
        employee_dimensions = {
            str(item or "").strip().lower()
            for item in list(semantic_query_hints.get("candidate_group_dimensions") or [])
            if str(item or "").strip()
        }
        employee_dimensions.update({"area", "cargo", "supervisor", "carpeta", "tipo_labor", "labor", "sede", "centro_costo"})
        if not attendance_match and QueryIntentResolver._has_employee_dimension_signal(
            normalized=normalized,
            employee_dimensions=employee_dimensions,
        ):
            return "empleados"
        if rrhh_match or generic_employee_lookup:
            return "empleados"
        if any(token in normalized for token in ("transporte", "ruta", "movilidad", "vehicul")):
            return "general"
        return normalizar_dominio_operativo(domain, fallback="general")

    @classmethod
    def _has_employee_inactive_signal(cls, normalized: str) -> bool:
        return bool(cls._EMPLOYEE_INACTIVE_SIGNAL_RE.search(str(normalized or "")))

    @classmethod
    def _has_employee_active_signal(cls, normalized: str) -> bool:
        return bool(cls._EMPLOYEE_ACTIVE_SIGNAL_RE.search(str(normalized or "")))

    @classmethod
    def _has_temporal_reference(cls, normalized: str) -> bool:
        return bool(cls._TEMPORAL_REFERENCE_RE.search(str(normalized or "")))

    @classmethod
    def _has_employee_status_metric_signal(cls, normalized: str) -> bool:
        text = str(normalized or "")
        if re.search(r"\b(egresos|retiros|desvinculaciones|bajas|rotacion|rotaciones)\b", text):
            return True
        if cls._has_employee_inactive_signal(text) and cls._has_temporal_reference(text):
            return True
        if cls._has_employee_active_signal(text) and cls._has_temporal_reference(text):
            return True
        return False

    @classmethod
    def _is_turnover_query(cls, normalized: str) -> bool:
        return bool(re.search(r"\b(rotacion|rotaciones|turnover)\b", str(normalized or "")))

    @classmethod
    def _extract_attendance_reason_filter(cls, *, normalized: str) -> str:
        text = str(normalized or "")
        for token, canonical in cls._ATTENDANCE_REASON_SIGNALS.items():
            if re.search(rf"\b{re.escape(token)}\b", text):
                return canonical
        return ""

    @classmethod
    def _looks_like_attendance_person_detail(cls, *, normalized: str, domain: str) -> bool:
        if normalizar_codigo_dominio(domain) != "ausentismo":
            return False
        if cls._has_explicit_grouping_phrase(normalized) or cls._has_aggregate_signal(normalized):
            return False
        if any(token in normalized for token in ("cantidad", "cuantos", "cuantas", "total", "numero", "tendencia", "historico", "evolucion")):
            return False
        has_reason = bool(cls._extract_attendance_reason_filter(normalized=normalized))
        has_people_scope = bool(
            re.search(r"\b(emplead\w*|colaborador(?:es)?|personal|persona(?:s)?)\b", str(normalized or ""))
        )
        return has_reason and has_people_scope

    @staticmethod
    def _has_group_dimension_signal(normalized: str) -> bool:
        return bool(
            re.search(
                r"\b(supervisor(?:es)?|jefe(?:s)?|lider(?:es)?|area|areas|cargo|cargos|carpeta|carpetas|labor(?:es)?|tipo_labor|tipo\s+labor|tipo\s+de\s+labor|centro\s+de\s+costo|centro\s+costo|cc)\b",
                str(normalized or ""),
            )
        )

    @staticmethod
    def _has_employee_dimension_signal(*, normalized: str, employee_dimensions: set[str]) -> bool:
        text = str(normalized or "")
        token_variants = set(employee_dimensions or set())
        token_variants.update({"labor", "labores", "tipo labor", "tipo de labor", "tipo_labor", "area", "areas"})
        for token in sorted(token_variants, key=len, reverse=True):
            if not token:
                continue
            if re.search(rf"\b{re.escape(token)}\b", text):
                return True
        return False

    @staticmethod
    def _has_explicit_grouping_phrase(normalized: str) -> bool:
        return bool(
            re.search(
                r"\bpor\s+(supervisor(?:es)?|jefe(?:s)?|lider(?:es)?|area|areas|cargo|cargos|carpeta|carpetas|labor(?:es)?|tipo_labor|tipo\s+labor|tipo\s+de\s+labor)\b",
                str(normalized or ""),
            )
        )

    @staticmethod
    def _has_aggregate_signal(normalized: str) -> bool:
        text = str(normalized or "")
        if "concentra" in text or "concentran" in text:
            return True
        if "distribucion" in text or "participacion" in text:
            return True
        if QueryIntentResolver._has_explicit_grouping_phrase(text):
            return True
        if QueryIntentResolver._has_group_dimension_signal(text) and any(
            token in text for token in ("mas", "top", "compar", "versus", "vs")
        ):
            return True
        return False

    @staticmethod
    def _has_identifier_signal(normalized: str) -> bool:
        text = str(normalized or "")
        if re.search(r"\b\d{6,13}\b", text):
            return True
        if EmployeeIdentifierService.has_movil_identifier(text):
            return True
        return bool(
            re.search(r"\b(?:info|informacion|detalle|datos|ficha)\s+de\s+[a-z0-9_-]{3,40}\b", text)
            or re.search(r"^\s*(?:info|informacion|detalle|datos|ficha)\s+[a-z0-9_-]{3,40}\s*$", text)
        )

    @staticmethod
    def _extract_raw_identifier_token(*, message: str, normalized_token: str) -> str:
        raw = str(message or "").strip()
        token = str(normalized_token or "").strip()
        if not raw or not token:
            return ""
        match = re.search(rf"\b{re.escape(token)}\b", raw, re.IGNORECASE)
        if not match:
            return ""
        return str(match.group(0) or "").strip()

    @staticmethod
    def _apply_common_business_typos(value: str) -> str:
        normalized = str(value or "")
        replacements = (
            (r"\bempelados\b", "empleados"),
            (r"\bempelado\b", "empleado"),
            (r"\bempeladas\b", "empleadas"),
            (r"\bempelada\b", "empleada"),
            (r"\bcantididad\b", "cantidad"),
            (r"\bares\b", "areas"),
            (r"\btipo\s+de\s+labro\b", "tipo de labor"),
            (r"\bvacasiones\b", "vacaciones"),
        )
        for pattern, replacement in replacements:
            normalized = re.sub(pattern, replacement, normalized)
        normalized = re.sub(r"\s+", " ", normalized).strip()
        return normalized
    _ATTENDANCE_REASON_SIGNALS = {
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
