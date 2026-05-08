from __future__ import annotations

import os
from dataclasses import dataclass
from unittest.mock import Mock, patch

from django.test import SimpleTestCase

from apps.ia_dev.application.contracts.query_intelligence_contracts import (
    ResolvedQuerySpec,
    StructuredQueryIntent,
)
from apps.ia_dev.application.context.run_context import RunContext
from apps.ia_dev.application.semantic.query_execution_planner import QueryExecutionPlanner
from apps.ia_dev.application.semantic.query_intent_resolver import QueryIntentResolver
from apps.ia_dev.application.semantic.column_semantic_resolver import (
    ColumnSemanticResolver,
)
from apps.ia_dev.application.semantic.relation_semantic_resolver import (
    RelationSemanticResolver,
)
from apps.ia_dev.application.semantic.rule_semantic_resolver import RuleSemanticResolver
from apps.ia_dev.application.semantic.semantic_business_resolver import (
    SemanticBusinessResolver,
)
from apps.ia_dev.application.semantic.synonym_semantic_resolver import (
    SynonymSemanticResolver,
)
from apps.ia_dev.services.ai_dictionary_remediation_service import (
    AIDictionaryRemediationService,
)


@dataclass
class _FakeDomain:
    raw_context: dict
    domain_status: str = "active"
    maturity_level: str = "mature"
    schema_confidence: float = 0.95
    main_entity: str = "empleado"
    business_goal: str = "analytics"


class _FakeRegistry:
    def __init__(self, domain: _FakeDomain):
        self._domain = domain

    @staticmethod
    def normalize_domain_code(value: str | None) -> str:
        return str(value or "").strip().lower() or "empleados"

    def get_domain(self, domain_code: str | None):
        return self._domain


class _DualRegistry(_FakeRegistry):
    def __init__(self, *, primary_domain: _FakeDomain, employee_domain: _FakeDomain):
        super().__init__(primary_domain)
        self._primary_domain = primary_domain
        self._employee_domain = employee_domain

    def get_domain(self, domain_code: str | None):
        normalized = self.normalize_domain_code(domain_code)
        if normalized == "empleados":
            return self._employee_domain
        return self._primary_domain


class _FakeDictionaryTool:
    @staticmethod
    def get_domain_context(domain: str, *, limit: int = 20) -> dict:
        normalized = str(domain or "").strip().lower()
        if normalized in {"ausentismo", "attendance"}:
            return {
                "domain": {"id": 2, "code": "AUSENTISMO", "matched": True},
                "tables": [
                    {
                        "id": 10,
                        "schema_name": "cincosas_cincosas",
                        "table_name": "gestionh_ausentismo",
                    },
                    {
                        "id": 11,
                        "schema_name": "cincosas_cincosas",
                        "table_name": "cinco_base_de_personal",
                    },
                ],
                "fields": [
                    {
                        "table_name": "gestionh_ausentismo",
                        "campo_logico": "fecha_ausentismo",
                        "column_name": "fecha_edit",
                        "es_filtro": True,
                        "is_date": True,
                    },
                    {
                        "table_name": "gestionh_ausentismo",
                        "campo_logico": "cedula",
                        "column_name": "cedula",
                        "is_identifier": True,
                        "es_filtro": True,
                    },
                    {
                        "table_name": "gestionh_ausentismo",
                        "campo_logico": "justificacion",
                        "column_name": "justificacion",
                        "es_filtro": True,
                        "es_group_by": True,
                    },
                    {
                        "table_name": "gestionh_ausentismo",
                        "campo_logico": "dias_perdidos",
                        "column_name": "dias_perdidos",
                        "es_metrica": True,
                        "supports_metric": True,
                    },
                ],
                "field_profiles": [],
                "rules": [{"resultado_funcional": "ausentismo = cedula"}],
                "relations": [
                    {
                        "nombre_relacion": "ausentismo_empleado",
                        "join_sql": "gestionh_ausentismo.cedula = cinco_base_de_personal.cedula",
                        "cardinalidad": "many_to_one",
                    }
                ],
                "synonyms": [
                    {"termino": "justificacion", "sinonimo": "motivo"},
                    {"termino": "justificacion", "sinonimo": "causa"},
                    {"termino": "activo", "sinonimo": "habilitado"},
                    {"termino": "activo", "sinonimo": "habilitados"},
                ],
            }
        return {
            "domain": {"id": 1, "code": "EMPLEADOS", "matched": True},
            "tables": [
                {
                    "id": 1,
                    "schema_name": "cincosas_cincosas",
                    "table_name": "cinco_base_de_personal",
                }
            ],
            "fields": [
                {
                    "table_name": "cinco_base_de_personal",
                    "campo_logico": "estado_empleado",
                    "column_name": "estado",
                    "valores_permitidos": "ACTIVO,INACTIVO",
                    "es_filtro": True,
                },
                {
                    "table_name": "cinco_base_de_personal",
                    "campo_logico": "supervisor",
                    "column_name": "supervisor",
                    "es_group_by": True,
                },
                {
                    "table_name": "cinco_base_de_personal",
                    "campo_logico": "area",
                    "column_name": "area",
                    "es_group_by": True,
                },
                {
                    "table_name": "cinco_base_de_personal",
                    "campo_logico": "cargo",
                    "column_name": "cargo",
                    "es_group_by": True,
                },
                {
                    "table_name": "cinco_base_de_personal",
                    "campo_logico": "tipo_labor",
                    "column_name": "tipo_labor",
                    "es_filtro": True,
                    "es_group_by": True,
                    "valores_permitidos": "OPERATIVO,ADMINISTRATIVO,SUPERVISOR,TRANSVERSAL",
                },
                {
                    "table_name": "cinco_base_de_personal",
                    "campo_logico": "fecha_ingreso",
                    "column_name": "fecha_ingreso",
                    "es_filtro": True,
                    "is_date": True,
                },
                {
                    "table_name": "cinco_base_de_personal",
                    "campo_logico": "fecha_egreso",
                    "column_name": "fecha_egreso",
                    "es_filtro": True,
                    "is_date": True,
                },
                {
                    "table_name": "cinco_base_de_personal",
                    "campo_logico": "fecha_nacimiento",
                    "column_name": "fnacimiento",
                    "es_filtro": True,
                    "es_group_by": True,
                    "is_date": True,
                },
                {
                    "table_name": "cinco_base_de_personal",
                    "campo_logico": "cedula",
                    "column_name": "cedula",
                    "is_identifier": True,
                    "es_filtro": True,
                },
                {
                    "table_name": "cinco_base_de_personal",
                    "campo_logico": "certificado_alturas_fecha_emision",
                    "column_name": "datos",
                    "es_filtro": True,
                    "is_date": True,
                    "definicion_negocio": "Fuente oficial. [json_path=$.certificados_alturas[*]][json_filter_tipo=alturas][json_date_key=fecha][fallback_column=calturas]",
                },
                {
                    "table_name": "cinco_base_de_personal",
                    "campo_logico": "certificado_alturas_fecha_vencimiento",
                    "column_name": "datos",
                    "es_filtro": True,
                    "is_date": True,
                    "definicion_negocio": "Fecha derivada. [json_path=$.certificados_alturas[*]][json_filter_tipo=alturas][json_date_key=fecha][fallback_column=calturas]",
                },
                {
                    "table_name": "cinco_base_de_personal",
                    "campo_logico": "certificado_alturas_estado_vigencia",
                    "column_name": "datos",
                    "es_filtro": True,
                    "definicion_negocio": "Estado derivado. [json_path=$.certificados_alturas[*]][json_filter_tipo=alturas][json_date_key=fecha][fallback_column=calturas]",
                },
            ],
            "field_profiles": [],
            "rules": [
                {"codigo": "certificado_alturas_vigencia_anual", "resultado_funcional": "vigencia anual"},
                {"codigo": "certificado_alturas_vencido", "resultado_funcional": "vencido"},
                {"codigo": "certificado_alturas_proximo_vencer_30_dias", "resultado_funcional": "proximo"},
                {"codigo": "personal_activo_operativo", "resultado_funcional": "activo operativo"},
                {"resultado_funcional": "empleado = cedula"},
            ],
            "relations": [
                {
                    "nombre_relacion": "empleado_supervisor",
                    "join_sql": "cinco_base_de_personal.supervisor = cinco_base_de_personal.cedula",
                    "cardinalidad": "many_to_one",
                }
            ],
            "synonyms": [
                {"termino": "supervisor", "sinonimo": "jefe"},
                {"termino": "supervisor", "sinonimo": "lider"},
                {"termino": "activo", "sinonimo": "habilitado"},
                {"termino": "activo", "sinonimo": "habilitados"},
                {"termino": "fecha_nacimiento", "sinonimo": "cumpleanos"},
                {"termino": "fecha_nacimiento", "sinonimo": "nacimiento"},
                {"termino": "fecha_ingreso", "sinonimo": "antiguedad"},
                {"termino": "certificado_alturas_fecha_emision", "sinonimo": "certificado de alturas"},
                {"termino": "certificado_alturas_fecha_emision", "sinonimo": "curso de alturas"},
                {"termino": "certificado_alturas_fecha_emision", "sinonimo": "alturas"},
                {"termino": "certificado_alturas_estado_vigencia", "sinonimo": "vencidos"},
                {"termino": "certificado_alturas_estado_vigencia", "sinonimo": "proximos a vencer"},
            ],
        }

    @staticmethod
    def get_table_field_profiles(table_names, *, limit: int = 80) -> list[dict]:
        requested = {str(item or "").strip().lower() for item in list(table_names or [])}
        if not ({"cinco_base_de_personal", "bd_c3nc4s1s.cinco_base_de_personal"} & requested):
            return []
        return [
            {
                "schema_name": "bd_c3nc4s1s",
                "table_name": "cinco_base_de_personal",
                "table_fqn": "bd_c3nc4s1s.cinco_base_de_personal",
                "campo_id": 999,
                "campo_logico": "sede",
                "column_name": "zona_nodo",
                "definicion_negocio": "Sede del colaborador",
                "es_filtro": True,
                "es_group_by": True,
                "supports_filter": True,
                "supports_group_by": True,
                "supports_metric": False,
                "supports_dimension": True,
                "is_date": False,
                "is_identifier": False,
                "is_chart_dimension": True,
                "is_chart_measure": False,
                "allowed_values": [],
                "allowed_operators": [],
                "allowed_aggregations": [],
                "normalization_strategy": "joined_table_profile",
                "priority": 90,
            },
            {
                "schema_name": "bd_c3nc4s1s",
                "table_name": "cinco_base_de_personal",
                "table_fqn": "bd_c3nc4s1s.cinco_base_de_personal",
                "campo_id": 1000,
                "campo_logico": "area",
                "column_name": "area",
                "definicion_negocio": "Area organizacional",
                "es_filtro": True,
                "es_group_by": True,
                "supports_filter": True,
                "supports_group_by": True,
                "supports_metric": False,
                "supports_dimension": True,
                "is_date": False,
                "is_identifier": False,
                "is_chart_dimension": True,
                "is_chart_measure": False,
                "allowed_values": [],
                "allowed_operators": [],
                "allowed_aggregations": [],
                "normalization_strategy": "joined_table_profile",
                "priority": 90,
            },
            {
                "schema_name": "bd_c3nc4s1s",
                "table_name": "cinco_base_de_personal",
                "table_fqn": "bd_c3nc4s1s.cinco_base_de_personal",
                "campo_id": 1001,
                "campo_logico": "cargo",
                "column_name": "cargo",
                "definicion_negocio": "Cargo del colaborador",
                "es_filtro": True,
                "es_group_by": True,
                "supports_filter": True,
                "supports_group_by": True,
                "supports_metric": False,
                "supports_dimension": True,
                "is_date": False,
                "is_identifier": False,
                "is_chart_dimension": True,
                "is_chart_measure": False,
                "allowed_values": [],
                "allowed_operators": [],
                "allowed_aggregations": [],
                "normalization_strategy": "joined_table_profile",
                "priority": 90,
            },
            {
                "schema_name": "bd_c3nc4s1s",
                "table_name": "cinco_base_de_personal",
                "table_fqn": "bd_c3nc4s1s.cinco_base_de_personal",
                "campo_id": 1002,
                "campo_logico": "supervisor",
                "column_name": "supervisor",
                "definicion_negocio": "Supervisor del colaborador",
                "es_filtro": True,
                "es_group_by": True,
                "supports_filter": True,
                "supports_group_by": True,
                "supports_metric": False,
                "supports_dimension": True,
                "is_date": False,
                "is_identifier": False,
                "is_chart_dimension": True,
                "is_chart_measure": False,
                "allowed_values": [],
                "allowed_operators": [],
                "allowed_aggregations": [],
                "normalization_strategy": "joined_table_profile",
                "priority": 90,
            },
            {
                "schema_name": "bd_c3nc4s1s",
                "table_name": "cinco_base_de_personal",
                "table_fqn": "bd_c3nc4s1s.cinco_base_de_personal",
                "campo_id": 1003,
                "campo_logico": "carpeta",
                "column_name": "carpeta",
                "definicion_negocio": "Carpeta del colaborador",
                "es_filtro": True,
                "es_group_by": True,
                "supports_filter": True,
                "supports_group_by": True,
                "supports_metric": False,
                "supports_dimension": True,
                "is_date": False,
                "is_identifier": False,
                "is_chart_dimension": True,
                "is_chart_measure": False,
                "allowed_values": [],
                "allowed_operators": [],
                "allowed_aggregations": [],
                "normalization_strategy": "joined_table_profile",
                "priority": 90,
            },
            {
                "schema_name": "bd_c3nc4s1s",
                "table_name": "cinco_base_de_personal",
                "table_fqn": "bd_c3nc4s1s.cinco_base_de_personal",
                "campo_id": 1004,
                "campo_logico": "tipo_labor",
                "column_name": "tipo_labor",
                "definicion_negocio": "Tipo de labor",
                "es_filtro": True,
                "es_group_by": True,
                "supports_filter": True,
                "supports_group_by": True,
                "supports_metric": False,
                "supports_dimension": True,
                "is_date": False,
                "is_identifier": False,
                "is_chart_dimension": True,
                "is_chart_measure": False,
                "allowed_values": [],
                "allowed_operators": [],
                "allowed_aggregations": [],
                "normalization_strategy": "joined_table_profile",
                "priority": 90,
            },
        ]


class QuerySemanticResolversTests(SimpleTestCase):
    def test_ai_dictionary_remediation_uses_bd_employee_table_for_empleados_domain(self):
        service = AIDictionaryRemediationService()
        manifest = service._build_domain_manifest(domain_code="empleados")
        employee_tables = [
            item for item in list(manifest.get("tables") or [])
            if str(item.get("table_name") or "").strip().lower() == "cinco_base_de_personal"
        ]
        self.assertEqual(len(employee_tables), 1)
        self.assertEqual(
            str(employee_tables[0].get("schema_name") or "").strip().lower(),
            "bd_c3nc4s1s",
        )

    def test_build_semantic_context_uses_employee_table_fqn_for_joined_profiles(self):
        resolver = SemanticBusinessResolver()
        context = resolver.build_semantic_context(domain_code="empleados", include_dictionary=True)
        employee_profiles = [
            item for item in list(context.get("column_profiles") or [])
            if str(item.get("logical_name") or item.get("campo_logico") or "").strip().lower() == "tipo_labor"
        ]
        self.assertTrue(employee_profiles)
        self.assertTrue(
            all(
                str(item.get("column_name") or "").strip().lower() == "tipo_labor"
                for item in employee_profiles
            )
        )

    def test_synonym_semantic_resolver_canonicalize(self):
        resolver = SynonymSemanticResolver()
        index = resolver.build_index(
            dictionary_synonyms=[{"termino": "supervisor", "sinonimo": "jefe"}],
            dictionary_fields=[],
            runtime_columns=[],
        )
        self.assertEqual(resolver.canonicalize(term="jefe", synonym_index=index), "supervisor")

    def test_synonym_semantic_resolver_maps_labor_to_tipo_labor(self):
        resolver = SynonymSemanticResolver()
        index = resolver.build_index(
            dictionary_synonyms=[],
            dictionary_fields=[],
            runtime_columns=[],
        )
        self.assertEqual(resolver.canonicalize(term="labor", synonym_index=index), "tipo_labor")

    def test_synonym_semantic_resolver_maps_categoria_laboral_to_tipo_labor(self):
        resolver = SynonymSemanticResolver()
        index = resolver.build_index(
            dictionary_synonyms=[],
            dictionary_fields=[],
            runtime_columns=[],
        )
        self.assertEqual(resolver.canonicalize(term="categoria laboral", synonym_index=index), "tipo_labor")

    def test_column_semantic_resolver_normalizes_status_filter(self):
        resolver = ColumnSemanticResolver()
        profiles = resolver.build_column_profiles(
            runtime_columns=[],
            dictionary_fields=[
                {
                    "table_name": "cinco_base_de_personal",
                    "campo_logico": "estado",
                    "column_name": "estado",
                    "valores_permitidos": "ACTIVO,INACTIVO",
                    "es_filtro": True,
                }
            ],
        )
        semantic_context = {"column_profiles": profiles}
        normalized, _ = resolver.resolve_filters(
            filters={"estado": "inactivos"},
            semantic_context=semantic_context,
            canonicalize_term=lambda term: str(term or "").lower(),
            normalize_status_value=lambda raw, allowed: RuleSemanticResolver().normalize_status_value(
                raw_value=raw,
                allowed_values=allowed,
            ),
        )
        self.assertEqual(str(normalized.get("estado") or ""), "INACTIVO")

    def test_column_semantic_resolver_binds_explicit_schema_value(self):
        resolver = ColumnSemanticResolver()
        profiles = resolver.build_column_profiles(
            runtime_columns=[],
            dictionary_fields=[
                {
                    "table_name": "cinco_base_de_personal",
                    "campo_logico": "cedula_empleado",
                    "column_name": "cedula",
                    "is_identifier": True,
                    "es_filtro": True,
                },
                {
                    "table_name": "cinco_base_de_personal",
                    "campo_logico": "movil",
                    "column_name": "movil",
                    "es_filtro": True,
                },
            ],
        )
        filters, resolutions = resolver.resolve_schema_value_filters(
            message="informacion del empleado con cedula: 98672304",
            semantic_context={"column_profiles": profiles},
        )
        self.assertEqual(str(filters.get("cedula_empleado") or ""), "98672304")
        self.assertTrue(resolutions)

    def test_column_semantic_resolver_does_not_reinterpret_value_as_second_column(self):
        resolver = ColumnSemanticResolver()
        profiles = resolver.build_column_profiles(
            runtime_columns=[],
            dictionary_fields=[
                {
                    "table_name": "cinco_base_de_personal",
                    "campo_logico": "cargo",
                    "column_name": "cargo",
                    "es_filtro": True,
                },
                {
                    "table_name": "cinco_base_de_personal",
                    "campo_logico": "supervisor",
                    "column_name": "supervisor",
                    "es_filtro": True,
                },
            ],
        )
        filters, _ = resolver.resolve_schema_value_filters(
            message="informacion de empleados cargo JEFE DEPARTAMENTO TI",
            semantic_context={
                "column_profiles": profiles,
                "synonym_index": {"jefe": "supervisor"},
            },
        )
        self.assertEqual(str(filters.get("cargo") or ""), "jefe departamento ti")
        self.assertNotIn("supervisor", filters)

    def test_column_semantic_resolver_ignores_dangling_conjunction_after_schema_term(self):
        resolver = ColumnSemanticResolver()
        profiles = resolver.build_column_profiles(
            runtime_columns=[],
            dictionary_fields=[
                {
                    "table_name": "cinco_base_de_personal",
                    "campo_logico": "area",
                    "column_name": "area",
                    "es_filtro": True,
                },
                {
                    "table_name": "cinco_base_de_personal",
                    "campo_logico": "carpeta",
                    "column_name": "carpeta",
                    "es_filtro": True,
                    "es_group_by": True,
                },
            ],
        )
        filters, _ = resolver.resolve_schema_value_filters(
            message="Personal activo por area y carpeta",
            semantic_context={"column_profiles": profiles},
        )
        self.assertNotIn("area", filters)

    def test_rule_semantic_resolver_extracts_identifier(self):
        resolver = RuleSemanticResolver()
        value = resolver.infer_identifier_from_message(
            message="Ausentismos del empleado 1055837370",
            domain_code="ausentismo",
        )
        self.assertEqual(value.get("cedula"), "1055837370")

    def test_semantic_business_resolver_resolves_filters_group_by_and_relations(self):
        fake_domain = _FakeDomain(
            raw_context={
                "tables": [
                    {
                        "schema_name": "cincosas_cincosas",
                        "table_name": "cinco_base_de_personal",
                        "table_fqn": "cincosas_cincosas.cinco_base_de_personal",
                        "rol": "dimension",
                        "es_principal": True,
                    }
                ],
                "columns": [
                    {"table_name": "cinco_base_de_personal", "column_name": "cedula", "nombre_columna_logico": "cedula"},
                    {"table_name": "cinco_base_de_personal", "column_name": "estado", "nombre_columna_logico": "estado"},
                    {"table_name": "cinco_base_de_personal", "column_name": "supervisor", "nombre_columna_logico": "supervisor"},
                    {"table_name": "cinco_base_de_personal", "column_name": "area", "nombre_columna_logico": "area"},
                ],
                "relationships": [
                    {
                        "nombre_relacion": "empleado_supervisor",
                        "condicion_join_sql": "cinco_base_de_personal.supervisor = cinco_base_de_personal.cedula",
                        "cardinalidad": "many_to_one",
                    }
                ],
                "flags": {"sql_asistido_permitido": False},
            }
        )
        resolver = SemanticBusinessResolver(
            registry=_FakeRegistry(fake_domain),
            dictionary_tool=_FakeDictionaryTool(),
        )
        intent = StructuredQueryIntent(
            raw_query="Cantidad empleados inactivos por jefe del empleado 1055837370",
            domain_code="empleados",
            operation="count",
            template_id="count_entities_by_status",
            filters={"estado": "inactivos"},
            group_by=["jefe"],
            metrics=["count"],
            confidence=0.9,
        )
        resolved = resolver.resolve_query(
            message=intent.raw_query,
            intent=intent,
            base_classification={"domain": "empleados"},
        )
        self.assertEqual(str(resolved.normalized_filters.get("estado") or ""), "INACTIVO")
        self.assertEqual(str(resolved.normalized_filters.get("cedula") or ""), "1055837370")
        self.assertIn("supervisor", list(resolved.intent.group_by or []))
        relation_payload = dict((resolved.semantic_context or {}).get("resolved_semantic") or {})
        self.assertTrue(list(relation_payload.get("relations") or []))

    def test_semantic_business_resolver_keeps_supervisor_as_group_dimension_and_operativo_as_filter(self):
        fake_domain = _FakeDomain(
            raw_context={
                "tables": [
                    {
                        "schema_name": "bd_c3nc4s1s",
                        "table_name": "cinco_base_de_personal",
                        "table_fqn": "bd_c3nc4s1s.cinco_base_de_personal",
                        "rol": "dimension",
                        "es_principal": True,
                    }
                ],
                "columns": [
                    {"table_name": "cinco_base_de_personal", "column_name": "estado", "nombre_columna_logico": "estado"},
                    {"table_name": "cinco_base_de_personal", "column_name": "tipo_labor", "nombre_columna_logico": "tipo_labor"},
                    {"table_name": "cinco_base_de_personal", "column_name": "supervisor", "nombre_columna_logico": "supervisor"},
                ],
                "relationships": [],
                "flags": {"sql_asistido_permitido": False},
            }
        )
        resolver = SemanticBusinessResolver(
            registry=_FakeRegistry(fake_domain),
            dictionary_tool=_FakeDictionaryTool(),
        )
        intent = StructuredQueryIntent(
            raw_query="Que supervisores tienen mas personal operativo asignado",
            domain_code="empleados",
            operation="aggregate",
            template_id="aggregate_by_group_and_period",
            filters={"tipo_labor": "OPERATIVO", "subtipo_personal_asignado": "OPERATIVO"},
            group_by=["supervisor"],
            metrics=["count"],
            confidence=0.92,
        )

        resolved = resolver.resolve_query(
            message=intent.raw_query,
            intent=intent,
            base_classification={"domain": "general"},
        )

        self.assertEqual(list(resolved.intent.group_by or []), ["supervisor"])
        self.assertEqual(str(resolved.normalized_filters.get("tipo_labor") or ""), "OPERATIVO")
        self.assertNotIn("supervisor", list(resolved.normalized_filters.keys()))

    def test_query_intent_dimension_variants_do_not_treat_tecnicos_as_tipo_labor_group_alias(self):
        variants = QueryIntentResolver._semantic_group_dimension_variants(
            semantic_context={
                "query_hints": {"candidate_group_dimensions": ["tipo_labor", "supervisor"]},
                "synonym_index": {
                    "tecnicos": "operativo",
                    "operativos": "operativo",
                    "jefes directos": "supervisor",
                    "tipo de labor": "tipo_labor",
                },
                "aliases": {"tipo_labor": "tipo_labor", "supervisor": "supervisor"},
            }
        )

        self.assertIn("tipo de labor", list(variants.get("tipo_labor") or []))
        self.assertNotIn("tecnicos", list(variants.get("tipo_labor") or []))

    def test_semantic_business_resolver_uses_dictionary_as_only_structural_source(self):
        fake_domain = _FakeDomain(
            raw_context={
                "tables": [
                    {
                        "table_name": "yaml_only_table",
                        "table_fqn": "demo.yaml_only_table",
                    }
                ],
                "columns": [
                    {
                        "table_name": "yaml_only_table",
                        "column_name": "yaml_only_column",
                        "nombre_columna_logico": "yaml_only_column",
                    }
                ],
                "relationships": [
                    {
                        "nombre_relacion": "yaml_only_relation",
                        "condicion": "yaml_only_table.id = otra.id",
                    }
                ],
                "contexto_agente": {"descripcion": "Narrativa de prueba"},
            }
        )
        resolver = SemanticBusinessResolver(
            registry=_FakeRegistry(fake_domain),
            dictionary_tool=_FakeDictionaryTool(),
        )

        context = resolver.build_semantic_context(domain_code="ausentismo", include_dictionary=True)

        table_names = {str(item.get("table_name") or "") for item in list(context.get("tables") or [])}
        column_names = {str(item.get("column_name") or "") for item in list(context.get("columns") or [])}
        relation_names = {str(item.get("nombre_relacion") or "") for item in list(context.get("relationships") or [])}
        self.assertIn("gestionh_ausentismo", table_names)
        self.assertNotIn("yaml_only_table", table_names)
        self.assertIn("fecha_edit", column_names)
        self.assertNotIn("yaml_only_column", column_names)
        self.assertIn("ausentismo_empleado", relation_names)
        self.assertNotIn("yaml_only_relation", relation_names)
        source_of_truth = dict(context.get("source_of_truth") or {})
        self.assertEqual(str(source_of_truth.get("structural_source") or ""), "ai_dictionary")
        self.assertEqual(str(source_of_truth.get("yaml_role") or ""), "narrative_only")
        self.assertTrue(bool(source_of_truth.get("yaml_structural_ignored")))
        self.assertIn("columns", list(context.get("yaml_fields_ignored") or []))

    def test_semantic_business_resolver_reports_missing_dictionary_metadata_without_yaml_fallback(self):
        fake_domain = _FakeDomain(
            raw_context={
                "columns": [
                    {
                        "table_name": "cinco_base_de_personal",
                        "column_name": "zona_nodo",
                        "nombre_columna_logico": "sede",
                    }
                ],
                "group_by_soportados": ["sede"],
            }
        )
        resolver = SemanticBusinessResolver(
            registry=_FakeRegistry(fake_domain),
            dictionary_tool=_FakeDictionaryTool(),
        )

        context = resolver.build_semantic_context(domain_code="empleados", include_dictionary=True)

        missing = {
            (str(item.get("type") or ""), str(item.get("value") or ""))
            for item in list(context.get("missing_dictionary_metadata") or [])
        }
        self.assertFalse(missing)
        self.assertIn("sede", list(context.get("allowed_columns") or []))

    def test_semantic_business_resolver_supplements_employee_dictionary_with_remediation_manifest(self):
        fake_domain = _FakeDomain(
            raw_context={
                "tables": [
                    {
                        "schema_name": "bd_c3nc4s1s",
                        "table_name": "cinco_base_de_personal",
                        "table_fqn": "bd_c3nc4s1s.cinco_base_de_personal",
                        "rol": "dimension",
                        "es_principal": True,
                    }
                ],
            }
        )
        resolver = SemanticBusinessResolver(
            registry=_FakeRegistry(fake_domain),
            dictionary_tool=_FakeDictionaryTool(),
        )

        context = resolver.build_semantic_context(domain_code="empleados", include_dictionary=True)

        self.assertEqual(str((context.get("synonym_index") or {}).get("cuadrillas") or ""), "movil")
        self.assertEqual(str((context.get("synonym_index") or {}).get("jefes directos") or ""), "supervisor")
        self.assertIn("movil", list(context.get("allowed_columns") or []))
        self.assertIn("sede", list(context.get("allowed_columns") or []))

    def test_query_execution_planner_treats_logical_cedula_as_employee_detail_identifier(self):
        planner = QueryExecutionPlanner()
        resolved = ResolvedQuerySpec(
            intent=StructuredQueryIntent(
                raw_query="informacion del empleado con cedula: 98672304",
                domain_code="empleados",
                operation="detail",
                template_id="detail_by_entity_and_period",
                filters={"cedula_empleado": "98672304"},
                confidence=0.9,
            ),
            semantic_context={
                "tables": [{"table_name": "cinco_base_de_personal"}],
                "columns": [{"column_name": "cedula"}, {"column_name": "nombre"}],
            },
            normalized_filters={"cedula_empleado": "98672304"},
            normalized_period={},
        )
        with patch.dict(
            os.environ,
            {
                "IA_DEV_CAP_EMPLEADOS_ENABLED": "1",
            },
            clear=False,
        ):
            plan = planner.plan(
                run_context=RunContext.create(message=resolved.intent.raw_query, session_id="test", reset_memory=False),
                resolved_query=resolved,
            )
        self.assertEqual(plan.strategy, "capability")
        self.assertEqual(plan.capability_id, "empleados.detail.v1")

    def test_query_execution_planner_allows_employee_detail_by_schema_filter(self):
        planner = QueryExecutionPlanner()
        resolved = ResolvedQuerySpec(
            intent=StructuredQueryIntent(
                raw_query="informacion de empleados del area DEPARTAMENTO TI",
                domain_code="empleados",
                operation="detail",
                template_id="detail_by_entity_and_period",
                filters={"area": "DEPARTAMENTO TI", "estado": "ACTIVO"},
                confidence=0.9,
            ),
            semantic_context={
                "tables": [{"table_name": "cinco_base_de_personal"}],
                "columns": [{"column_name": "area"}, {"column_name": "cedula"}],
            },
            normalized_filters={"area": "DEPARTAMENTO TI", "estado": "ACTIVO"},
            normalized_period={},
        )
        with patch.dict(
            os.environ,
            {
                "IA_DEV_CAP_EMPLEADOS_ENABLED": "1",
            },
            clear=False,
        ):
            plan = planner.plan(
                run_context=RunContext.create(message=resolved.intent.raw_query, session_id="test", reset_memory=False),
                resolved_query=resolved,
            )
        self.assertEqual(plan.strategy, "capability")
        self.assertEqual(plan.capability_id, "empleados.detail.v1")

    def test_query_execution_planner_routes_birthday_month_to_sql_assisted(self):
        planner = QueryExecutionPlanner()
        resolved = ResolvedQuerySpec(
            intent=StructuredQueryIntent(
                raw_query="empleados que cumplen años en mayo",
                domain_code="empleados",
                operation="detail",
                template_id="detail_by_entity_and_period",
                filters={"fnacimiento_month": "5", "estado": "ACTIVO"},
                confidence=0.9,
            ),
            semantic_context={
                "domain_status": "active",
                "supports_sql_assisted": True,
                "tables": [{"table_name": "cinco_base_de_personal", "table_fqn": "cincosas_cincosas.cinco_base_de_personal"}],
                "columns": [{"column_name": "fnacimiento"}, {"column_name": "cedula"}, {"column_name": "estado"}],
                "column_profiles": [
                    {"table_name": "cinco_base_de_personal", "logical_name": "fecha_nacimiento", "column_name": "fnacimiento", "supports_filter": True, "supports_group_by": True, "is_date": True},
                    {"table_name": "cinco_base_de_personal", "logical_name": "cedula", "column_name": "cedula", "is_identifier": True},
                    {"table_name": "cinco_base_de_personal", "logical_name": "estado_empleado", "column_name": "estado", "supports_filter": True, "allowed_values": ["ACTIVO", "INACTIVO"]},
                ],
                "allowed_tables": ["cinco_base_de_personal", "cincosas_cincosas.cinco_base_de_personal"],
                "allowed_columns": ["fnacimiento", "cedula", "estado"],
                "source_of_truth": {"pilot_sql_assisted_enabled": True},
            },
            normalized_filters={"fnacimiento_month": "5", "estado": "ACTIVO"},
            normalized_period={},
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
                run_context=RunContext.create(message=resolved.intent.raw_query, session_id="test", reset_memory=False),
                resolved_query=resolved,
            )
        self.assertEqual(plan.strategy, "sql_assisted")
        self.assertIn("MONTH(fnacimiento) = 5", str(plan.sql_query or ""))
        self.assertEqual(str((plan.metadata or {}).get("compiler") or ""), "employee_semantic_sql")

    def test_semantic_business_resolver_maps_birthday_month_to_detail_filter(self):
        resolver = SemanticBusinessResolver(
            registry=_FakeRegistry(_FakeDomain(raw_context={})),
            dictionary_tool=_FakeDictionaryTool(),
        )
        semantic_context = {
            "tables": [{"table_name": "cinco_base_de_personal"}],
            "columns": [{"column_name": "fnacimiento"}, {"column_name": "estado"}],
            "relationships": [],
            "dictionary": {"rules": [], "fields": [], "relations": [], "synonyms": []},
            "column_profiles": [
                {
                    "table_name": "cinco_base_de_personal",
                    "logical_name": "fnacimiento",
                    "column_name": "fnacimiento",
                    "supports_filter": True,
                    "is_date": True,
                },
                {
                    "table_name": "cinco_base_de_personal",
                    "logical_name": "estado",
                    "column_name": "estado",
                    "supports_filter": True,
                    "allowed_values": ["ACTIVO", "INACTIVO"],
                },
            ],
            "relation_profiles": [],
            "synonym_index": {},
            "allowed_tables": ["cinco_base_de_personal"],
            "allowed_columns": ["fnacimiento", "estado"],
            "aliases": {},
            "company_operational_scope": {"domain_known": True, "domain_operational": True},
        }
        intent = StructuredQueryIntent(
            raw_query="empleados que cumplen años en mayo",
            domain_code="empleados",
            operation="count",
            template_id="count_records_by_period",
            filters={"month_of_birth": "mayo"},
            confidence=0.8,
        )
        resolved = resolver.resolve_query(
            message=intent.raw_query,
            intent=intent,
            base_classification={"domain": "empleados"},
            semantic_context_override=semantic_context,
        )
        self.assertEqual(str(resolved.normalized_filters.get("fnacimiento_month") or ""), "5")
        self.assertEqual(resolved.intent.operation, "count")
        self.assertEqual(resolved.intent.template_id, "count_records_by_period")
        self.assertNotIn("temporal_scope_ambiguous", resolved.warnings)
        field_match = dict(((resolved.semantic_context or {}).get("resolved_semantic") or {}).get("field_match") or {})
        self.assertEqual(str(field_match.get("logical_name") or ""), "fecha_nacimiento")
        self.assertIn("birthday", list(field_match.get("business_concepts") or []))

    def test_semantic_business_resolver_maps_birthday_group_by_month(self):
        resolver = SemanticBusinessResolver(
            registry=_FakeRegistry(_FakeDomain(raw_context={})),
            dictionary_tool=_FakeDictionaryTool(),
        )
        intent = StructuredQueryIntent(
            raw_query="cumpleanos por mes",
            domain_code="empleados",
            operation="aggregate",
            template_id="aggregate_by_group_and_period",
            filters={},
            group_by=["birth_month"],
            metrics=["count"],
            confidence=0.8,
        )
        resolved = resolver.resolve_query(
            message=intent.raw_query,
            intent=intent,
            base_classification={"domain": "empleados"},
        )
        self.assertIn("birth_month", list(resolved.intent.group_by or []))
        field_match = dict(((resolved.semantic_context or {}).get("resolved_semantic") or {}).get("field_match") or {})
        self.assertEqual(str(field_match.get("semantic_role") or ""), "person_birth_date")

    def test_semantic_business_resolver_exposes_group_by_candidate_metadata_for_birthday_by_area(self):
        resolver = SemanticBusinessResolver(
            registry=_FakeRegistry(_FakeDomain(raw_context={})),
            dictionary_tool=_FakeDictionaryTool(),
        )
        intent = StructuredQueryIntent(
            raw_query="cumpleanos de mayo por area",
            domain_code="empleados",
            operation="aggregate",
            template_id="aggregate_by_group_and_period",
            filters={"fnacimiento_month": "5"},
            group_by=["area"],
            metrics=["count"],
            confidence=0.88,
        )
        resolved = resolver.resolve_query(
            message=intent.raw_query,
            intent=intent,
            base_classification={"domain": "empleados"},
        )
        group_candidates = list(((resolved.semantic_context or {}).get("resolved_semantic") or {}).get("group_by_candidates") or [])
        self.assertTrue(group_candidates)
        self.assertEqual(str(group_candidates[0].get("business_name") or ""), "area")
        self.assertEqual(str(group_candidates[0].get("physical_column") or ""), "area")
        self.assertEqual(str(group_candidates[0].get("table") or ""), "cinco_base_de_personal")
        self.assertEqual(str(group_candidates[0].get("semantic_role") or ""), "organizational_dimension")
        self.assertIn("group_by", list(group_candidates[0].get("allowed_operations") or []))

    def test_semantic_business_resolver_inferrs_group_by_area_from_plural_question(self):
        fake_domain = _FakeDomain(
            raw_context={
                "tables": [
                    {
                        "schema_name": "cincosas_cincosas",
                        "table_name": "cinco_base_de_personal",
                        "table_fqn": "cincosas_cincosas.cinco_base_de_personal",
                        "rol": "dimension",
                        "es_principal": True,
                    }
                ],
                "columns": [
                    {"table_name": "cinco_base_de_personal", "column_name": "area", "nombre_columna_logico": "area"},
                ],
                "relationships": [],
                "flags": {"sql_asistido_permitido": False},
            }
        )
        resolver = SemanticBusinessResolver(
            registry=_FakeRegistry(fake_domain),
            dictionary_tool=_FakeDictionaryTool(),
        )
        intent = StructuredQueryIntent(
            raw_query="¿Qué áreas concentran más ausentismos en rolling 90 días?",
            domain_code="ausentismo",
            operation="aggregate",
            template_id="aggregate_by_group_and_period",
            filters={},
            group_by=[],
            metrics=["count"],
            confidence=0.9,
        )
        resolved = resolver.resolve_query(
            message=intent.raw_query,
            intent=intent,
            base_classification={"domain": "ausentismo"},
        )
        self.assertIn("area", list(resolved.intent.group_by or []))

    def test_semantic_business_resolver_recovers_attendance_group_by_from_entity_type_when_llm_omits_it(self):
        fake_domain = _FakeDomain(
            raw_context={
                "tables": [
                    {
                        "schema_name": "cincosas_cincosas",
                        "table_name": "gestionh_ausentismo",
                        "table_fqn": "cincosas_cincosas.gestionh_ausentismo",
                        "rol": "hechos",
                        "es_principal": True,
                    },
                    {
                        "schema_name": "cincosas_cincosas",
                        "table_name": "cinco_base_de_personal",
                        "table_fqn": "cincosas_cincosas.cinco_base_de_personal",
                        "rol": "dimension",
                        "es_principal": False,
                    },
                ],
                "columns": [
                    {"table_name": "gestionh_ausentismo", "column_name": "cedula", "nombre_columna_logico": "cedula"},
                    {"table_name": "gestionh_ausentismo", "column_name": "fecha_edit", "nombre_columna_logico": "fecha_ausentismo"},
                ],
                "relationships": [
                    {
                        "nombre_relacion": "ausentismo_empleado",
                        "condicion_join_sql": "gestionh_ausentismo.cedula = cinco_base_de_personal.cedula",
                        "cardinalidad": "many_to_one",
                    }
                ],
                "flags": {"sql_asistido_permitido": False},
            }
        )
        resolver = SemanticBusinessResolver(
            registry=_FakeRegistry(fake_domain),
            dictionary_tool=_FakeDictionaryTool(),
        )
        intent = StructuredQueryIntent(
            raw_query="ausentismos por area",
            domain_code="ausentismo",
            operation="aggregate",
            template_id="aggregate_by_group_and_period",
            entity_type="area",
            filters={},
            group_by=[],
            metrics=["count"],
            confidence=0.7,
            source="openai",
        )
        resolved = resolver.resolve_query(
            message=intent.raw_query,
            intent=intent,
            base_classification={"domain": "ausentismo"},
        )
        self.assertIn("area", list(resolved.intent.group_by or []))

    def test_semantic_business_resolver_supports_new_attendance_group_dimension_from_joined_employee_table(self):
        fake_domain = _FakeDomain(
            raw_context={
                "tables": [
                    {
                        "schema_name": "cincosas_cincosas",
                        "table_name": "gestionh_ausentismo",
                        "table_fqn": "cincosas_cincosas.gestionh_ausentismo",
                        "rol": "hechos",
                        "es_principal": True,
                    },
                    {
                        "schema_name": "cincosas_cincosas",
                        "table_name": "cinco_base_de_personal",
                        "table_fqn": "cincosas_cincosas.cinco_base_de_personal",
                        "rol": "dimension",
                        "es_principal": False,
                    },
                ],
                "columns": [
                    {"table_name": "gestionh_ausentismo", "column_name": "cedula", "nombre_columna_logico": "cedula"},
                ],
                "relationships": [
                    {
                        "nombre_relacion": "ausentismo_empleado",
                        "condicion_join_sql": "gestionh_ausentismo.cedula = cinco_base_de_personal.cedula",
                        "cardinalidad": "many_to_one",
                    }
                ],
                "flags": {"sql_asistido_permitido": False},
            }
        )
        resolver = SemanticBusinessResolver(
            registry=_FakeRegistry(fake_domain),
            dictionary_tool=_FakeDictionaryTool(),
        )
        intent = StructuredQueryIntent(
            raw_query="ausentismos por sede",
            domain_code="ausentismo",
            operation="aggregate",
            template_id="aggregate_by_group_and_period",
            filters={},
            group_by=[],
            metrics=["count"],
            confidence=0.8,
        )
        resolved = resolver.resolve_query(
            message=intent.raw_query,
            intent=intent,
            base_classification={"domain": "ausentismo"},
        )
        self.assertIn("sede", list(resolved.intent.group_by or []))

    def test_semantic_business_resolver_maps_labor_to_tipo_labor_for_attendance_join(self):
        attendance_domain = _FakeDomain(
            raw_context={
                "tables": [
                    {
                        "schema_name": "cincosas_cincosas",
                        "table_name": "gestionh_ausentismo",
                        "table_fqn": "cincosas_cincosas.gestionh_ausentismo",
                        "rol": "hechos",
                        "es_principal": True,
                    },
                    {
                        "schema_name": "cincosas_cincosas",
                        "table_name": "cinco_base_de_personal",
                        "table_fqn": "cincosas_cincosas.cinco_base_de_personal",
                        "rol": "dimension",
                        "es_principal": False,
                    },
                ],
                "columns": [
                    {"table_name": "gestionh_ausentismo", "column_name": "cedula", "nombre_columna_logico": "cedula"},
                ],
                "relationships": [
                    {
                        "nombre_relacion": "ausentismo_empleado",
                        "condicion_join_sql": "gestionh_ausentismo.cedula = cinco_base_de_personal.cedula",
                        "cardinalidad": "many_to_one",
                    }
                ],
                "flags": {"sql_asistido_permitido": False},
            }
        )
        employee_domain = _FakeDomain(
            raw_context={
                "columnas_clave": [
                    {
                        "table_name": "cinco_base_de_personal",
                        "column_name": "tipo_labor",
                        "nombre_columna_logico": "tipo_labor",
                    }
                ],
                "filtros_soportados": ["tipo_labor"],
                "group_by_soportados": ["tipo_labor"],
            }
        )
        resolver = SemanticBusinessResolver(
            registry=_DualRegistry(primary_domain=attendance_domain, employee_domain=employee_domain),
            dictionary_tool=_FakeDictionaryTool(),
        )
        intent = StructuredQueryIntent(
            raw_query="ausentismos por labor",
            domain_code="ausentismo",
            operation="aggregate",
            template_id="aggregate_by_group_and_period",
            filters={},
            group_by=["labor"],
            metrics=["count"],
            confidence=0.8,
        )
        resolved = resolver.resolve_query(
            message=intent.raw_query,
            intent=intent,
            base_classification={"domain": "ausentismo"},
        )
        self.assertIn("tipo_labor", list(resolved.intent.group_by or []))
        self.assertNotIn("estado_justificacion", list(resolved.intent.group_by or []))

    def test_semantic_business_resolver_resolves_habilitados_status_from_dictionary(self):
        fake_domain = _FakeDomain(
            raw_context={
                "tables": [
                    {
                        "schema_name": "cincosas_cincosas",
                        "table_name": "cinco_base_de_personal",
                        "table_fqn": "cincosas_cincosas.cinco_base_de_personal",
                        "rol": "dimension",
                        "es_principal": True,
                    }
                ],
                "columns": [
                    {"table_name": "cinco_base_de_personal", "column_name": "estado", "nombre_columna_logico": "estado_empleado"},
                ],
                "relationships": [],
                "flags": {"sql_asistido_permitido": False},
            }
        )
        resolver = SemanticBusinessResolver(
            registry=_FakeRegistry(fake_domain),
            dictionary_tool=_FakeDictionaryTool(),
        )
        intent = StructuredQueryIntent(
            raw_query="¿Cuántos colaboradores habilitados tenemos hoy?",
            domain_code="empleados",
            operation="count",
            template_id="count_records_by_period",
            filters={},
            group_by=[],
            metrics=["count"],
            confidence=0.9,
        )
        resolved = resolver.resolve_query(
            message=intent.raw_query,
            intent=intent,
            base_classification={"domain": "empleados"},
        )
        self.assertEqual(str(resolved.normalized_filters.get("estado") or ""), "ACTIVO")
        self.assertEqual(str(resolved.intent.template_id or ""), "count_entities_by_status")

    def test_semantic_business_resolver_binds_egresos_this_month_to_fecha_egreso(self):
        fake_domain = _FakeDomain(
            raw_context={
                "tables": [
                    {
                        "schema_name": "cincosas_cincosas",
                        "table_name": "cinco_base_de_personal",
                        "table_fqn": "cincosas_cincosas.cinco_base_de_personal",
                        "rol": "dimension",
                        "es_principal": True,
                    }
                ],
                "columns": [
                    {"table_name": "cinco_base_de_personal", "column_name": "estado", "nombre_columna_logico": "estado_empleado"},
                    {"table_name": "cinco_base_de_personal", "column_name": "fecha_egreso", "nombre_columna_logico": "fecha_egreso"},
                ],
                "relationships": [],
                "flags": {"sql_asistido_permitido": False},
            }
        )
        resolver = SemanticBusinessResolver(
            registry=_FakeRegistry(fake_domain),
            dictionary_tool=_FakeDictionaryTool(),
        )
        intent = StructuredQueryIntent(
            raw_query="Egresos de este mes?",
            domain_code="empleados",
            operation="count",
            template_id="count_records_by_period",
            filters={},
            group_by=[],
            metrics=["count"],
            confidence=0.9,
        )
        resolved = resolver.resolve_query(
            message=intent.raw_query,
            intent=intent,
            base_classification={"domain": "general"},
        )
        self.assertEqual(str(resolved.normalized_filters.get("estado") or ""), "INACTIVO")
        self.assertEqual(str(resolved.intent.template_id or ""), "count_entities_by_status")
        temporal_scope = dict(((resolved.semantic_context or {}).get("resolved_semantic") or {}).get("temporal_scope") or {})
        self.assertEqual(str(temporal_scope.get("column_hint") or ""), "fecha_egreso")
        self.assertEqual(str(temporal_scope.get("status_value") or ""), "INACTIVO")
        self.assertFalse(bool(temporal_scope.get("ambiguous")))

    def test_semantic_business_resolver_defaults_employee_queries_to_active_status(self):
        fake_domain = _FakeDomain(
            raw_context={
                "tables": [
                    {
                        "schema_name": "cincosas_cincosas",
                        "table_name": "cinco_base_de_personal",
                        "table_fqn": "cincosas_cincosas.cinco_base_de_personal",
                        "rol": "dimension",
                        "es_principal": True,
                    }
                ],
                "columns": [
                    {"table_name": "cinco_base_de_personal", "column_name": "estado", "nombre_columna_logico": "estado_empleado"},
                    {"table_name": "cinco_base_de_personal", "column_name": "area", "nombre_columna_logico": "area"},
                ],
                "relationships": [],
                "flags": {"sql_asistido_permitido": False},
            }
        )
        resolver = SemanticBusinessResolver(
            registry=_FakeRegistry(fake_domain),
            dictionary_tool=_FakeDictionaryTool(),
        )
        intent = StructuredQueryIntent(
            raw_query="empleados por area",
            domain_code="empleados",
            operation="aggregate",
            template_id="aggregate_by_group_and_period",
            filters={},
            group_by=["area"],
            metrics=["count"],
            confidence=0.9,
        )
        resolved = resolver.resolve_query(
            message=intent.raw_query,
            intent=intent,
            base_classification={"domain": "empleados"},
        )
        self.assertEqual(str(resolved.normalized_filters.get("estado") or ""), "ACTIVO")
        self.assertEqual(str(resolved.normalized_filters.get("estado_empleado") or ""), "ACTIVO")
        self.assertIn("area", list(resolved.intent.group_by or []))

    def test_semantic_business_resolver_upgrades_grouped_employee_population_count_to_aggregate_template(self):
        fake_domain = _FakeDomain(
            raw_context={
                "tables": [
                    {
                        "schema_name": "cincosas_cincosas",
                        "table_name": "cinco_base_de_personal",
                        "table_fqn": "cincosas_cincosas.cinco_base_de_personal",
                        "rol": "dimension",
                        "es_principal": True,
                    }
                ],
                "columns": [
                    {"table_name": "cinco_base_de_personal", "column_name": "estado", "nombre_columna_logico": "estado_empleado"},
                    {"table_name": "cinco_base_de_personal", "column_name": "tipo_labor", "nombre_columna_logico": "tipo_labor"},
                ],
                "relationships": [],
                "flags": {"sql_asistido_permitido": False},
            }
        )
        resolver = SemanticBusinessResolver(
            registry=_FakeRegistry(fake_domain),
            dictionary_tool=_FakeDictionaryTool(),
        )
        intent = StructuredQueryIntent(
            raw_query="Cuantos empleados activos hay y como se distribuyen por tipo de labor",
            domain_code="empleados",
            operation="count",
            template_id="count_entities_by_status",
            filters={"estado": "ACTIVO"},
            group_by=["tipo_labor"],
            metrics=["count"],
            confidence=0.9,
        )
        resolved = resolver.resolve_query(
            message=intent.raw_query,
            intent=intent,
            base_classification={"domain": "empleados"},
        )
        self.assertEqual(str(resolved.intent.operation or ""), "aggregate")
        self.assertEqual(str(resolved.intent.template_id or ""), "aggregate_by_group_and_period")
        self.assertIn("tipo_labor", list(resolved.intent.group_by or []))

    def test_semantic_business_resolver_treats_personal_activo_hoy_as_current_population_count(self):
        fake_domain = _FakeDomain(
            raw_context={
                "tables": [
                    {
                        "schema_name": "cincosas_cincosas",
                        "table_name": "cinco_base_de_personal",
                        "table_fqn": "cincosas_cincosas.cinco_base_de_personal",
                        "rol": "dimension",
                        "es_principal": True,
                    }
                ],
                "columns": [
                    {"table_name": "cinco_base_de_personal", "column_name": "estado", "nombre_columna_logico": "estado_empleado"},
                    {"table_name": "cinco_base_de_personal", "column_name": "fecha_ingreso", "nombre_columna_logico": "fecha_ingreso"},
                ],
                "relationships": [],
                "flags": {"sql_asistido_permitido": False},
            }
        )
        resolver = SemanticBusinessResolver(
            registry=_FakeRegistry(fake_domain),
            dictionary_tool=_FakeDictionaryTool(),
        )
        intent = StructuredQueryIntent(
            raw_query="personal activo hoy",
            domain_code="empleados",
            operation="count",
            template_id="count_records_by_period",
            filters={},
            period={"label": "hoy", "start_date": "2026-05-04", "end_date": "2026-05-04"},
            group_by=[],
            metrics=["count"],
            confidence=0.9,
        )
        resolved = resolver.resolve_query(
            message=intent.raw_query,
            intent=intent,
            base_classification={"domain": "empleados"},
        )
        self.assertEqual(str(resolved.intent.operation or ""), "count")
        self.assertEqual(str(resolved.intent.template_id or ""), "count_entities_by_status")
        self.assertEqual(str(resolved.normalized_filters.get("estado") or ""), "ACTIVO")
        temporal_scope = dict(((resolved.semantic_context or {}).get("resolved_semantic") or {}).get("temporal_scope") or {})
        self.assertEqual(temporal_scope, {})

    def test_semantic_business_resolver_preserves_group_by_from_domain_scope_when_dictionary_profile_is_weaker(self):
        fake_domain = _FakeDomain(
            raw_context={
                "tables": [
                    {
                        "schema_name": "cincosas_cincosas",
                        "table_name": "cinco_base_de_personal",
                        "table_fqn": "cincosas_cincosas.cinco_base_de_personal",
                        "rol": "dimension",
                        "es_principal": True,
                    }
                ],
                "columns": [
                    {"table_name": "cinco_base_de_personal", "column_name": "cargo", "nombre_columna_logico": "cargo"},
                ],
                "group_by_soportados": ["cargo"],
                "relationships": [],
                "flags": {"sql_asistido_permitido": False},
            }
        )
        resolver = SemanticBusinessResolver(
            registry=_FakeRegistry(fake_domain),
            dictionary_tool=_FakeDictionaryTool(),
        )
        intent = StructuredQueryIntent(
            raw_query="Cantidad de empleados activos por cargo",
            domain_code="empleados",
            operation="aggregate",
            template_id="aggregate_by_group_and_period",
            filters={"estado": "ACTIVO"},
            group_by=["cargo"],
            metrics=["count"],
            confidence=0.9,
        )
        resolved = resolver.resolve_query(
            message=intent.raw_query,
            intent=intent,
            base_classification={"domain": "empleados"},
        )
        self.assertIn("cargo", list(resolved.intent.group_by or []))

    def test_semantic_business_resolver_keeps_missing_supervisor_as_filter_without_inferred_group_by(self):
        resolver = SemanticBusinessResolver(
            registry=_FakeRegistry(_FakeDomain(raw_context={"tables": [], "columns": [], "relationships": [], "flags": {}})),
            dictionary_tool=_FakeDictionaryTool(),
        )
        intent = StructuredQueryIntent(
            raw_query="Que empleados activos no tienen supervisor registrado",
            domain_code="empleados",
            operation="detail",
            template_id="detail_by_entity_and_period",
            filters={
                "supervisor": {"operator": "is_missing", "match_mode": "null_or_empty"},
                "estado": "ACTIVO",
            },
            group_by=[],
            metrics=["count"],
            confidence=0.9,
        )
        resolved = resolver.resolve_query(
            message=intent.raw_query,
            intent=intent,
            base_classification={"domain": "empleados"},
        )
        self.assertEqual(str(resolved.intent.operation or ""), "detail")
        self.assertEqual(list(resolved.intent.group_by or []), [])
        self.assertEqual(
            dict(resolved.normalized_filters or {}).get("supervisor"),
            {"operator": "is_missing", "match_mode": "null_or_empty"},
        )
        self.assertNotIn("conduce", dict(resolved.normalized_filters or {}))

    def test_relation_semantic_resolver_builds_relation_profiles(self):
        resolver = RelationSemanticResolver()
        profiles = resolver.build_relation_profiles(
            runtime_relationships=[],
            dictionary_relations=[
                {
                    "nombre_relacion": "ausentismo_empleado",
                    "join_sql": "gestionh_ausentismo.cedula = cinco_base_de_personal.cedula",
                    "cardinalidad": "many_to_one",
                }
            ],
        )
        self.assertEqual(len(profiles), 1)
        self.assertEqual(str(profiles[0].get("relation_name") or ""), "ausentismo_empleado")

    def test_semantic_business_resolver_rrhh_synonym_seed_flag_controls_bootstrap(self):
        fake_domain = _FakeDomain(raw_context={"tables": [], "columns": [], "relationships": [], "flags": {}})
        dictionary_tool = Mock()
        dictionary_tool.get_domain_context.return_value = {
            "fields": [],
            "relations": [],
            "rules": [],
            "synonyms": [],
            "field_profiles": [],
            "tables": [],
        }
        dictionary_tool.ensure_rrhh_status_synonyms_seed.return_value = {
            "ok": True,
            "status": "applied",
            "inserted": 2,
            "skipped": 6,
            "errors": [],
        }
        resolver = SemanticBusinessResolver(
            registry=_FakeRegistry(fake_domain),
            dictionary_tool=dictionary_tool,
        )

        with patch.dict(
            os.environ,
            {"IA_DEV_QUERY_INTELLIGENCE_RRHH_SYNONYM_SEED_ENABLED": "0"},
            clear=False,
        ):
            context = resolver.build_semantic_context(domain_code="empleados", include_dictionary=True)
        self.assertEqual(str((context.get("dictionary_seed") or {}).get("status") or ""), "skipped")
        dictionary_tool.ensure_rrhh_status_synonyms_seed.assert_not_called()

        with patch.dict(
            os.environ,
            {"IA_DEV_QUERY_INTELLIGENCE_RRHH_SYNONYM_SEED_ENABLED": "1"},
            clear=False,
        ):
            context = resolver.build_semantic_context(domain_code="empleados", include_dictionary=True)
        self.assertEqual(str((context.get("dictionary_seed") or {}).get("status") or ""), "applied")
        dictionary_tool.ensure_rrhh_status_synonyms_seed.assert_called()

    def test_semantic_business_resolver_marks_known_domain_without_operational_scope(self):
        fake_domain = _FakeDomain(
            raw_context={
                "tables": [
                    {
                        "schema_name": "cincosas_cincosas",
                        "table_name": "cinco_base_de_transportes",
                        "table_fqn": "cincosas_cincosas.cinco_base_de_transportes",
                        "rol": "dimension",
                        "es_principal": True,
                    }
                ],
                "columns": [],
                "relationships": [],
                "flags": {"sql_asistido_permitido": False},
                "company_context": {
                    "codigo_compania": "CINCO",
                    "dominios_oficiales": ["empleados", "ausentismo", "transporte"],
                    "dominios_operativos": ["empleados", "ausentismo"],
                },
            }
        )
        resolver = SemanticBusinessResolver(
            registry=_FakeRegistry(fake_domain),
            dictionary_tool=_FakeDictionaryTool(),
        )
        intent = StructuredQueryIntent(
            raw_query="Vehiculo asignado al tecnico",
            domain_code="transporte",
            operation="detail",
            template_id="detail_by_entity_and_period",
            filters={},
            group_by=[],
            metrics=[],
            confidence=0.7,
        )
        resolved = resolver.resolve_query(
            message=intent.raw_query,
            intent=intent,
            base_classification={"domain": "transporte"},
        )
        warnings = list(resolved.warnings or [])
        self.assertIn("domain_known_but_not_operational", warnings)
        scope = dict((resolved.semantic_context or {}).get("company_operational_scope") or {})
        self.assertTrue(bool(scope.get("domain_known")))
        self.assertFalse(bool(scope.get("domain_operational")))

    def test_semantic_business_resolver_rescues_personal_en_vacaciones_to_attendance(self):
        attendance_domain = _FakeDomain(
            raw_context={
                "tables": [
                    {
                        "schema_name": "cincosas_cincosas",
                        "table_name": "gestionh_ausentismo",
                        "table_fqn": "cincosas_cincosas.gestionh_ausentismo",
                        "rol": "hechos",
                        "es_principal": True,
                    },
                    {
                        "schema_name": "cincosas_cincosas",
                        "table_name": "cinco_base_de_personal",
                        "table_fqn": "cincosas_cincosas.cinco_base_de_personal",
                        "rol": "dimension",
                    },
                ],
                "columns": [
                    {
                        "table_name": "gestionh_ausentismo",
                        "column_name": "fecha_edit",
                        "nombre_columna_logico": "fecha_ausentismo",
                        "es_filtro": True,
                    },
                    {
                        "table_name": "gestionh_ausentismo",
                        "column_name": "justificacion",
                        "nombre_columna_logico": "justificacion",
                        "es_filtro": True,
                        "es_group_by": True,
                    },
                    {
                        "table_name": "gestionh_ausentismo",
                        "column_name": "cedula",
                        "nombre_columna_logico": "cedula",
                        "es_filtro": True,
                    },
                ],
                "relationships": [
                    {
                        "nombre_relacion": "ausentismo_empleado",
                        "condicion": "gestionh_ausentismo.cedula = cinco_base_de_personal.cedula",
                    }
                ],
                "flags": {"sql_asistido_permitido": False},
            }
        )
        employee_domain = _FakeDomain(
            raw_context={
                "tables": [
                    {
                        "schema_name": "cincosas_cincosas",
                        "table_name": "cinco_base_de_personal",
                        "table_fqn": "cincosas_cincosas.cinco_base_de_personal",
                        "rol": "dimension",
                        "es_principal": True,
                    }
                ],
                "columns": [
                    {
                        "table_name": "cinco_base_de_personal",
                        "column_name": "area",
                        "nombre_columna_logico": "area",
                        "es_group_by": True,
                    }
                ],
                "relationships": [],
                "flags": {"sql_asistido_permitido": False},
            }
        )
        resolver = SemanticBusinessResolver(
            registry=_DualRegistry(primary_domain=attendance_domain, employee_domain=employee_domain),
            dictionary_tool=_FakeDictionaryTool(),
        )
        intent = StructuredQueryIntent(
            raw_query="personal en vacaciones del 2026-04-01 al 2026-04-19",
            domain_code="empleados",
            operation="detail",
            template_id="detail_by_entity_and_period",
            filters={"estado_empleado": "VACACIONES"},
            group_by=[],
            metrics=[],
            confidence=0.8,
        )
        resolved = resolver.resolve_query(
            message=intent.raw_query,
            intent=intent,
            base_classification={"domain": "empleados"},
        )
        self.assertEqual(str(resolved.intent.domain_code or ""), "ausentismo")
        self.assertEqual(str((resolved.normalized_filters or {}).get("justificacion") or ""), "VACACIONES")
