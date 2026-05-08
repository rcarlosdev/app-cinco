from __future__ import annotations

import os
from unittest.mock import patch

from django.test import SimpleTestCase

from apps.ia_dev.application.context.run_context import RunContext
from apps.ia_dev.application.contracts.query_intelligence_contracts import (
    QueryExecutionPlan,
    ResolvedQuerySpec,
    StructuredQueryIntent,
)
from apps.ia_dev.application.policies.query_execution_policy import QueryExecutionPolicy
from apps.ia_dev.application.semantic.query_execution_planner import QueryExecutionPlanner
from apps.ia_dev.application.semantic.query_intent_resolver import QueryIntentResolver
from apps.ia_dev.application.semantic.query_pattern_memory_service import QueryPatternMemoryService
from apps.ia_dev.application.semantic.result_satisfaction_validator import (
    ResultSatisfactionValidator,
)


class QueryIntelligenceLayerTests(SimpleTestCase):
    def test_query_intent_resolver_rules_are_accent_insensitive_for_rrhh_count(self):
        resolver = QueryIntentResolver()
        with patch.dict(os.environ, {"IA_DEV_QUERY_INTELLIGENCE_OPENAI_ENABLED": "0"}, clear=False):
            intent = resolver.resolve(
                message="¿Cuántos colaboradores habilitados tenemos hoy?",
                base_classification={
                    "domain": "general",
                    "intent": "general_question",
                    "needs_database": False,
                },
                semantic_context={},
            )
        self.assertEqual(intent.domain_code, "empleados")
        self.assertEqual(intent.operation, "count")

    def test_query_intent_resolver_rules_for_empleados_activos(self):
        resolver = QueryIntentResolver()
        with patch.dict(os.environ, {"IA_DEV_QUERY_INTELLIGENCE_OPENAI_ENABLED": "0"}, clear=False):
            intent = resolver.resolve(
                message="Cantidad empleados activos",
                base_classification={
                    "domain": "empleados",
                    "intent": "empleados_query",
                    "needs_database": True,
                },
                semantic_context={},
            )
        self.assertEqual(intent.domain_code, "empleados")
        self.assertEqual(intent.operation, "count")
        self.assertEqual(intent.template_id, "count_entities_by_status")
        # El estado se resuelve en la capa semantica (dd_campos/dd_sinonimos), no en intent resolver.
        self.assertEqual(str(intent.filters.get("estado") or ""), "")

    def test_query_intent_resolver_treats_personal_activo_hoy_as_employee_count(self):
        resolver = QueryIntentResolver()
        with patch.dict(os.environ, {"IA_DEV_QUERY_INTELLIGENCE_OPENAI_ENABLED": "0"}, clear=False):
            intent = resolver.resolve(
                message="personal activo hoy",
                base_classification={
                    "domain": "empleados",
                    "intent": "empleados_query",
                    "needs_database": True,
                },
                semantic_context={},
            )
        self.assertEqual(intent.domain_code, "empleados")
        self.assertEqual(intent.operation, "count")
        self.assertEqual(intent.template_id, "count_entities_by_status")
        self.assertEqual(dict(intent.period or {}), {})

    def test_query_intent_resolver_treats_colaboradores_activos_as_employee_count(self):
        resolver = QueryIntentResolver()
        with patch.dict(os.environ, {"IA_DEV_QUERY_INTELLIGENCE_OPENAI_ENABLED": "0"}, clear=False):
            intent = resolver.resolve(
                message="colaboradores activos",
                base_classification={
                    "domain": "general",
                    "intent": "general_question",
                    "needs_database": False,
                },
                semantic_context={},
            )
        self.assertEqual(intent.domain_code, "empleados")
        self.assertEqual(intent.operation, "count")
        self.assertEqual(intent.template_id, "count_entities_by_status")

    def test_query_intent_resolver_inferrs_employee_egresos_this_month_as_inactive_count(self):
        resolver = QueryIntentResolver()
        with patch.dict(os.environ, {"IA_DEV_QUERY_INTELLIGENCE_OPENAI_ENABLED": "0"}, clear=False):
            intent = resolver.resolve(
                message="Egresos de este mes?",
                base_classification={
                    "domain": "general",
                    "intent": "general_question",
                    "needs_database": False,
                },
                semantic_context={},
            )
        self.assertEqual(intent.domain_code, "empleados")
        self.assertEqual(intent.operation, "count")
        self.assertEqual(intent.template_id, "count_entities_by_status")
        self.assertEqual(str(intent.filters.get("estado") or ""), "INACTIVO")
        self.assertEqual(str((intent.period or {}).get("label") or ""), "mes_actual")
        self.assertTrue(bool((intent.period or {}).get("start_date")))
        self.assertTrue(bool((intent.period or {}).get("end_date")))

    def test_query_intent_resolver_infers_employee_turnover_last_month_as_inactive_count(self):
        resolver = QueryIntentResolver()
        with patch.dict(os.environ, {"IA_DEV_QUERY_INTELLIGENCE_OPENAI_ENABLED": "0"}, clear=False):
            intent = resolver.resolve(
                message="rotacion de personal ultimo mes?",
                base_classification={
                    "domain": "general",
                    "intent": "general_question",
                    "needs_database": False,
                },
                semantic_context={},
            )
        self.assertEqual(intent.domain_code, "empleados")
        self.assertEqual(intent.operation, "count")
        self.assertEqual(intent.template_id, "count_entities_by_status")
        self.assertEqual(str(intent.filters.get("estado") or ""), "INACTIVO")
        self.assertIn("turnover_rate", list(intent.metrics or []))
        self.assertEqual(str((intent.period or {}).get("label") or ""), "ultimo_mes_30_dias")

    def test_query_intent_resolver_preserves_turnover_when_openai_marks_trend(self):
        resolver = QueryIntentResolver()
        fallback = StructuredQueryIntent(
            raw_query="Rotación de empelados de I&M",
            domain_code="empleados",
            operation="count",
            template_id="count_entities_by_status",
            filters={"estado": "INACTIVO", "area": "I&M"},
            period={"label": "ultimo_mes_30_dias", "start_date": "2026-03-26", "end_date": "2026-04-24"},
            group_by=[],
            metrics=["turnover_rate", "count"],
            confidence=0.8,
            source="rules",
        )
        llm = StructuredQueryIntent(
            raw_query="Rotación de empelados de I&M",
            domain_code="empleados",
            operation="trend",
            template_id="trend_by_period",
            filters={"estado": "INACTIVO", "area": "I&M"},
            period={"label": "ultimo_mes_30_dias", "start_date": "2026-03-26", "end_date": "2026-04-24"},
            group_by=[],
            metrics=["count"],
            confidence=0.6,
            source="openai",
        )

        merged = resolver._merge_intents(fallback=fallback, llm=llm)

        self.assertEqual(merged.domain_code, "empleados")
        self.assertEqual(merged.operation, "count")
        self.assertEqual(merged.template_id, "count_entities_by_status")
        self.assertIn("turnover_rate", list(merged.metrics or []))
        self.assertEqual(str(merged.filters.get("area") or ""), "I&M")

    def test_query_intent_resolver_treats_por_area_as_grouped_employee_aggregate(self):
        resolver = QueryIntentResolver()
        with patch.dict(os.environ, {"IA_DEV_QUERY_INTELLIGENCE_OPENAI_ENABLED": "0"}, clear=False):
            intent = resolver.resolve(
                message="empleados por area",
                base_classification={
                    "domain": "empleados",
                    "intent": "empleados_query",
                    "needs_database": True,
                },
                semantic_context={},
            )
        self.assertEqual(intent.domain_code, "empleados")
        self.assertEqual(intent.operation, "aggregate")
        self.assertEqual(intent.template_id, "aggregate_by_group_and_period")
        self.assertEqual(list(intent.group_by or []), ["area"])
        self.assertIn("count", list(intent.metrics or []))

    def test_query_intent_resolver_treats_birthday_by_area_as_grouped_employee_aggregate(self):
        resolver = QueryIntentResolver()
        with patch.dict(os.environ, {"IA_DEV_QUERY_INTELLIGENCE_OPENAI_ENABLED": "0"}, clear=False):
            intent = resolver.resolve(
                message="cumpleanos de mayo por area",
                base_classification={
                    "domain": "general",
                    "intent": "general_question",
                    "needs_database": False,
                },
                semantic_context={
                    "query_hints": {
                        "candidate_group_dimensions": ["area", "cargo", "birth_month"],
                    },
                    "synonym_index": {
                        "cumpleanos": "fecha_nacimiento",
                        "cumpleanos de empleados": "fecha_nacimiento",
                    },
                },
            )
        self.assertEqual(intent.domain_code, "empleados")
        self.assertEqual(intent.operation, "aggregate")
        self.assertEqual(intent.template_id, "aggregate_by_group_and_period")
        self.assertEqual(str((intent.filters or {}).get("fnacimiento_month") or ""), "5")
        self.assertEqual(list(intent.group_by or []), ["area"])

    def test_query_intent_resolver_treats_por_labor_as_grouped_employee_aggregate(self):
        resolver = QueryIntentResolver()
        with patch.dict(os.environ, {"IA_DEV_QUERY_INTELLIGENCE_OPENAI_ENABLED": "0"}, clear=False):
            intent = resolver.resolve(
                message="empleados por labor",
                base_classification={
                    "domain": "empleados",
                    "intent": "empleados_query",
                    "needs_database": True,
                },
                semantic_context={},
            )
        self.assertEqual(intent.domain_code, "empleados")
        self.assertEqual(intent.operation, "aggregate")
        self.assertIn("tipo_labor", list(intent.group_by or []))

    def test_query_intent_resolver_treats_movil_and_tecnicos_as_operational_grouped_employee_aggregate(self):
        resolver = QueryIntentResolver()
        with patch.dict(os.environ, {"IA_DEV_QUERY_INTELLIGENCE_OPENAI_ENABLED": "0"}, clear=False):
            intent = resolver.resolve(
                message="Que moviles o cuadrillas tienen mas tecnicos asignados",
                base_classification={
                    "domain": "general",
                    "intent": "general_question",
                    "needs_database": False,
                },
                semantic_context={
                    "column_profiles": [
                        {
                            "logical_name": "movil",
                            "column_name": "movil",
                            "supports_group_by": True,
                            "supports_dimension": True,
                        },
                        {
                            "logical_name": "tipo_labor",
                            "column_name": "tipo_labor",
                            "supports_filter": True,
                            "allowed_values": ["OPERATIVO", "ADMINISTRATIVO", "SUPERVISOR", "TRANSVERSAL"],
                        },
                    ],
                    "synonym_index": {
                        "cuadrilla": "movil",
                        "cuadrillas": "movil",
                        "tecnico": "operativo",
                        "tecnicos": "operativo",
                    },
                    "query_hints": {
                        "candidate_group_dimensions": ["movil", "tipo_labor"],
                    },
                },
            )
        self.assertEqual(intent.domain_code, "empleados")
        self.assertEqual(intent.operation, "aggregate")
        self.assertEqual(intent.template_id, "aggregate_by_group_and_period")
        self.assertIn("movil", list(intent.group_by or []))
        self.assertEqual(str((intent.filters or {}).get("tipo_labor") or ""), "OPERATIVO")

    def test_query_intent_resolver_detects_identity_document_missingness_as_general_operator(self):
        resolver = QueryIntentResolver()
        with patch.dict(os.environ, {"IA_DEV_QUERY_INTELLIGENCE_OPENAI_ENABLED": "0"}, clear=False):
            intent = resolver.resolve(
                message="Que documentos de identidad faltan",
                base_classification={
                    "domain": "empleados",
                    "intent": "analytics_query",
                    "needs_database": True,
                },
                semantic_context={
                    "column_profiles": [
                        {"logical_name": "documento_identidad_lado_a", "column_name": "datos", "supports_filter": True},
                        {"logical_name": "documento_identidad_lado_b", "column_name": "datos", "supports_filter": True},
                    ],
                    "synonym_index": {"documento de identidad": "documento_identidad_lado_a"},
                },
            )
        self.assertEqual(str(intent.domain_code or ""), "empleados")
        self.assertEqual(
            dict(intent.filters or {}).get("documento_identidad"),
            {"operator": "is_incomplete", "match_mode": "null_or_empty"},
        )

    def test_query_intent_resolver_merge_preserves_missingness_filters_over_llm_noise(self):
        resolver = QueryIntentResolver()
        fallback = StructuredQueryIntent(
            raw_query="Que empleados activos no tienen supervisor registrado",
            domain_code="empleados",
            operation="detail",
            template_id="detail_by_entity_and_period",
            filters={"supervisor": {"operator": "is_missing", "match_mode": "null_or_empty"}},
            period={},
            group_by=[],
            metrics=["count"],
            confidence=0.8,
            source="rules",
        )
        llm = StructuredQueryIntent(
            raw_query=fallback.raw_query,
            domain_code="empleados",
            operation="aggregate",
            template_id="aggregate_by_group_and_period",
            filters={"conduce": "NO", "estado": "ACTIVO"},
            period={},
            group_by=["supervisor"],
            metrics=["count"],
            confidence=0.9,
            source="openai",
        )
        merged = resolver._merge_intents(fallback=fallback, llm=llm)
        self.assertEqual(str(merged.operation or ""), "detail")
        self.assertEqual(str(merged.template_id or ""), "detail_by_entity_and_period")
        self.assertEqual(list(merged.group_by or []), [])
        self.assertEqual(
            dict(merged.filters or {}).get("supervisor"),
            {"operator": "is_missing", "match_mode": "null_or_empty"},
        )
        self.assertNotIn("conduce", dict(merged.filters or {}))

    def test_query_intent_resolver_does_not_convert_group_dimension_into_tipo_labor_filter(self):
        resolver = QueryIntentResolver()
        with patch.dict(os.environ, {"IA_DEV_QUERY_INTELLIGENCE_OPENAI_ENABLED": "0"}, clear=False):
            intent = resolver.resolve(
                message="Empleados operativos por supervisor",
                base_classification={
                    "domain": "empleados",
                    "intent": "empleados_query",
                    "needs_database": True,
                },
                semantic_context={
                    "column_profiles": [
                        {
                            "logical_name": "supervisor",
                            "column_name": "supervisor",
                            "supports_group_by": True,
                            "supports_dimension": True,
                        },
                        {
                            "logical_name": "tipo_labor",
                            "column_name": "tipo_labor",
                            "supports_filter": True,
                            "allowed_values": ["OPERATIVO", "ADMINISTRATIVO", "SUPERVISOR", "TRANSVERSAL"],
                        },
                    ],
                    "synonym_index": {
                        "operativos": "operativo",
                    },
                    "query_hints": {
                        "candidate_group_dimensions": ["supervisor"],
                    },
                },
            )
        self.assertEqual(list(intent.group_by or []), ["supervisor"])
        self.assertEqual(str((intent.filters or {}).get("tipo_labor") or ""), "OPERATIVO")

    def test_query_intent_resolver_infers_empleados_domain_from_business_dimensions_only(self):
        resolver = QueryIntentResolver()
        with patch.dict(os.environ, {"IA_DEV_QUERY_INTELLIGENCE_OPENAI_ENABLED": "0"}, clear=False):
            intent = resolver.resolve(
                message="cantidad de tipo de labor por area",
                base_classification={
                    "domain": "general",
                    "intent": "general_question",
                    "needs_database": False,
                },
                semantic_context={
                    "query_hints": {
                        "candidate_group_dimensions": ["tipo_labor", "area", "cargo"],
                    }
                },
            )
        self.assertEqual(intent.domain_code, "empleados")
        self.assertEqual(intent.operation, "count")
        self.assertEqual(intent.template_id, "aggregate_by_group_and_period")
        self.assertEqual(list(intent.group_by or []), ["tipo_labor", "area"])

    def test_query_intent_resolver_normalizes_common_employee_typos(self):
        resolver = QueryIntentResolver()
        with patch.dict(os.environ, {"IA_DEV_QUERY_INTELLIGENCE_OPENAI_ENABLED": "0"}, clear=False):
            intent = resolver.resolve(
                message="cantidad empelados por ares",
                base_classification={
                    "domain": "general",
                    "intent": "general_question",
                    "needs_database": False,
                },
                semantic_context={},
            )
        self.assertEqual(intent.domain_code, "empleados")
        self.assertIn("area", list(intent.group_by or []))

    def test_query_intent_resolver_detects_employee_detail_by_movil_identifier(self):
        resolver = QueryIntentResolver()
        with patch.dict(os.environ, {"IA_DEV_QUERY_INTELLIGENCE_OPENAI_ENABLED": "0"}, clear=False):
            intent = resolver.resolve(
                message="informacion de TIRAN462",
                base_classification={
                    "domain": "empleados",
                    "intent": "empleados_query",
                    "needs_database": True,
                },
                semantic_context={},
            )
        self.assertEqual(intent.domain_code, "empleados")
        self.assertEqual(intent.operation, "detail")
        self.assertEqual(intent.template_id, "detail_by_entity_and_period")
        self.assertEqual(intent.entity_type, "movil")
        self.assertEqual(str(intent.filters.get("movil") or ""), "TIRAN462")

    def test_query_intent_resolver_detects_employee_detail_by_movil_identifier_without_preposition(self):
        resolver = QueryIntentResolver()
        with patch.dict(os.environ, {"IA_DEV_QUERY_INTELLIGENCE_OPENAI_ENABLED": "0"}, clear=False):
            intent = resolver.resolve(
                message="informacion TIRAN462",
                base_classification={
                    "domain": "empleados",
                    "intent": "empleados_query",
                    "needs_database": True,
                },
                semantic_context={},
            )
        self.assertEqual(intent.domain_code, "empleados")
        self.assertEqual(intent.operation, "detail")
        self.assertEqual(str(intent.filters.get("movil") or ""), "TIRAN462")

    def test_query_intent_resolver_detects_employee_detail_by_movil_identifier_with_space(self):
        resolver = QueryIntentResolver()
        with patch.dict(os.environ, {"IA_DEV_QUERY_INTELLIGENCE_OPENAI_ENABLED": "0"}, clear=False):
            intent = resolver.resolve(
                message="informacion tiran 462",
                base_classification={
                    "domain": "empleados",
                    "intent": "empleados_query",
                    "needs_database": True,
                },
                semantic_context={},
            )
        self.assertEqual(intent.domain_code, "empleados")
        self.assertEqual(intent.operation, "detail")
        self.assertEqual(str(intent.filters.get("movil") or ""), "TIRAN462")

    def test_query_intent_resolver_detects_employee_detail_by_movil_numeric_suffix(self):
        resolver = QueryIntentResolver()
        with patch.dict(os.environ, {"IA_DEV_QUERY_INTELLIGENCE_OPENAI_ENABLED": "0"}, clear=False):
            intent = resolver.resolve(
                message="462",
                base_classification={
                    "domain": "general",
                    "intent": "general_question",
                    "needs_database": False,
                },
                semantic_context={},
            )
        self.assertEqual(intent.domain_code, "empleados")
        self.assertEqual(intent.operation, "detail")
        self.assertEqual(str(intent.filters.get("movil") or ""), "462")

    def test_query_intent_resolver_detects_employee_detail_by_name_lookup(self):
        resolver = QueryIntentResolver()
        with patch.dict(os.environ, {"IA_DEV_QUERY_INTELLIGENCE_OPENAI_ENABLED": "0"}, clear=False):
            intent = resolver.resolve(
                message="buscar Juan Perez",
                base_classification={
                    "domain": "empleados",
                    "intent": "empleados_query",
                    "needs_database": True,
                },
                semantic_context={},
            )
        self.assertEqual(intent.domain_code, "empleados")
        self.assertEqual(intent.operation, "detail")
        self.assertEqual(intent.template_id, "detail_by_entity_and_period")
        self.assertEqual(str(intent.filters.get("nombre") or ""), "juan perez")

    def test_query_intent_resolver_detects_employee_detail_by_numeric_employee_code(self):
        resolver = QueryIntentResolver()
        with patch.dict(os.environ, {"IA_DEV_QUERY_INTELLIGENCE_OPENAI_ENABLED": "0"}, clear=False):
            intent = resolver.resolve(
                message="empleado 123456",
                base_classification={
                    "domain": "general",
                    "intent": "general_question",
                    "needs_database": False,
                },
                semantic_context={},
            )
        self.assertEqual(intent.domain_code, "empleados")
        self.assertEqual(intent.operation, "detail")
        self.assertEqual(intent.template_id, "detail_by_entity_and_period")
        self.assertEqual(str(intent.filters.get("cedula") or ""), "123456")

    def test_query_intent_resolver_merge_discards_search_when_identifier_is_present(self):
        fallback = StructuredQueryIntent(
            raw_query="informacion TIRAN462",
            domain_code="empleados",
            operation="detail",
            template_id="detail_by_entity_and_period",
            entity_type="movil",
            entity_value="TIRAN462",
            filters={"movil": "TIRAN462"},
            source="rules",
        )
        llm = StructuredQueryIntent(
            raw_query="informacion TIRAN462",
            domain_code="empleados",
            operation="detail",
            template_id="detail_by_entity_and_period",
            entity_type="entity_code",
            entity_value="TIRAN462",
            filters={"search": "informacion tiran462"},
            source="openai",
        )
        merged = QueryIntentResolver._merge_intents(fallback=fallback, llm=llm)
        self.assertEqual(str(merged.filters.get("movil") or ""), "TIRAN462")
        self.assertNotIn("search", dict(merged.filters or {}))

    def test_query_intent_resolver_merge_keeps_employee_domain_when_llm_falls_back_to_general(self):
        fallback = StructuredQueryIntent(
            raw_query="informacion de TIRAN462",
            domain_code="empleados",
            operation="detail",
            template_id="detail_by_entity_and_period",
            entity_type="movil",
            entity_value="TIRAN462",
            filters={"movil": "TIRAN462"},
            source="rules",
        )
        llm = StructuredQueryIntent(
            raw_query="informacion de TIRAN462",
            domain_code="general",
            operation="detail",
            template_id="detail_by_entity_and_period",
            entity_type="movil",
            entity_value="TIRAN462",
            filters={"movil": "TIRAN462"},
            source="openai",
        )
        merged = QueryIntentResolver._merge_intents(fallback=fallback, llm=llm)
        self.assertEqual(merged.domain_code, "empleados")

    def test_query_intent_resolver_detects_group_by_area_and_rolling_period_from_concentration_question(self):
        resolver = QueryIntentResolver()
        with patch.dict(os.environ, {"IA_DEV_QUERY_INTELLIGENCE_OPENAI_ENABLED": "0"}, clear=False):
            intent = resolver.resolve(
                message="que areas concentran mas ausentismos en rolling 90 dias y que causas probables sugieres?",
                base_classification={
                    "domain": "attendance",
                    "intent": "attendance_query",
                    "needs_database": True,
                },
                semantic_context={},
            )
        self.assertEqual(intent.domain_code, "ausentismo")
        self.assertEqual(intent.template_id, "aggregate_by_group_and_period")
        self.assertIn("area", list(intent.group_by or []))
        self.assertEqual(str((intent.period or {}).get("label") or ""), "rolling_90_dias")

    def test_query_intent_resolver_maps_personal_en_vacaciones_to_attendance_detail_with_reason_filter(self):
        resolver = QueryIntentResolver()
        with patch.dict(os.environ, {"IA_DEV_QUERY_INTELLIGENCE_OPENAI_ENABLED": "0"}, clear=False):
            intent = resolver.resolve(
                message="personal en vacaciones del 2026-04-01 al 2026-04-19",
                base_classification={
                    "domain": "empleados",
                    "intent": "empleados_query",
                    "needs_database": True,
                },
                semantic_context={},
            )
        self.assertEqual(intent.domain_code, "ausentismo")
        self.assertEqual(intent.operation, "detail")
        self.assertEqual(intent.template_id, "detail_by_entity_and_period")
        self.assertEqual(str(intent.filters.get("justificacion") or ""), "VACACIONES")

    def test_query_intent_resolver_compact_context_exposes_hybrid_yaml_and_db_contract(self):
        payload = QueryIntentResolver._compact_semantic_context(
            semantic_context={
                "source_of_truth": "hybrid",
                "tables": [{"table_name": "cinco_base_de_personal", "table_fqn": "bd.cinco_base_de_personal"}],
                "columns": [{"table_name": "cinco_base_de_personal", "column_name": "area", "nombre_columna_logico": "area"}],
                "contexto_agente": {"descripcion": "Dominio de empleados"},
                "reglas_negocio": [{"codigo": "empleados_estado_por_defecto", "descripcion": "usar activo"}],
                "ejemplos_consulta": [{"consulta": "empleados por area", "interpretacion": "agrupado"}],
                "vocabulario_negocio": ["empleados", "labor"],
                "tablas_prioritarias": ["cinco_base_de_personal"],
                "columnas_prioritarias": ["area", "tipo_labor"],
            }
        )
        contract = dict(payload.get("semantic_contract") or {})
        self.assertEqual(str(contract.get("source_of_truth") or ""), "hybrid")
        self.assertTrue(bool(contract.get("use_yaml_business_context")))
        self.assertTrue(bool(contract.get("use_db_structured_metadata")))
        self.assertIn("empleados", list(payload.get("vocabulario_negocio") or []))
        self.assertIn("cinco_base_de_personal", list(payload.get("tablas_prioritarias") or []))

    def test_query_intent_resolver_reuses_exact_successful_query_pattern_fastpath(self):
        resolver = QueryIntentResolver()
        with patch.dict(
            os.environ,
            {
                "IA_DEV_QUERY_INTELLIGENCE_OPENAI_ENABLED": "0",
                "IA_DEV_QUERY_PATTERN_FASTPATH_ENABLED": "1",
            },
            clear=False,
        ):
            intent = resolver.resolve(
                message="cantidad de tipo de labor por área",
                base_classification={
                    "domain": "general",
                    "intent": "general_question",
                    "needs_database": False,
                },
                semantic_context={},
                memory_hints={
                    "query_patterns": [
                        {
                            "domain_code": "empleados",
                            "template_id": "aggregate_by_group_and_period",
                            "operation": "count",
                            "capability_id": "empleados.count.active.v1",
                            "group_by": ["tipo_labor", "area"],
                            "metrics": ["count"],
                            "filters": {"estado": "ACTIVO"},
                            "query_shape_key": QueryIntentResolver._build_query_shape_key("cantidad de tipo de labor por area"),
                            "score": 0.98,
                        }
                    ]
                },
            )
        self.assertEqual(intent.domain_code, "empleados")
        self.assertEqual(intent.template_id, "aggregate_by_group_and_period")
        self.assertEqual(list(intent.group_by or []), ["tipo_labor", "area"])
        self.assertEqual(str(intent.filters.get("estado") or ""), "ACTIVO")
        self.assertEqual(intent.source, "memory_pattern")

    def test_query_pattern_memory_service_builds_stable_query_shape_key(self):
        key_a = QueryPatternMemoryService._build_query_shape_key("informacion TIRAN462")
        key_b = QueryPatternMemoryService._build_query_shape_key("información TIRAN999")
        self.assertEqual(key_a, key_b)
        self.assertIn("<codigo>", key_a)

    def test_query_execution_planner_selects_capability_for_empleados_count_active(self):
        planner = QueryExecutionPlanner()
        intent = StructuredQueryIntent(
            raw_query="Cantidad empleados activos",
            domain_code="empleados",
            operation="count",
            template_id="count_entities_by_status",
            filters={"estado": "ACTIVO"},
            period={},
            group_by=[],
            metrics=["count"],
            confidence=0.9,
            source="rules",
        )
        resolved_query = ResolvedQuerySpec(
            intent=intent,
            semantic_context={
                "domain_status": "active",
                "supports_sql_assisted": False,
                "tables": [{"table_fqn": "bd_c3nc4s1s.cinco_base_de_personal", "table_name": "cinco_base_de_personal"}],
                "allowed_tables": ["cinco_base_de_personal", "bd_c3nc4s1s.cinco_base_de_personal"],
                "allowed_columns": ["estado", "cedula"],
            },
            normalized_filters={"estado": "ACTIVO"},
            normalized_period={},
            mapped_columns={"estado": "estado"},
        )
        with patch.dict(
            os.environ,
            {
                "IA_DEV_CAP_EMPLEADOS_ENABLED": "1",
                "IA_DEV_CAP_EMPLEADOS_COUNT_ENABLED": "1",
            },
            clear=False,
        ):
            run_context = RunContext.create(message="Cantidad empleados activos")
            plan = planner.plan(
                run_context=run_context,
                resolved_query=resolved_query,
            )
        self.assertEqual(plan.strategy, "capability")
        self.assertEqual(plan.capability_id, "empleados.count.active.v1")

    def test_query_execution_planner_selects_count_capability_for_personal_activo_hoy_without_search_literal(self):
        planner = QueryExecutionPlanner()
        intent = StructuredQueryIntent(
            raw_query="personal activo hoy",
            domain_code="empleados",
            operation="count",
            template_id="count_entities_by_status",
            filters={"estado": "ACTIVO"},
            period={},
            group_by=[],
            metrics=["count"],
            confidence=0.9,
            source="rules",
        )
        resolved_query = ResolvedQuerySpec(
            intent=intent,
            semantic_context={
                "domain_status": "active",
                "supports_sql_assisted": False,
                "tables": [{"table_fqn": "bd_c3nc4s1s.cinco_base_de_personal", "table_name": "cinco_base_de_personal"}],
                "allowed_tables": ["cinco_base_de_personal", "bd_c3nc4s1s.cinco_base_de_personal"],
                "allowed_columns": ["estado", "cedula"],
            },
            normalized_filters={"estado": "ACTIVO"},
            normalized_period={},
            mapped_columns={"estado": "estado"},
        )
        with patch.dict(
            os.environ,
            {
                "IA_DEV_CAP_EMPLEADOS_ENABLED": "1",
                "IA_DEV_CAP_EMPLEADOS_COUNT_ENABLED": "1",
            },
            clear=False,
        ):
            plan = planner.plan(
                run_context=RunContext.create(message=intent.raw_query),
                resolved_query=resolved_query,
            )
        self.assertEqual(plan.strategy, "capability")
        self.assertEqual(plan.capability_id, "empleados.count.active.v1")
        self.assertFalse(bool(((plan.constraints or {}).get("entity_scope") or {}).get("has_entity_filter")))
        self.assertNotIn("search", dict((plan.constraints or {}).get("filters") or {}))

    def test_query_execution_planner_recovers_population_summary_when_upstream_marks_employee_detail(self):
        planner = QueryExecutionPlanner()
        intent = StructuredQueryIntent(
            raw_query="personal activo hoy",
            domain_code="empleados",
            operation="detail",
            template_id="detail_by_entity_and_period",
            filters={"estado": "ACTIVO"},
            period={"label": "hoy", "start_date": "2026-05-06", "end_date": "2026-05-06"},
            group_by=[],
            metrics=["count"],
            confidence=0.63,
            source="openai",
        )
        resolved_query = ResolvedQuerySpec(
            intent=intent,
            semantic_context={
                "domain_status": "active",
                "supports_sql_assisted": False,
                "tables": [{"table_fqn": "bd_c3nc4s1s.cinco_base_de_personal", "table_name": "cinco_base_de_personal"}],
                "allowed_tables": ["cinco_base_de_personal", "bd_c3nc4s1s.cinco_base_de_personal"],
                "allowed_columns": ["estado", "cedula"],
            },
            normalized_filters={"estado": "ACTIVO"},
            normalized_period={},
            mapped_columns={"estado": "estado"},
        )
        with patch.dict(
            os.environ,
            {
                "IA_DEV_CAP_EMPLEADOS_ENABLED": "1",
                "IA_DEV_CAP_EMPLEADOS_COUNT_ENABLED": "1",
            },
            clear=False,
        ):
            plan = planner.plan(
                run_context=RunContext.create(message=intent.raw_query),
                resolved_query=resolved_query,
            )
        self.assertEqual(plan.strategy, "capability")
        self.assertEqual(plan.capability_id, "empleados.count.active.v1")
        self.assertEqual(str((plan.constraints or {}).get("result_shape") or ""), "kpi")

    def test_query_execution_planner_selects_rrhh_capability_even_with_generic_template(self):
        planner = QueryExecutionPlanner()
        intent = StructuredQueryIntent(
            raw_query="¿Cuántos colaboradores habilitados tenemos hoy?",
            domain_code="empleados",
            operation="count",
            template_id="count_records_by_period",
            filters={"estado_empleado": "ACTIVO"},
            period={},
            group_by=[],
            metrics=["count"],
            confidence=0.9,
            source="rules",
        )
        resolved_query = ResolvedQuerySpec(
            intent=intent,
            semantic_context={
                "domain_status": "active",
                "supports_sql_assisted": False,
                "tables": [{"table_fqn": "bd_c3nc4s1s.cinco_base_de_personal", "table_name": "cinco_base_de_personal"}],
                "allowed_tables": ["cinco_base_de_personal", "bd_c3nc4s1s.cinco_base_de_personal"],
                "allowed_columns": ["estado", "cedula"],
            },
            normalized_filters={"estado_empleado": "ACTIVO"},
            normalized_period={"label": "hoy", "start_date": "2026-04-16", "end_date": "2026-04-16"},
            mapped_columns={"estado_empleado": "estado"},
        )
        with patch.dict(
            os.environ,
            {
                "IA_DEV_CAP_EMPLEADOS_ENABLED": "1",
                "IA_DEV_CAP_EMPLEADOS_COUNT_ENABLED": "1",
            },
            clear=False,
        ):
            run_context = RunContext.create(message="¿Cuántos colaboradores habilitados tenemos hoy?")
            plan = planner.plan(
                run_context=run_context,
                resolved_query=resolved_query,
            )
        self.assertEqual(plan.strategy, "capability")
        self.assertEqual(plan.capability_id, "empleados.count.active.v1")

    def test_query_execution_planner_selects_employee_capability_for_egresos_this_month(self):
        planner = QueryExecutionPlanner()
        intent = StructuredQueryIntent(
            raw_query="Egresos de este mes?",
            domain_code="empleados",
            operation="count",
            template_id="count_entities_by_status",
            filters={"estado": "INACTIVO"},
            period={"label": "mes_actual", "start_date": "2026-04-01", "end_date": "2026-04-23"},
            group_by=[],
            metrics=["count"],
            confidence=0.9,
            source="rules",
        )
        resolved_query = ResolvedQuerySpec(
            intent=intent,
            semantic_context={
                "domain_status": "active",
                "supports_sql_assisted": False,
                "tables": [{"table_fqn": "bd_c3nc4s1s.cinco_base_de_personal", "table_name": "cinco_base_de_personal"}],
                "allowed_tables": ["cinco_base_de_personal", "bd_c3nc4s1s.cinco_base_de_personal"],
                "allowed_columns": ["estado", "cedula", "fecha_egreso"],
                "resolved_semantic": {
                    "temporal_scope": {
                        "column_hint": "fecha_egreso",
                        "start_date": "2026-04-01",
                        "end_date": "2026-04-23",
                        "status_value": "INACTIVO",
                        "ambiguous": False,
                    }
                },
            },
            normalized_filters={"estado": "INACTIVO"},
            normalized_period={"label": "mes_actual", "start_date": "2026-04-01", "end_date": "2026-04-23"},
            mapped_columns={"estado": "estado"},
        )
        with patch.dict(
            os.environ,
            {
                "IA_DEV_CAP_EMPLEADOS_ENABLED": "1",
                "IA_DEV_CAP_EMPLEADOS_COUNT_ENABLED": "1",
            },
            clear=False,
        ):
            run_context = RunContext.create(message=intent.raw_query)
            plan = planner.plan(
                run_context=run_context,
                resolved_query=resolved_query,
            )
        self.assertEqual(plan.strategy, "capability")
        self.assertEqual(plan.capability_id, "empleados.count.active.v1")
        temporal_scope = dict((plan.constraints or {}).get("temporal_scope") or {})
        self.assertEqual(str(temporal_scope.get("column_hint") or ""), "fecha_egreso")

    def test_query_execution_planner_rescues_employee_turnover_even_if_operation_is_trend(self):
        planner = QueryExecutionPlanner()
        intent = StructuredQueryIntent(
            raw_query="Rotación de empelados de I&M",
            domain_code="empleados",
            operation="trend",
            template_id="trend_by_period",
            filters={"estado": "INACTIVO", "area": "I&M"},
            period={"label": "ultimo_mes_30_dias", "start_date": "2026-03-26", "end_date": "2026-04-24"},
            group_by=[],
            metrics=["turnover_rate", "count"],
            confidence=0.6,
            source="openai",
        )
        resolved_query = ResolvedQuerySpec(
            intent=intent,
            semantic_context={
                "domain_status": "active",
                "supports_sql_assisted": False,
                "tables": [{"table_fqn": "bd_c3nc4s1s.cinco_base_de_personal", "table_name": "cinco_base_de_personal"}],
                "allowed_tables": ["cinco_base_de_personal", "bd_c3nc4s1s.cinco_base_de_personal"],
                "allowed_columns": ["estado", "area", "fecha_ingreso", "fecha_egreso"],
            },
            normalized_filters={"estado": "INACTIVO", "area": "I&M"},
            normalized_period={"label": "ultimo_mes_30_dias", "start_date": "2026-03-26", "end_date": "2026-04-24"},
            mapped_columns={"estado": "estado", "area": "area"},
        )
        with patch.dict(
            os.environ,
            {
                "IA_DEV_CAP_EMPLEADOS_ENABLED": "1",
                "IA_DEV_CAP_EMPLEADOS_COUNT_ENABLED": "1",
            },
            clear=False,
        ):
            run_context = RunContext.create(message=intent.raw_query)
            plan = planner.plan(run_context=run_context, resolved_query=resolved_query)
        self.assertEqual(plan.strategy, "capability")
        self.assertEqual(plan.capability_id, "empleados.count.active.v1")

    def test_query_execution_planner_marks_grouped_employee_count_as_table(self):
        planner = QueryExecutionPlanner()
        intent = StructuredQueryIntent(
            raw_query="Cantidad de empleados activos por cargo",
            domain_code="empleados",
            operation="count",
            template_id="count_entities_by_status",
            filters={"estado": "ACTIVO"},
            period={},
            group_by=["cargo"],
            metrics=["count"],
            confidence=0.9,
            source="rules",
        )
        resolved_query = ResolvedQuerySpec(
            intent=intent,
            semantic_context={
                "domain_status": "active",
                "supports_sql_assisted": False,
                "tables": [{"table_fqn": "bd_c3nc4s1s.cinco_base_de_personal", "table_name": "cinco_base_de_personal"}],
                "allowed_tables": ["cinco_base_de_personal", "bd_c3nc4s1s.cinco_base_de_personal"],
                "allowed_columns": ["estado", "cedula", "cargo"],
            },
            normalized_filters={"estado": "ACTIVO"},
            normalized_period={},
            mapped_columns={"estado": "estado", "cargo": "cargo"},
        )
        with patch.dict(
            os.environ,
            {
                "IA_DEV_CAP_EMPLEADOS_ENABLED": "1",
                "IA_DEV_CAP_EMPLEADOS_COUNT_ENABLED": "1",
            },
            clear=False,
        ):
            run_context = RunContext.create(message="Cantidad de empleados activos por cargo")
            plan = planner.plan(
                run_context=run_context,
                resolved_query=resolved_query,
            )
        self.assertEqual(plan.strategy, "capability")
        self.assertEqual(plan.capability_id, "empleados.count.active.v1")
        self.assertEqual(str((plan.constraints or {}).get("result_shape") or ""), "table")

    def test_query_execution_planner_selects_employee_detail_capability_for_movil(self):
        planner = QueryExecutionPlanner()
        intent = StructuredQueryIntent(
            raw_query="informacion de TIRAN462",
            domain_code="empleados",
            operation="detail",
            template_id="detail_by_entity_and_period",
            filters={"movil": "TIRAN462"},
            period={},
            group_by=[],
            metrics=[],
            confidence=0.9,
            source="rules",
        )
        resolved_query = ResolvedQuerySpec(
            intent=intent,
            semantic_context={
                "domain_status": "active",
                "supports_sql_assisted": False,
                "tables": [{"table_fqn": "bd_c3nc4s1s.cinco_base_de_personal", "table_name": "cinco_base_de_personal"}],
                "allowed_tables": ["cinco_base_de_personal", "bd_c3nc4s1s.cinco_base_de_personal"],
                "allowed_columns": ["cedula", "movil", "cargo", "area", "estado"],
            },
            normalized_filters={"movil": "TIRAN462"},
            normalized_period={},
            mapped_columns={"movil": "movil"},
        )
        with patch.dict(
            os.environ,
            {
                "IA_DEV_CAP_EMPLEADOS_ENABLED": "1",
            },
            clear=False,
        ):
            run_context = RunContext.create(message="informacion de TIRAN462")
            plan = planner.plan(
                run_context=run_context,
                resolved_query=resolved_query,
            )
        self.assertEqual(plan.strategy, "capability")
        self.assertEqual(plan.capability_id, "empleados.detail.v1")

    def test_query_execution_planner_selects_attendance_by_attribute_for_tipo_labor(self):
        planner = QueryExecutionPlanner()
        intent = StructuredQueryIntent(
            raw_query="ausentismos por labor",
            domain_code="attendance",
            operation="aggregate",
            template_id="aggregate_by_group_and_period",
            filters={},
            period={},
            group_by=["tipo_labor"],
            metrics=["count"],
            confidence=0.9,
            source="rules",
        )
        resolved_query = ResolvedQuerySpec(
            intent=intent,
            semantic_context={
                "domain_status": "active",
                "supports_sql_assisted": False,
                "tables": [{"table_fqn": "bd_c3nc4s1s.gestionh_ausentismo", "table_name": "gestionh_ausentismo"}],
                "allowed_tables": ["gestionh_ausentismo"],
                "allowed_columns": ["cedula", "tipo_labor"],
            },
            normalized_filters={},
            normalized_period={},
            mapped_columns={"tipo_labor": "tipo_labor"},
        )
        with patch.dict(
            os.environ,
            {
                "IA_DEV_CAP_ATTENDANCE_ENABLED": "1",
                "IA_DEV_CAP_ATTENDANCE_ANALYTICS_ENABLED": "1",
            },
            clear=False,
        ):
            run_context = RunContext.create(message="ausentismos por labor")
            plan = planner.plan(
                run_context=run_context,
                resolved_query=resolved_query,
            )
        self.assertEqual(plan.strategy, "capability")
        self.assertEqual(plan.capability_id, "attendance.summary.by_attribute.v1")

    def test_query_execution_planner_prioritizes_attendance_detail_for_personal_en_vacaciones(self):
        planner = QueryExecutionPlanner()
        intent = StructuredQueryIntent(
            raw_query="personal en vacaciones del 2026-04-01 al 2026-04-19",
            domain_code="attendance",
            operation="detail",
            template_id="detail_by_entity_and_period",
            filters={"justificacion": "VACACIONES"},
            period={"label": "custom", "start_date": "2026-04-01", "end_date": "2026-04-19"},
            group_by=[],
            metrics=[],
            confidence=0.9,
            source="rules",
        )
        resolved_query = ResolvedQuerySpec(
            intent=intent,
            semantic_context={
                "domain_status": "active",
                "supports_sql_assisted": False,
                "tables": [
                    {"table_fqn": "bd_c3nc4s1s.gestionh_ausentismo", "table_name": "gestionh_ausentismo"},
                    {"table_fqn": "bd_c3nc4s1s.cinco_base_de_personal", "table_name": "cinco_base_de_personal"},
                ],
                "allowed_tables": ["gestionh_ausentismo", "cinco_base_de_personal"],
                "allowed_columns": ["cedula", "justificacion", "fecha_edit"],
            },
            normalized_filters={"justificacion": "VACACIONES"},
            normalized_period={"label": "custom", "start_date": "2026-04-01", "end_date": "2026-04-19"},
            mapped_columns={"justificacion": "justificacion"},
        )
        with patch.dict(
            os.environ,
            {
                "IA_DEV_CAP_ATTENDANCE_ENABLED": "1",
            },
            clear=False,
        ):
            run_context = RunContext.create(message=intent.raw_query)
            plan = planner.plan(
                run_context=run_context,
                resolved_query=resolved_query,
            )
        self.assertEqual(plan.strategy, "capability")
        self.assertEqual(plan.capability_id, "attendance.unjustified.table_with_personal.v1")

    def test_query_execution_planner_rescues_detail_for_empleados_en_vacaciones_even_if_upstream_marks_summary(self):
        planner = QueryExecutionPlanner()
        intent = StructuredQueryIntent(
            raw_query="empleados en vacaciones los ultimos 15 dias",
            domain_code="attendance",
            operation="summary",
            template_id="count_records_by_period",
            filters={"justificacion": "VACACIONES"},
            period={"label": "ultimos_15_dias", "start_date": "2026-04-05", "end_date": "2026-04-19"},
            group_by=[],
            metrics=["count"],
            confidence=0.72,
            source="openai",
        )
        resolved_query = ResolvedQuerySpec(
            intent=intent,
            semantic_context={
                "domain_status": "active",
                "supports_sql_assisted": False,
                "tables": [
                    {"table_fqn": "bd_c3nc4s1s.gestionh_ausentismo", "table_name": "gestionh_ausentismo"},
                    {"table_fqn": "bd_c3nc4s1s.cinco_base_de_personal", "table_name": "cinco_base_de_personal"},
                ],
                "allowed_tables": ["gestionh_ausentismo", "cinco_base_de_personal"],
                "allowed_columns": ["cedula", "justificacion", "fecha_edit"],
            },
            normalized_filters={"justificacion": "VACACIONES"},
            normalized_period={"label": "ultimos_15_dias", "start_date": "2026-04-05", "end_date": "2026-04-19"},
            mapped_columns={"justificacion": "justificacion"},
        )
        with patch.dict(
            os.environ,
            {
                "IA_DEV_CAP_ATTENDANCE_ENABLED": "1",
            },
            clear=False,
        ):
            run_context = RunContext.create(message=intent.raw_query)
            plan = planner.plan(
                run_context=run_context,
                resolved_query=resolved_query,
            )
        self.assertEqual(plan.strategy, "capability")
        self.assertEqual(plan.capability_id, "attendance.unjustified.table_with_personal.v1")

    def test_query_execution_planner_selects_capability_for_employee_grouped_aggregate(self):
        planner = QueryExecutionPlanner()
        intent = StructuredQueryIntent(
            raw_query="Cantidad de empleados activos por cargo",
            domain_code="empleados",
            operation="aggregate",
            template_id="aggregate_by_group_and_period",
            filters={"estado": "ACTIVO"},
            period={},
            group_by=["cargo"],
            metrics=["count"],
            confidence=0.9,
            source="openai",
        )
        resolved_query = ResolvedQuerySpec(
            intent=intent,
            semantic_context={
                "domain_status": "active",
                "supports_sql_assisted": False,
                "tables": [{"table_fqn": "bd_c3nc4s1s.cinco_base_de_personal", "table_name": "cinco_base_de_personal"}],
                "allowed_tables": ["cinco_base_de_personal", "bd_c3nc4s1s.cinco_base_de_personal"],
                "allowed_columns": ["estado", "cedula", "cargo"],
            },
            normalized_filters={"estado": "ACTIVO"},
            normalized_period={},
            mapped_columns={"estado": "estado", "cargo": "cargo"},
        )
        with patch.dict(
            os.environ,
            {
                "IA_DEV_CAP_EMPLEADOS_ENABLED": "1",
                "IA_DEV_CAP_EMPLEADOS_COUNT_ENABLED": "1",
            },
            clear=False,
        ):
            run_context = RunContext.create(message="Cantidad de empleados activos por cargo")
            plan = planner.plan(
                run_context=run_context,
                resolved_query=resolved_query,
            )
        self.assertEqual(plan.strategy, "capability")
        self.assertEqual(plan.capability_id, "empleados.count.active.v1")
        self.assertEqual(list((plan.constraints or {}).get("group_by") or []), ["cargo"])

    def test_query_execution_planner_routes_recurrent_attendance_to_recurrence_capability(self):
        planner = QueryExecutionPlanner()
        intent = StructuredQueryIntent(
            raw_query="Reincidentes del ultimo mes de Implementacio",
            domain_code="ausentismo",
            operation="aggregate",
            template_id="aggregate_by_group_and_period",
            filters={"indicador_ausentismo": "SI", "estado": "ACTIVO"},
            period={"label": "ultimo_mes_30_dias", "start_date": "2026-03-26", "end_date": "2026-04-24"},
            group_by=[],
            metrics=["count"],
            confidence=0.75,
            source="openai",
        )
        resolved_query = ResolvedQuerySpec(
            intent=intent,
            semantic_context={
                "domain_status": "active",
                "tables": [{"table_name": "gestionh_ausentismo"}],
                "allowed_tables": ["gestionh_ausentismo"],
                "allowed_columns": ["ausentismo", "fecha_edit", "cedula"],
            },
            normalized_filters={"indicador_ausentismo": "SI", "estado": "ACTIVO"},
            normalized_period={"label": "ultimo_mes_30_dias", "start_date": "2026-03-26", "end_date": "2026-04-24"},
            mapped_columns={"indicador_ausentismo": "ausentismo"},
        )
        with patch.dict(
            os.environ,
            {
                "IA_DEV_CAP_ATTENDANCE_ENABLED": "1",
                "IA_DEV_CAP_ATTENDANCE_RECURRENCE_ENABLED": "1",
            },
            clear=False,
        ):
            plan = planner.plan(
                run_context=RunContext.create(message=intent.raw_query),
                resolved_query=resolved_query,
            )
        self.assertEqual(plan.strategy, "capability")
        self.assertEqual(plan.capability_id, "attendance.recurrence.grouped.v1")

    def test_query_execution_planner_general_domain_uses_fallback_not_ask_context(self):
        planner = QueryExecutionPlanner()
        intent = StructuredQueryIntent(
            raw_query="3 personajes de juego de tronos",
            domain_code="general",
            operation="detail",
            template_id="detail_by_entity_and_period",
            filters={},
            period={"label": "hoy", "start_date": "2026-04-18", "end_date": "2026-04-18"},
            group_by=[],
            metrics=["count"],
            confidence=0.7,
            source="openai",
        )
        resolved_query = ResolvedQuerySpec(
            intent=intent,
            semantic_context={
                "domain_status": "planned",
                "supports_sql_assisted": False,
                "tables": [],
                "allowed_tables": [],
                "allowed_columns": [],
            },
            normalized_filters={},
            normalized_period={"label": "hoy", "start_date": "2026-04-18", "end_date": "2026-04-18"},
            mapped_columns={},
        )
        run_context = RunContext.create(message="3 personajes de juego de tronos")
        plan = planner.plan(
            run_context=run_context,
            resolved_query=resolved_query,
        )
        self.assertEqual(plan.strategy, "fallback")
        self.assertEqual(plan.reason, "general_domain_conversational_fallback")

    def test_query_execution_policy_rejects_unsafe_sql(self):
        policy = QueryExecutionPolicy()
        decision = policy.validate_sql_query(
            query="UPDATE tabla SET a = 1 LIMIT 1",
            allowed_tables=["tabla"],
            allowed_columns=["a"],
            max_limit=100,
        )
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, "sql_must_start_with_select")

    def test_query_execution_policy_allows_json_table_when_declared_columns_are_safe(self):
        policy = QueryExecutionPolicy()
        decision = policy.validate_sql_query(
            query=(
                "SELECT COUNT(*) AS total FROM bd_c3nc4s1s.cinco_base_de_personal AS e "
                "JOIN JSON_TABLE(e.datos, '$.certificados_alturas[*]' "
                "COLUMNS(tipo VARCHAR(50) PATH '$.tipo', fecha VARCHAR(20) PATH '$.fecha')) AS jt "
                "ON jt.tipo = 'alturas' WHERE e.estado = 'ACTIVO' LIMIT 1"
            ),
            allowed_tables=["bd_c3nc4s1s.cinco_base_de_personal"],
            allowed_columns=["datos", "estado"],
            declared_columns=["datos", "estado"],
            max_limit=100,
        )
        self.assertTrue(decision.allowed)

    def test_query_execution_planner_routes_heights_certificate_summary_to_sql_assisted(self):
        planner = QueryExecutionPlanner()
        intent = StructuredQueryIntent(
            raw_query="si el certificado de alturas vence cada año, cuántos certificados están vencidos y cuántos certificados están próximos a vencer, solo personal activo y tipo de labor operativo",
            domain_code="empleados",
            operation="count",
            template_id="count_entities_by_status",
            filters={"estado_empleado": "ACTIVO", "tipo_labor": "OPERATIVO"},
            period={},
            group_by=[],
            metrics=["count"],
            confidence=0.94,
            source="rules",
        )
        resolved_query = ResolvedQuerySpec(
            intent=intent,
            semantic_context={
                "domain_status": "active",
                "supports_sql_assisted": True,
                "tables": [{"table_fqn": "bd_c3nc4s1s.cinco_base_de_personal", "table_name": "cinco_base_de_personal"}],
                "allowed_tables": ["cinco_base_de_personal", "bd_c3nc4s1s.cinco_base_de_personal"],
                "allowed_columns": ["datos", "estado", "tipo_labor"],
                "dictionary": {
                    "rules": [
                        {"codigo": "certificado_alturas_vigencia_anual"},
                        {"codigo": "certificado_alturas_vencido"},
                        {"codigo": "certificado_alturas_proximo_vencer_30_dias"},
                        {"codigo": "personal_activo_operativo"},
                    ]
                },
                "column_profiles": [
                    {"table_name": "cinco_base_de_personal", "logical_name": "estado_empleado", "column_name": "estado", "supports_filter": True, "allowed_values": ["ACTIVO", "INACTIVO"]},
                    {"table_name": "cinco_base_de_personal", "logical_name": "tipo_labor", "column_name": "tipo_labor", "supports_filter": True, "allowed_values": ["OPERATIVO", "ADMINISTRATIVO"]},
                    {
                        "table_name": "cinco_base_de_personal",
                        "logical_name": "certificado_alturas_fecha_emision",
                        "column_name": "datos",
                        "supports_filter": True,
                        "is_date": True,
                        "definicion_negocio": "Fuente oficial. [json_path=$.certificados_alturas[*]][json_filter_tipo=alturas][json_date_key=fecha][fallback_column=calturas]",
                    },
                ],
                "resolved_semantic": {
                    "field_match": {
                        "logical_name": "certificado_alturas_fecha_emision",
                        "semantic_role": "heights_certificate_validity",
                        "business_concepts": ["certificate", "expiration"],
                    }
                },
                "source_of_truth": {"pilot_sql_assisted_enabled": True},
            },
            normalized_filters={"estado_empleado": "ACTIVO", "tipo_labor": "OPERATIVO"},
            normalized_period={},
            mapped_columns={"estado_empleado": "estado", "tipo_labor": "tipo_labor"},
        )
        with patch.dict(
            os.environ,
            {
                "IA_DEV_CAP_EMPLEADOS_ENABLED": "1",
                "IA_DEV_QUERY_SQL_ASSISTED_ENABLED": "1",
                "IA_DEV_QUERY_INTELLIGENCE_ENABLED": "1",
                "IA_DEV_ATTENDANCE_EMPLOYEES_PILOT_ENABLED": "1",
            },
            clear=False,
        ):
            plan = planner.plan(
                run_context=RunContext.create(message=intent.raw_query, session_id="heights-sql", reset_memory=False),
                resolved_query=resolved_query,
            )
        self.assertEqual(plan.strategy, "sql_assisted")
        self.assertIn("JSON_TABLE", str(plan.sql_query or ""))
        self.assertIn("e.estado = 'ACTIVO'", str(plan.sql_query or ""))
        self.assertIn("e.tipo_labor = 'OPERATIVO'", str(plan.sql_query or ""))
        self.assertEqual(str((plan.metadata or {}).get("compiler") or ""), "employee_semantic_sql")
        self.assertEqual(str((plan.metadata or {}).get("metric_used") or ""), "certificado_alturas_vigencia")
        self.assertEqual(str((plan.constraints or {}).get("result_shape") or ""), "kpi")
        self.assertFalse(bool((plan.constraints or {}).get("chart_requested")))

    def test_query_execution_planner_prioritizes_employee_group_by_over_generic_count_template(self):
        planner = QueryExecutionPlanner()
        intent = StructuredQueryIntent(
            raw_query="Cuantos empleados activos hay y como se distribuyen por tipo de labor",
            domain_code="empleados",
            operation="count",
            template_id="count_entities_by_status",
            filters={"estado": "ACTIVO"},
            period={},
            group_by=["tipo_labor"],
            metrics=["count"],
            confidence=0.9,
            source="rules",
        )
        resolved_query = ResolvedQuerySpec(
            intent=intent,
            semantic_context={
                "domain_status": "active",
                "supports_sql_assisted": True,
                "tables": [{"table_fqn": "bd_c3nc4s1s.cinco_base_de_personal", "table_name": "cinco_base_de_personal"}],
                "columns": [{"column_name": "estado"}, {"column_name": "tipo_labor"}],
                "column_profiles": [
                    {"table_name": "cinco_base_de_personal", "logical_name": "estado", "column_name": "estado", "supports_filter": True, "allowed_values": ["ACTIVO", "INACTIVO"]},
                    {"table_name": "cinco_base_de_personal", "logical_name": "tipo_labor", "column_name": "tipo_labor", "supports_group_by": True, "supports_filter": True},
                ],
                "allowed_tables": ["cinco_base_de_personal", "bd_c3nc4s1s.cinco_base_de_personal"],
                "allowed_columns": ["estado", "tipo_labor"],
                "aliases": {"tipo_labor": "tipo_labor"},
                "source_of_truth": {"pilot_sql_assisted_enabled": True},
            },
            normalized_filters={"estado": "ACTIVO"},
            normalized_period={},
            mapped_columns={"estado": "estado", "tipo_labor": "tipo_labor"},
        )
        with patch.dict(
            os.environ,
            {
                "IA_DEV_CAP_EMPLEADOS_ENABLED": "1",
                "IA_DEV_QUERY_SQL_ASSISTED_ENABLED": "1",
                "IA_DEV_QUERY_INTELLIGENCE_ENABLED": "1",
                "IA_DEV_ATTENDANCE_EMPLOYEES_PILOT_ENABLED": "1",
            },
            clear=False,
        ):
            plan = planner.plan(
                run_context=RunContext.create(message=intent.raw_query, session_id="employee-group-by", reset_memory=False),
                resolved_query=resolved_query,
            )
        self.assertEqual(plan.strategy, "sql_assisted")
        self.assertIn("GROUP BY tipo_labor", str(plan.sql_query or ""))
        self.assertNotIn("LIMIT 1", str(plan.sql_query or ""))
        self.assertEqual(str((plan.metadata or {}).get("compiler") or ""), "employee_semantic_sql")

    def test_query_execution_planner_keeps_all_employee_group_dimensions(self):
        planner = QueryExecutionPlanner()
        intent = StructuredQueryIntent(
            raw_query="Personal activo por area y carpeta",
            domain_code="empleados",
            operation="count",
            template_id="aggregate_by_group_and_period",
            filters={"estado": "ACTIVO"},
            period={},
            group_by=["area", "carpeta"],
            metrics=["count"],
            confidence=0.91,
            source="rules",
        )
        resolved_query = ResolvedQuerySpec(
            intent=intent,
            semantic_context={
                "domain_status": "active",
                "supports_sql_assisted": True,
                "tables": [{"table_fqn": "bd_c3nc4s1s.cinco_base_de_personal", "table_name": "cinco_base_de_personal"}],
                "columns": [{"column_name": "estado"}, {"column_name": "area"}, {"column_name": "carpeta"}],
                "column_profiles": [
                    {"table_name": "cinco_base_de_personal", "logical_name": "estado", "column_name": "estado", "supports_filter": True, "allowed_values": ["ACTIVO", "INACTIVO"]},
                    {"table_name": "cinco_base_de_personal", "logical_name": "area", "column_name": "area", "supports_group_by": True, "supports_filter": True},
                    {"table_name": "cinco_base_de_personal", "logical_name": "carpeta", "column_name": "carpeta", "supports_group_by": True, "supports_filter": True},
                ],
                "allowed_tables": ["cinco_base_de_personal", "bd_c3nc4s1s.cinco_base_de_personal"],
                "allowed_columns": ["estado", "area", "carpeta"],
                "aliases": {"area": "area", "carpeta": "carpeta"},
                "source_of_truth": {"pilot_sql_assisted_enabled": True},
            },
            normalized_filters={"estado": "ACTIVO"},
            normalized_period={},
            mapped_columns={"estado": "estado", "area": "area", "carpeta": "carpeta"},
        )
        with patch.dict(
            os.environ,
            {
                "IA_DEV_CAP_EMPLEADOS_ENABLED": "1",
                "IA_DEV_QUERY_SQL_ASSISTED_ENABLED": "1",
                "IA_DEV_QUERY_INTELLIGENCE_ENABLED": "1",
                "IA_DEV_ATTENDANCE_EMPLOYEES_PILOT_ENABLED": "1",
            },
            clear=False,
        ):
            plan = planner.plan(
                run_context=RunContext.create(message=intent.raw_query, session_id="employee-group-by-multi", reset_memory=False),
                resolved_query=resolved_query,
            )
        self.assertEqual(plan.strategy, "sql_assisted")
        self.assertIn("SELECT area AS area, carpeta AS carpeta, COUNT(*) AS total_registros", str(plan.sql_query or ""))
        self.assertIn("GROUP BY area, carpeta", str(plan.sql_query or ""))
        self.assertEqual(list((plan.metadata or {}).get("dimensions_used") or []), ["area", "carpeta"])
        self.assertEqual(str((plan.metadata or {}).get("compiler") or ""), "employee_semantic_sql")

    def test_query_execution_planner_does_not_emit_unregistered_alias_as_group_column(self):
        planner = QueryExecutionPlanner()
        intent = StructuredQueryIntent(
            raw_query="Distribuye el personal activo por tipo de labor",
            domain_code="empleados",
            operation="aggregate",
            template_id="aggregate_by_group_and_period",
            filters={"estado": "ACTIVO"},
            period={},
            group_by=["tipo_labor"],
            metrics=["count"],
            confidence=0.91,
            source="rules",
        )
        resolved_query = ResolvedQuerySpec(
            intent=intent,
            semantic_context={
                "domain_status": "active",
                "supports_sql_assisted": True,
                "tables": [{"table_fqn": "bd_c3nc4s1s.cinco_base_de_personal", "table_name": "cinco_base_de_personal"}],
                "columns": [{"column_name": "estado"}, {"column_name": "tipo_labor"}],
                "column_profiles": [
                    {"table_name": "cinco_base_de_personal", "logical_name": "estado", "column_name": "estado", "supports_filter": True, "allowed_values": ["ACTIVO", "INACTIVO"]},
                    {"table_name": "cinco_base_de_personal", "logical_name": "tipo_labor", "column_name": "tipo_labor", "supports_group_by": True, "supports_filter": True},
                ],
                "allowed_tables": ["cinco_base_de_personal", "bd_c3nc4s1s.cinco_base_de_personal"],
                "allowed_columns": ["estado", "tipo_labor"],
                "aliases": {"tipo_labor": "tipo"},
                "source_of_truth": {"pilot_sql_assisted_enabled": True},
            },
            normalized_filters={"estado": "ACTIVO"},
            normalized_period={},
            mapped_columns={"estado": "estado", "tipo_labor": "tipo_labor"},
        )
        with patch.dict(
            os.environ,
            {
                "IA_DEV_CAP_EMPLEADOS_ENABLED": "1",
                "IA_DEV_QUERY_SQL_ASSISTED_ENABLED": "1",
                "IA_DEV_QUERY_INTELLIGENCE_ENABLED": "1",
                "IA_DEV_ATTENDANCE_EMPLOYEES_PILOT_ENABLED": "1",
            },
            clear=False,
        ):
            plan = planner.plan(
                run_context=RunContext.create(message=intent.raw_query, session_id="employee-group-alias-safe", reset_memory=False),
                resolved_query=resolved_query,
            )
        self.assertEqual(plan.strategy, "sql_assisted")
        self.assertIn("SELECT tipo_labor AS tipo_labor, COUNT(*) AS total_registros", str(plan.sql_query or ""))
        self.assertIn("GROUP BY tipo_labor", str(plan.sql_query or ""))
        self.assertNotIn("GROUP BY tipo ORDER BY", str(plan.sql_query or ""))

    def test_query_execution_planner_heights_certificate_uses_calturas_fallback_when_json_path_missing(self):
        planner = QueryExecutionPlanner()
        intent = StructuredQueryIntent(
            raw_query="certificado de alturas vencidos del personal activo operativo",
            domain_code="empleados",
            operation="count",
            template_id="count_entities_by_status",
            filters={"estado": "ACTIVO", "tipo_labor": "OPERATIVO"},
            metrics=["count"],
            confidence=0.9,
            source="rules",
        )
        resolved_query = ResolvedQuerySpec(
            intent=intent,
            semantic_context={
                "domain_status": "active",
                "supports_sql_assisted": True,
                "tables": [{"table_fqn": "bd_c3nc4s1s.cinco_base_de_personal", "table_name": "cinco_base_de_personal"}],
                "allowed_tables": ["bd_c3nc4s1s.cinco_base_de_personal"],
                "allowed_columns": ["calturas", "estado", "tipo_labor"],
                "dictionary": {
                    "rules": [
                        {"codigo": "certificado_alturas_vigencia_anual"},
                        {"codigo": "certificado_alturas_vencido"},
                        {"codigo": "certificado_alturas_proximo_vencer_30_dias"},
                        {"codigo": "personal_activo_operativo"},
                    ]
                },
                "column_profiles": [
                    {"table_name": "cinco_base_de_personal", "logical_name": "estado_empleado", "column_name": "estado", "supports_filter": True, "allowed_values": ["ACTIVO", "INACTIVO"]},
                    {"table_name": "cinco_base_de_personal", "logical_name": "tipo_labor", "column_name": "tipo_labor", "supports_filter": True, "allowed_values": ["OPERATIVO", "ADMINISTRATIVO"]},
                    {
                        "table_name": "cinco_base_de_personal",
                        "logical_name": "certificado_alturas_fecha_emision",
                        "column_name": "calturas",
                        "supports_filter": True,
                        "is_date": True,
                        "definicion_negocio": "Fallback controlado para alturas.",
                    },
                ],
                "resolved_semantic": {
                    "field_match": {
                        "logical_name": "certificado_alturas_fecha_emision",
                        "semantic_role": "heights_certificate_validity",
                    }
                },
                "source_of_truth": {"pilot_sql_assisted_enabled": True},
            },
            normalized_filters={"estado": "ACTIVO", "tipo_labor": "OPERATIVO"},
            mapped_columns={"estado": "estado", "tipo_labor": "tipo_labor"},
        )
        with patch.dict(
            os.environ,
            {
                "IA_DEV_QUERY_SQL_ASSISTED_ENABLED": "1",
                "IA_DEV_QUERY_INTELLIGENCE_ENABLED": "1",
                "IA_DEV_ATTENDANCE_EMPLOYEES_PILOT_ENABLED": "1",
            },
            clear=False,
        ):
            plan = planner.plan(
                run_context=RunContext.create(message=intent.raw_query, session_id="heights-fallback", reset_memory=False),
                resolved_query=resolved_query,
            )
        self.assertEqual(plan.strategy, "sql_assisted")
        self.assertIn("DATE(e.calturas)", str(plan.sql_query or ""))
        self.assertEqual(str((plan.metadata or {}).get("source_mode") or ""), "fallback_calturas")

    def test_query_execution_planner_heights_certificate_prefers_table_covering_required_columns(self):
        planner = QueryExecutionPlanner()
        intent = StructuredQueryIntent(
            raw_query="certificados de alturas vencidos del personal activo operativo",
            domain_code="empleados",
            operation="count",
            template_id="count_entities_by_status",
            filters={"estado_empleado": "ACTIVO", "tipo_labor": "OPERATIVO"},
            metrics=["count"],
            confidence=0.9,
            source="rules",
        )
        resolved_query = ResolvedQuerySpec(
            intent=intent,
            semantic_context={
                "domain_status": "active",
                "supports_sql_assisted": True,
                "tables": [
                    {"schema_name": "cincosas_cincosas", "table_fqn": "cincosas_cincosas.cinco_base_de_personal", "table_name": "cinco_base_de_personal"},
                    {"schema_name": "bd_c3nc4s1s", "table_fqn": "bd_c3nc4s1s.cinco_base_de_personal", "table_name": "cinco_base_de_personal"},
                ],
                "allowed_tables": [
                    "cincosas_cincosas.cinco_base_de_personal",
                    "bd_c3nc4s1s.cinco_base_de_personal",
                ],
                "allowed_columns": ["datos", "calturas", "estado", "tipo_labor"],
                "dictionary": {
                    "rules": [
                        {"codigo": "certificado_alturas_vigencia_anual"},
                        {"codigo": "certificado_alturas_vencido"},
                        {"codigo": "certificado_alturas_proximo_vencer_30_dias"},
                        {"codigo": "personal_activo_operativo"},
                    ],
                    "fields": [
                        {
                            "schema_name": "bd_c3nc4s1s",
                            "table_name": "cinco_base_de_personal",
                            "table_fqn": "bd_c3nc4s1s.cinco_base_de_personal",
                            "campo_logico": "certificado_alturas_fecha_emision",
                            "column_name": "datos",
                            "definicion_negocio": "Fuente oficial. [json_path=$.certificados_alturas[*]][json_filter_tipo=alturas][json_date_key=fecha][fallback_column=calturas]",
                        }
                    ],
                },
                "column_profiles": [
                    {"schema_name": "cincosas_cincosas", "table_name": "cinco_base_de_personal", "table_fqn": "cincosas_cincosas.cinco_base_de_personal", "logical_name": "estado_empleado", "column_name": "estado", "supports_filter": True, "allowed_values": ["ACTIVO", "INACTIVO"]},
                    {"schema_name": "bd_c3nc4s1s", "table_name": "cinco_base_de_personal", "table_fqn": "bd_c3nc4s1s.cinco_base_de_personal", "logical_name": "estado_empleado", "column_name": "estado", "supports_filter": True, "allowed_values": ["ACTIVO", "INACTIVO"]},
                    {"schema_name": "bd_c3nc4s1s", "table_name": "cinco_base_de_personal", "table_fqn": "bd_c3nc4s1s.cinco_base_de_personal", "logical_name": "tipo_labor", "column_name": "tipo_labor", "supports_filter": True, "allowed_values": ["OPERATIVO", "ADMINISTRATIVO"]},
                    {"schema_name": "bd_c3nc4s1s", "table_name": "cinco_base_de_personal", "table_fqn": "bd_c3nc4s1s.cinco_base_de_personal", "logical_name": "certificado_alturas_fecha_emision", "column_name": "datos", "supports_filter": True, "is_date": True, "definicion_negocio": "Fuente oficial. [json_path=$.certificados_alturas[*]][json_filter_tipo=alturas][json_date_key=fecha][fallback_column=calturas]"},
                    {"schema_name": "bd_c3nc4s1s", "table_name": "cinco_base_de_personal", "table_fqn": "bd_c3nc4s1s.cinco_base_de_personal", "logical_name": "certificado_alturas_fallback", "column_name": "calturas", "supports_filter": True, "is_date": True},
                ],
                "resolved_semantic": {
                    "field_match": {
                        "logical_name": "certificado_alturas_fecha_emision",
                        "semantic_role": "heights_certificate_validity",
                    }
                },
                "source_of_truth": {"pilot_sql_assisted_enabled": True},
            },
            normalized_filters={"estado_empleado": "ACTIVO", "tipo_labor": "OPERATIVO"},
            mapped_columns={"estado_empleado": "estado", "tipo_labor": "tipo_labor"},
        )
        with patch.dict(
            os.environ,
            {
                "IA_DEV_QUERY_SQL_ASSISTED_ENABLED": "1",
                "IA_DEV_QUERY_INTELLIGENCE_ENABLED": "1",
                "IA_DEV_ATTENDANCE_EMPLOYEES_PILOT_ENABLED": "1",
            },
            clear=False,
        ):
            plan = planner.plan(
                run_context=RunContext.create(message=intent.raw_query, session_id="heights-prefers-bd", reset_memory=False),
                resolved_query=resolved_query,
            )
        self.assertEqual(plan.strategy, "sql_assisted")
        self.assertIn("FROM bd_c3nc4s1s.cinco_base_de_personal AS e", str(plan.sql_query or ""))
        self.assertNotIn("FROM cincosas_cincosas.cinco_base_de_personal AS e", str(plan.sql_query or ""))
        self.assertIn("JSON_TABLE(e.datos", str(plan.sql_query or ""))

    def test_query_execution_planner_heights_certificate_does_not_use_cer_alturas_as_date_source(self):
        planner = QueryExecutionPlanner()
        intent = StructuredQueryIntent(
            raw_query="certificados de alturas vencidos del personal activo operativo",
            domain_code="empleados",
            operation="count",
            template_id="count_entities_by_status",
            filters={"estado": "ACTIVO", "tipo_labor": "OPERATIVO"},
            metrics=["count"],
            confidence=0.9,
            source="rules",
        )
        resolved_query = ResolvedQuerySpec(
            intent=intent,
            semantic_context={
                "domain_status": "active",
                "supports_sql_assisted": True,
                "tables": [{"table_fqn": "bd_c3nc4s1s.cinco_base_de_personal", "table_name": "cinco_base_de_personal"}],
                "allowed_tables": ["bd_c3nc4s1s.cinco_base_de_personal"],
                "allowed_columns": ["cer_alturas", "estado", "tipo_labor"],
                "dictionary": {
                    "rules": [
                        {"codigo": "certificado_alturas_vigencia_anual"},
                        {"codigo": "certificado_alturas_vencido"},
                        {"codigo": "certificado_alturas_proximo_vencer_30_dias"},
                        {"codigo": "personal_activo_operativo"},
                    ]
                },
                "column_profiles": [
                    {"table_name": "cinco_base_de_personal", "logical_name": "estado_empleado", "column_name": "estado", "supports_filter": True, "allowed_values": ["ACTIVO", "INACTIVO"]},
                    {"table_name": "cinco_base_de_personal", "logical_name": "tipo_labor", "column_name": "tipo_labor", "supports_filter": True, "allowed_values": ["OPERATIVO", "ADMINISTRATIVO"]},
                    {"table_name": "cinco_base_de_personal", "logical_name": "certificado_alturas_fecha_emision", "column_name": "cer_alturas", "supports_filter": True, "definicion_negocio": "Fuente invalida para fecha."},
                ],
                "resolved_semantic": {
                    "field_match": {
                        "logical_name": "certificado_alturas_fecha_emision",
                        "semantic_role": "heights_certificate_validity",
                    }
                },
                "source_of_truth": {"pilot_sql_assisted_enabled": True},
            },
            normalized_filters={"estado": "ACTIVO", "tipo_labor": "OPERATIVO"},
            mapped_columns={"estado": "estado", "tipo_labor": "tipo_labor"},
        )
        with patch.dict(
            os.environ,
            {
                "IA_DEV_QUERY_SQL_ASSISTED_ENABLED": "1",
                "IA_DEV_QUERY_INTELLIGENCE_ENABLED": "1",
                "IA_DEV_ATTENDANCE_EMPLOYEES_PILOT_ENABLED": "1",
            },
            clear=False,
        ):
            plan = planner.plan(
                run_context=RunContext.create(message=intent.raw_query, session_id="heights-no-cer", reset_memory=False),
                resolved_query=resolved_query,
            )
        self.assertEqual(plan.strategy, "fallback")
        self.assertEqual(plan.reason, "sql_rejected:sql_uses_unregistered_column")

    def test_result_satisfaction_validator_detects_cedula_mismatch(self):
        validator = ResultSatisfactionValidator()
        response = {
            "reply": "Detalle de ausentismos del periodo 2025-04-14 al 2026-04-13",
            "data": {
                "kpis": {},
                "table": {
                    "columns": ["cedula"],
                    "rows": [{"cedula": "1000087030"}, {"cedula": "1011510709"}],
                    "rowcount": 2,
                },
            },
        }
        validation = validator.validate(
            message="Ausentismos del ultimo ano del empleado 1055837370",
            response=response,
            resolved_query=None,
        )
        self.assertFalse(validation.satisfied)
        self.assertEqual(validation.reason, "entity_filter_not_applied_for_cedula")

    def test_result_satisfaction_validator_detects_group_count_not_aggregated(self):
        validator = ResultSatisfactionValidator()
        response = {
            "reply": "Detalle de ausentismos del periodo 2026-03-30 al 2026-04-13",
            "data": {
                "kpis": {"total_ausentismos": 150},
                "table": {
                    "columns": ["cedula", "fecha_ausentismo", "supervisor"],
                    "rows": [
                        {"cedula": "1000087030", "fecha_ausentismo": "2026-04-13", "supervisor": "A"},
                        {"cedula": "1011510709", "fecha_ausentismo": "2026-04-13", "supervisor": "B"},
                    ],
                    "rowcount": 2,
                },
            },
        }
        validation = validator.validate(
            message="Cantidad de ausentismos por supervisor los ultimos 15 dias",
            response=response,
            resolved_query=None,
        )
        self.assertFalse(validation.satisfied)
        self.assertEqual(validation.reason, "group_count_requested_but_result_is_not_aggregated")

    def test_result_satisfaction_validator_accepts_grouped_count_with_generic_numeric_alias(self):
        validator = ResultSatisfactionValidator()
        response = {
            "reply": "Personal activo agrupado por area.",
            "data": {
                "kpis": {"rowcount": 3},
                "table": {
                    "columns": ["area", "total_registros"],
                    "rows": [
                        {"area": "OPERACIONES", "total_registros": 120},
                        {"area": "MANTENIMIENTO", "total_registros": 87},
                    ],
                    "rowcount": 2,
                },
            },
        }
        validation = validator.validate(
            message="Cantidad de personal activo por area",
            response=response,
            resolved_query=None,
        )
        self.assertTrue(validation.satisfied)
        self.assertEqual(validation.reason, "ok")

    def test_result_satisfaction_validator_respects_explicit_empty_group_by_from_planner_for_heights_kpi(self):
        validator = ResultSatisfactionValidator()
        resolved_query = ResolvedQuerySpec(
            intent=StructuredQueryIntent(
                raw_query="si el certificado de alturas vence cada ano, cuantos certificados estan vencidos y cuantos certificados estan proximos a vencer, solo personal activo y tipo de labor operativo",
                domain_code="empleados",
                operation="aggregate",
                template_id="aggregate_by_group_and_period",
                filters={"estado_empleado": "ACTIVO", "tipo_labor": "OPERATIVO"},
                group_by=["area"],
                metrics=["count"],
                confidence=0.94,
                source="rules",
            ),
            normalized_filters={"estado_empleado": "ACTIVO", "tipo_labor": "OPERATIVO"},
        )
        execution_plan = QueryExecutionPlan(
            strategy="sql_assisted",
            reason="sql_assisted_ready",
            domain_code="empleados",
            constraints={
                "filters": {"estado_empleado": "ACTIVO", "tipo_labor": "OPERATIVO"},
                "group_by": [],
                "result_shape": "kpi",
                "operation": "count",
            },
            metadata={"compiler": "employee_semantic_sql", "metric_used": "certificado_alturas_vigencia"},
        )
        response = {
            "reply": "312 certificados de alturas vencidos y 52 proximos a vencer en personal activo de labor operativa.",
            "data": {
                "kpis": {
                    "certificados_vencidos": 312,
                    "certificados_proximos_vencer": 52,
                },
                "table": {
                    "columns": ["certificados_vencidos", "certificados_proximos_vencer"],
                    "rows": [{"certificados_vencidos": 312, "certificados_proximos_vencer": 52}],
                    "rowcount": 1,
                },
            },
        }
        validation = validator.validate(
            message=resolved_query.intent.raw_query,
            response=response,
            resolved_query=resolved_query,
            execution_plan=execution_plan,
        )
        self.assertTrue(validation.satisfied)
        self.assertEqual(validation.reason, "ok")
        self.assertEqual(list(validation.checks.get("expected_group_by") or []), [])

    def test_query_shape_key_generalizes_birthday_month_queries(self):
        first = QueryIntentResolver._build_query_shape_key("Cumpleaños de mayo")
        second = QueryIntentResolver._build_query_shape_key("Cumpleaños de junio")
        self.assertEqual(first, second)
        self.assertIn("<mes>", first)
