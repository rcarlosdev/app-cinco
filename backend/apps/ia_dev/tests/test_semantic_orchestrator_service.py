from __future__ import annotations

from django.test import SimpleTestCase

from apps.ia_dev.application.context.run_context import RunContext
from apps.ia_dev.application.semantic.semantic_orchestrator_service import (
    SemanticOrchestratorService,
)
from apps.ia_dev.infrastructure.ai.openai_gateway_contracts import (
    OpenAIGatewayResponse,
    OpenAIToolLoopResult,
)


def _inventory_dictionary_summary() -> dict:
    return {
        "table_names": [
            "base_codigos",
            "cinco_base_de_personal",
            "logistica_movimientos_entrada",
            "logistica_movimientos_entrega",
            "logistica_movimientos_devolucion",
            "logistica_movimientos_consumo",
            "logistica_movimientos_cobro",
            "logistica_movimientos_traslado",
            "logistica_base_seriales",
            "logistica_seriales_asociados",
            "a_promedios_consumo",
            "bd_c3nc4s1s.facturacion_facturado_wfm",
        ],
        "column_names": ["bodega", "codigo", "serial", "cedula", "movil", "orden_trabajo", "nombre", "apellido"],
        "joins": [
            {
                "from_table": "logistica_movimientos_consumo",
                "to_table": "a_promedios_consumo",
                "join_sql": "logistica_movimientos_consumo.orden_trabajo = a_promedios_consumo.ot",
            },
            {
                "from_table": "a_promedios_consumo",
                "to_table": "bd_c3nc4s1s.facturacion_facturado_wfm",
                "join_sql": "a_promedios_consumo.ot = bd_c3nc4s1s.facturacion_facturado_wfm.ot",
            },
            {
                "from_table": "logistica_movimientos_consumo",
                "to_table": "cinco_base_de_personal",
                "join_sql": "logistica_movimientos_consumo.cedula = cinco_base_de_personal.cedula",
            },
        ],
    }


class SemanticOrchestratorServiceTests(SimpleTestCase):
    def test_inventory_natural_query_produces_valid_governed_json(self):
        service = SemanticOrchestratorService()

        result = service.orchestrate(
            user_message="cuánto tengo en operación hfc",
            candidate_domain="inventario_logistica",
            candidate_agent="inventario_logistica_agent",
            agent_contract=None,
            ai_dictionary_summary=_inventory_dictionary_summary(),
            domain_semantic_summary={"business_rules": ["dictionary_table_mapping_required"]},
            memory_context={},
            route_debug_hints={},
        )

        self.assertEqual(str(result.get("domain") or ""), "inventario_logistica")
        self.assertEqual(str(result.get("agent_id") or ""), "inventario_logistica_agent")
        self.assertEqual(str(result.get("intent") or ""), "inventory_stock_by_warehouse")
        self.assertEqual(str(result.get("capability") or ""), "inventory_stock_balance_by_warehouse")
        self.assertEqual(str(result.get("recommended_route") or ""), "sql_assisted")
        self.assertEqual(str((result.get("filters") or {}).get("bodega") or ""), "operacion_hfc")
        self.assertGreaterEqual(float(result.get("confidence") or 0.0), 0.65)

    def test_orchestrator_cannot_invent_table(self):
        service = SemanticOrchestratorService(
            llm_resolver=lambda **_: {
                "domain": "inventario_logistica",
                "agent_id": "inventario_logistica_agent",
                "intent": "inventory_kardex",
                "capability": "inventory_kardex_consolidated",
                "confidence": 0.91,
                "filters": {"codigo": "ABC"},
                "entities": {},
                "dimensions": [],
                "metrics": [],
                "required_tables": ["tabla_inventada"],
                "required_joins": [],
                "business_rules": [],
                "risk_flags": [],
                "needs_clarification": False,
                "clarification_question": None,
                "recommended_route": "sql_assisted",
                "reasoning_summary": "x",
                "scope": "general",
                "user_response_strategy": {"tone": "business", "sections": [], "warnings_to_include": [], "next_best_action": ""},
            }
        )

        result = service.orchestrate(
            user_message="kardex del código ABC",
            candidate_domain="inventario_logistica",
            candidate_agent="inventario_logistica_agent",
            agent_contract=None,
            ai_dictionary_summary=_inventory_dictionary_summary(),
            domain_semantic_summary={},
            memory_context={},
            route_debug_hints={},
        )

        self.assertNotIn("tabla_inventada", list(result.get("required_tables") or []))
        self.assertIn("table_not_governed", list(result.get("risk_flags") or []))

    def test_orchestrator_cannot_invent_column(self):
        service = SemanticOrchestratorService(
            llm_resolver=lambda **_: {
                "domain": "inventario_logistica",
                "agent_id": "inventario_logistica_agent",
                "intent": "inventory_kardex",
                "capability": "inventory_kardex_consolidated",
                "confidence": 0.91,
                "filters": {"columna_inventada": "ABC", "codigo": "ABC"},
                "entities": {},
                "dimensions": [],
                "metrics": [],
                "required_tables": ["logistica_movimientos_entrada"],
                "required_joins": [],
                "business_rules": [],
                "risk_flags": [],
                "needs_clarification": False,
                "clarification_question": None,
                "recommended_route": "sql_assisted",
                "reasoning_summary": "x",
                "scope": "general",
                "user_response_strategy": {"tone": "business", "sections": [], "warnings_to_include": [], "next_best_action": ""},
            }
        )

        result = service.orchestrate(
            user_message="kardex del código ABC",
            candidate_domain="inventario_logistica",
            candidate_agent="inventario_logistica_agent",
            agent_contract=None,
            ai_dictionary_summary=_inventory_dictionary_summary(),
            domain_semantic_summary={},
            memory_context={},
            route_debug_hints={},
        )

        self.assertNotIn("columna_inventada", dict(result.get("filters") or {}))
        self.assertIn("unsupported_filter", list(result.get("risk_flags") or []))

    def test_orchestrator_cannot_decide_execute_true(self):
        service = SemanticOrchestratorService()
        result = service.orchestrate(
            user_message="información empleado 98672304",
            candidate_domain="empleados",
            candidate_agent="empleados_agent",
            agent_contract=None,
            ai_dictionary_summary={"table_names": ["cinco_base_de_personal"], "column_names": ["cedula"], "joins": []},
            domain_semantic_summary={},
            memory_context={},
            route_debug_hints={},
        )

        self.assertNotIn("execute", result)

    def test_route_is_validated_against_agent_contract(self):
        service = SemanticOrchestratorService(
            llm_resolver=lambda **_: {
                "domain": "empleados",
                "agent_id": "empleados_agent",
                "intent": "employee_detail",
                "capability": "empleados.detail.v1",
                "confidence": 0.95,
                "filters": {"cedula": "98672304"},
                "entities": {"cedula": "98672304"},
                "dimensions": [],
                "metrics": [],
                "required_tables": ["cinco_base_de_personal"],
                "required_joins": [],
                "business_rules": [],
                "risk_flags": [],
                "needs_clarification": False,
                "clarification_question": None,
                "recommended_route": "sql_assisted",
                "reasoning_summary": "x",
                "scope": "persona_operativa",
                "user_response_strategy": {"tone": "business", "sections": [], "warnings_to_include": [], "next_best_action": ""},
            }
        )

        result = service.orchestrate(
            user_message="información empleado 98672304",
            candidate_domain="empleados",
            candidate_agent="empleados_agent",
            agent_contract=None,
            ai_dictionary_summary={"table_names": ["cinco_base_de_personal"], "column_names": ["cedula"], "joins": []},
            domain_semantic_summary={},
            memory_context={},
            route_debug_hints={},
        )

        self.assertEqual(str(result.get("recommended_route") or ""), "handler")

    def test_ambiguous_query_requires_clarification(self):
        service = SemanticOrchestratorService()
        result = service.orchestrate(
            user_message="información o saldo empleado 98672304",
            candidate_domain="empleados",
            candidate_agent="empleados_agent",
            agent_contract=None,
            ai_dictionary_summary={"table_names": ["cinco_base_de_personal"], "column_names": ["cedula"], "joins": []},
            domain_semantic_summary={},
            memory_context={},
            route_debug_hints={},
        )

        self.assertTrue(bool(result.get("needs_clarification")))
        self.assertEqual(str(result.get("recommended_route") or ""), "needs_clarification")

    def test_saldo_empleado_routes_to_inventory(self):
        service = SemanticOrchestratorService()
        result = service.orchestrate(
            user_message="saldo empleado 98672304",
            candidate_domain="empleados",
            candidate_agent="empleados_agent",
            agent_contract=None,
            ai_dictionary_summary=_inventory_dictionary_summary(),
            domain_semantic_summary={},
            memory_context={},
            route_debug_hints={},
        )

        self.assertEqual(str(result.get("domain") or ""), "inventario_logistica")
        self.assertEqual(str(result.get("agent_id") or ""), "inventario_logistica_agent")

    def test_inventory_cross_with_employee_data_keeps_inventory_priority(self):
        service = SemanticOrchestratorService()
        result = service.orchestrate(
            user_message="inventario de la cuadrilla TIRAN224 con datos del empleado",
            candidate_domain="ausentismo",
            candidate_agent="ausentismo_agent",
            agent_contract=None,
            ai_dictionary_summary=_inventory_dictionary_summary(),
            domain_semantic_summary={},
            memory_context={},
            route_debug_hints={},
        )

        self.assertEqual(str(result.get("domain") or ""), "inventario_logistica")
        self.assertEqual(str(result.get("capability") or ""), "inventory_stock_balance_by_mobile")

    def test_inventory_governed_matcher_handles_real_variation_for_movil(self):
        service = SemanticOrchestratorService()
        result = service.orchestrate(
            user_message="muéstrame lo que tiene el móvil TIRAN224",
            candidate_domain="general",
            candidate_agent="inventario_logistica_agent",
            agent_contract=None,
            ai_dictionary_summary=_inventory_dictionary_summary(),
            domain_semantic_summary={},
            memory_context={},
            route_debug_hints={},
        )

        self.assertEqual(str(result.get("domain") or ""), "inventario_logistica")
        self.assertEqual(str(result.get("capability") or ""), "inventory_stock_balance_by_mobile")
        self.assertEqual(str((result.get("filters") or {}).get("movil") or ""), "TIRAN224")

    def test_inventory_governed_matcher_requires_clarification_for_name_only(self):
        service = SemanticOrchestratorService()
        result = service.orchestrate(
            user_message="qué tiene Juan Pérez",
            candidate_domain="general",
            candidate_agent="inventario_logistica_agent",
            agent_contract=None,
            ai_dictionary_summary=_inventory_dictionary_summary(),
            domain_semantic_summary={},
            memory_context={},
            route_debug_hints={},
        )

        self.assertTrue(bool(result.get("needs_clarification")))
        self.assertEqual(str(result.get("recommended_route") or ""), "needs_clarification")

    def test_inventory_governed_matcher_declares_sap_acta_limitation(self):
        service = SemanticOrchestratorService()
        result = service.orchestrate(
            user_message="actas SAP del empleado 5098747",
            candidate_domain="inventario_logistica",
            candidate_agent="inventario_logistica_agent",
            agent_contract=None,
            ai_dictionary_summary=_inventory_dictionary_summary(),
            domain_semantic_summary={},
            memory_context={},
            route_debug_hints={},
        )

        self.assertEqual(str(result.get("domain") or ""), "inventario_logistica")
        self.assertEqual(str(result.get("capability") or ""), "inventory_document_generation_pending")
        self.assertEqual(str(result.get("recommended_route") or ""), "external_pending")

    def test_native_tool_loop_persists_trace_without_moving_runtime_authority(self):
        run_context = RunContext.create(
            message="inventario de la cuadrilla TIRAN224 con datos del empleado",
            session_id="sess-native-tools",
            reset_memory=False,
        )

        class _Gateway:
            @staticmethod
            def create(request):
                raise AssertionError("No debe usar create directo cuando el loop nativo esta habilitado")

            @staticmethod
            def run_function_tool_loop(*, request, tool_executor, max_rounds=4, on_tool_result=None):
                tool_executor(
                    {
                        "name": "semantic_orchestrator.dictionary_summary.v1",
                        "call_id": "call_dict_1",
                        "arguments": {"focus": "joins"},
                    }
                )
                if callable(on_tool_result):
                    on_tool_result(
                        {
                            "tool_call_id": "call_dict_1",
                            "tool_name": "semantic_orchestrator.dictionary_summary.v1",
                            "arguments": {"focus": "joins"},
                            "execution_status": "completed",
                            "validation_status": "validated",
                            "duration_ms": 3,
                            "evidence_metadata": {"source": "test"},
                            "output_payload": {"table_names": ["base_codigos"]},
                            "model_response_id": "resp_native_1",
                            "loop_iteration": 1,
                            "started_at": "2026-05-16T00:00:00+00:00",
                            "finished_at": "2026-05-16T00:00:00+00:00",
                        }
                    )
                return OpenAIToolLoopResult(
                    response=OpenAIGatewayResponse(
                        response={},
                        output_text=json_payload,
                        model="gpt-test",
                        model_source="explicit",
                        response_id="resp_native_2",
                        usage={},
                        metadata={},
                        output_items=[],
                        function_calls=[],
                    ),
                    tool_traces=[
                        {
                            "tool_call_id": "call_dict_1",
                            "tool_name": "semantic_orchestrator.dictionary_summary.v1",
                        }
                    ],
                    response_ids=["resp_native_1", "resp_native_2"],
                    turns=2,
                )

        json_payload = """{
            "domain": "inventario_logistica",
            "agent_id": "inventario_logistica_agent",
            "intent": "inventory_stock_by_mobile",
            "capability": "inventory_stock_balance_by_mobile",
            "confidence": 0.93,
            "scope": "persona_operativa",
            "filters": {"movil": "TIRAN224"},
            "entities": {"movil": "TIRAN224"},
            "dimensions": [],
            "metrics": ["cantidad"],
            "required_tables": ["base_codigos"],
            "required_joins": [],
            "business_rules": [],
            "risk_flags": [],
            "needs_clarification": false,
            "clarification_question": null,
            "recommended_route": "sql_assisted",
            "reasoning_summary": "ok",
            "user_response_strategy": {"tone": "business", "sections": [], "warnings_to_include": [], "next_best_action": ""}
        }"""

        service = SemanticOrchestratorService(gateway=_Gateway())
        result = service.orchestrate(
            user_message="inventario de la cuadrilla TIRAN224 con datos del empleado",
            candidate_domain="inventario_logistica",
            candidate_agent="inventario_logistica_agent",
            agent_contract=None,
            ai_dictionary_summary=_inventory_dictionary_summary(),
            domain_semantic_summary={},
            memory_context={},
            route_debug_hints={},
            run_context=run_context,
            observability=None,
        )

        self.assertEqual(str(result.get("capability") or ""), "inventory_stock_balance_by_mobile")
        self.assertEqual(len(list(run_context.metadata.get("response_native_tool_trace") or [])), 1)
        loop_meta = dict(run_context.metadata.get("response_native_tool_loop") or {})
        self.assertEqual(int(loop_meta.get("turns") or 0), 2)
        self.assertEqual(str((list(run_context.metadata.get("response_native_tool_trace") or [])[0] or {}).get("tool_call_id") or ""), "call_dict_1")

    def test_informacion_empleado_routes_to_empleados(self):
        service = SemanticOrchestratorService()
        result = service.orchestrate(
            user_message="información empleado 98672304",
            candidate_domain="inventario_logistica",
            candidate_agent="inventario_logistica_agent",
            agent_contract=None,
            ai_dictionary_summary={"table_names": ["cinco_base_de_personal"], "column_names": ["cedula"], "joins": []},
            domain_semantic_summary={},
            memory_context={},
            route_debug_hints={},
        )

        self.assertEqual(str(result.get("domain") or ""), "empleados")
        self.assertEqual(str(result.get("agent_id") or ""), "empleados_agent")
