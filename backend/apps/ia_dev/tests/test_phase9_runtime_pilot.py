from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from apps.ia_dev.application.context.run_context import RunContext
from apps.ia_dev.application.contracts.query_intelligence_contracts import (
    ResolvedQuerySpec,
    StructuredQueryIntent,
)
from apps.ia_dev.application.orchestration.chat_application_service import (
    ChatApplicationService,
)
from apps.ia_dev.application.semantic.query_execution_planner import QueryExecutionPlanner
from apps.ia_dev.services.runtime_governance_service import RuntimeGovernanceService


class _ObservabilityStub:
    def __init__(self):
        self.events: list[dict] = []

    def record_event(self, *, event_type: str, source: str, meta: dict):
        self.events.append({"event_type": event_type, "source": source, "meta": dict(meta or {})})


def _ausentismo_pilot_context() -> dict:
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
        "dictionary": {
            "relations": [
                {
                    "nombre_relacion": "ausentismo_empleado",
                    "join_sql": "gestionh_ausentismo.cedula = cinco_base_de_personal.cedula",
                }
            ]
        },
        "source_of_truth": {
            "pilot_sql_assisted_enabled": True,
            "used_dictionary": True,
            "used_yaml": True,
        },
        "supports_sql_assisted": True,
        "domain_status": "partial",
    }


class Phase9PilotTelemetryTests(SimpleTestCase):
    def test_pilot_active_registers_runtime_telemetry_for_ausentismo(self):
        observability = _ObservabilityStub()
        run_context = RunContext.create(
            message="Que areas tienen mas ausentismo",
            session_id="pilot-sess",
            reset_memory=False,
        )

        with patch.dict(
            "os.environ",
            {"IA_DEV_ATTENDANCE_EMPLOYEES_PILOT_ENABLED": "1"},
            clear=False,
        ):
            ChatApplicationService()._record_runtime_resolution_event(
                observability=observability,
                run_context=run_context,
                query_intelligence={
                    "execution_plan": {
                        "metadata": {
                            "compiler": "join_aware_pilot",
                            "physical_columns_used": ["fecha_edit", "dias_perdidos", "area", "cedula"],
                            "relations_used": [
                                "gestionh_ausentismo.cedula = cinco_base_de_personal.cedula"
                            ],
                            "metric_used": "dias_perdidos",
                            "aggregation_used": "sum",
                            "dimensions_used": ["area"],
                        },
                        "sql_query": "SELECT area, SUM(dias_perdidos) FROM demo LIMIT 10",
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
                            },
                        },
                    },
                },
                route={"reason": "query_intelligence_active_precomputed_response"},
                response={
                    "orchestrator": {"classifier_source": "query_intelligence_sql_assisted"},
                    "data": {"insights": ["Hallazgo 1", "Hallazgo 2"], "table": {"columns": ["area", "total"]}},
                    "data_sources": {
                        "query_intelligence": {
                            "query": "SELECT area, SUM(dias_perdidos) FROM demo LIMIT 10",
                        }
                    },
                },
                execution_meta={"analytics_router_decision": "join_aware_sql"},
                response_flow="sql_assisted",
                satisfaction_snapshot={"satisfied": True, "gate_score": 0.9},
            )

        self.assertEqual(len(observability.events), 1)
        meta = dict(observability.events[0].get("meta") or {})
        self.assertTrue(bool(meta.get("pilot_enabled")))
        self.assertEqual(str(meta.get("pilot_mode") or ""), "productive_pilot")
        self.assertEqual(str(meta.get("pilot_phase") or ""), "phase_9")
        self.assertEqual(str(meta.get("sql_used") or ""), "SELECT area, SUM(dias_perdidos) FROM demo LIMIT 10")
        self.assertEqual(list(meta.get("columns_used") or []), ["area", "cedula", "dias_perdidos", "fecha_edit"])
        self.assertEqual(str(meta.get("insight_quality") or ""), "good")


class Phase9PilotHealthTests(SimpleTestCase):
    def test_health_green_with_clean_metrics(self):
        observability = MagicMock()
        observability.list_events.return_value = [
            {
                "event_type": "runtime_response_resolved",
                "meta": {
                    "pilot_enabled": True,
                    "domain_resolved": "ausentismo",
                    "response_flow": "sql_assisted",
                    "original_question": "Que areas tienen mas ausentismo",
                    "columns_used": ["area", "dias_perdidos"],
                    "relations_used": ["gestionh_ausentismo.cedula = cinco_base_de_personal.cedula"],
                    "satisfaction_review": {"satisfied": True},
                    "insight_quality": "good",
                },
            }
        ]
        service = RuntimeGovernanceService(observability_service=observability)

        health = service.build_pilot_health(domain="ausentismo", days=1)

        self.assertEqual(str(health.get("status") or ""), "healthy")
        self.assertEqual(list(health.get("failing_checks") or []), [])

    def test_health_red_with_runtime_fallback_and_sql_errors(self):
        observability = MagicMock()
        observability.list_events.return_value = [
            {
                "event_type": "runtime_response_resolved",
                "meta": {
                    "pilot_enabled": True,
                    "domain_resolved": "ausentismo",
                    "response_flow": "runtime_only_fallback",
                    "blocked_legacy_fallback": True,
                    "runtime_only_fallback_reason": "missing_dictionary_relation",
                    "original_question": "Que empleados tienen mayor riesgo",
                    "satisfaction_review": {"satisfied": False},
                    "insight_quality": "poor",
                },
            },
            {
                "event_type": "runtime_response_resolved",
                "meta": {
                    "pilot_enabled": True,
                    "domain_resolved": "ausentismo",
                    "response_flow": "legacy_fallback",
                    "original_question": "Otra consulta",
                    "satisfaction_review": {"satisfied": True},
                    "insight_quality": "poor",
                },
            },
            {
                "event_type": "query_sql_assisted_error",
                "meta": {
                    "pilot_enabled": True,
                    "domain_code": "ausentismo",
                    "error": "sql_execution_error:timeout",
                },
            },
        ]
        service = RuntimeGovernanceService(observability_service=observability)

        health = service.build_pilot_health(domain="ausentismo", days=1)

        self.assertEqual(str(health.get("status") or ""), "unhealthy")
        self.assertIn("legacy_count=1", list(health.get("failing_checks") or []))
        self.assertIn("runtime_only_fallback_count=1", list(health.get("failing_checks") or []))
        self.assertIn("blocked_legacy_count=1", list(health.get("failing_checks") or []))
        self.assertIn("errores_sql=1", list(health.get("failing_checks") or []))
        self.assertIn("satisfaction_review_failed_count=1", list(health.get("failing_checks") or []))
        self.assertIn("insight_poor_count=2", list(health.get("failing_checks") or []))

    def test_health_green_with_since_fix_clean_window(self):
        observability = MagicMock()
        observability.list_events.return_value = [
            {
                "event_type": "runtime_response_resolved",
                "meta": {
                    "pilot_enabled": True,
                    "domain_resolved": "ausentismo",
                    "response_flow": "sql_assisted",
                    "original_question": "Que sedes presentan mas ausencias",
                    "columns_used": ["zona_nodo", "cedula", "fecha_edit"],
                    "relations_used": ["gestionh_ausentismo.cedula = cinco_base_de_personal.cedula"],
                    "satisfaction_review": {"satisfied": True},
                    "insight_quality": "good",
                },
            }
        ]
        sql_store = MagicMock()
        sql_store.get_latest_domain_fix_timestamp.return_value = 1710001000
        service = RuntimeGovernanceService(observability_service=observability, sql_store=sql_store)

        health = service.build_pilot_health(domain="ausentismo", days=1, since_fix=True)

        self.assertEqual(str(health.get("status") or ""), "healthy")
        observability.list_events.assert_called_once()
        self.assertEqual(int(observability.list_events.call_args.kwargs.get("created_after") or 0), 1710001000)

    def test_pilot_report_since_fix_filters_historical_events(self):
        observability = MagicMock()
        observability.list_events.return_value = [
            {
                "event_type": "runtime_response_resolved",
                "created_at": 1710002000,
                "meta": {
                    "pilot_enabled": True,
                    "domain_resolved": "ausentismo",
                    "response_flow": "sql_assisted",
                    "compiler_used": "join_aware_pilot",
                    "original_question": "Que sedes presentan mas ausencias",
                    "columns_used": ["zona_nodo", "cedula", "fecha_edit"],
                    "relations_used": ["gestionh_ausentismo.cedula = cinco_base_de_personal.cedula"],
                    "satisfaction_review": {"satisfied": True},
                    "insight_quality": "good",
                },
            }
        ]
        sql_store = MagicMock()
        sql_store.get_latest_domain_fix_timestamp.return_value = 1710001000
        service = RuntimeGovernanceService(observability_service=observability, sql_store=sql_store)

        report = service.build_pilot_report(domain="ausentismo", days=1, since_fix=True)

        self.assertEqual(int(report.get("created_after") or 0), 1710001000)
        self.assertTrue(bool(report.get("since_fix")))
        self.assertEqual(int(report.get("sql_assisted_count") or 0), 1)
        self.assertEqual(int(report.get("runtime_only_fallback_count") or 0), 0)
        observability.list_events.assert_called_once()
        self.assertEqual(int(observability.list_events.call_args.kwargs.get("created_after") or 0), 1710001000)

    def test_since_fix_uses_phase9_constant_when_store_has_no_fix_timestamp(self):
        observability = MagicMock()
        observability.list_events.return_value = []
        sql_store = MagicMock()
        sql_store.get_latest_domain_fix_timestamp.return_value = 0
        service = RuntimeGovernanceService(observability_service=observability, sql_store=sql_store)

        report = service.build_pilot_report(domain="ausentismo", days=1, since_fix=True)

        self.assertEqual(
            int(report.get("created_after") or 0),
            int(RuntimeGovernanceService.PHASE9_LAST_FIX_AT.timestamp()),
        )
        observability.list_events.assert_called_once()
        self.assertEqual(
            int(observability.list_events.call_args.kwargs.get("created_after") or 0),
            int(RuntimeGovernanceService.PHASE9_LAST_FIX_AT.timestamp()),
        )

    def test_created_after_accepts_human_datetime_string(self):
        observability = MagicMock()
        observability.list_events.return_value = []
        service = RuntimeGovernanceService(observability_service=observability)

        report = service.build_pilot_report(
            domain="ausentismo",
            days=1,
            created_after="2026-05-02 00:00:00",
        )

        self.assertEqual(int(report.get("created_after") or 0), 1777680000)
        observability.list_events.assert_called_once()
        self.assertEqual(int(observability.list_events.call_args.kwargs.get("created_after") or 0), 1777680000)


class Phase9PilotIsolationTests(SimpleTestCase):
    def test_productive_pilot_does_not_affect_other_domains(self):
        planner = QueryExecutionPlanner()
        resolved = ResolvedQuerySpec(
            intent=StructuredQueryIntent(
                raw_query="Resumen de transporte por ruta",
                domain_code="transporte",
                operation="aggregate",
                template_id="aggregate_by_group_and_period",
                group_by=["ruta"],
                metrics=["count"],
            ),
            semantic_context={"supports_sql_assisted": False, "domain_status": "partial"},
            normalized_period={"start_date": "2026-01-01", "end_date": "2026-01-31"},
        )

        with patch.dict(
            "os.environ",
            {
                "IA_DEV_ATTENDANCE_EMPLOYEES_PILOT_ENABLED": "1",
                "IA_DEV_DISABLE_LEGACY_ANALYTICS_FALLBACK": "0",
            },
            clear=False,
        ):
            blocked = planner._cleanup_blocks_legacy_analytics_fallback(
                resolved_query=resolved,
                pilot_analytics_candidate=True,
            )

        self.assertFalse(blocked)

    def test_legacy_remains_available_outside_pilot_scope(self):
        planner = QueryExecutionPlanner()
        resolved = ResolvedQuerySpec(
            intent=StructuredQueryIntent(
                raw_query="Que alertas deberia revisar talento humano",
                domain_code="general",
                operation="summary",
                template_id="summary_alerts",
            ),
            semantic_context={"tables": []},
        )

        with patch.dict(
            "os.environ",
            {
                "IA_DEV_ATTENDANCE_EMPLOYEES_PILOT_ENABLED": "1",
                "IA_DEV_DISABLE_LEGACY_ANALYTICS_FALLBACK": "0",
            },
            clear=False,
        ):
            plan = planner.plan(
                run_context=RunContext.create(message=resolved.intent.raw_query),
                resolved_query=resolved,
            )

        self.assertEqual(plan.strategy, "fallback")
        self.assertFalse(bool((plan.metadata or {}).get("blocked_legacy_fallback")))
