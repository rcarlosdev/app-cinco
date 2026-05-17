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
from apps.ia_dev.application.runtime.semantic_gap_registry_service import SemanticGapRegistryService


class _ObservabilityStub:
    def __init__(self):
        self.events: list[dict] = []

    def record_event(self, *, event_type: str, source: str, meta: dict):
        self.events.append({"event_type": event_type, "source": source, "meta": dict(meta or {})})


class _TaskStateUpdateStub:
    def __init__(self):
        self.updated = None

    def update_state(self, *, run_id: str, extra_state: dict | None = None, **kwargs):
        self.updated = {"run_id": run_id, "extra_state": dict(extra_state or {})}

    def get(self, *, run_id: str):
        return {
            "workflow_key": f"task_runtime:{run_id}",
            "state": dict((self.updated or {}).get("extra_state") or {}),
        }


class _GapRegistryStub(SemanticGapRegistryService):
    def __init__(self):
        pass

    def register_from_runtime(self, *, response: dict, run_context):
        return {
            "registrada": True,
            "idempotente": False,
            "registro": {
                "id": 41,
                "categoria_brecha": "consulta_ambigua",
                "prioridad": "media",
                "estado_revision": "nueva",
                "origen_registro": "runtime",
            },
        }


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

    def test_resolve_query_intelligence_routes_certificados_altura_proximos_a_vencer_without_fallback(self):
        service = ChatApplicationService()
        message = "certificados de altura proximos a vencer del personal activo operativo"
        run_context = RunContext.create(message=message, session_id="sess-heights", reset_memory=False)
        intent = StructuredQueryIntent(
            raw_query=message,
            domain_code="empleados",
            operation="count",
            template_id="count_entities_by_status",
            filters={},
            period={},
            group_by=[],
            metrics=["count"],
            confidence=0.91,
            source="rules",
        )
        resolved_query = ResolvedQuerySpec(
            intent=StructuredQueryIntent(
                raw_query=message,
                domain_code="empleados",
                operation="count",
                template_id="count_entities_by_status",
                filters={"estado_empleado": "ACTIVO", "tipo_labor": "OPERATIVO"},
                period={},
                group_by=[],
                metrics=["count"],
                confidence=0.94,
                source="rules_arbitrated",
            ),
            semantic_context={
                "tables": [{"table_name": "cinco_base_de_personal"}],
                "allowed_tables": ["cinco_base_de_personal", "bd_c3nc4s1s.cinco_base_de_personal"],
                "allowed_columns": ["datos", "calturas", "estado", "tipo_labor"],
                "column_profiles": [
                    {"table_name": "cinco_base_de_personal", "logical_name": "estado_empleado", "column_name": "estado"},
                    {"table_name": "cinco_base_de_personal", "logical_name": "tipo_labor", "column_name": "tipo_labor"},
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
                    }
                },
                "source_of_truth": {"pilot_sql_assisted_enabled": True},
            },
            normalized_filters={"estado_empleado": "ACTIVO", "tipo_labor": "OPERATIVO"},
            normalized_period={},
            mapped_columns={"estado_empleado": "estado", "tipo_labor": "tipo_labor"},
        )
        execution_plan = QueryExecutionPlan(
            strategy="sql_assisted",
            reason="employee_heights_certificate_summary_json",
            domain_code="empleados",
            sql_query="SELECT 1 AS certificados_proximos_vencer LIMIT 1",
            constraints={"filters": {"estado_empleado": "ACTIVO", "tipo_labor": "OPERATIVO"}, "group_by": [], "result_shape": "kpi"},
            policy={"allowed": True, "reason": "sql_validated"},
            metadata={"compiler": "employee_semantic_sql", "metric_used": "certificado_alturas_vigencia"},
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
                "should_use_handler": False,
                "should_use_sql_assisted": True,
                "should_fallback": False,
                "confidence": 0.96,
                "reasoning_summary": "Consulta de vigencia de certificados de alturas en empleados.",
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
                message=message,
                base_classification={"domain": "empleados", "intent": "empleados_query", "needs_database": True},
                session_context={},
                run_context=run_context,
                observability=_ObservabilityStub(),
            )

        self.assertEqual(str(payload.get("error") or ""), "")
        self.assertEqual(str(((payload.get("resolved_query") or {}).get("intent") or {}).get("domain_code") or ""), "empleados")
        self.assertEqual(str(((payload.get("execution_plan") or {}).get("strategy") or "")), "sql_assisted")
        self.assertEqual(str(((payload.get("execution_plan") or {}).get("metadata") or {}).get("metric_used") or ""), "certificado_alturas_vigencia")

    def test_resolve_query_intelligence_exposes_empleados_errors_in_metadata_and_observability(self):
        service = ChatApplicationService()
        observability = _ObservabilityStub()
        run_context = RunContext.create(message="empleados activos", session_id="sess-qi-error", reset_memory=False)

        with patch.object(
            service.semantic_business_resolver,
            "build_semantic_context",
            side_effect=RuntimeError("boom empleados"),
        ):
            payload = service._resolve_query_intelligence(
                message="empleados activos",
                base_classification={"domain": "empleados", "intent": "empleados_query", "needs_database": True},
                session_context={},
                run_context=run_context,
                observability=observability,
            )

        self.assertEqual(str(payload.get("mode") or ""), "active")
        self.assertIn("boom empleados", str(payload.get("error") or ""))
        self.assertIn("boom empleados", str((run_context.metadata.get("query_intelligence") or {}).get("error") or ""))
        self.assertTrue(any(event.get("event_type") == "query_intelligence_error" for event in observability.events))

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
        self.assertEqual(str((response.get("task") or {}).get("task_id") or ""), "task_runtime:run-1")
        self.assertEqual(str((((response.get("task") or {}).get("current_run") or {}).get("run_id") or "")), run_context.run_id)
        self.assertEqual(str((((response.get("task") or {}).get("current_run") or {}).get("status") or "")), "completed")
        self.assertEqual(str((((response.get("task") or {}).get("current_run") or {}).get("domain") or "")), "ausentismo")
        self.assertEqual(str((((response.get("task") or {}).get("current_run") or {}).get("intent") or "")), "analytics_query")
        self.assertEqual(
            list((((response.get("task") or {}).get("current_run") or {}).get("required_tools") or [])),
            ["query_execution_planner.sql_assisted"],
        )
        selected_tool_id = str(
            ((((response.get("task") or {}).get("current_run") or {}).get("tool_execution") or {}).get("selected_tool_id") or "")
        )
        self.assertEqual(selected_tool_id, "")
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

    def test_attach_runtime_metadata_exposes_tool_execution_trace_from_task_state(self):
        run_context = RunContext.create(message="personal activo hoy", session_id="sess-tools", reset_memory=False)
        run_context.metadata["task_state"] = {
            "workflow_key": "task_runtime:run-tool",
            "status": "completed",
            "state": {
                "task_status": "completed",
                "agents": [
                    {"agent_name": "manager_agent", "role": "manager"},
                    {"agent_name": "empleados_agent", "role": "specialist"},
                ],
                "handoffs": [
                    {
                        "handoff_origin": "manager_agent",
                        "handoff_target": "empleados_agent",
                    }
                ],
                "handoff_trace": [
                    {
                        "handoff_id": "handoff-1",
                        "handoff_origin": "manager_agent",
                        "handoff_target": "empleados_agent",
                    }
                ],
                "agent_trace": [
                    {"agent_name": "manager_agent"},
                    {"agent_name": "empleados_agent"},
                ],
                "approvals": [
                    {
                        "approval_request_id": "apr-1",
                        "approval_status": "awaiting_approval",
                        "resume_token": "resume-1",
                    }
                ],
                "approval_trace": [
                    {"approval_request_id": "apr-1", "status": "awaiting_approval"}
                ],
                "tool_execution": {
                    "selected_tool_id": "empleados.count.active.v1",
                    "registry_version": "tool_registry.v1",
                },
                "tool_execution_trace": [
                    {
                        "tool_id": "empleados.count.active.v1",
                        "status": "completed",
                    }
                ],
            },
        }
        run_context.metadata["intent_arbitration"] = {"final_intent": "empleados_query", "final_domain": "empleados"}
        run_context.metadata["query_intelligence"] = {"execution_plan": {"strategy": "capability", "capability_id": "empleados.count.active.v1"}}

        response = ChatApplicationService._attach_runtime_metadata(
            response={"orchestrator": {"domain": "empleados", "intent": "empleados_query"}, "data_sources": {}},
            run_context=run_context,
            response_flow="handler",
        )

        task_execution = dict((((response.get("task") or {}).get("current_run") or {}).get("tool_execution") or {}))
        task_run = dict(((response.get("task") or {}).get("current_run") or {}))
        runtime_execution = dict(((response.get("data_sources") or {}).get("runtime") or {}).get("tool_execution") or {})
        runtime_payload = dict(((response.get("data_sources") or {}).get("runtime") or {}))
        self.assertEqual(str(task_execution.get("selected_tool_id") or ""), "empleados.count.active.v1")
        self.assertEqual(len(list(task_execution.get("trace") or [])), 1)
        self.assertEqual(len(list(task_run.get("agents") or [])), 2)
        self.assertEqual(len(list(task_run.get("handoffs") or [])), 1)
        self.assertEqual(len(list(task_run.get("approvals") or [])), 1)
        self.assertEqual(str(runtime_execution.get("selected_tool_id") or ""), "empleados.count.active.v1")
        self.assertEqual(len(list(runtime_execution.get("trace") or [])), 1)
        self.assertEqual(len(list(runtime_payload.get("agents") or [])), 2)
        self.assertEqual(len(list(runtime_payload.get("handoffs") or [])), 1)
        self.assertEqual(len(list(runtime_payload.get("handoff_trace") or [])), 1)
        self.assertEqual(len(list(runtime_payload.get("approvals") or [])), 1)

    def test_runtime_tool_execution_state_merges_native_tool_trace(self):
        run_context = RunContext.create(message="inventario tiran224", session_id="sess-native", reset_memory=False)
        run_context.metadata["response_native_tool_trace"] = [
            {
                "tool_call_id": "call_native_1",
                "tool_name": "semantic_orchestrator.dictionary_summary.v1",
                "tool_id": "semantic_orchestrator.dictionary_summary.v1",
                "status": "completed",
            }
        ]
        run_context.metadata["response_native_tool_loop"] = {
            "component": "semantic_orchestrator_service",
            "turns": 2,
            "tool_trace_count": 1,
        }

        service = ChatApplicationService()
        state = service._build_runtime_tool_execution_state(
            run_context=run_context,
            response_flow="sql_assisted",
            route_payload={},
            execution_plan={"capability_id": "inventory_stock_balance_by_mobile"},
            response={"reply": "ok", "data": {"table": {"rowcount": 1}}, "observability": {"duration_ms": 1}},
            fallback_used={"used": False},
            validation_result={"satisfied": True},
        )

        execution = dict(state.get("tool_execution") or {})
        trace = list(state.get("tool_execution_trace") or [])
        self.assertEqual(int(execution.get("native_tool_calls_count") or 0), 1)
        self.assertEqual(str((dict(execution.get("response_tool_loop") or {})).get("component") or ""), "semantic_orchestrator_service")
        self.assertEqual(len(trace), 2)
        self.assertEqual(str((trace[0] or {}).get("tool_call_id") or ""), "call_native_1")

    def test_build_runtime_agent_execution_state_reads_agents_runtime_metadata(self):
        run_context = RunContext.create(message="inventario tiran224", session_id="sess-agent-state", reset_memory=False)
        run_context.metadata["agents_runtime"] = {
            "agents": [
                {"agent_name": "manager_agent"},
                {"agent_name": "inventory_agent"},
            ],
            "handoffs": [
                {"handoff_origin": "manager_agent", "handoff_target": "inventory_agent"},
            ],
            "handoff_trace": [
                {"handoff_id": "handoff-1", "handoff_origin": "manager_agent", "handoff_target": "inventory_agent"},
            ],
            "agent_trace": [
                {"agent_name": "manager_agent"},
                {"agent_name": "inventory_agent"},
            ],
            "bootstrap": {"implementation": "gateway_function_loop"},
        }
        run_context.metadata["approval_runtime"] = {
            "approvals": [{"approval_request_id": "apr-1", "approval_status": "awaiting_approval"}],
            "approval_trace": [{"approval_request_id": "apr-1", "status": "awaiting_approval"}],
        }

        state = ChatApplicationService._build_runtime_agent_execution_state(run_context=run_context)
        approval_state = ChatApplicationService._build_runtime_approval_execution_state(run_context=run_context)

        self.assertEqual(len(list(state.get("agents") or [])), 2)
        self.assertEqual(len(list(state.get("handoffs") or [])), 1)
        self.assertEqual(len(list(state.get("handoff_trace") or [])), 1)
        self.assertEqual(len(list(state.get("agent_trace") or [])), 2)
        self.assertEqual(str((state.get("agents_runtime_bootstrap") or {}).get("implementation") or ""), "gateway_function_loop")
        self.assertEqual(len(list(approval_state.get("approvals") or [])), 1)
        self.assertEqual(len(list(approval_state.get("approval_trace") or [])), 1)

    def test_build_runtime_background_execution_state_reads_background_runtime_metadata(self):
        run_context = RunContext.create(message="proceso largo", session_id="sess-bg-state", reset_memory=False)
        run_context.metadata["background_runtime"] = {
            "background": {
                "background_run_id": "bg-1",
                "run_status": "queued",
                "resume_token": "resume-1",
            },
            "background_trace": [{"event_type": "background_run_queued"}],
            "checkpoints": [{"checkpoint_id": "chk-1"}],
        }

        state = ChatApplicationService._build_runtime_background_execution_state(run_context=run_context)

        self.assertEqual(str((state.get("background") or {}).get("background_run_id") or ""), "bg-1")
        self.assertEqual(len(list(state.get("background_trace") or [])), 1)
        self.assertEqual(len(list(state.get("checkpoints") or [])), 1)

    def test_attach_runtime_metadata_exposes_background_state(self):
        run_context = RunContext.create(message="proceso largo", session_id="sess-bg-meta", reset_memory=False)
        run_context.metadata["task_state"] = {
            "workflow_key": "task_runtime:run-bg-meta",
            "status": "queued",
            "state": {
                "task_id": "task_runtime:run-bg-meta",
                "task_status": "queued",
                "detected_domain": "empleados",
                "plan": {},
                "source_used": {"response_flow": "handler"},
                "background": {
                    "background_run_id": "bg-meta-1",
                    "run_status": "queued",
                    "resume_token": "resume-meta-1",
                },
                "background_trace": [{"event_type": "background_run_queued"}],
                "checkpoints": [{"checkpoint_id": "chk-meta-1"}],
                "tool_execution": {"selected_tool_id": "empleados.count.active.v1"},
                "tool_execution_trace": [],
            },
        }

        response = ChatApplicationService._attach_runtime_metadata(
            response={"orchestrator": {"domain": "empleados", "intent": "empleados_query"}, "data_sources": {}},
            run_context=run_context,
            response_flow="handler",
        )

        task_run = dict(((response.get("task") or {}).get("current_run") or {}))
        runtime_payload = dict(((response.get("data_sources") or {}).get("runtime") or {}))
        self.assertEqual(str((task_run.get("background") or {}).get("background_run_id") or ""), "bg-meta-1")
        self.assertEqual(str((runtime_payload.get("background") or {}).get("resume_token") or ""), "resume-meta-1")
        self.assertEqual(len(list(runtime_payload.get("background_trace") or [])), 1)
        self.assertEqual(len(list(runtime_payload.get("checkpoints") or [])), 1)

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

    def test_attach_runtime_metadata_carries_business_response_evidence_trace(self):
        run_context = RunContext.create(message="inventario tiran224", session_id="sess-p4", reset_memory=False)
        run_context.metadata["semantic_orchestrator"] = {
            "domain": "inventario_logistica",
            "intent": "stock_balance",
            "selected_agent": "inventory_agent",
        }
        run_context.metadata["query_intelligence"] = {
            "execution_plan": {
                "strategy": "sql_assisted",
                "capability_id": "inventory_stock_balance_by_mobile",
            }
        }
        run_context.metadata["task_state"] = {
            "workflow_key": "task_runtime:run-p4",
            "status": "completed",
            "state": {
                "task_id": "task_runtime:run-p4",
                "task_status": "completed",
                "detected_domain": "inventario_logistica",
                "validation_result": {"satisfied": True, "reason": "ok"},
                "tool_execution": {"selected_tool_id": "query_execution_planner.sql_assisted"},
                "tool_execution_trace": [],
                "agents": [{"agent_name": "inventory_agent"}],
            },
        }

        response = ChatApplicationService._attach_runtime_metadata(
            response={
                "reply": "ok",
                "orchestrator": {"domain": "inventario_logistica", "intent": "stock_balance"},
                "data_sources": {},
                "data": {
                    "business_response": {
                        "metadata": {
                            "response_profile_usado": "inventory.stock.mobile.detail",
                            "evidence_sources_used": ["semantic_context", "result_set"],
                            "semantic_context_used": True,
                            "fallback_narrativo_usado": False,
                            "missing_evidence_reason": "",
                            "paquete_capacidad_usado": "inventario_logistica",
                            "version_paquete": "1.0.0",
                            "capacidades_declaradas": ["inventory_stock_balance_by_mobile"],
                            "reglas_declaradas": ["inventario.filter.material_generico"],
                            "perfiles_respuesta": ["inventory.stock.mobile.detail"],
                            "evaluaciones_asociadas": ["inventario_runtime_eval_v1"],
                            "candidate_capability": "inventory_stock_balance_by_mobile",
                            "planner_route_hint": "inventory.material_stock.mobile",
                            "tool_id": "query_execution_planner.sql_assisted",
                            "filters": {"movil": "TIRAN224", "tipo": ["material", "ferretero"]},
                            "semantic_trace": {
                                "fuente_dd": ["dd_sinonimos", "dd_reglas"],
                                "regla_metadata_usada": ["inventario.filter.material_generico"],
                                "fallback_sombreado_usado": False,
                                "regla_legacy_detectada": False,
                                "paquete_capacidad_usado": "inventario_logistica",
                                "version_paquete": "1.0.0",
                                "capacidades_declaradas": ["inventory_stock_balance_by_mobile"],
                                "reglas_declaradas": ["inventario.route.stock_balance_holder"],
                                "perfiles_respuesta": ["inventory.stock.mobile.detail"],
                                "evaluaciones_asociadas": ["inventario_runtime_eval_v1"],
                            },
                        },
                        "evidence_summary": {
                            "response_profile_usado": "inventory.stock.mobile.detail",
                            "entity": {"field": "movil", "identifier": "TIRAN224"},
                            "filters": {"movil": "TIRAN224", "tipo": ["material", "ferretero"]},
                            "output_profile": {"grain": "saldo_por_codigo", "columns": ["codigo", "saldo"]},
                            "capability_pack": {
                                "paquete_capacidad_usado": "inventario_logistica",
                                "version_paquete": "1.0.0",
                                "capacidades_declaradas": ["inventory_stock_balance_by_mobile"],
                                "reglas_declaradas": ["inventario.route.stock_balance_holder"],
                                "perfiles_respuesta": ["inventory.stock.mobile.detail"],
                                "evaluaciones_asociadas": ["inventario_runtime_eval_v1"],
                            },
                        },
                    },
                    "table": {
                        "columns": ["codigo", "saldo"],
                        "rows": [{"codigo": "MAT-1", "saldo": 2}],
                        "rowcount": 1,
                    },
                },
            },
            run_context=run_context,
            response_flow="sql_assisted",
        )

        evidence = dict((((response.get("task") or {}).get("current_run") or {}).get("evidence") or {}))
        self.assertEqual(str(evidence.get("response_profile_usado") or ""), "inventory.stock.mobile.detail")
        self.assertIn("semantic_context", list(evidence.get("evidence_sources_used") or []))
        self.assertTrue(bool(evidence.get("semantic_context_used")))
        self.assertFalse(bool(evidence.get("fallback_narrativo_usado")))
        self.assertEqual(str(evidence.get("paquete_capacidad_usado") or ""), "inventario_logistica")
        self.assertEqual(str(evidence.get("version_paquete") or ""), "1.0.0")
        explanation = dict((((response.get("task") or {}).get("current_run") or {}).get("semantic_explanation") or {}))
        self.assertEqual(str(explanation.get("domain") or ""), "inventario_logistica")
        self.assertEqual(str(explanation.get("intent") or ""), "stock_balance")
        self.assertEqual(str(explanation.get("selected_capability") or ""), "inventory_stock_balance_by_mobile")
        self.assertEqual(str(explanation.get("selected_tool") or ""), "query_execution_planner.sql_assisted")
        self.assertEqual(str((dict(explanation.get("entity") or {})).get("identifier") or ""), "TIRAN224")
        self.assertTrue(bool((dict(explanation.get("metadata_used") or {})).get("governed_used")))
        self.assertEqual(str((dict(explanation.get("capability_pack") or {}).get("paquete_capacidad_usado") or "")), "inventario_logistica")
        self.assertEqual(str((dict(explanation.get("capability_pack") or {}).get("version_paquete") or "")), "1.0.0")
        self.assertEqual(int((dict(explanation.get("evidence_summary") or {})).get("rowcount") or 0), 1)

    def test_attach_runtime_metadata_marks_semantic_explanation_for_approval_and_clarification(self):
        run_context = RunContext.create(message="que tiene Juan Perez", session_id="sess-clarify", reset_memory=False)
        run_context.metadata["semantic_orchestrator"] = {
            "domain": "inventario_logistica",
            "intent": "needs_clarification",
            "clarification_question": "Aclara si buscas por cedula, movil o codigo.",
            "needs_clarification": True,
            "selected_agent": "semantic_resolution_agent",
        }
        run_context.metadata["intent_arbitration"] = {
            "final_intent": "needs_clarification",
            "required_clarification": "Aclara si buscas por cedula, movil o codigo.",
        }
        run_context.metadata["task_state"] = {
            "workflow_key": "task_runtime:run-clarify",
            "status": "awaiting_approval",
            "state": {
                "task_id": "task_runtime:run-clarify",
                "task_status": "awaiting_approval",
                "detected_domain": "inventario_logistica",
                "validation_result": {
                    "satisfied": False,
                    "reason": "missing_structural_context",
                    "needs_clarification": True,
                },
                "approvals": [
                    {"approval_request_id": "apr-1", "approval_status": "awaiting_approval"}
                ],
                "background": {
                    "background_run_id": "bg-clarify-1",
                    "run_status": "awaiting_approval",
                    "resume_token": "resume-clarify-1",
                },
                "tool_execution": {"selected_tool_id": ""},
                "tool_execution_trace": [],
            },
        }

        response = ChatApplicationService._attach_runtime_metadata(
            response={
                "reply": "Aclara si buscas por cedula, movil o codigo.",
                "orchestrator": {"domain": "inventario_logistica", "intent": "needs_clarification"},
                "data_sources": {},
                "data": {
                    "business_response": {
                        "metadata": {
                            "response_status": "clarification_required",
                            "limitations": [],
                        },
                        "evidence_summary": {
                            "response_profile_usado": "inventory.stock.mobile.detail",
                        },
                    }
                },
            },
            run_context=run_context,
            response_flow="sql_assisted",
        )

        explanation = dict((((response.get("task") or {}).get("current_run") or {}).get("semantic_explanation") or {}))
        clarification = dict(explanation.get("clarification_needed") or {})
        approvals = dict(explanation.get("approvals_status") or {})
        background = dict(explanation.get("background_status") or {})
        self.assertTrue(bool(clarification.get("required")))
        self.assertIn("cedula", str(clarification.get("question") or "").lower())
        self.assertEqual(str(approvals.get("status") or ""), "awaiting_approval")
        self.assertEqual(int(approvals.get("pending_count") or 0), 1)
        self.assertEqual(str(background.get("status") or ""), "awaiting_approval")
        self.assertTrue(bool(background.get("resume_token_available")))

    def test_attach_runtime_metadata_humanizes_inventory_shadow_fallback_for_semantic_explanation(self):
        run_context = RunContext.create(message="saldo en moviles de CONECTOR RJ 45", session_id="sess-shadow", reset_memory=False)
        run_context.metadata["semantic_orchestrator"] = {
            "domain": "inventario_logistica",
            "intent": "stock_balance",
            "selected_agent": "inventory_agent",
        }
        run_context.metadata["query_intelligence"] = {
            "execution_plan": {
                "strategy": "sql_assisted",
                "capability_id": "inventory_stock_balance_by_material_dimension",
            }
        }
        run_context.metadata["task_state"] = {
            "workflow_key": "task_runtime:run-shadow",
            "status": "completed",
            "state": {
                "task_id": "task_runtime:run-shadow",
                "task_status": "completed",
                "detected_domain": "inventario_logistica",
                "validation_result": {"satisfied": True, "reason": "ok"},
                "fallback_used": {"used": False},
                "tool_execution": {"selected_tool_id": "query_execution_planner.sql_assisted"},
                "tool_execution_trace": [],
            },
        }

        response = ChatApplicationService._attach_runtime_metadata(
            response={
                "reply": "ok",
                "orchestrator": {"domain": "inventario_logistica", "intent": "stock_balance"},
                "data_sources": {},
                "data": {
                    "business_response": {
                        "metadata": {
                            "response_profile_usado": "inventory.stock.dimension.summary",
                            "candidate_capability": "inventory_stock_balance_by_material_dimension",
                            "tool_id": "query_execution_planner.sql_assisted",
                            "semantic_trace": {
                                "fallback_sombreado_usado": True,
                                "regla_legacy_detectada": True,
                                "fuente_dd": ["ai_dictionary.dd_sinonimos"],
                            },
                        },
                        "evidence_summary": {
                            "response_profile_usado": "inventory.stock.dimension.summary",
                            "filters": {"descripcion": "CONECTOR RJ 45", "grouping_dimension": "movil"},
                            "output_profile": {"grain": "saldo_por_dimension_y_codigo", "columns": ["movil", "codigo", "saldo"]},
                        },
                    }
                },
            },
            run_context=run_context,
            response_flow="sql_assisted",
        )

        explanation = dict((((response.get("task") or {}).get("current_run") or {}).get("semantic_explanation") or {}))
        fallback = dict(explanation.get("fallback_used") or {})
        self.assertIn("compatibilidad semántica temporal", str(fallback.get("reason") or "").lower())
        self.assertNotIn("legacy_semantic_binding_shadowed", str(explanation))

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

    def test_inventory_employee_stock_route_guard_disables_legacy_path(self):
        route = ChatApplicationService._enforce_inventory_employee_stock_route(
            message="saldo empleado 1214730857 con nombre y movil asignada",
            route={
                "routing_mode": "capability",
                "selected_capability_id": "empleados.count.active.v1",
                "use_legacy": True,
                "legacy_capability_path_used": True,
            },
            query_intelligence={
                "execution_plan": {
                    "strategy": "sql_assisted",
                    "domain_code": "inventario_logistica",
                    "capability_id": "inventory_stock_balance_by_mobile",
                    "metadata": {"capability_id": "inventory_stock_balance_by_mobile"},
                }
            },
        )

        self.assertFalse(bool(route.get("use_legacy")))
        self.assertFalse(bool(route.get("legacy_capability_path_used")))
        self.assertEqual(str(route.get("selected_capability_compat_id") or ""), "inventory_stock_balance_by_mobile")
        self.assertEqual(str(route.get("reason") or ""), "inventory_employee_stock_route_guard")

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

    def test_attach_semantic_gap_learning_enriches_response_and_task_state(self):
        task_state_service = _TaskStateUpdateStub()
        service = ChatApplicationService(
            task_state_service=task_state_service,
            semantic_gap_registry_service=_GapRegistryStub(),
        )
        run_context = RunContext.create(
            message="que tiene Juan Perez",
            session_id="sess-gap-meta",
            reset_memory=False,
        )
        run_context.run_id = "run-gap-meta"
        run_context.metadata["task_state"] = {
            "workflow_key": "task_runtime:run-gap-meta",
            "state": {"task_id": "task_runtime:run-gap-meta"},
        }
        response = {
            "task_state": {
                "workflow_key": "task_runtime:run-gap-meta",
                "state": {"task_id": "task_runtime:run-gap-meta"},
            },
            "task": {
                "current_run": {
                    "evidence": {},
                    "semantic_explanation": {},
                }
            },
            "data_sources": {"runtime": {}},
        }

        enriched = service._attach_semantic_gap_learning(
            response=response,
            run_context=run_context,
        )

        trace = dict(
            ((((enriched.get("task") or {}).get("current_run") or {}).get("semantic_explanation") or {}).get(
                "continuous_runtime_learning"
            )
            or {}
        )
        )
        self.assertEqual(int(trace.get("registro_id") or 0), 41)
        self.assertEqual(str(trace.get("categoria_brecha") or ""), "consulta_ambigua")
        self.assertEqual(
            str((((enriched.get("data_sources") or {}).get("runtime") or {}).get("continuous_runtime_learning") or {}).get("estado_revision") or ""),
            "nueva",
        )
        self.assertEqual(str((task_state_service.updated or {}).get("run_id") or ""), "run-gap-meta")
