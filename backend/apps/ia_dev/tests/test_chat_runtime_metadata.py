from __future__ import annotations

import os
import inspect
from unittest.mock import patch

from django.test import SimpleTestCase

from apps.ia_dev.application.context.run_context import RunContext
from apps.ia_dev.application.contracts.query_intelligence_contracts import (
    QueryExecutionPlan,
    ResolvedQuerySpec,
    StructuredQueryIntent,
)
from apps.ia_dev.application.orchestration.response_assembler import ResponseAssembler
from apps.ia_dev.application.orchestration.chat_application_service import ChatApplicationService


class _ObservabilityStub:
    def __init__(self):
        self.events: list[dict] = []

    def record_event(self, *, event_type: str, source: str, meta: dict):
        self.events.append({"event_type": event_type, "source": source, "meta": dict(meta or {})})


class ChatRuntimeMetadataTests(SimpleTestCase):
    def test_response_assembler_preserves_existing_business_response(self):
        assembler = ResponseAssembler()
        response = {
            "reply": "12 certificados de alturas vencidos y 7 proximos a vencer.",
            "data": {
                "business_response": {
                    "dato": "12 certificados de alturas vencidos y 7 proximos a vencer.",
                    "hallazgo": "El personal operativo activo tiene riesgo documental si hay certificados vencidos.",
                    "interpretacion": "La vigencia anual del certificado de alturas impacta la habilitacion operativa.",
                    "riesgo": "Tecnicos con certificado vencido no deberian ser asignados a trabajos en alturas.",
                    "recomendacion": "Priorizar renovacion de vencidos y programar renovacion de proximos a vencer.",
                    "siguiente_accion": "Muestrame el detalle por empleado, area o supervisor.",
                },
                "table": {"columns": [], "rows": [], "rowcount": 0},
                "insights": [],
                "findings": [],
                "kpis": {},
            },
            "actions": [],
            "trace": [],
            "data_sources": {},
        }

        assembled = assembler.assemble(
            legacy_response=response,
            run_context=RunContext.create(message="certificados de alturas", session_id="heights", reset_memory=False),
            planned_capability={},
            route={},
            policy_decision=None,  # type: ignore[arg-type]
            divergence={},
            memory_effects={},
        )

        business_response = dict((assembled.get("data") or {}).get("business_response") or {})
        self.assertEqual(
            str(business_response.get("siguiente_accion") or ""),
            "Muestrame el detalle por empleado, area o supervisor.",
        )

    def test_response_assembler_builds_heights_business_response_from_sql_kpis(self):
        assembler = ResponseAssembler()
        response = {
            "reply": "97 certificados de alturas vencidos y 78 proximos a vencer en personal activo de labor operativa.",
            "data": {
                "kpis": {
                    "certificados_vencidos": 97,
                    "certificados_proximos_vencer": 78,
                },
                "table": {
                    "columns": ["certificados_vencidos", "certificados_proximos_vencer"],
                    "rows": [{"certificados_vencidos": 97, "certificados_proximos_vencer": 78}],
                    "rowcount": 1,
                },
                "insights": [],
                "findings": [],
            },
            "actions": [],
            "trace": [],
            "data_sources": {},
        }

        assembled = assembler.assemble(
            legacy_response=response,
            run_context=RunContext.create(message="certificados de alturas", session_id="heights-kpi", reset_memory=False),
            planned_capability={},
            route={},
            policy_decision=None,  # type: ignore[arg-type]
            divergence={},
            memory_effects={},
        )

        business_response = dict((assembled.get("data") or {}).get("business_response") or {})
        self.assertIn("certificados de alturas vencidos", str(business_response.get("dato") or "").lower())
        self.assertIn("riesgo documental", str(business_response.get("hallazgo") or "").lower())
        self.assertIn("trabajos en alturas", str(business_response.get("riesgo") or "").lower())
        self.assertIn("priorizar renovacion", str(business_response.get("recomendacion") or "").lower())

    def test_intent_arbitration_does_not_fallback_governed_heights_certificate_sql(self):
        plan = QueryExecutionPlan(
            strategy="sql_assisted",
            reason="employee_heights_certificate_summary_json",
            domain_code="empleados",
            sql_query="SELECT 1 AS certificados_proximos_vencer LIMIT 1",
            constraints={"result_shape": "kpi"},
            policy={"allowed": True, "reason": "sql_validated"},
            metadata={
                "compiler": "employee_semantic_sql",
                "metric_used": "certificado_alturas_vigencia",
                "aggregation_used": "count_by_validity",
            },
        )

        resolved = ChatApplicationService._apply_intent_arbitration_to_execution_plan(
            execution_plan=plan,
            arbitration={
                "final_intent": "analytics_query",
                "final_domain": "empleados",
                "should_fallback": True,
                "confidence": 0.65,
            },
        )

        self.assertEqual(resolved.strategy, "sql_assisted")
        self.assertEqual(str(resolved.sql_query or ""), str(plan.sql_query or ""))
        self.assertTrue(bool((resolved.policy or {}).get("allowed")))

    def test_resolve_query_intelligence_keeps_planner_payload_for_personal_activo_hoy(self):
        service = ChatApplicationService()
        run_context = RunContext.create(message="personal activo hoy", session_id="sess-qi", reset_memory=False)
        intent = StructuredQueryIntent(
            raw_query="personal activo hoy",
            domain_code="empleados",
            operation="count",
            template_id="count_entities_by_status",
            filters={},
            period={},
            group_by=[],
            metrics=["count"],
            confidence=0.9,
            source="rules",
        )
        resolved_query = ResolvedQuerySpec(
            intent=StructuredQueryIntent(
                raw_query="personal activo hoy",
                domain_code="empleados",
                operation="count",
                template_id="count_entities_by_status",
                filters={"estado": "ACTIVO"},
                period={},
                group_by=[],
                metrics=["count"],
                confidence=0.92,
                source="rules_arbitrated",
            ),
            semantic_context={"source_of_truth": {"used_dictionary": True, "used_yaml": True}},
            normalized_filters={"estado": "ACTIVO"},
            normalized_period={},
            mapped_columns={"estado": "estado"},
        )
        execution_plan = QueryExecutionPlan(
            strategy="capability",
            reason="capability_selected_from_query_intelligence",
            domain_code="empleados",
            capability_id="empleados.count.active.v1",
            constraints={"filters": {"estado": "ACTIVO"}, "group_by": [], "result_shape": "kpi"},
            metadata={"analytics_router_decision": "handler_modern"},
        )

        with patch.object(service.semantic_business_resolver, "build_semantic_context", return_value={}), patch.object(
            service.capability_runtime,
            "build_candidate_hints",
            return_value=[{"capability_id": "empleados.count.active.v1", "reason": "bootstrap"}],
        ), patch.object(service.query_intent_resolver, "match_query_pattern", return_value=None), patch.object(
            service.query_intent_resolver,
            "resolve",
            return_value=intent,
        ), patch.object(
            service.intent_arbitration_service,
            "arbitrate",
            return_value={
                "final_intent": "analytics_query",
                "final_domain": "empleados",
                "should_execute_query": True,
                "should_use_handler": True,
                "should_use_sql_assisted": False,
                "should_fallback": False,
                "confidence": 0.91,
                "reasoning_summary": "Consulta analitica de empleados activos.",
            },
        ), patch.object(
            service.semantic_business_resolver,
            "resolve_query",
            return_value=resolved_query,
        ), patch.object(
            service.query_execution_planner,
            "plan",
            return_value=execution_plan,
        ):
            payload = service._resolve_query_intelligence(
                message="personal activo hoy",
                base_classification={"domain": "empleados", "intent": "empleados_query", "needs_database": True},
                session_context={},
                run_context=run_context,
                observability=_ObservabilityStub(),
            )

        self.assertEqual(str(payload.get("error") or ""), "")
        self.assertEqual(str(((payload.get("execution_plan") or {}).get("strategy") or "")), "capability")
        self.assertEqual(
            str(((payload.get("execution_plan") or {}).get("capability_id") or "")),
            "empleados.count.active.v1",
        )

    def test_resolve_query_intelligence_realigns_semantic_context_to_employee_intent_domain(self):
        service = ChatApplicationService()
        service.intent_arbitration_service.enable_openai = False
        run_context = RunContext.create(
            message="Que moviles o cuadrillas tienen mas tecnicos asignados",
            session_id="sess-qi-movil",
            reset_memory=False,
        )
        intent = StructuredQueryIntent(
            raw_query="Que moviles o cuadrillas tienen mas tecnicos asignados",
            domain_code="empleados",
            operation="aggregate",
            template_id="aggregate_by_group_and_period",
            filters={"tipo_labor": "OPERATIVO"},
            period={},
            group_by=["movil"],
            metrics=["count"],
            confidence=0.9,
            source="rules",
        )
        resolved_query = ResolvedQuerySpec(
            intent=intent,
            semantic_context={"source_of_truth": {"used_dictionary": True, "used_yaml": True}},
            normalized_filters={"tipo_labor": "OPERATIVO", "estado": "ACTIVO"},
            normalized_period={},
            mapped_columns={"tipo_labor": "tipo_labor", "estado": "estado", "movil": "movil"},
        )
        execution_plan = QueryExecutionPlan(
            strategy="sql_assisted",
            reason="employee_grouped_population",
            domain_code="empleados",
            capability_id="empleados.count.active.v1",
            sql_query=(
                "SELECT movil AS movil, COUNT(*) AS total_registros "
                "FROM bd_c3nc4s1s.cinco_base_de_personal "
                "WHERE estado = 'ACTIVO' AND tipo_labor = 'operativo' "
                "GROUP BY movil ORDER BY total_registros DESC LIMIT 500"
            ),
            constraints={
                "filters": {"estado": "ACTIVO", "tipo_labor": "OPERATIVO"},
                "group_by": ["movil"],
                "result_shape": "table",
            },
            policy={"allowed": True, "reason": "sql_validated"},
            metadata={"analytics_router_decision": "join_aware_sql", "compiler": "employee_semantic_sql"},
        )
        general_context = {"domain_code": "general", "dictionary": {}}
        employee_context = {
            "domain_code": "empleados",
            "dictionary": {
                "fields": [
                    {
                        "logical_name": "movil",
                        "table_name": "cinco_base_de_personal",
                        "column_name": "movil",
                        "supports_group_by": True,
                    }
                ],
                "relations": [{"nombre_relacion": "empleado_supervisor"}],
                "synonyms": [{"termino": "movil", "sinonimo": "cuadrilla"}],
            },
        }

        with patch.dict(
            os.environ,
            {
                "IA_DEV_QUERY_INTELLIGENCE_ENABLED": "1",
                "IA_DEV_QUERY_INTELLIGENCE_MODE": "active",
            },
            clear=False,
        ), patch.object(
            service.semantic_business_resolver,
            "build_semantic_context",
            side_effect=[general_context, employee_context],
        ) as build_context, patch.object(
            service.capability_runtime,
            "build_candidate_hints",
            return_value=[{"capability_id": "empleados.count.active.v1", "reason": "bootstrap"}],
        ), patch.object(service.query_intent_resolver, "match_query_pattern", return_value=None), patch.object(
            service.query_intent_resolver,
            "resolve",
            return_value=intent,
        ), patch.object(
            service.semantic_business_resolver,
            "resolve_query",
            return_value=resolved_query,
        ), patch.object(
            service.query_execution_planner,
            "plan",
            return_value=execution_plan,
        ), patch.object(
            service.query_execution_planner,
            "execute_sql_assisted",
            return_value={
                "ok": True,
                "response": {
                    "reply": "Consulta analitica ejecutada en modo SQL asistido restringido para empleados: 2 filas.",
                    "orchestrator": {"classifier_source": "query_intelligence_sql_assisted"},
                    "data": {
                        "table": {
                            "columns": ["movil", "total_registros"],
                            "rows": [
                                {"movil": "M1", "total_registros": 12},
                                {"movil": "M2", "total_registros": 10},
                            ],
                            "rowcount": 2,
                        },
                        "business_response": {
                            "dato": "2 moviles",
                            "hallazgo": "M1 concentra mas tecnicos activos.",
                            "interpretacion": "La distribucion operativa es comparable por movil.",
                            "riesgo": "La concentracion puede ocultar desbalance operativo.",
                            "recomendacion": "Revisar asignacion de tecnicos por movil.",
                            "siguiente_accion": "Profundizar por sede o supervisor.",
                        },
                    },
                },
                "used_legacy": False,
            },
        ):
            payload = service._resolve_query_intelligence(
                message="Que moviles o cuadrillas tienen mas tecnicos asignados",
                base_classification={"domain": "general", "intent": "general_question", "needs_database": False},
                session_context={},
                run_context=run_context,
                observability=_ObservabilityStub(),
            )

        self.assertEqual(build_context.call_count, 2)
        self.assertEqual(
            build_context.call_args_list[1].kwargs,
            {"domain_code": "empleados", "include_dictionary": True},
        )
        self.assertEqual(str(payload.get("error") or ""), "")
        self.assertEqual(str(((payload.get("execution_plan") or {}).get("strategy") or "")), "sql_assisted")
        arbitration = dict(run_context.metadata.get("intent_arbitration") or {})
        self.assertEqual(str(arbitration.get("final_domain") or ""), "empleados")
        self.assertFalse(bool(arbitration.get("should_fallback")))
        self.assertTrue(bool(arbitration.get("should_execute_query")))
        self.assertTrue(bool(arbitration.get("should_use_sql_assisted")))

    def test_attach_runtime_metadata_includes_task_state_and_flow(self):
        run_context = RunContext.create(message="x", session_id="sess-1", reset_memory=False)
        run_context.metadata["task_state"] = {
            "workflow_key": "task_runtime:run-1",
            "status": "completed",
        }
        run_context.metadata["intent_arbitration"] = {
            "heuristic_intent": "knowledge_change_request",
            "llm_intent": "aggregate",
            "final_intent": "analytics_query",
            "final_domain": "ausentismo",
            "confidence": 0.91,
            "reasoning_summary": "Consulta analitica sobre datos existentes.",
            "should_create_kpro": False,
            "should_use_sql_assisted": True,
        }
        run_context.metadata["query_intelligence"] = {
            "execution_plan": {
                "strategy": "sql_assisted",
                "sql_query": "SELECT area, COUNT(*) AS total_registros FROM demo GROUP BY area",
                "policy": {"allowed": True},
                "metadata": {
                    "compiler": "join_aware_pilot",
                    "analytics_router_decision": "join_aware_sql",
                }
            }
        }
        run_context.metadata["cleanup_guard"] = {
            "analytics_router_decision": "runtime_only_fallback",
            "legacy_analytics_isolated": True,
            "legacy_analytics_fallback_disabled": True,
            "blocked_legacy_fallback": True,
            "blocked_tool_ausentismo_service": True,
            "blocked_run_legacy_for_analytics": True,
            "runtime_only_fallback_reason": "missing_dictionary_relation",
            "fallback_reason": "pilot_relation_missing",
            "cleanup_phase": "phase_7",
        }
        run_context.metadata["runtime_compatibility"] = {
            "runtime_authority": "query_execution_planner",
            "planner_was_authority": True,
            "planner_selected_strategy": "sql_assisted",
            "legacy_capability_path_used": False,
            "routing_mode": "intent",
        }

        response = ChatApplicationService._attach_runtime_metadata(
            response={"orchestrator": {}, "data_sources": {}},
            run_context=run_context,
            response_flow="sql_assisted",
        )

        self.assertEqual(str((response.get("orchestrator") or {}).get("runtime_flow") or ""), "sql_assisted")
        self.assertEqual(str((response.get("orchestrator") or {}).get("arbitrated_intent") or ""), "analytics_query")
        self.assertEqual(str((response.get("orchestrator") or {}).get("final_intent") or ""), "analytics_query")
        self.assertEqual(str((response.get("orchestrator") or {}).get("final_domain") or ""), "ausentismo")
        self.assertEqual(str((response.get("orchestrator") or {}).get("compiler_used") or ""), "join_aware_pilot")
        self.assertEqual(str((response.get("orchestrator") or {}).get("analytics_router_decision") or ""), "sql_assisted")
        self.assertEqual(str((response.get("orchestrator") or {}).get("fallback_reason") or ""), "")
        self.assertEqual(str((response.get("task_state") or {}).get("workflow_key") or ""), "task_runtime:run-1")
        self.assertEqual(str(((response.get("data_sources") or {}).get("runtime") or {}).get("flow") or ""), "sql_assisted")
        self.assertEqual(
            str(((response.get("data_sources") or {}).get("runtime") or {}).get("runtime_authority") or ""),
            "query_execution_planner",
        )
        self.assertTrue(bool(((response.get("data_sources") or {}).get("runtime") or {}).get("planner_was_authority")))
        self.assertFalse(bool(((response.get("data_sources") or {}).get("runtime") or {}).get("blocked_legacy_fallback")))
        self.assertEqual(
            str(((response.get("data_sources") or {}).get("runtime") or {}).get("analytics_router_decision") or ""),
            "sql_assisted",
        )
        self.assertEqual(str(((response.get("data_sources") or {}).get("runtime") or {}).get("final_domain") or ""), "ausentismo")
        self.assertEqual(
            str(((response.get("data_sources") or {}).get("runtime") or {}).get("fallback_reason") or ""),
            "",
        )

    def test_attach_runtime_metadata_promotes_employee_sql_assisted_fallback_to_analytics_intent(self):
        run_context = RunContext.create(message="personal activo por area y carpeta", session_id="sess-emp", reset_memory=False)
        run_context.metadata["intent_arbitration"] = {
            "final_intent": "fallback",
            "final_domain": "empleados",
            "should_fallback": True,
        }
        run_context.metadata["query_intelligence"] = {
            "execution_plan": {
                "domain_code": "empleados",
                "constraints": {
                    "filters": {"estado": "ACTIVO"},
                    "group_by": ["area", "carpeta"],
                },
                "metadata": {
                    "compiler": "employee_semantic_sql",
                    "analytics_router_decision": "join_aware_sql",
                },
            },
            "resolved_query": {
                "semantic_context": {
                    "source_of_truth": {"used_dictionary": True},
                }
            },
        }

        response = ChatApplicationService._attach_runtime_metadata(
            response={"orchestrator": {}, "data_sources": {}},
            run_context=run_context,
            response_flow="sql_assisted",
        )

        self.assertEqual(str((response.get("orchestrator") or {}).get("arbitrated_intent") or ""), "fallback")
        self.assertEqual(str((response.get("orchestrator") or {}).get("final_intent") or ""), "analytics_query")
        self.assertEqual(
            str(((response.get("data_sources") or {}).get("runtime") or {}).get("final_intent") or ""),
            "analytics_query",
        )

    def test_build_runtime_compatibility_metadata_marks_legacy_path_usage(self):
        metadata = ChatApplicationService._build_runtime_compatibility_metadata(
            query_intelligence={"execution_plan": {"strategy": "fallback"}},
            route={
                "routing_mode": "capability",
                "runtime_authority": "query_execution_planner",
                "use_legacy": True,
            },
            execution_meta={"used_legacy": True},
        )

        self.assertTrue(bool(metadata.get("legacy_capability_path_used")))
        self.assertEqual(str(metadata.get("runtime_authority") or ""), "query_execution_planner")
        self.assertEqual(str(metadata.get("planner_selected_strategy") or ""), "fallback")
        self.assertTrue(bool(metadata.get("planner_was_authority")))
        self.assertEqual(str(metadata.get("routing_mode") or ""), "capability")

    def test_chat_application_service_source_does_not_import_legacy_capability_components(self):
        import apps.ia_dev.application.orchestration.chat_application_service as chat_module

        source = inspect.getsource(chat_module)
        self.assertNotIn("CapabilityRouter", source)
        self.assertNotIn("CapabilityPlanner", source)
        self.assertNotIn("IntentToCapabilityBridge", source)

    def test_proactive_loop_flag_off_keeps_loop_disabled(self):
        with patch.dict(
            os.environ,
            {
                "IA_DEV_ROUTING_MODE": "capability",
                "IA_DEV_PROACTIVE_LOOP_ENABLED": "0",
            },
            clear=False,
        ):
            run_context = RunContext.create(message="x", session_id="sess-2", reset_memory=False)
            self.assertFalse(ChatApplicationService._proactive_loop_enabled(run_context=run_context))

    def test_resolve_runtime_response_flow_covers_sql_handler_runtime_only_and_legacy(self):
        self.assertEqual(
            ChatApplicationService._resolve_runtime_response_flow(
                query_intelligence={"execution_plan": {"strategy": "sql_assisted"}},
                route={"execute_capability": False},
                response={"orchestrator": {"classifier_source": "query_intelligence_sql_assisted"}},
                execution_meta={},
            ),
            "sql_assisted",
        )
        self.assertEqual(
            ChatApplicationService._resolve_runtime_response_flow(
                query_intelligence={},
                route={"execute_capability": True},
                response={"orchestrator": {"classifier_source": "handler_runtime"}},
                execution_meta={},
            ),
            "handler",
        )
        self.assertEqual(
            ChatApplicationService._resolve_runtime_response_flow(
                query_intelligence={},
                route={"execute_capability": False},
                response={"orchestrator": {"classifier_source": "query_intelligence_runtime_only_fallback"}},
                execution_meta={"blocked_legacy_fallback": True},
            ),
            "runtime_only_fallback",
        )
        self.assertEqual(
            ChatApplicationService._resolve_runtime_response_flow(
                query_intelligence={},
                route={"execute_capability": False},
                response={"orchestrator": {"classifier_source": "general_answer"}},
                execution_meta={"used_legacy": True},
            ),
            "legacy_fallback",
        )

    def test_resolve_runtime_response_flow_prioritizes_valid_sql_assisted_authority(self):
        self.assertEqual(
            ChatApplicationService._resolve_runtime_response_flow(
                query_intelligence={
                    "execution_plan": {
                        "strategy": "sql_assisted",
                        "sql_query": "SELECT 1",
                        "policy": {"allowed": True},
                    },
                    "execution_result": {
                        "ok": True,
                        "response": {"orchestrator": {"classifier_source": "query_intelligence_sql_assisted"}},
                        "satisfied": True,
                        "used_legacy": False,
                    },
                },
                route={"execute_capability": True, "runtime_authority": "query_execution_planner"},
                response={"orchestrator": {"classifier_source": "handler_runtime"}},
                execution_meta={
                    "response": {"orchestrator": {"classifier_source": "query_intelligence_sql_assisted"}},
                    "satisfied": True,
                    "used_legacy": False,
                },
            ),
            "sql_assisted",
        )

    def test_planner_valid_sql_result_wins_disables_capability_execution(self):
        route = ChatApplicationService._enforce_planner_sql_authority_route(
            route={
                "routing_mode": "capability",
                "selected_capability_id": "empleados.count.active.v1",
                "execute_capability": True,
                "use_legacy": False,
            },
            query_intelligence={
                "execution_plan": {
                    "strategy": "sql_assisted",
                    "sql_query": "SELECT 1",
                    "policy": {"allowed": True},
                    "metadata": {"capability_id": "empleados.count.active.v1"},
                },
                "execution_result": {
                    "ok": True,
                    "response": {"reply": "sql ok"},
                    "satisfied": True,
                    "used_legacy": False,
                },
            },
            execution_meta={"response": {"reply": "sql ok"}, "satisfied": True, "used_legacy": False},
        )

        self.assertFalse(bool(route.get("execute_capability")))
        self.assertFalse(bool(route.get("use_legacy")))
        self.assertEqual(str(route.get("runtime_authority") or ""), "query_execution_planner")
        self.assertTrue(bool(route.get("planner_was_authority")))
        self.assertEqual(str(route.get("reason") or ""), "query_execution_planner_sql_assisted_authority")

    def test_record_runtime_resolution_event_includes_compiler_and_satisfaction(self):
        observability = _ObservabilityStub()
        run_context = RunContext.create(message="x", session_id="sess-1", reset_memory=False)

        ChatApplicationService()._record_runtime_resolution_event(
            observability=observability,
            run_context=run_context,
            query_intelligence={
                "execution_plan": {
                    "strategy": "sql_assisted",
                    "sql_query": "SELECT area, SUM(dias_perdidos) AS total_dias FROM demo GROUP BY area",
                    "policy": {"allowed": True},
                    "metadata": {
                        "compiler": "join_aware_pilot",
                        "relations_used": ["gestionh_ausentismo.cedula = cinco_base_de_personal.cedula"],
                        "metric_used": "dias_perdidos",
                        "aggregation_used": "sum",
                        "dimensions_used": ["area"],
                        "declared_metric_source": "ai_dictionary.dd_campos",
                        "declared_dimensions_source": "ai_dictionary.dd_campos",
                    }
                },
                "resolved_query": {
                    "intent": {"domain_code": "ausentismo"},
                    "semantic_context": {
                        "tables": [
                            {"table_name": "gestionh_ausentismo"},
                            {"table_name": "cinco_base_de_personal"},
                        ],
                        "column_profiles": [
                            {"column_name": "fecha_edit"},
                            {"column_name": "cedula"},
                        ],
                        "source_of_truth": {
                            "used_dictionary": True,
                            "used_yaml": True,
                            "structural_source": "ai_dictionary",
                            "yaml_role": "narrative_only",
                            "yaml_structural_ignored": True,
                        },
                    },
                },
            },
            route={"reason": "query_intelligence_active_precomputed_response"},
            response={"orchestrator": {"classifier_source": "query_intelligence_sql_assisted"}},
            execution_meta={
                "analytics_router_decision": "join_aware_sql",
                "legacy_analytics_isolated": True,
                "fallback_reason": "",
                "legacy_analytics_fallback_disabled": True,
                "blocked_legacy_fallback": False,
                "blocked_tool_ausentismo_service": False,
                "blocked_run_legacy_for_analytics": False,
                "runtime_only_fallback_reason": "",
                "cleanup_phase": "phase_7",
            },
            response_flow="sql_assisted",
            satisfaction_snapshot={"satisfied": True, "gate_score": 0.88},
        )

        self.assertEqual(len(observability.events), 1)
        meta = dict(observability.events[0].get("meta") or {})
        self.assertEqual(str(meta.get("compiler_used") or ""), "join_aware_pilot")
        self.assertEqual(str(meta.get("domain_resolved") or ""), "ausentismo")
        self.assertEqual(str(meta.get("structural_source") or ""), "ai_dictionary")
        self.assertEqual(str(meta.get("yaml_role") or ""), "narrative_only")
        self.assertTrue(bool(meta.get("yaml_structural_ignored")))
        self.assertEqual(list(meta.get("tables_detected") or []), ["gestionh_ausentismo", "cinco_base_de_personal"])
        self.assertEqual(str(meta.get("metric_used") or ""), "dias_perdidos")
        self.assertEqual(str(meta.get("aggregation_used") or ""), "sum")
        self.assertEqual(list(meta.get("dimensions_used") or []), ["area"])
        self.assertTrue(bool((meta.get("satisfaction_review") or {}).get("satisfied")))
        self.assertEqual(str(meta.get("analytics_router_decision") or ""), "sql_assisted")
        self.assertFalse(bool(meta.get("legacy_analytics_isolated")))
        self.assertEqual(str(meta.get("cleanup_phase") or ""), "")
