from __future__ import annotations

import json
import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.ia_dev.application.context.run_context import RunContext
from apps.ia_dev.application.contracts.chat_contracts import build_chat_response_snapshot
from apps.ia_dev.application.orchestration.response_assembler import LegacyResponseAssembler
from apps.ia_dev.application.runtime.service_runtime_bootstrap import apply_service_runtime_bootstrap
from apps.ia_dev.application.policies.policy_guard import PolicyAction, PolicyDecision
from apps.ia_dev.services.runtime_fallback_service import RuntimeFallbackService
from apps.ia_dev.views import chat_view as chat_view_module
from apps.ia_dev.views.chat_view import (
    IADevAttendancePeriodResolveView,
    IADevChatView,
    IADevKnowledgeApproveView,
    IADevMemoryResetView,
    IADevObservabilitySummaryView,
)


class IADevRegressionEndpointsTests(SimpleTestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = SimpleNamespace(
            id=77,
            username="regression-user",
            is_authenticated=True,
            is_staff=False,
            is_superuser=False,
        )
        chat_view_module.chat_application_service = None
        chat_view_module.runtime_fallback_service = None
        chat_view_module.session_memory_runtime_service = MagicMock()
        chat_view_module.attendance_period_resolver_service = MagicMock()

    def test_chat_endpoint_keeps_contract_shape(self):
        snapshot = build_chat_response_snapshot()
        snapshot["session_id"] = "sess-123"
        snapshot["reply"] = "ok"
        chat_service = MagicMock()
        chat_service.run.return_value = snapshot
        chat_view_module.chat_application_service = chat_service

        with patch.object(chat_view_module, "_get_runtime_fallback_service", side_effect=AssertionError("runtime fallback no debe inicializarse")):
            with patch.object(chat_view_module.observability_service, "record_event"):
                request = self.factory.post(
                    "/ia-dev/chat/",
                    {"message": "hola", "session_id": "sess-123"},
                    format="json",
                )
                force_authenticate(request, user=self.user)
                response = IADevChatView.as_view()(request)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(set(response.data.keys()), set(snapshot.keys()))
        self.assertEqual(response.data["session_id"], "sess-123")
        self.assertIn("observability", response.data)
        self.assertEqual(
            response.data.get("data_sources", {}).get("runtime", {}).get("entrypoint"),
            "chat_view_direct",
        )
        self.assertEqual(
            response.data.get("data_sources", {}).get("runtime", {}).get("runtime_owner"),
            "ChatApplicationService",
        )
        self.assertTrue(bool(response.data.get("data_sources", {}).get("runtime", {}).get("legacy_adapter_removed")))
        self.assertFalse(bool(response.data.get("data_sources", {}).get("runtime", {}).get("legacy_runtime_fallback_used")))
        chat_service.run.assert_called_once()

    def test_chat_endpoint_calls_chat_application_service_directly(self):
        snapshot = build_chat_response_snapshot()
        snapshot["session_id"] = "sess-direct"
        snapshot["reply"] = "direct"
        chat_service = MagicMock()
        chat_service.run.return_value = snapshot
        chat_view_module.chat_application_service = chat_service

        with patch.object(chat_view_module.observability_service, "record_event") as mock_record_event:
            request = self.factory.post(
                "/ia-dev/chat/",
                {"message": "consulta sana", "session_id": "sess-direct"},
                format="json",
            )
            force_authenticate(request, user=self.user)
            response = IADevChatView.as_view()(request)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        call_kwargs = chat_service.run.call_args.kwargs
        self.assertEqual(call_kwargs["message"], "consulta sana")
        self.assertEqual(call_kwargs["session_id"], "sess-direct")
        self.assertEqual(call_kwargs["actor_user_key"], "user:77")
        self.assertIs(call_kwargs["observability"], chat_view_module.observability_service)
        self.assertTrue(callable(call_kwargs["legacy_runner"]))
        meta = mock_record_event.call_args.kwargs["meta"]
        self.assertEqual(meta["entrypoint"], "chat_view_direct")
        self.assertEqual(meta["runtime_owner"], "ChatApplicationService")
        self.assertTrue(bool(meta["legacy_adapter_removed"]))
        self.assertFalse(bool(meta["legacy_runtime_fallback_used"]))

    def test_chat_endpoint_fallbacks_to_runtime_fallback_service_when_chat_application_service_fails(self):
        chat_service = MagicMock()
        chat_service.run.side_effect = RuntimeError("boom")
        legacy_service = MagicMock()
        legacy_snapshot = build_chat_response_snapshot()
        legacy_snapshot["session_id"] = "sess-fallback"
        legacy_snapshot["reply"] = "legacy ok"
        legacy_service.run.return_value = legacy_snapshot
        chat_view_module.chat_application_service = chat_service
        chat_view_module.runtime_fallback_service = legacy_service

        with patch.object(chat_view_module.observability_service, "record_event") as mock_record_event:
            request = self.factory.post(
                "/ia-dev/chat/",
                {"message": "consulta fallback", "session_id": "sess-fallback"},
                format="json",
            )
            force_authenticate(request, user=self.user)
            response = IADevChatView.as_view()(request)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        legacy_service.run.assert_called_once_with(
            message="consulta fallback",
            session_id="sess-fallback",
            reset_memory=False,
            actor_user_key="user:77",
            fallback_reason="chat_application_service_exception:RuntimeError",
        )
        runtime_meta = response.data.get("data_sources", {}).get("runtime", {})
        self.assertTrue(bool(runtime_meta.get("legacy_adapter_removed")))
        self.assertTrue(bool(runtime_meta.get("legacy_runtime_fallback_used")))
        self.assertEqual(runtime_meta.get("runtime_owner"), "ChatApplicationService")
        self.assertIn(
            "chat_application_service_exception:RuntimeError",
            str(runtime_meta.get("legacy_runtime_fallback_reason") or ""),
        )
        meta = mock_record_event.call_args.kwargs["meta"]
        self.assertTrue(bool(meta["legacy_adapter_removed"]))
        self.assertTrue(bool(meta["legacy_runtime_fallback_used"]))
        self.assertIn(
            "chat_application_service_exception:RuntimeError",
            str(meta["legacy_runtime_fallback_reason"] or ""),
        )

    def test_chat_endpoint_preserves_internal_legacy_runtime_fallback_metadata(self):
        snapshot = build_chat_response_snapshot()
        snapshot["session_id"] = "sess-inner-fallback"
        snapshot["reply"] = "legacy interno"
        snapshot["data_sources"] = {
            "runtime": {
                "legacy_runtime_fallback_used": True,
                "legacy_runtime_fallback_reason": "legacy_runtime_fallback",
            }
        }
        chat_service = MagicMock()
        chat_service.run.return_value = snapshot
        chat_view_module.chat_application_service = chat_service

        with patch.object(chat_view_module.observability_service, "record_event") as mock_record_event:
            request = self.factory.post(
                "/ia-dev/chat/",
                {"message": "consulta con fallback interno", "session_id": "sess-inner-fallback"},
                format="json",
            )
            force_authenticate(request, user=self.user)
            response = IADevChatView.as_view()(request)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        runtime_meta = response.data.get("data_sources", {}).get("runtime", {})
        self.assertTrue(bool(runtime_meta.get("legacy_runtime_fallback_used")))
        self.assertEqual(
            str(runtime_meta.get("legacy_runtime_fallback_reason") or ""),
            "legacy_runtime_fallback",
        )
        meta = mock_record_event.call_args.kwargs["meta"]
        self.assertTrue(bool(meta["legacy_runtime_fallback_used"]))
        self.assertEqual(
            str(meta["legacy_runtime_fallback_reason"] or ""),
            "legacy_runtime_fallback",
        )

    def test_memory_reset_endpoint_uses_session_memory_runtime_service(self):
        chat_view_module.session_memory_runtime_service.reset_memory.return_value = {
            "session_id": "sess-reset",
            "memory": {"used_messages": 0},
        }

        request = self.factory.post(
            "/ia-dev/memory/reset/",
            {"session_id": "sess-reset"},
            format="json",
        )
        force_authenticate(request, user=self.user)
        response = IADevMemoryResetView.as_view()(request)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        chat_view_module.session_memory_runtime_service.reset_memory.assert_called_once_with("sess-reset")

    def test_attendance_period_endpoint_uses_period_resolver_service(self):
        chat_view_module.attendance_period_resolver_service.resolve_attendance_period.return_value = {
            "session_id": "sess-period",
            "resolved_period": {"label": "hoy", "start_date": "2026-05-03", "end_date": "2026-05-03"},
            "rules_fallback_period": {"label": "hoy", "start_date": "2026-05-03", "end_date": "2026-05-03"},
        }

        request = self.factory.post(
            "/ia-dev/attendance/period/resolve/",
            {"message": "hoy", "session_id": "sess-period"},
            format="json",
        )
        force_authenticate(request, user=self.user)
        response = IADevAttendancePeriodResolveView.as_view()(request)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        chat_view_module.attendance_period_resolver_service.resolve_attendance_period.assert_called_once_with(
            message="hoy",
            session_id="sess-period",
        )

    def test_runtime_fallback_bootstraps_http_runtime_defaults_when_explicitly_enabled(self):
        with patch.dict(
            os.environ,
            {
                "IA_DEV_SERVICE_RUNTIME_BOOTSTRAP_ENABLED": "1",
                "IA_DEV_SERVICE_RUNTIME_BOOTSTRAP_FORCE": "0",
                "IA_DEV_CAP_ATTENDANCE_ENABLED": "",
                "IA_DEV_CAP_ATTENDANCE_ANALYTICS_ENABLED": "",
                "IA_DEV_CAP_ATTENDANCE_TABLE_ENABLED": "",
                "IA_DEV_POLICY_CAPABILITY_EXECUTION_ENABLED": "",
                "IA_DEV_POLICY_MEMORY_HINTS_ENABLED": "",
                "IA_DEV_POLICY_ATTENDANCE_PERSONAL_JOIN_ENABLED": "",
                "IA_DEV_QUERY_PATTERN_MEMORY_ENABLED": "",
                "IA_DEV_QUERY_PATTERN_FASTPATH_ENABLED": "",
            },
            clear=False,
        ):
            service = RuntimeFallbackService()

        applied = dict(service.runtime_bootstrap.get("applied") or {})
        self.assertEqual(applied.get("IA_DEV_CAP_ATTENDANCE_ENABLED"), "1")
        self.assertEqual(applied.get("IA_DEV_CAP_ATTENDANCE_ANALYTICS_ENABLED"), "1")
        self.assertEqual(applied.get("IA_DEV_CAP_ATTENDANCE_TABLE_ENABLED"), "1")
        self.assertEqual(applied.get("IA_DEV_POLICY_CAPABILITY_EXECUTION_ENABLED"), "1")
        self.assertEqual(applied.get("IA_DEV_POLICY_MEMORY_HINTS_ENABLED"), "1")
        self.assertEqual(applied.get("IA_DEV_POLICY_ATTENDANCE_PERSONAL_JOIN_ENABLED"), "1")
        self.assertEqual(applied.get("IA_DEV_QUERY_PATTERN_MEMORY_ENABLED"), "1")
        self.assertEqual(applied.get("IA_DEV_QUERY_PATTERN_FASTPATH_ENABLED"), "1")
        self.assertTrue(service.runtime_bootstrap.get("enabled"))

    def test_runtime_bootstrap_helper_does_not_override_runtime_env_when_bootstrap_disabled(self):
        with patch.dict(
            os.environ,
            {
                "IA_DEV_SERVICE_RUNTIME_BOOTSTRAP_ENABLED": "0",
                "IA_DEV_SERVICE_RUNTIME_BOOTSTRAP_FORCE": "0",
                "IA_DEV_ROUTING_MODE": "intent",
                "IA_DEV_QUERY_SQL_ASSISTED_ENABLED": "0",
                "IA_DEV_ATTENDANCE_EMPLOYEES_PILOT_ENABLED": "0",
            },
            clear=False,
        ):
            bootstrap = apply_service_runtime_bootstrap()
            self.assertFalse(bool(bootstrap.get("enabled")))
            self.assertEqual(os.getenv("IA_DEV_ROUTING_MODE"), "intent")
            self.assertEqual(os.getenv("IA_DEV_QUERY_SQL_ASSISTED_ENABLED"), "0")
            self.assertEqual(os.getenv("IA_DEV_ATTENDANCE_EMPLOYEES_PILOT_ENABLED"), "0")

    def test_runtime_fallback_does_not_force_runtime_env_when_force_flag_is_disabled(self):
        with patch.dict(
            os.environ,
            {
                "IA_DEV_SERVICE_RUNTIME_BOOTSTRAP_ENABLED": "1",
                "IA_DEV_SERVICE_RUNTIME_BOOTSTRAP_FORCE": "0",
                "IA_DEV_ROUTING_MODE": "intent",
                "IA_DEV_QUERY_SQL_ASSISTED_ENABLED": "0",
                "IA_DEV_ATTENDANCE_EMPLOYEES_PILOT_ENABLED": "0",
            },
            clear=False,
        ):
            service = RuntimeFallbackService()

        applied = dict(service.runtime_bootstrap.get("applied") or {})
        skipped = dict(service.runtime_bootstrap.get("skipped") or {})
        self.assertNotIn("IA_DEV_ROUTING_MODE", applied)
        self.assertNotIn("IA_DEV_QUERY_SQL_ASSISTED_ENABLED", applied)
        self.assertNotIn("IA_DEV_ATTENDANCE_EMPLOYEES_PILOT_ENABLED", applied)
        self.assertEqual(skipped.get("IA_DEV_ROUTING_MODE"), "intent")
        self.assertEqual(skipped.get("IA_DEV_QUERY_SQL_ASSISTED_ENABLED"), "0")
        self.assertEqual(skipped.get("IA_DEV_ATTENDANCE_EMPLOYEES_PILOT_ENABLED"), "0")

    def test_response_assembler_infers_frontend_chart_and_presentation_meta(self):
        assembler = LegacyResponseAssembler()
        legacy_response = build_chat_response_snapshot()
        legacy_response["session_id"] = "sess-chart"
        legacy_response["reply"] = "Distribucion de empleados activos por area."
        legacy_response["data"] = {
            "kpis": {"total_empleados": 866, "total_grupos": 12},
            "labels": ["OPERACIONES", "GESTION HUMANA"],
            "series": [{"name": "cantidad", "data": [500, 120]}],
            "insights": ["Distribucion lista para grafica."],
            "table": {
                "columns": ["area", "cantidad"],
                "rows": [
                    {"area": "OPERACIONES", "cantidad": 500},
                    {"area": "GESTION HUMANA", "cantidad": 120},
                ],
                "rowcount": 2,
            },
        }

        run_context = RunContext(
            run_id="run_chart",
            trace_id="trace_chart",
            session_id="sess-chart",
            message="empleados por area",
            reset_memory=False,
            routing_mode="capability",
            started_at_ms=0,
            started_at_iso="2026-04-20T00:00:00+00:00",
            metadata={},
        )
        policy = PolicyDecision(
            action=PolicyAction.ALLOW,
            policy_id="policy.test.allow",
            reason="test allow",
            metadata={},
        )

        response = assembler.assemble(
            legacy_response=legacy_response,
            run_context=run_context,
            planned_capability={"capability_id": "empleados.count.active.v1"},
            route={"reason": "test"},
            policy_decision=policy,
            divergence={"diverged": False, "reason": "none"},
            memory_effects={},
        )

        data = dict(response.get("data") or {})
        chart = dict(data.get("chart") or {})
        meta = dict(data.get("meta") or {})
        presentation = dict(meta.get("presentation") or {})
        business_response = dict(data.get("business_response") or {})

        self.assertEqual(chart.get("chart_library"), "amcharts5")
        self.assertEqual(chart.get("type"), "bar")
        self.assertEqual(presentation.get("primary"), "chart")
        self.assertTrue(presentation.get("has_kpis"))
        self.assertEqual(str(business_response.get("dato") or ""), "Actualmente hay 866 empleados activos.")
        self.assertTrue(bool(str(business_response.get("hallazgo") or "").strip()))
        self.assertTrue(bool(str(business_response.get("interpretacion") or "").strip()))
        self.assertTrue(bool(str(business_response.get("recomendacion") or "").strip()))

    def test_observability_summary_endpoint_accepts_filters(self):
        payload = {"enabled": True, "window_seconds": 3600, "sample_size": 0}
        with patch.object(
            chat_view_module.observability_service,
            "summary_filtered",
            return_value=payload,
        ) as mock_summary:
            request = self.factory.get(
                "/ia-dev/observability/summary/?window_seconds=3600&limit=2000&domain_code=attendance&generator=openai&fallback_reason=openai_disabled_by_flag"
            )
            force_authenticate(request, user=self.user)
            response = IADevObservabilitySummaryView.as_view()(request)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data.get("status"), "ok")
        self.assertEqual(response.data.get("observability"), payload)
        mock_summary.assert_called_once_with(
            window_seconds=3600,
            limit=2000,
            domain_code="attendance",
            generator="openai",
            fallback_reason="openai_disabled_by_flag",
        )

    def test_observability_summary_endpoint_rejects_invalid_generator(self):
        request = self.factory.get("/ia-dev/observability/summary/?generator=invalid")
        force_authenticate(request, user=self.user)
        response = IADevObservabilitySummaryView.as_view()(request)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("generator", str(response.data.get("detail") or "").lower())

    def test_knowledge_approve_sync_flow_still_works(self):
        result = {"ok": True, "applied": True, "proposal": {"proposal_id": "KPRO-01"}}
        with patch.object(chat_view_module.async_job_service, "mode", "sync"):
            with patch.object(
                chat_view_module.knowledge_governance_service,
                "apply_proposal",
                return_value=result,
            ) as mock_apply:
                request = self.factory.post(
                    "/ia-dev/knowledge/proposals/approve/",
                    {
                        "proposal_id": "KPRO-01",
                        "idempotency_key": "idem-knowledge-01",
                    },
                    format="json",
                )
                force_authenticate(request, user=self.user)
                response = IADevKnowledgeApproveView.as_view()(request)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data.get("ok"))
        mock_apply.assert_called_once_with(
            proposal_id="KPRO-01",
            auth_key=None,
            idempotency_key="idem-knowledge-01",
        )

    def test_response_assembler_does_not_emit_capability_shadow_metadata(self):
        assembler = LegacyResponseAssembler()
        legacy_response = build_chat_response_snapshot()
        legacy_response["session_id"] = "sess-shadow"
        legacy_response["reply"] = "respuesta"
        legacy_response["orchestrator"] = {
            "intent": "attendance_query",
            "domain": "attendance",
            "selected_agent": "attendance_agent",
            "classifier_source": "query_intelligence_sql_assisted",
            "needs_database": True,
            "output_mode": "table",
            "used_tools": ["query_sql_assisted_executor"],
        }
        precomputed_response = dict(legacy_response)
        run_context = RunContext(
            run_id="run_test_shadow",
            trace_id="trace_test_shadow",
            session_id="sess-shadow",
            message="consulta de prueba",
            reset_memory=False,
            routing_mode="intent",
            started_at_ms=0,
            started_at_iso="2026-04-16T00:00:00+00:00",
            metadata={
                "query_intelligence": {
                    "mode": "active",
                    "precomputed_response": precomputed_response,
                }
            },
        )
        policy = PolicyDecision(
            action=PolicyAction.ALLOW,
            policy_id="policy.test.allow",
            reason="test allow",
            metadata={},
        )
        response = assembler.assemble(
            legacy_response=legacy_response,
            run_context=run_context,
            planned_capability={"capability_id": "attendance.unjustified.table.v1"},
            route={"reason": "test"},
            policy_decision=policy,
            divergence={"diverged": False, "reason": "none"},
            memory_effects={},
        )

        serialized = json.dumps(response, ensure_ascii=False)
        self.assertNotIn("capability_shadow", serialized)
        self.assertNotIn("proactive_loop", serialized)

    def test_response_assembler_injects_semantic_diagnostics_for_training(self):
        assembler = LegacyResponseAssembler()
        legacy_response = build_chat_response_snapshot()
        legacy_response["session_id"] = "sess-diagnostics"
        legacy_response["reply"] = "ok"

        run_context = RunContext(
            run_id="run_diag",
            trace_id="trace_diag",
            session_id="sess-diagnostics",
            message="Que areas concentran mas ausentismos en rolling 90 dias y que causas sugieres",
            reset_memory=False,
            routing_mode="intent",
            started_at_ms=0,
            started_at_iso="2026-04-16T00:00:00+00:00",
            metadata={
                "query_intelligence": {
                    "mode": "active",
                    "resolved_query": {
                        "intent": {
                            "domain_code": "ausentismo",
                            "operation": "aggregate",
                            "template_id": "aggregate_by_group_and_period",
                            "filters": {"habilitados": "si"},
                            "group_by": ["areas", "turno"],
                            "metrics": ["count", "promedio"],
                        },
                        "semantic_context": {
                            "tables": [
                                {
                                    "table_fqn": "bd_c3nc4s1s.gestionh_ausentismo",
                                    "table_name": "gestionh_ausentismo",
                                },
                                {
                                    "table_fqn": "cincosas_cincosas.cinco_base_de_personal",
                                    "table_name": "cinco_base_de_personal",
                                },
                            ],
                            "dictionary_meta": {
                                "schema": "ai_dictionary",
                                "dictionary_table": "ai_dictionary.dd_dominios",
                                "domain": {"code": "AUSENTISMOS", "name": "Ausentismos", "matched": True},
                            },
                            "resolved_semantic": {
                                "filters": [
                                    {
                                        "requested_term": "habilitados",
                                        "canonical_term": "estado_empleado",
                                        "table_name": "cinco_base_de_personal",
                                        "column_name": "estado",
                                        "supports_filter": True,
                                    }
                                ],
                                "group_by": [
                                    {
                                        "requested_term": "areas",
                                        "canonical_term": "area",
                                        "table_name": "cinco_base_de_personal",
                                        "column_name": "area",
                                        "supports_group_by": True,
                                    }
                                ],
                                "metrics": [],
                            },
                            "semantic_events": [
                                {
                                    "event_type": "semantic_status_resolved_from_dictionary",
                                    "matched_token": "habilitados",
                                    "status_value": "ACTIVO",
                                    "status_key": "estado",
                                }
                            ],
                        },
                        "normalized_filters": {"estado": "ACTIVO"},
                        "mapped_columns": {"estado": "estado"},
                        "warnings": [],
                    },
                    "execution_plan": {
                        "strategy": "capability",
                    },
                }
            },
        )
        policy = PolicyDecision(
            action=PolicyAction.ALLOW,
            policy_id="policy.test.allow",
            reason="test allow",
            metadata={},
        )

        response = assembler.assemble(
            legacy_response=legacy_response,
            run_context=run_context,
            planned_capability={"capability_id": "attendance.summary.by_area.v1"},
            route={"reason": "test"},
            policy_decision=policy,
            divergence={"diverged": False, "reason": "none"},
            memory_effects={},
        )

        qi_source = dict((response.get("data_sources") or {}).get("query_intelligence") or {})
        diagnostics = dict(qi_source.get("semantic_diagnostics") or {})
        self.assertTrue(bool(diagnostics))
        self.assertEqual(str(qi_source.get("mode") or ""), "active")
        self.assertTrue(list(diagnostics.get("synonyms_applied") or []))
        self.assertTrue(list(diagnostics.get("column_actions") or []))
        unresolved_terms = list(diagnostics.get("unresolved_terms") or [])
        self.assertTrue(any(str(item.get("requested_term") or "") == "turno" for item in unresolved_terms))
        self.assertTrue(any(str(item.get("requested_term") or "") == "promedio" for item in unresolved_terms))
        search_bases = dict(diagnostics.get("search_bases") or {})
        self.assertEqual(
            str((dict(search_bases.get("ai_dictionary") or {})).get("schema") or ""),
            "ai_dictionary",
        )

    def test_response_assembler_injects_cause_diagnostics_trace_event(self):
        assembler = LegacyResponseAssembler()
        legacy_response = build_chat_response_snapshot()
        legacy_response["session_id"] = "sess-cause-trace"
        legacy_response["reply"] = "ok"
        legacy_response["data"]["cause_generation_meta"] = {
            "generator": "heuristic",
            "confidence": 0.55,
            "validated": True,
            "fallback_reason": "openai_disabled_by_flag",
            "prompt_hash": "abc123def456",
            "top_group": "I&M",
            "top_pct": 73.2,
            "validation_errors": ["openai_disabled_by_flag"],
            "policy_decision": {
                "reason": "openai_disabled_by_flag",
                "selected_generator": "heuristic",
                "allowed": False,
            },
        }

        run_context = RunContext(
            run_id="run_cause_trace",
            trace_id="trace_cause_trace",
            session_id="sess-cause-trace",
            message="que areas concentran mas ausentismos y que causas sugieres",
            reset_memory=False,
            routing_mode="intent",
            started_at_ms=0,
            started_at_iso="2026-04-16T00:00:00+00:00",
            metadata={},
        )
        policy = PolicyDecision(
            action=PolicyAction.ALLOW,
            policy_id="policy.test.allow",
            reason="test allow",
            metadata={},
        )
        response = assembler.assemble(
            legacy_response=legacy_response,
            run_context=run_context,
            planned_capability={"capability_id": "attendance.summary.by_area.v1"},
            route={"reason": "test"},
            policy_decision=policy,
            divergence={"diverged": False, "reason": "none"},
            memory_effects={},
        )

        trace = list(response.get("trace") or [])
        cause_events = [item for item in trace if str((item or {}).get("phase") or "") == "cause_diagnostics"]
        self.assertTrue(bool(cause_events))
        detail = dict(cause_events[0].get("detail") or {})
        self.assertEqual(str(detail.get("generator") or ""), "heuristic")
        self.assertEqual(str(detail.get("fallback_reason") or ""), "openai_disabled_by_flag")
