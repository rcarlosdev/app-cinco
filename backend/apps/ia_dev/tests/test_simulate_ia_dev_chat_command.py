from __future__ import annotations

import json
import os
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import SimpleTestCase

from apps.ia_dev.application.contracts.query_intelligence_contracts import (
    QueryExecutionPlan,
    ResolvedQuerySpec,
    StructuredQueryIntent,
)
from apps.ia_dev.application.orchestration.chat_application_service import (
    ChatApplicationService,
)
from apps.ia_dev.application.policies.policy_guard import (
    PolicyAction,
    PolicyDecision,
)
from apps.ia_dev.application.routing.capability_catalog import CapabilityCatalog


def _pilot_context() -> dict:
    return {
        "tables": [
            {"schema_name": "cincosas_cincosas", "table_name": "gestionh_ausentismo"},
            {"schema_name": "cincosas_cincosas", "table_name": "cinco_base_de_personal"},
        ],
        "column_profiles": [
            {"table_name": "gestionh_ausentismo", "logical_name": "fecha_ausentismo", "column_name": "fecha_edit"},
            {"table_name": "gestionh_ausentismo", "logical_name": "cedula", "column_name": "cedula"},
            {"table_name": "cinco_base_de_personal", "logical_name": "cedula", "column_name": "cedula"},
            {"table_name": "cinco_base_de_personal", "logical_name": "area", "column_name": "area"},
            {"table_name": "cinco_base_de_personal", "logical_name": "cargo", "column_name": "cargo"},
            {"table_name": "cinco_base_de_personal", "logical_name": "sede", "column_name": "zona_nodo"},
        ],
        "allowed_tables": [
            "cincosas_cincosas.gestionh_ausentismo",
            "cincosas_cincosas.cinco_base_de_personal",
        ],
        "allowed_columns": ["fecha_edit", "cedula", "area", "cargo", "zona_nodo"],
        "dictionary": {
            "fields": [{"logical_name": "area"}, {"logical_name": "cargo"}, {"logical_name": "sede"}],
            "relations": [
                {
                    "nombre_relacion": "ausentismo_empleado",
                    "join_sql": "gestionh_ausentismo.cedula = cinco_base_de_personal.cedula",
                }
            ],
        },
        "source_of_truth": {
            "pilot_sql_assisted_enabled": True,
            "used_dictionary": True,
            "used_yaml": True,
        },
        "query_hints": {
            "candidate_group_dimensions": ["area", "cargo", "sede"],
        },
        "supports_sql_assisted": True,
        "domain_status": "partial",
    }


def _sql_response() -> dict:
    return {
        "session_id": "simulate-arb-session",
        "reply": "Patrones detectados por area, cargo y sede.",
        "orchestrator": {
            "intent": "aggregate",
            "domain": "ausentismo",
            "selected_agent": "ausentismo_agent",
            "classifier_source": "query_intelligence_sql_assisted",
            "needs_database": True,
            "output_mode": "table",
            "used_tools": ["query_sql_assisted_executor"],
        },
        "data": {
            "kpis": {"total_grupos": 3},
            "series": [],
            "labels": [],
            "insights": ["Analisis resuelto con SQL assisted."],
            "table": {
                "columns": ["area", "cargo", "sede", "total_ausencias"],
                "rows": [
                    {"area": "OPERACIONES", "cargo": "AUXILIAR", "sede": "NORTE", "total_ausencias": 12},
                ],
                "rowcount": 1,
            },
        },
        "actions": [],
        "memory_candidates": [],
        "pending_proposals": [],
        "data_sources": {
            "query_intelligence": {
                "ok": True,
                "compiler": "join_aware_pilot",
                "analytics_router_decision": "join_aware_sql",
            }
        },
        "trace": [],
        "memory": {
            "used_messages": 0,
            "capacity_messages": 20,
            "usage_ratio": 0.0,
            "trim_events": 0,
            "saturated": False,
        },
        "observability": {
            "enabled": False,
            "duration_ms": 0,
            "tool_latencies_ms": {},
            "tokens_in": 0,
            "tokens_out": 0,
            "estimated_cost_usd": 0.0,
        },
        "active_nodes": [],
    }


def _birthday_sql_response() -> dict:
    return {
        "session_id": "birthday-session",
        "reply": "Se listan 2 empleados con cumpleanos en el mes 5.",
        "orchestrator": {
            "intent": "detail",
            "domain": "empleados",
            "selected_agent": "analista_agent",
            "classifier_source": "query_intelligence_sql_assisted",
            "needs_database": True,
            "output_mode": "table",
            "used_tools": ["query_sql_assisted_executor"],
            "runtime_flow": "sql_assisted",
        },
        "data": {
            "kpis": {"rowcount": 2},
            "series": [],
            "labels": [],
            "insights": ["Analisis resuelto con SQL assisted sobre fecha_nacimiento."],
            "table": {
                "columns": ["cedula", "nombre", "fnacimiento", "area"],
                "rows": [
                    {"cedula": "201", "nombre": "Diana", "fnacimiento": "1992-05-10", "area": "OPERACIONES"},
                    {"cedula": "202", "nombre": "Carlos", "fnacimiento": "1988-05-22", "area": "LOGISTICA"},
                ],
                "rowcount": 2,
            },
        },
        "actions": [],
        "memory_candidates": [],
        "pending_proposals": [],
        "data_sources": {
            "query_intelligence": {
                "ok": True,
                "compiler": "employee_semantic_sql",
                "metric_used": "employees",
            },
            "runtime": {
                "runtime_authority": "query_execution_planner",
                "planner_was_authority": True,
            },
        },
        "trace": [],
        "memory": {"used_messages": 0, "capacity_messages": 20, "usage_ratio": 0.0, "trim_events": 0, "saturated": False},
        "observability": {"enabled": False, "duration_ms": 0, "tool_latencies_ms": {}, "tokens_in": 0, "tokens_out": 0, "estimated_cost_usd": 0.0},
        "active_nodes": [],
    }


def _heights_sql_response() -> dict:
    return {
        "session_id": "heights-session",
        "reply": "12 certificados de alturas vencidos y 7 proximos a vencer en personal activo de labor operativa.",
        "orchestrator": {
            "intent": "count",
            "domain": "empleados",
            "selected_agent": "analista_agent",
            "classifier_source": "query_intelligence_sql_assisted",
            "needs_database": True,
            "output_mode": "summary",
            "used_tools": ["query_sql_assisted_executor"],
            "runtime_flow": "sql_assisted",
        },
        "data": {
            "kpis": {
                "certificados_vencidos": 12,
                "certificados_proximos_vencer": 7,
            },
            "series": [],
            "labels": [],
            "insights": [
                "Dato principal: 12 certificados de alturas vencidos y 7 proximos a vencer.",
                "Riesgo: tecnicos con certificado vencido no deberian ser asignados a trabajos en alturas.",
                "Recomendacion: priorizar renovacion de vencidos y programar renovacion de proximos a vencer.",
            ],
            "findings": [
                {
                    "title": "Riesgo documental operativo",
                    "detail": "El personal operativo activo tiene riesgo documental si hay certificados vencidos.",
                }
            ],
            "business_response": {
                "dato": "12 certificados de alturas vencidos y 7 proximos a vencer.",
                "hallazgo": "El personal operativo activo tiene riesgo documental si hay certificados vencidos.",
                "interpretacion": "La vigencia anual del certificado de alturas impacta la habilitacion operativa.",
                "riesgo": "Tecnicos con certificado vencido no deberian ser asignados a trabajos en alturas.",
                "recomendacion": "Priorizar renovacion de vencidos y programar renovacion de proximos a vencer.",
                "siguiente_accion": "Muestrame el detalle por empleado, area, supervisor o movil.",
            },
            "table": {
                "columns": ["certificados_vencidos", "certificados_proximos_vencer"],
                "rows": [{"certificados_vencidos": 12, "certificados_proximos_vencer": 7}],
                "rowcount": 1,
            },
        },
        "actions": [
            {
                "id": "heights-followup",
                "type": "followup",
                "label": "Muestrame el detalle por empleado, area, supervisor o movil.",
                "payload": {"metric_used": "certificado_alturas_vigencia"},
            }
        ],
        "memory_candidates": [],
        "pending_proposals": [],
        "data_sources": {
            "query_intelligence": {
                "ok": True,
                "compiler": "employee_semantic_sql",
                "metric_used": "certificado_alturas_vigencia",
            },
            "runtime": {
                "runtime_authority": "query_execution_planner",
                "planner_was_authority": True,
            },
        },
        "trace": [],
        "memory": {"used_messages": 0, "capacity_messages": 20, "usage_ratio": 0.0, "trim_events": 0, "saturated": False},
        "observability": {"enabled": False, "duration_ms": 0, "tool_latencies_ms": {}, "tokens_in": 0, "tokens_out": 0, "estimated_cost_usd": 0.0},
        "active_nodes": [],
    }


class _CapabilityRuntimeStub:
    def __init__(self):
        self.classifications_seen: list[dict] = []
        self.execute_calls: list[str] = []
        self.catalog = CapabilityCatalog()

    def _plan(self, classification: dict) -> dict:
        self.classifications_seen.append(dict(classification or {}))
        intent = str(classification.get("intent") or "")
        capability_id = (
            "knowledge.proposal.create.v1"
            if intent == "knowledge_change_request"
            else "attendance.summary.by_attribute.v1"
        )
        definition = self.catalog.get(capability_id)
        domain = capability_id.split(".", 1)[0] if "." in capability_id else "general"
        return {
            "capability_id": capability_id,
            "capability_exists": bool(definition),
            "rollout_enabled": True,
            "handler_key": definition.handler_key if definition else "legacy.passthrough",
            "policy_tags": list(definition.policy_tags) if definition else [],
            "legacy_intents": list(definition.legacy_intents) if definition else [],
            "reason": "test_plan",
            "source": {
                "intent": intent or "general_question",
                "domain": str(classification.get("domain") or domain),
                "output_mode": "table",
                "needs_database": True,
            },
            "dictionary_hints": {},
            "query_constraints": {},
            "candidate_rank": 1,
            "candidate_score": 100,
        }

    def build_bootstrap_plan(self, **kwargs):
        return self._plan(kwargs.get("classification") or {})

    def build_candidate_hints(self, **kwargs):
        return []

    def build_candidate_plans(self, **kwargs):
        return [self._plan(kwargs.get("classification") or {})]

    def build_route(self, **kwargs):
        planned = dict(kwargs.get("planned_capability") or {})
        capability_id = str(planned.get("capability_id") or "")
        return {
            "routing_mode": "capability",
            "selected_capability_id": capability_id,
            "execute_capability": True,
            "use_legacy": False,
            "reason": "test_route",
            "policy_action": "allow",
            "policy_allowed": True,
            "capability_exists": True,
            "rollout_enabled": True,
        }

    def execute(self, **kwargs):
        planned = dict(kwargs.get("planned_capability") or {})
        capability_id = str(planned.get("capability_id") or "")
        self.execute_calls.append(capability_id)
        raise AssertionError("capability_handler no debe ejecutarse antes del arbitraje sql_assisted")


class _PolicyGuardStub:
    def evaluate(self, **kwargs):
        return PolicyDecision(
            action=PolicyAction.ALLOW,
            policy_id="policy.test.allow",
            reason="allow",
            metadata={},
        )


class _NoDelegationCoordinator:
    def plan_and_maybe_execute(self, **kwargs):
        return {
            "mode": "off",
            "should_delegate": False,
            "plan_reason": "",
            "selected_domains": [],
            "tasks": [],
            "executed": False,
            "response": None,
            "warnings": [],
        }


class _MemoryRuntimeStub:
    def load_context_for_chat(self, **kwargs):
        return {
            "flags": {"read_enabled": True, "write_enabled": True, "proposals_enabled": True},
            "decision": {"action": "read", "reason": "test"},
            "user_memory": [],
            "business_memory": [],
            "used": False,
        }

    def detect_candidates(self, **kwargs):
        return []

    def persist_candidates(self, **kwargs):
        return {"memory_candidates": [], "pending_proposals": [], "actions": []}


class _TaskStateServiceStub:
    def save(self, **kwargs):
        return {
            "workflow_key": "task_runtime:test",
            "status": str(kwargs.get("status") or ""),
        }


class _FakeChatApplicationService:
    last_capability_runtime: _CapabilityRuntimeStub | None = None

    def __init__(self):
        capability_runtime = _CapabilityRuntimeStub()
        self._service = ChatApplicationService(
            capability_runtime_adapter=capability_runtime,
            policy_guard=_PolicyGuardStub(),
            memory_runtime=_MemoryRuntimeStub(),
            delegation_coordinator=_NoDelegationCoordinator(),
            task_state_service=_TaskStateServiceStub(),
        )
        self._service.semantic_business_resolver.build_semantic_context = lambda **_: _pilot_context()
        self._service.semantic_business_resolver.resolve_query = lambda **kwargs: ResolvedQuerySpec(
            intent=kwargs["intent"],
            semantic_context=_pilot_context(),
            normalized_period={"start_date": "2026-01-01", "end_date": "2026-01-31"},
        )
        self._service.query_intent_resolver.match_query_pattern = lambda **_: None
        self._service.query_intent_resolver.resolve = lambda **kwargs: StructuredQueryIntent(
            raw_query=kwargs["message"],
            domain_code="ausentismo",
            operation="aggregate",
            template_id="aggregate_by_group_and_period",
            confidence=0.86,
            source="rules",
            group_by=["area", "cargo", "sede"],
        )
        self._service.query_execution_planner.plan = lambda **kwargs: QueryExecutionPlan(
            strategy="sql_assisted",
            reason="sql_assisted_ready",
            domain_code="ausentismo",
            capability_id="attendance.summary.by_attribute.v1",
            sql_query="SELECT area, cargo, zona_nodo, COUNT(*) AS total_ausencias FROM demo",
            metadata={
                "analytics_router_decision": "join_aware_sql",
                "compiler": "join_aware_pilot",
                "relations_used": ["gestionh_ausentismo.cedula = cinco_base_de_personal.cedula"],
                "dimensions_used": ["area", "cargo", "sede"],
                "cleanup_phase": "phase_7",
            },
        )
        self._service.query_execution_planner.execute_sql_assisted = lambda **_: {
            "ok": True,
            "response": _sql_response(),
            "used_legacy": False,
            "analytics_router_decision": "join_aware_sql",
        }
        def _resolve_query_intelligence_stub(**kwargs):
            payload = {
                "mode": "active",
                "enabled": True,
                "resolved_query": {
                    "intent": {
                        "raw_query": kwargs["message"],
                        "domain_code": "ausentismo",
                        "operation": "aggregate",
                        "template_id": "aggregate_by_group_and_period",
                        "group_by": ["area", "cargo", "sede"],
                    },
                    "semantic_context": _pilot_context(),
                    "normalized_period": {"start_date": "2026-01-01", "end_date": "2026-01-31"},
                },
                "execution_plan": {
                    "strategy": "sql_assisted",
                    "reason": "sql_assisted_ready",
                    "domain_code": "ausentismo",
                    "capability_id": "attendance.summary.by_attribute.v1",
                    "sql_query": "SELECT area, cargo, zona_nodo, COUNT(*) AS total_ausencias FROM demo",
                    "metadata": {
                        "analytics_router_decision": "join_aware_sql",
                        "compiler": "join_aware_pilot",
                        "relations_used": ["gestionh_ausentismo.cedula = cinco_base_de_personal.cedula"],
                        "dimensions_used": ["area", "cargo", "sede"],
                        "cleanup_phase": "phase_7",
                    },
                },
                "classification_override": {
                    "intent": "aggregate",
                    "domain": "ausentismo",
                    "selected_agent": "ausentismo_agent",
                    "classifier_source": "query_intelligence_rules",
                    "needs_database": True,
                    "output_mode": "table",
                },
                "precomputed_response": _sql_response(),
                "execution_result": {
                    "ok": True,
                    "response": _sql_response(),
                    "used_legacy": False,
                    "analytics_router_decision": "join_aware_sql",
                },
                "intent_arbitration": {
                    "final_intent": "analytics_query",
                    "final_domain": "ausentismo",
                    "heuristic_intent": "knowledge_change_request",
                    "llm_intent": "aggregate",
                    "confidence": 0.91,
                    "reasoning_summary": "Consulta analitica sobre datos existentes.",
                    "should_execute_query": True,
                    "should_use_sql_assisted": True,
                    "sql_assisted_selected_by_arbitration": True,
                },
            }
            kwargs["run_context"].metadata["query_intelligence"] = dict(payload)
            kwargs["run_context"].metadata["intent_arbitration"] = dict(payload["intent_arbitration"])
            return payload

        self._service._resolve_query_intelligence = _resolve_query_intelligence_stub
        self._service.result_satisfaction_validator.validate = lambda **_: type(
            "_Validation",
            (),
            {"satisfied": True, "as_dict": lambda self: {"satisfied": True}},
        )()
        _FakeChatApplicationService.last_capability_runtime = capability_runtime

    def run(
        self,
        *,
        message: str,
        session_id: str | None = None,
        reset_memory: bool = False,
        actor_user_key: str | None = None,
        legacy_runner=None,
        observability=None,
    ):
        del legacy_runner, observability
        with patch.object(
            ChatApplicationService,
            "_bootstrap_classification",
            return_value={
                "intent": "knowledge_change_request",
                "domain": "knowledge",
                "selected_agent": "analista_agent",
                "classifier_source": "test_conflicting_heuristic",
                "needs_database": False,
                "output_mode": "summary",
                "confidence": 0.84,
            },
        ):
            return self._service.run(
                message=message,
                session_id=session_id,
                reset_memory=reset_memory,
                legacy_runner=lambda **_: {"reply": "legacy"},
                actor_user_key=actor_user_key,
            )


class _CaptureChatApplicationService:
    calls: list[dict] = []

    def run(
        self,
        *,
        message: str,
        session_id: str | None = None,
        reset_memory: bool = False,
        actor_user_key: str | None = None,
        legacy_runner=None,
        observability=None,
    ):
        del actor_user_key, legacy_runner, observability
        self.__class__.calls.append(
            {
                "message": message,
                "session_id": session_id,
                "reset_memory": reset_memory,
            }
        )
        return _sql_response()


class SimulateIADevChatCommandTests(SimpleTestCase):
    def test_resolution_summary_prefers_final_ausentismo_domain_for_sql_assisted_runtime(self):
        from apps.ia_dev.management.commands.simulate_ia_dev_chat import Command

        resumen = Command()._build_resolucion_consulta_resumen(
            orchestrator={
                "domain": "ausentismo",
                "runtime_flow": "sql_assisted",
                "arbitrated_intent": "analytics_query",
                "final_intent": "analytics_query",
            },
            route={"selected_capability_id": "attendance.summary.by_attribute.v1"},
            intent={
                "raw_query": "Que patrones existen por area, cargo y sede",
                "domain_code": "empleados",
                "operation": "aggregate",
                "filters": {},
            },
            execution_plan={
                "domain_code": "ausentismo",
                "capability_id": "attendance.summary.by_attribute.v1",
                "constraints": {"filters": {}},
            },
            semantic_normalization={"domain_code": "empleados", "normalized_filters": {}},
            canonical_resolution={},
        )

        self.assertEqual(str(resumen.get("codigo_dominio") or ""), "ausentismo")

    def test_service_runtime_prefers_arbitrated_sql_assisted_without_kpro(self):
        env = {
            "IA_DEV_QUERY_INTELLIGENCE_ENABLED": "1",
            "IA_DEV_QUERY_INTELLIGENCE_MODE": "active",
            "IA_DEV_QUERY_SQL_ASSISTED_ENABLED": "1",
            "IA_DEV_ATTENDANCE_EMPLOYEES_PILOT_ENABLED": "1",
            "IA_DEV_USE_OPENAI_INTENT_ARBITRATION": "0",
            "IA_DEV_QUERY_INTELLIGENCE_OPENAI_ENABLED": "0",
            "IA_DEV_CONTEXT_BUILDER_ENABLED": "0",
            "IA_DEV_CONTEXT_BUILDER_SHADOW_ENABLED": "0",
            "IA_DEV_SEMANTIC_NORMALIZATION_ENABLED": "0",
            "IA_DEV_SEMANTIC_NORMALIZATION_SHADOW_ENABLED": "0",
            "IA_DEV_CANONICAL_RESOLUTION_ENABLED": "0",
            "IA_DEV_CANONICAL_RESOLUTION_SHADOW_ENABLED": "0",
        }
        with patch.dict(os.environ, env, clear=False):
            service = _FakeChatApplicationService()
            response = service.run(
                message="Que patrones existen por area, cargo y sede",
                session_id="simulate-arb-session",
            )

        orchestrator_meta = dict(response.get("orchestrator") or {})
        runtime_meta = dict((response.get("data_sources") or {}).get("runtime") or {})

        self.assertEqual(str(orchestrator_meta.get("arbitrated_intent") or ""), "analytics_query")
        self.assertEqual(str(orchestrator_meta.get("final_intent") or ""), "analytics_query")
        self.assertEqual(str(orchestrator_meta.get("runtime_flow") or ""), "sql_assisted")
        self.assertEqual(str(orchestrator_meta.get("compiler_used") or ""), "join_aware_pilot")
        self.assertEqual(str(orchestrator_meta.get("analytics_router_decision") or ""), "join_aware_sql")
        self.assertEqual(str(runtime_meta.get("analytics_router_decision") or ""), "join_aware_sql")
        self.assertEqual(str(runtime_meta.get("compiler_used") or ""), "join_aware_pilot")
        self.assertEqual(str(runtime_meta.get("runtime_authority") or ""), "query_execution_planner")
        self.assertFalse(bool(runtime_meta.get("legacy_capability_path_used")))
        self.assertEqual(
            str((_FakeChatApplicationService.last_capability_runtime.classifications_seen[0] or {}).get("intent") or ""),
            "aggregate",
        )
        self.assertEqual(_FakeChatApplicationService.last_capability_runtime.execute_calls, [])

    def test_management_command_raw_output_exposes_runtime_metadata(self):
        env = {
            "IA_DEV_QUERY_INTELLIGENCE_ENABLED": "1",
            "IA_DEV_QUERY_INTELLIGENCE_MODE": "active",
            "IA_DEV_QUERY_SQL_ASSISTED_ENABLED": "1",
            "IA_DEV_ATTENDANCE_EMPLOYEES_PILOT_ENABLED": "1",
            "IA_DEV_USE_OPENAI_INTENT_ARBITRATION": "0",
            "IA_DEV_QUERY_INTELLIGENCE_OPENAI_ENABLED": "0",
            "IA_DEV_CONTEXT_BUILDER_ENABLED": "0",
            "IA_DEV_CONTEXT_BUILDER_SHADOW_ENABLED": "0",
            "IA_DEV_SEMANTIC_NORMALIZATION_ENABLED": "0",
            "IA_DEV_SEMANTIC_NORMALIZATION_SHADOW_ENABLED": "0",
            "IA_DEV_CANONICAL_RESOLUTION_ENABLED": "0",
            "IA_DEV_CANONICAL_RESOLUTION_SHADOW_ENABLED": "0",
        }
        stdout = StringIO()

        with patch.dict(os.environ, env, clear=False):
            with patch(
                "apps.ia_dev.management.commands.simulate_ia_dev_chat.ChatApplicationService",
                _FakeChatApplicationService,
            ):
                call_command(
                    "simulate_ia_dev_chat",
                    "--message",
                    "Que patrones existen por area, cargo y sede",
                    "--session-id",
                    "simulate-arb-session",
                    "--raw",
                    stdout=stdout,
                )

        payload = json.loads(stdout.getvalue())
        orchestrator = dict(payload.get("orchestrator") or {})

        self.assertEqual(str(orchestrator.get("runtime_flow") or ""), "sql_assisted")
        self.assertEqual(str(orchestrator.get("compiler_used") or ""), "join_aware_pilot")
        self.assertEqual(str(orchestrator.get("analytics_router_decision") or ""), "join_aware_sql")
        self.assertEqual(str(orchestrator.get("arbitrated_intent") or ""), "analytics_query")

    def test_management_command_raw_output_exposes_employee_birthday_sql_runtime(self):
        stdout = StringIO()

        class _BirthdayChatApplicationService:
            def run(self, **kwargs):
                del kwargs
                return _birthday_sql_response()

        with patch(
            "apps.ia_dev.management.commands.simulate_ia_dev_chat.ChatApplicationService",
            _BirthdayChatApplicationService,
        ):
            call_command(
                "simulate_ia_dev_chat",
                "--message",
                "Cumpleaños de mayo",
                "--session-id",
                "birthday-session",
                "--raw",
                stdout=stdout,
            )

        payload = json.loads(stdout.getvalue())
        orchestrator = dict(payload.get("orchestrator") or {})
        runtime = dict((payload.get("data_sources") or {}).get("runtime") or {})
        table = dict((payload.get("data") or {}).get("table") or {})

        self.assertEqual(str(orchestrator.get("domain") or ""), "empleados")
        self.assertEqual(str(orchestrator.get("runtime_flow") or ""), "sql_assisted")
        self.assertEqual(str(runtime.get("runtime_authority") or ""), "query_execution_planner")
        self.assertTrue(bool(runtime.get("planner_was_authority")))
        self.assertEqual(int(table.get("rowcount") or 0), 2)

    def test_management_command_raw_output_preserves_heights_business_response(self):
        stdout = StringIO()

        class _HeightsChatApplicationService:
            def run(self, **kwargs):
                del kwargs
                return _heights_sql_response()

        with patch(
            "apps.ia_dev.management.commands.simulate_ia_dev_chat.ChatApplicationService",
            _HeightsChatApplicationService,
        ):
            call_command(
                "simulate_ia_dev_chat",
                "--message",
                "si el certificado de alturas vence cada año, cuántos certificados están vencidos y cuántos certificados están próximos a vencer, solo personal activo y tipo de labor operativo",
                "--session-id",
                "heights-session",
                "--raw",
                stdout=stdout,
            )

        payload = json.loads(stdout.getvalue())
        business_response = dict((payload.get("data") or {}).get("business_response") or {})
        query_intelligence = dict((payload.get("data_sources") or {}).get("query_intelligence") or {})

        self.assertEqual(str(query_intelligence.get("metric_used") or ""), "certificado_alturas_vigencia")
        self.assertIn("certificados de alturas vencidos", str(business_response.get("dato") or "").lower())
        self.assertIn("riesgo documental", str(business_response.get("hallazgo") or "").lower())
        self.assertIn("no deberian ser asignados", str(business_response.get("riesgo") or "").lower())
        self.assertIn("priorizar renovacion", str(business_response.get("recomendacion") or "").lower())
        self.assertEqual(
            str(business_response.get("siguiente_accion") or ""),
            "Muestrame el detalle por empleado, area, supervisor o movil.",
        )

    def test_management_command_module_does_not_import_legacy_adapter(self):
        import apps.ia_dev.management.commands.simulate_ia_dev_chat as command_module

        self.assertFalse(hasattr(command_module, "IADevOrchestratorService"))

    def test_cli_message_normalizer_repairs_utf8_mojibake(self):
        from apps.ia_dev.management.commands.simulate_ia_dev_chat import Command

        repaired = Command._normalize_cli_message("QuÃ© patrones existen por Ã¡rea, cargo y sede")

        self.assertEqual(repaired, "Qué patrones existen por área, cargo y sede")

    def test_interactive_and_non_interactive_pass_same_normalized_message(self):
        stdout = StringIO()
        _CaptureChatApplicationService.calls = []

        with patch(
            "apps.ia_dev.management.commands.simulate_ia_dev_chat.ChatApplicationService",
            _CaptureChatApplicationService,
        ):
            call_command(
                "simulate_ia_dev_chat",
                "--message",
                "QuÃ© patrones existen por Ã¡rea, cargo y sede",
                "--session-id",
                "sem-final-check",
                stdout=stdout,
            )
            with patch("builtins.input", side_effect=["QuÃ© patrones existen por Ã¡rea, cargo y sede", "/exit"]):
                call_command(
                    "simulate_ia_dev_chat",
                    "--interactive",
                    "--session-id",
                    "sem-final-check",
                    stdout=stdout,
                )

        self.assertEqual(len(_CaptureChatApplicationService.calls), 2)
        self.assertEqual(
            [item.get("message") for item in _CaptureChatApplicationService.calls],
            [
                "Qué patrones existen por área, cargo y sede",
                "Qué patrones existen por área, cargo y sede",
            ],
        )

    def test_service_runtime_bootstrap_includes_sql_assisted_and_pilot_flags(self):
        from apps.ia_dev.application.runtime.service_runtime_bootstrap import SERVICE_RUNTIME_DEFAULTS

        self.assertEqual(str(SERVICE_RUNTIME_DEFAULTS.get("IA_DEV_QUERY_SQL_ASSISTED_ENABLED") or ""), "1")
        self.assertEqual(str(SERVICE_RUNTIME_DEFAULTS.get("IA_DEV_ATTENDANCE_EMPLOYEES_PILOT_ENABLED") or ""), "1")

    def test_interactive_live_human_command_is_accepted(self):
        stdout = StringIO()

        with patch("builtins.input", side_effect=["/live human", "/exit"]):
            call_command(
                "simulate_ia_dev_chat",
                "--interactive",
                "--session-id",
                "demo-ia",
                stdout=stdout,
            )

        output = stdout.getvalue()
        self.assertIn("live_mode=human", output)
        self.assertNotIn("live invalido", output)

    def test_interactive_auto_live_defaults_to_human(self):
        stdout = StringIO()

        with patch("builtins.input", side_effect=["/exit"]):
            call_command(
                "simulate_ia_dev_chat",
                "--interactive",
                "--session-id",
                "demo-ia",
                stdout=stdout,
            )

        output = stdout.getvalue()
        self.assertIn("live_mode=human", output)

    def test_runtime_event_humanizer_translates_memory_event(self):
        from apps.ia_dev.management.commands.simulate_ia_dev_chat import RuntimeEventHumanizer

        rendered = RuntimeEventHumanizer(message="ausentismos de hoy").humanize_event(
            {
                "event_type": "memory_used_in_chat",
                "meta": {
                    "user_memory_count": 1,
                    "business_memory_count": 2,
                },
            }
        )

        self.assertIsNotNone(rendered)
        self.assertIn("memoria y contexto del negocio", str(rendered.get("message") or "").lower())

    def test_query_intelligence_error_is_explained_in_spanish(self):
        from apps.ia_dev.management.commands.simulate_ia_dev_chat import RuntimeEventHumanizer

        rendered = RuntimeEventHumanizer().humanize_event(
            {
                "event_type": "query_intelligence_error",
                "meta": {"error": "planner failed"},
            }
        )

        message = str(rendered.get("message") or "")
        self.assertIn("ruta inteligente de consulta", message)
        self.assertIn("ruta segura alternativa", message)

    def test_sql_assisted_event_is_described_as_intelligent_data_query(self):
        from apps.ia_dev.management.commands.simulate_ia_dev_chat import RuntimeEventHumanizer

        rendered = RuntimeEventHumanizer().humanize_event(
            {
                "event_type": "query_sql_assisted_executed",
                "meta": {"domain_code": "ausentismo", "rowcount": 53},
            }
        )

        message = str(rendered.get("message") or "").lower()
        self.assertIn("consulta inteligente sobre datos reales", message)
        self.assertIn("ausentismo", message)

    def test_handler_event_is_described_as_modern_safe_route(self):
        from apps.ia_dev.management.commands.simulate_ia_dev_chat import RuntimeEventHumanizer

        rendered = RuntimeEventHumanizer().humanize_event(
            {
                "event_type": "ausentismo_handler_executed",
                "meta": {
                    "capability_domain": "ausentismo",
                    "capability_id": "attendance.summary.by_attribute.v1",
                },
            }
        )

        message = str(rendered.get("message") or "").lower()
        self.assertIn("handler moderno seguro", message)
        self.assertIn("ruta moderna segura", message)

    def test_fallback_event_is_soft_and_non_alarmist(self):
        from apps.ia_dev.management.commands.simulate_ia_dev_chat import RuntimeEventHumanizer

        rendered = RuntimeEventHumanizer().humanize_event(
            {
                "event_type": "runtime_fallback_used",
                "meta": {"fallback_reason": "missing_metadata"},
            }
        )

        message = str(rendered.get("message") or "").lower()
        self.assertIn("fallback seguro", message)
        self.assertIn("metadata", message)
        self.assertNotIn("fatal", message)

    def test_compact_and_full_live_modes_keep_technical_rendering(self):
        from apps.ia_dev.management.commands.simulate_ia_dev_chat import Command

        command = Command()
        command.stdout = StringIO()
        event = {
            "event_type": "query_sql_assisted_executed",
            "source": "QueryExecutionPlanner",
            "duration_ms": 12,
            "meta": {
                "domain_code": "ausentismo",
                "strategy": "sql_assisted",
                "reply_preview": "53 hallazgos",
            },
        }

        command._emit_live_event(event=event, live_mode="compact")
        compact_output = command.stdout.getvalue()
        self.assertIn("live>", compact_output)
        self.assertIn("query_sql_assisted_executed", compact_output)

        command.stdout = StringIO()
        command._emit_live_event(event=event, live_mode="full")
        full_output = command.stdout.getvalue()
        self.assertIn("live>", full_output)
        self.assertIn("meta=", full_output)

    def test_print_payload_human_adds_executive_summary(self):
        from apps.ia_dev.management.commands.simulate_ia_dev_chat import Command, RuntimeEventHumanizer

        payload = {
            "reply": "Hoy se registran 53 ausentismos injustificados.",
            "session_id": "demo-ia",
            "orchestrator": {
                "domain": "ausentismo",
                "runtime_flow": "handler",
            },
            "data": {
                "kpis": {"total_ausentismos_injustificados": 53},
                "insights": ["Se concentran en una misma franja operativa."],
            },
            "data_sources": {
                "query_intelligence": {
                    "resolved_query": {
                        "intent": {"domain_code": "ausentismo"},
                        "normalized_period": {"start_date": "2026-05-04", "end_date": "2026-05-04"},
                    },
                    "execution_plan": {"strategy": "handler"},
                },
                "runtime": {"runtime_authority": "query_execution_planner"},
            },
            "actions": [],
        }
        command = Command()
        command.stdout = StringIO()
        command._active_humanizer = RuntimeEventHumanizer(message="ausentismos de hoy")

        command._print_payload(payload, raw=False, flow_mode="off", live_mode="human")
        output = command.stdout.getvalue()

        self.assertIn("Dato principal:", output)
        self.assertIn("Flujo explicado:", output)
        self.assertIn("Se identifico el dominio: ausentismo.", output)
