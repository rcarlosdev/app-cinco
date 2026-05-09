from __future__ import annotations

import os
from unittest.mock import Mock, patch

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


class _ObservabilityStub:
    def __init__(self):
        self.events: list[dict] = []

    def record_event(self, *, event_type: str, source: str, meta: dict):
        self.events.append(
            {
                "event_type": event_type,
                "source": source,
                "meta": dict(meta or {}),
            }
        )


class QueryIntelligenceDomainRescueTests(SimpleTestCase):
    def test_bootstrap_prioritizes_inventory_for_saldo_empleado_but_not_information_employee(self):
        saldo = ChatApplicationService._bootstrap_classification(
            message="saldo empleado 98672304",
            session_context={"last_domain": "ausentismo", "last_needs_database": True},
        )
        info = ChatApplicationService._bootstrap_classification(
            message="informacion empleado 98672304",
            session_context={},
        )

        self.assertEqual(str(saldo.get("domain") or ""), "inventario_logistica")
        self.assertEqual(str(saldo.get("intent") or ""), "stock_balance")
        self.assertEqual(str(info.get("domain") or ""), "empleados")
        self.assertEqual(str(info.get("intent") or ""), "empleados_query")

    def test_resolve_query_intelligence_rescues_general_to_inventario(self):
        semantic_resolver = Mock()
        semantic_resolver.build_semantic_context.return_value = {
            "domain_code": "inventario_logistica",
            "tables": [{"table_name": "logistica_movimientos_entrada"}],
            "column_profiles": [],
            "dictionary": {"fields": [{"campo_logico": "bodega"}], "relations": []},
            "dictionary_seed": {"enabled": False, "status": "skipped"},
            "supports_sql_assisted": True,
        }
        resolved_intent = StructuredQueryIntent(
            raw_query="saldo bodega operacion_hfc",
            domain_code="inventario_logistica",
            operation="stock_balance",
            template_id="inventory_material_stock_by_warehouse",
            filters={"bodega": "operacion_hfc", "stock_scope": "bodega"},
            group_by=["bodega"],
            metrics=[],
            confidence=0.9,
        )
        semantic_resolver.resolve_query.return_value = ResolvedQuerySpec(
            intent=resolved_intent,
            semantic_context={"tables": [{"table_name": "logistica_movimientos_entrada"}]},
            normalized_filters={"bodega": "operacion_hfc", "stock_scope": "bodega"},
            normalized_period={},
            mapped_columns={"bodega": "bodega"},
            warnings=[],
        )

        intent_resolver = Mock()
        intent_resolver.resolve.return_value = resolved_intent

        execution_planner = Mock()
        execution_planner.plan.return_value = QueryExecutionPlan(
            strategy="sql_assisted",
            reason="inventory_material_stock_by_warehouse",
            domain_code="inventario_logistica",
            capability_id="inventory_stock_balance_by_warehouse",
            sql_query="SELECT codigo FROM logistica_movimientos_entrada LIMIT 100",
            constraints={"filters": {"bodega": "operacion_hfc", "stock_scope": "bodega"}},
            policy={"allowed": True},
            metadata={"capability_id": "inventory_stock_balance_by_warehouse"},
        )
        execution_planner.execute_sql_assisted.return_value = {
            "ok": True,
            "response": {"answer": "ok"},
            "used_legacy": False,
        }

        service = ChatApplicationService(
            semantic_business_resolver=semantic_resolver,
            query_intent_resolver=intent_resolver,
            query_execution_planner=execution_planner,
        )
        run_context = RunContext.create(message="saldo bodega operacion_hfc")
        observability = _ObservabilityStub()

        with patch.dict(
            os.environ,
            {
                "IA_DEV_QUERY_INTELLIGENCE_ENABLED": "1",
                "IA_DEV_QUERY_INTELLIGENCE_MODE": "active",
            },
            clear=False,
        ):
            payload = service._resolve_query_intelligence(
                message="saldo bodega operacion_hfc",
                base_classification={
                    "domain": "general",
                    "intent": "general_question",
                    "needs_database": False,
                },
                run_context=run_context,
                observability=observability,
            )

        self.assertEqual(payload.get("mode"), "active")
        self.assertEqual(str(payload.get("intent", {}).get("domain_code") or ""), "inventario_logistica")
        self.assertEqual(str(payload.get("intent", {}).get("operation") or ""), "stock_balance")
        self.assertEqual(str(payload.get("execution_plan", {}).get("strategy") or ""), "sql_assisted")
        self.assertEqual(
            str(payload.get("execution_plan", {}).get("capability_id") or ""),
            "inventory_stock_balance_by_warehouse",
        )
        called_domain = str(semantic_resolver.build_semantic_context.call_args.kwargs.get("domain_code") or "")
        self.assertEqual(called_domain, "inventario_logistica")
        self.assertTrue(any(item.get("event_type") == "pre_router_match" for item in observability.events))
        self.assertTrue(any(item.get("event_type") == "planner_called" for item in observability.events))
        self.assertTrue(any(item.get("event_type") == "semantic_context_loading" for item in observability.events))

    def test_memory_policy_blocks_cross_domain_hints_for_inventory(self):
        service = ChatApplicationService()
        run_context = RunContext.create(message="saldo bodega operacion_hfc")
        observability = _ObservabilityStub()

        filtered = service._apply_memory_policy(
            memory_hints={
                "personal_status": "activo",
                "query_patterns": [
                    {
                        "domain_code": "ausentismo",
                        "capability_id": "attendance.summary.by_attribute.v1",
                        "score": 0.91,
                    }
                ],
            },
            allowed_domain="inventario_logistica",
            capability_id="inventory_stock_balance_by_warehouse",
            run_context=run_context,
            observability=observability,
        )

        self.assertNotIn("personal_status", filtered)
        self.assertEqual(list(filtered.get("query_patterns") or []), [])
        self.assertEqual(str(filtered.get("cross_domain_memory_blocked_for") or ""), "inventario_logistica")
        self.assertTrue(any(item.get("event_type") == "memory_policy_applied" for item in observability.events))

    def test_saldo_bodega_operacion_hfc_does_not_use_ausentismo_memory_hint(self):
        semantic_resolver = Mock()
        semantic_resolver.build_semantic_context.return_value = {
            "domain_code": "inventario_logistica",
            "tables": [{"table_name": "logistica_movimientos_entrada"}],
            "column_profiles": [],
            "dictionary": {"fields": [{"campo_logico": "bodega"}], "relations": []},
            "dictionary_seed": {"enabled": False, "status": "skipped"},
            "supports_sql_assisted": True,
        }
        resolved_intent = StructuredQueryIntent(
            raw_query="saldo bodega operacion_hfc",
            domain_code="inventario_logistica",
            operation="stock_balance",
            template_id="inventory_material_stock_by_warehouse",
            filters={"bodega": "operacion_hfc"},
            group_by=["bodega"],
            metrics=[],
            confidence=0.91,
        )
        semantic_resolver.resolve_query.return_value = ResolvedQuerySpec(
            intent=resolved_intent,
            semantic_context={"tables": [{"table_name": "logistica_movimientos_entrada"}]},
            normalized_filters={"bodega": "operacion_hfc"},
            normalized_period={},
            mapped_columns={"bodega": "bodega"},
            warnings=[],
        )

        class _IntentResolver:
            def __init__(self):
                self.last_memory_hints = None

            def resolve(self, **kwargs):
                self.last_memory_hints = dict(kwargs.get("memory_hints") or {})
                return resolved_intent

        intent_resolver = _IntentResolver()
        execution_planner = Mock()
        execution_planner.plan.return_value = QueryExecutionPlan(
            strategy="sql_assisted",
            reason="inventory_material_stock_by_warehouse",
            domain_code="inventario_logistica",
            capability_id="inventory_stock_balance_by_warehouse",
            sql_query="SELECT 1",
            constraints={"filters": {"bodega": "operacion_hfc"}},
            policy={"allowed": True},
            metadata={"capability_id": "inventory_stock_balance_by_warehouse"},
        )

        service = ChatApplicationService(
            semantic_business_resolver=semantic_resolver,
            query_intent_resolver=intent_resolver,
            query_execution_planner=execution_planner,
        )
        run_context = RunContext.create(message="saldo bodega operacion_hfc")
        run_context.metadata["memory_context"] = {
            "hints": {
                "personal_status": "activo",
                "query_patterns": [
                    {
                        "domain_code": "ausentismo",
                        "capability_id": "attendance.summary.by_attribute.v1",
                        "score": 0.93,
                    }
                ]
            }
        }

        with patch.dict(
            os.environ,
            {
                "IA_DEV_QUERY_INTELLIGENCE_ENABLED": "1",
                "IA_DEV_QUERY_INTELLIGENCE_MODE": "active",
            },
            clear=False,
        ):
            service._resolve_query_intelligence(
                message="saldo bodega operacion_hfc",
                base_classification={
                    "domain": "general",
                    "intent": "general_question",
                    "needs_database": False,
                },
                run_context=run_context,
                observability=_ObservabilityStub(),
            )

        self.assertEqual(
            dict(intent_resolver.last_memory_hints or {}).get("query_patterns") or [],
            [],
        )
        self.assertNotIn("personal_status", dict(intent_resolver.last_memory_hints or {}))

    def test_resolve_query_intelligence_rescues_general_to_empleados(self):
        semantic_resolver = Mock()
        semantic_resolver.build_semantic_context.return_value = {
            "domain_code": "empleados",
            "tables": [{"table_name": "cinco_base_de_personal"}],
            "column_profiles": [],
            "dictionary_seed": {"enabled": False, "status": "skipped"},
        }
        resolved_intent = StructuredQueryIntent(
            raw_query="¿Cuántos colaboradores habilitados tenemos hoy?",
            domain_code="empleados",
            operation="count",
            template_id="count_entities_by_status",
            filters={},
            period={"label": "hoy", "start_date": "2026-04-16", "end_date": "2026-04-16"},
            group_by=[],
            metrics=["count"],
            confidence=0.9,
        )
        semantic_resolver.resolve_query.return_value = ResolvedQuerySpec(
            intent=resolved_intent,
            semantic_context={"tables": [{"table_name": "cinco_base_de_personal"}]},
            normalized_filters={"estado": "ACTIVO"},
            normalized_period={"label": "hoy", "start_date": "2026-04-16", "end_date": "2026-04-16"},
            mapped_columns={"estado": "estado"},
            warnings=[],
        )

        intent_resolver = Mock()
        intent_resolver.resolve.return_value = resolved_intent

        execution_planner = Mock()
        execution_planner.plan.return_value = QueryExecutionPlan(
            strategy="capability",
            reason="capability_selected_from_query_intelligence",
            domain_code="empleados",
            capability_id="empleados.count.active.v1",
            constraints={"filters": {"estado": "ACTIVO"}},
            policy={"allowed": True},
            metadata={"operation": "count"},
        )

        service = ChatApplicationService(
            semantic_business_resolver=semantic_resolver,
            query_intent_resolver=intent_resolver,
            query_execution_planner=execution_planner,
        )
        run_context = RunContext.create(message="¿Cuántos colaboradores habilitados tenemos hoy?")
        observability = _ObservabilityStub()

        with patch.dict(
            os.environ,
            {
                "IA_DEV_QUERY_INTELLIGENCE_ENABLED": "1",
                "IA_DEV_QUERY_INTELLIGENCE_MODE": "active",
            },
            clear=False,
        ):
            payload = service._resolve_query_intelligence(
                message="¿Cuántos colaboradores habilitados tenemos hoy?",
                base_classification={
                    "domain": "general",
                    "intent": "general_question",
                    "needs_database": False,
                },
                run_context=run_context,
                observability=observability,
            )

        self.assertEqual(payload.get("mode"), "active")
        self.assertEqual(str(payload.get("execution_plan", {}).get("strategy") or ""), "capability")
        self.assertNotEqual(str(payload.get("execution_plan", {}).get("strategy") or ""), "ask_context")

        called_domain = str(semantic_resolver.build_semantic_context.call_args.kwargs.get("domain_code") or "")
        self.assertEqual(called_domain, "empleados")
        self.assertTrue(any(item.get("event_type") == "query_domain_rescued" for item in observability.events))
