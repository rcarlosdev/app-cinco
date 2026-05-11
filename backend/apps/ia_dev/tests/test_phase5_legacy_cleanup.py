from __future__ import annotations

import ast
import inspect
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from apps.ia_dev.application.context.run_context import RunContext
from apps.ia_dev.application.contracts.query_intelligence_contracts import (
    QueryExecutionPlan,
    ResolvedQuerySpec,
    StructuredQueryIntent,
)
from apps.ia_dev.application.orchestration.chat_application_service import (
    ChatApplicationService,
)
from apps.ia_dev.application.semantic.query_execution_planner import QueryExecutionPlanner


def _pilot_context(*, include_relation: bool = True) -> dict:
    relations = []
    if include_relation:
        relations = [
            {
                "nombre_relacion": "ausentismo_empleado",
                "join_sql": "gestionh_ausentismo.cedula = cinco_base_de_personal.cedula",
            }
        ]
    return {
        "tables": [
            {"schema_name": "cincosas_cincosas", "table_name": "gestionh_ausentismo"},
            {"schema_name": "cincosas_cincosas", "table_name": "cinco_base_de_personal"},
        ],
        "column_profiles": [
            {"table_name": "gestionh_ausentismo", "logical_name": "fecha_ausentismo", "column_name": "fecha_edit"},
            {
                "table_name": "gestionh_ausentismo",
                "logical_name": "dias_perdidos",
                "column_name": "dias_perdidos",
                "supports_metric": True,
            },
            {"table_name": "cinco_base_de_personal", "logical_name": "area", "column_name": "area"},
            {"table_name": "cinco_base_de_personal", "logical_name": "cedula", "column_name": "cedula"},
        ],
        "allowed_tables": [
            "cincosas_cincosas.gestionh_ausentismo",
            "cincosas_cincosas.cinco_base_de_personal",
        ],
        "allowed_columns": ["fecha_edit", "dias_perdidos", "area", "cedula"],
        "dictionary": {"relations": relations},
        "source_of_truth": {
            "pilot_sql_assisted_enabled": True,
            "used_dictionary": True,
            "used_yaml": True,
        },
        "supports_sql_assisted": True,
        "domain_status": "partial",
    }


class Phase5LegacyCleanupTests(SimpleTestCase):
    def test_legacy_routing_modules_were_pruned_from_runtime_package(self):
        routing_dir = Path(__file__).resolve().parents[1] / "application" / "routing"

        self.assertFalse((routing_dir / "capability_planner.py").exists())
        self.assertFalse((routing_dir / "capability_router.py").exists())
        self.assertFalse((routing_dir / "intent_to_capability_bridge.py").exists())

    def test_attendance_skill_metadata_no_longer_declares_legacy_planner_consumer(self):
        meta_path = Path(__file__).resolve().parents[1] / "SKILLS" / "attendance" / "recurrence_analysis.meta.json"

        payload = json.loads(meta_path.read_text(encoding="utf-8"))

        self.assertNotIn("capability_planner", list(payload.get("consumers") or []))

    def test_chat_application_service_does_not_top_level_import_legacy_router_or_delegation(self):
        import apps.ia_dev.application.orchestration.chat_application_service as chat_module

        source = inspect.getsource(chat_module)
        tree = ast.parse(source)
        top_level_from_imports = {
            str(node.module or "")
            for node in tree.body
            if isinstance(node, ast.ImportFrom)
        }
        self.assertNotIn(
            "apps.ia_dev.application.routing.capability_router",
            top_level_from_imports,
        )
        self.assertNotIn(
            "apps.ia_dev.application.delegation.delegation_coordinator",
            top_level_from_imports,
        )

    def test_chat_view_does_not_top_level_import_public_orchestrator_adapter(self):
        import apps.ia_dev.views.chat_view as chat_view_module

        source = inspect.getsource(chat_view_module)
        tree = ast.parse(source)
        top_level_from_imports = {
            str(node.module or "")
            for node in tree.body
            if isinstance(node, ast.ImportFrom)
        }

        self.assertNotIn(
            "apps.ia_dev.services.orchestrator_service",
            top_level_from_imports,
        )

    def test_response_assembler_keeps_runtime_payload_without_capability_shadow(self):
        from apps.ia_dev.application.orchestration.response_assembler import ResponseAssembler

        assembler = ResponseAssembler()
        response = assembler.assemble(
            legacy_response={"reply": "ok", "orchestrator": {}, "data": {}, "data_sources": {}},
            run_context=RunContext.create(message="hola", session_id="sess-5", reset_memory=False),
            planned_capability={},
            route={},
            policy_decision=MagicMock(action=MagicMock(value="allow"), policy_id="p", reason="ok", metadata={}),
            divergence={},
            memory_effects={},
        )
        self.assertNotIn("capability_shadow", str(response))
        self.assertNotIn("proactive_loop", str(response))

    def test_covered_analytics_prefers_join_aware_sql_with_explicit_router_metadata(self):
        planner = QueryExecutionPlanner()
        resolved = ResolvedQuerySpec(
            intent=StructuredQueryIntent(
                raw_query="Que areas tienen mas ausentismo",
                domain_code="ausentismo",
                operation="aggregate",
                template_id="aggregate_by_group_and_period",
                group_by=["area"],
                metrics=["count"],
            ),
            semantic_context=_pilot_context(include_relation=True),
            normalized_period={"start_date": "2026-01-01", "end_date": "2026-01-31"},
        )

        with patch.dict(
            "os.environ",
            {
                "IA_DEV_QUERY_SQL_ASSISTED_ENABLED": "1",
                "IA_DEV_QUERY_INTELLIGENCE_ENABLED": "1",
                "IA_DEV_DISABLE_LEGACY_ANALYTICS_FALLBACK": "1",
            },
            clear=False,
        ):
            plan = planner.plan(
                run_context=RunContext.create(message=resolved.intent.raw_query),
                resolved_query=resolved,
            )

        self.assertEqual(plan.strategy, "sql_assisted")
        self.assertEqual(str((plan.metadata or {}).get("analytics_router_decision") or ""), "join_aware_sql")
        self.assertTrue(bool((plan.metadata or {}).get("legacy_analytics_isolated")))
        self.assertEqual(str((plan.metadata or {}).get("cleanup_phase") or ""), "phase_7")

    def test_flag_off_preserves_previous_capability_behavior(self):
        planner = QueryExecutionPlanner()
        resolved = ResolvedQuerySpec(
            intent=StructuredQueryIntent(
                raw_query="Que areas tienen mas ausentismo",
                domain_code="ausentismo",
                operation="aggregate",
                template_id="aggregate_by_group_and_period",
                group_by=["area"],
                metrics=["count"],
            ),
            semantic_context=_pilot_context(include_relation=False),
            normalized_period={"start_date": "2026-01-01", "end_date": "2026-01-31"},
        )

        with patch.dict(
            "os.environ",
            {
                "IA_DEV_QUERY_SQL_ASSISTED_ENABLED": "1",
                "IA_DEV_QUERY_INTELLIGENCE_ENABLED": "1",
                "IA_DEV_DISABLE_LEGACY_ANALYTICS_FALLBACK": "0",
                "IA_DEV_ATTENDANCE_EMPLOYEES_PILOT_ENABLED": "0",
            },
            clear=False,
        ):
            with patch.object(planner, "_is_capability_rollout_enabled", return_value=True):
                with patch.object(planner, "_build_sql_query", return_value=("", "pilot_relation_missing", {})):
                    plan = planner.plan(
                        run_context=RunContext.create(message=resolved.intent.raw_query),
                        resolved_query=resolved,
                    )

        self.assertEqual(plan.strategy, "capability")
        self.assertEqual(str(plan.capability_id or ""), "attendance.summary.by_area.v1")

    def test_covered_analytics_compiler_failure_blocks_legacy_and_returns_runtime_only_reason(self):
        planner = QueryExecutionPlanner()
        resolved = ResolvedQuerySpec(
            intent=StructuredQueryIntent(
                raw_query="Que areas tienen mas ausentismo",
                domain_code="ausentismo",
                operation="aggregate",
                template_id="aggregate_by_group_and_period",
                group_by=["area"],
                metrics=["count"],
            ),
            semantic_context=_pilot_context(include_relation=False),
            normalized_period={"start_date": "2026-01-01", "end_date": "2026-01-31"},
        )

        with patch.dict(
            "os.environ",
            {
                "IA_DEV_QUERY_SQL_ASSISTED_ENABLED": "1",
                "IA_DEV_QUERY_INTELLIGENCE_ENABLED": "1",
                "IA_DEV_DISABLE_LEGACY_ANALYTICS_FALLBACK": "1",
            },
            clear=False,
        ):
            with patch.object(planner, "_is_capability_rollout_enabled", return_value=True):
                with patch.object(planner, "_build_sql_query", return_value=("", "pilot_relation_missing", {})):
                    plan = planner.plan(
                        run_context=RunContext.create(message=resolved.intent.raw_query),
                        resolved_query=resolved,
                    )

        self.assertEqual(plan.strategy, "fallback")
        self.assertEqual(str(plan.reason or ""), "missing_dictionary_relation")
        self.assertTrue(bool((plan.metadata or {}).get("blocked_legacy_fallback")))
        self.assertTrue(bool((plan.metadata or {}).get("blocked_tool_ausentismo_service")))
        self.assertTrue(bool((plan.metadata or {}).get("blocked_run_legacy_for_analytics")))
        self.assertEqual(str((plan.metadata or {}).get("analytics_router_decision") or ""), "runtime_only_fallback")
        self.assertEqual(str((plan.metadata or {}).get("cleanup_phase") or ""), "phase_7")

    def test_runtime_only_fallback_does_not_call_legacy_runner_or_attendance_service(self):
        adapter = MagicMock()
        service = ChatApplicationService(capability_runtime_adapter=adapter)
        run_context = RunContext.create(message="Que areas tienen mas ausentismo", session_id="sess-clean", reset_memory=False)
        resolved = ResolvedQuerySpec(
            intent=StructuredQueryIntent(
                raw_query="Que areas tienen mas ausentismo",
                domain_code="ausentismo",
                operation="aggregate",
                template_id="aggregate_by_group_and_period",
                group_by=["area"],
                metrics=["count"],
            ),
            semantic_context=_pilot_context(include_relation=False),
            normalized_period={"start_date": "2026-01-01", "end_date": "2026-01-31"},
        )
        execution_plan = QueryExecutionPlan(
            strategy="fallback",
            reason="missing_dictionary_relation",
            domain_code="ausentismo",
            capability_id="attendance.summary.by_area.v1",
            metadata={
                "analytics_router_decision": "runtime_only_fallback",
                "legacy_analytics_isolated": True,
                "legacy_analytics_fallback_disabled": True,
                "blocked_legacy_fallback": True,
                "blocked_tool_ausentismo_service": True,
                "blocked_run_legacy_for_analytics": True,
                "runtime_only_fallback_reason": "missing_dictionary_relation",
                "fallback_reason": "pilot_relation_missing",
                "cleanup_phase": "phase_7",
            },
        )
        legacy_runner = MagicMock(side_effect=AssertionError("legacy should not be called"))

        result = service._execute_primary_path(
            message="Que areas tienen mas ausentismo",
            session_id="sess-clean",
            reset_memory=False,
            run_context=run_context,
            planned_capability={"capability_id": "attendance.summary.by_area.v1"},
            route={
                "selected_capability_id": "attendance.summary.by_area.v1",
                "execute_capability": True,
                "use_legacy": True,
                "reason": "capability_mode_attendance_execution_enabled",
            },
            legacy_runner=legacy_runner,
            observability=None,
            memory_context={},
            resolved_query=resolved,
            execution_plan=execution_plan,
            allow_legacy_fallback=True,
        )

        legacy_runner.assert_not_called()
        adapter.execute.assert_not_called()
        self.assertTrue(bool(result.get("blocked_legacy_fallback")))
        self.assertTrue(bool(result.get("blocked_tool_ausentismo_service")))
        self.assertTrue(bool(result.get("blocked_run_legacy_for_analytics")))
        self.assertFalse(bool(result.get("used_legacy")))
        self.assertEqual(str(result.get("runtime_only_fallback_reason") or ""), "missing_dictionary_relation")
        self.assertIn("ai_dictionary.dd_relaciones", str((result.get("response") or {}).get("reply") or ""))

    def test_modern_empleados_handler_keeps_legacy_available_for_non_migrated_routes(self):
        planner = QueryExecutionPlanner()
        empleados_resolved = ResolvedQuerySpec(
            intent=StructuredQueryIntent(
                raw_query="Que empleados cumplen anos en Mayo",
                domain_code="empleados",
                operation="detail",
                template_id="detail_by_entity_and_period",
                filters={"birth_month": "05"},
                metrics=["count"],
            ),
            semantic_context={"tables": [{"table_name": "cinco_base_de_personal"}]},
            normalized_filters={"birth_month": "05"},
            normalized_period={"label": "mayo"},
        )
        legacy_resolved = ResolvedQuerySpec(
            intent=StructuredQueryIntent(
                raw_query="Que alertas deberia revisar talento humano",
                domain_code="general",
                operation="summary",
                template_id="summary_alerts",
            ),
            semantic_context={"tables": []},
        )

        with patch.object(planner, "_resolve_capability_id", return_value="empleados.detail.v1"):
            with patch.object(planner, "_is_capability_rollout_enabled", return_value=True):
                empleados_plan = planner.plan(
                    run_context=RunContext.create(message=empleados_resolved.intent.raw_query),
                    resolved_query=empleados_resolved,
                )

        legacy_plan = planner.plan(
            run_context=RunContext.create(message=legacy_resolved.intent.raw_query),
            resolved_query=legacy_resolved,
        )

        self.assertEqual(empleados_plan.strategy, "capability")
        self.assertEqual(str((empleados_plan.metadata or {}).get("analytics_router_decision") or ""), "handler_modern")
        self.assertTrue(bool((empleados_plan.metadata or {}).get("legacy_analytics_isolated")))
        self.assertEqual(legacy_plan.strategy, "fallback")
        self.assertFalse(bool((legacy_plan.metadata or {}).get("legacy_analytics_isolated")))

    def test_runtime_only_fallback_supports_specific_reason_copy(self):
        service = ChatApplicationService(capability_runtime_adapter=MagicMock())
        run_context = RunContext.create(message="Que metrica nueva existe", session_id="sess-copy", reset_memory=False)

        response = service._build_runtime_only_fallback_response(
            run_context=run_context,
            resolved_query=None,
            runtime_execution_plan=None,
            fallback_reason="unsupported_metric",
        )

        self.assertEqual(
            str(((response.get("data_sources") or {}).get("query_intelligence") or {}).get("reason") or ""),
            "unsupported_metric",
        )
        self.assertIn("dd_campos", " ".join((response.get("data") or {}).get("insights") or []))

    def test_runtime_only_sql_failure_meta_blocks_legacy_after_join_aware_execution_error(self):
        service = ChatApplicationService(capability_runtime_adapter=MagicMock())
        execution_plan = QueryExecutionPlan(
            strategy="sql_assisted",
            reason="sql_assisted_ready",
            domain_code="ausentismo",
            capability_id="attendance.summary.by_area.v1",
            metadata={
                "analytics_router_decision": "join_aware_sql",
                "legacy_analytics_isolated": True,
                "cleanup_phase": "phase_7",
            },
        )
        resolved = ResolvedQuerySpec(
            intent=StructuredQueryIntent(
                raw_query="Que areas tienen mas ausentismo",
                domain_code="ausentismo",
                operation="aggregate",
                template_id="aggregate_by_group_and_period",
            ),
            semantic_context=_pilot_context(include_relation=True),
        )

        metadata = service._build_runtime_only_sql_failure_meta(
            execution_plan=execution_plan,
            resolved_query=resolved,
            execution_result={"ok": False, "error": "sql_execution_error:timeout"},
        )

        self.assertEqual(str(metadata.get("analytics_router_decision") or ""), "runtime_only_fallback")
        self.assertEqual(str(metadata.get("runtime_only_fallback_reason") or ""), "unsafe_sql_plan")
        self.assertTrue(bool(metadata.get("blocked_tool_ausentismo_service")))
        self.assertTrue(bool(metadata.get("blocked_run_legacy_for_analytics")))
