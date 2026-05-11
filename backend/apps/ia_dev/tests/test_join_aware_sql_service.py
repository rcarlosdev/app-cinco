from __future__ import annotations

import os
from django.test import SimpleTestCase
from unittest.mock import patch

from apps.ia_dev.application.contracts.query_intelligence_contracts import (
    ResolvedQuerySpec,
    StructuredQueryIntent,
)
from apps.ia_dev.application.policies.query_execution_policy import QueryExecutionPolicy
from apps.ia_dev.application.semantic.join_aware_sql_service import JoinAwarePilotSqlService
from apps.ia_dev.application.semantic.query_execution_planner import QueryExecutionPlanner


def _pilot_semantic_context() -> dict:
    return {
        "tables": [
            {"schema_name": "cincosas_cincosas", "table_name": "gestionh_ausentismo"},
            {"schema_name": "cincosas_cincosas", "table_name": "cinco_base_de_personal"},
        ],
        "column_profiles": [
            {"table_name": "gestionh_ausentismo", "logical_name": "fecha_ausentismo", "column_name": "fecha_edit"},
            {"table_name": "gestionh_ausentismo", "logical_name": "justificacion", "column_name": "justificacion"},
            {
                "table_name": "gestionh_ausentismo",
                "logical_name": "dias_perdidos",
                "column_name": "dias_perdidos",
                "supports_metric": True,
            },
            {"table_name": "cinco_base_de_personal", "logical_name": "area", "column_name": "area"},
            {"table_name": "cinco_base_de_personal", "logical_name": "cargo", "column_name": "cargo"},
            {"table_name": "cinco_base_de_personal", "logical_name": "sede", "column_name": "sede"},
            {"table_name": "cinco_base_de_personal", "logical_name": "nombre", "column_name": "nombre"},
            {"table_name": "cinco_base_de_personal", "logical_name": "apellido", "column_name": "apellido"},
            {"table_name": "cinco_base_de_personal", "logical_name": "cedula", "column_name": "cedula"},
        ],
        "allowed_tables": [
            "cincosas_cincosas.gestionh_ausentismo",
            "cincosas_cincosas.cinco_base_de_personal",
        ],
        "allowed_columns": [
            "fecha_edit",
            "justificacion",
            "area",
            "cargo",
            "sede",
            "nombre",
            "apellido",
            "cedula",
            "dias_perdidos",
        ],
        "dictionary": {
            "relations": [
                {
                    "nombre_relacion": "ausentismo_empleado",
                    "join_sql": "gestionh_ausentismo.cedula = cinco_base_de_personal.cedula",
                }
            ]
        },
        "synonym_index": {"areas": "area", "cargos": "cargo", "empleados": "empleado"},
        "aliases": {"areas": "area", "cargos": "cargo"},
        "source_of_truth": {
            "pilot_sql_assisted_enabled": True,
            "used_dictionary": True,
            "used_yaml": True,
        },
        "supports_sql_assisted": True,
        "domain_status": "active",
    }


class JoinAwarePilotSqlServiceTests(SimpleTestCase):
    def test_compile_generates_joined_area_query(self):
        service = JoinAwarePilotSqlService()
        resolved = ResolvedQuerySpec(
            intent=StructuredQueryIntent(
                raw_query="Que areas tienen mas ausentismo",
                domain_code="ausentismo",
                operation="aggregate",
                template_id="aggregate_by_group_and_period",
                group_by=["area"],
                metrics=["count"],
            ),
            semantic_context=_pilot_semantic_context(),
            normalized_period={"start_date": "2026-01-01", "end_date": "2026-01-31"},
        )

        compiled = service.compile(resolved_query=resolved, max_limit=50)

        self.assertTrue(compiled.get("ok"))
        self.assertIn("JOIN cincosas_cincosas.cinco_base_de_personal AS e", str(compiled.get("sql_query") or ""))
        self.assertIn("GROUP BY e.area", str(compiled.get("sql_query") or ""))
        metadata = dict(compiled.get("metadata") or {})
        self.assertEqual(str(metadata.get("compiler_used") or ""), "join_aware_pilot")
        self.assertIn("area", list(metadata.get("physical_columns_used") or []))

    def test_compile_uses_sum_metric_for_dias_perdidos(self):
        service = JoinAwarePilotSqlService()
        resolved = ResolvedQuerySpec(
            intent=StructuredQueryIntent(
                raw_query="Que areas tienen mas dias perdidos",
                domain_code="ausentismo",
                operation="aggregate",
                template_id="aggregate_by_group_and_period",
                group_by=["area"],
                metrics=["sum:dias_perdidos"],
            ),
            semantic_context=_pilot_semantic_context(),
            normalized_period={"start_date": "2026-01-01", "end_date": "2026-01-31"},
        )

        compiled = service.compile(resolved_query=resolved, max_limit=50)

        self.assertTrue(compiled.get("ok"))
        self.assertIn("SUM(COALESCE(a.dias_perdidos, 0))", str(compiled.get("sql_query") or ""))
        metadata = dict(compiled.get("metadata") or {})
        self.assertEqual(str(metadata.get("metric_used") or ""), "dias_perdidos")
        self.assertEqual(str(metadata.get("aggregation_used") or ""), "sum")
        self.assertEqual(str(metadata.get("declared_metric_source") or ""), "ai_dictionary.dd_campos")

    def test_compile_supports_up_to_three_dimensions(self):
        service = JoinAwarePilotSqlService()
        resolved = ResolvedQuerySpec(
            intent=StructuredQueryIntent(
                raw_query="Que patrones existen por area, cargo y sede",
                domain_code="ausentismo",
                operation="aggregate",
                template_id="aggregate_by_group_and_period",
                group_by=["area", "cargo", "sede"],
                metrics=["count"],
            ),
            semantic_context=_pilot_semantic_context(),
            normalized_period={"start_date": "2026-01-01", "end_date": "2026-01-31"},
        )

        compiled = service.compile(resolved_query=resolved, max_limit=50)

        self.assertTrue(compiled.get("ok"))
        sql_query = str(compiled.get("sql_query") or "")
        self.assertIn("SELECT e.area AS area, e.cargo AS cargo, e.sede AS sede, COUNT(*) AS total_ausentismos", sql_query)
        self.assertIn("GROUP BY e.area, e.cargo, e.sede", sql_query)
        metadata = dict(compiled.get("metadata") or {})
        self.assertEqual(list(metadata.get("dimensions_used") or []), ["area", "cargo", "sede"])

    def test_compile_rejects_metric_not_declared(self):
        service = JoinAwarePilotSqlService()
        context = _pilot_semantic_context()
        context["allowed_columns"] = [item for item in list(context.get("allowed_columns") or []) if item != "dias_perdidos"]
        resolved = ResolvedQuerySpec(
            intent=StructuredQueryIntent(
                raw_query="Que areas tienen mas dias perdidos",
                domain_code="ausentismo",
                operation="aggregate",
                template_id="aggregate_by_group_and_period",
                group_by=["area"],
                metrics=["sum:dias_perdidos"],
            ),
            semantic_context=context,
            normalized_period={"start_date": "2026-01-01", "end_date": "2026-01-31"},
        )

        compiled = service.compile(resolved_query=resolved, max_limit=50)

        self.assertFalse(bool(compiled.get("ok")))
        self.assertEqual(str(compiled.get("reason") or ""), "no_metric_column_declared")

    def test_compile_rejects_dimension_not_allowed(self):
        service = JoinAwarePilotSqlService()
        resolved = ResolvedQuerySpec(
            intent=StructuredQueryIntent(
                raw_query="Que patrones existen por area y supervisor",
                domain_code="ausentismo",
                operation="aggregate",
                template_id="aggregate_by_group_and_period",
                group_by=["area", "supervisor"],
                metrics=["count"],
            ),
            semantic_context=_pilot_semantic_context(),
            normalized_period={"start_date": "2026-01-01", "end_date": "2026-01-31"},
        )

        compiled = service.compile(resolved_query=resolved, max_limit=50)

        self.assertFalse(bool(compiled.get("ok")))
        self.assertEqual(str(compiled.get("reason") or ""), "no_allowed_dimension")

    def test_compile_rejects_more_than_three_dimensions(self):
        service = JoinAwarePilotSqlService()
        resolved = ResolvedQuerySpec(
            intent=StructuredQueryIntent(
                raw_query="Que patrones existen por area, cargo, sede y fecha",
                domain_code="ausentismo",
                operation="aggregate",
                template_id="aggregate_by_group_and_period",
                group_by=["area", "cargo", "sede", "fecha"],
                metrics=["count"],
            ),
            semantic_context=_pilot_semantic_context(),
            normalized_period={"start_date": "2026-01-01", "end_date": "2026-01-31"},
        )

        compiled = service.compile(resolved_query=resolved, max_limit=50)

        self.assertFalse(bool(compiled.get("ok")))
        self.assertEqual(str(compiled.get("reason") or ""), "max_dimensions_exceeded")

    def test_query_execution_planner_prefers_pilot_sql_when_safe(self):
        planner = QueryExecutionPlanner()
        resolved = ResolvedQuerySpec(
            intent=StructuredQueryIntent(
                raw_query="Que empleados tienen mas riesgo",
                domain_code="ausentismo",
                operation="aggregate",
                template_id="aggregate_by_group_and_period",
                metrics=["count"],
            ),
            semantic_context=_pilot_semantic_context(),
            normalized_period={"start_date": "2026-01-01", "end_date": "2026-01-31"},
        )

        sql_query, reason, metadata = planner._build_sql_query(resolved_query=resolved)

        self.assertIn("nivel_riesgo", sql_query)
        self.assertEqual(reason, "pilot_join_aware_empleado")
        self.assertEqual(str(metadata.get("compiler") or ""), "join_aware_pilot")

    def test_compile_rejects_runtime_only_relation_when_dictionary_relation_missing(self):
        service = JoinAwarePilotSqlService()
        context = _pilot_semantic_context()
        context["dictionary"] = {"relations": []}
        context["relation_profiles"] = [
            {
                "relation_name": "yaml_only_relation",
                "join_sql": "gestionh_ausentismo.cedula = cinco_base_de_personal.cedula",
            }
        ]
        resolved = ResolvedQuerySpec(
            intent=StructuredQueryIntent(
                raw_query="Que areas tienen mas ausentismo",
                domain_code="ausentismo",
                operation="aggregate",
                template_id="aggregate_by_group_and_period",
                group_by=["area"],
                metrics=["count"],
            ),
            semantic_context=context,
            normalized_period={"start_date": "2026-01-01", "end_date": "2026-01-31"},
        )

        compiled = service.compile(resolved_query=resolved, max_limit=50)

        self.assertFalse(bool(compiled.get("ok")))
        self.assertEqual(str(compiled.get("reason") or ""), "pilot_relation_missing")

    def test_query_policy_rejects_unregistered_column_from_compiler_metadata(self):
        decision = QueryExecutionPolicy().validate_sql_query(
            query="SELECT e.area AS area FROM cincosas_cincosas.cinco_base_de_personal AS e LIMIT 10",
            allowed_tables=["cincosas_cincosas.cinco_base_de_personal"],
            allowed_columns=["cedula"],
            declared_columns=["area"],
            max_limit=50,
        )

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, "sql_uses_unregistered_column")

    def test_query_policy_rejects_unregistered_relation_from_compiler_metadata(self):
        decision = QueryExecutionPolicy().validate_sql_query(
            query=(
                "SELECT COUNT(*) AS total "
                "FROM cincosas_cincosas.gestionh_ausentismo AS a "
                "JOIN cincosas_cincosas.cinco_base_de_personal AS e ON a.cedula = e.cedula "
                "LIMIT 10"
            ),
            allowed_tables=[
                "cincosas_cincosas.gestionh_ausentismo",
                "cincosas_cincosas.cinco_base_de_personal",
            ],
            allowed_columns=["cedula"],
            allowed_relations=["gestionh_ausentismo.id_empleado = cinco_base_de_personal.id_empleado"],
            declared_columns=["cedula"],
            declared_relations=["gestionh_ausentismo.cedula = cinco_base_de_personal.cedula"],
            max_limit=50,
        )

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, "sql_uses_unregistered_relation")

    def test_query_execution_planner_falls_back_safely_when_compiler_cannot_resolve(self):
        planner = QueryExecutionPlanner()
        context = _pilot_semantic_context()
        context["dictionary"] = {"relations": []}
        resolved = ResolvedQuerySpec(
            intent=StructuredQueryIntent(
                raw_query="Que empleados tienen mas riesgo",
                domain_code="ausentismo",
                operation="aggregate",
                template_id="aggregate_by_group_and_period",
                metrics=["count"],
            ),
            semantic_context=context,
            normalized_period={"start_date": "2026-01-01", "end_date": "2026-01-31"},
        )

        with patch.dict(
            os.environ,
            {
                "IA_DEV_QUERY_SQL_ASSISTED_ENABLED": "1",
                "IA_DEV_QUERY_INTELLIGENCE_ENABLED": "1",
            },
            clear=False,
        ):
            with patch.object(planner, "_is_capability_rollout_enabled", return_value=False):
                plan = planner.plan(
                    run_context=type("RunContextStub", (), {"routing_mode": "capability"})(),
                    resolved_query=resolved,
                )

        self.assertEqual(plan.strategy, "fallback")
        self.assertEqual(str(plan.reason or ""), "handler_not_available")
