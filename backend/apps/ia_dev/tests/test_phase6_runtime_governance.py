from __future__ import annotations

import json
from io import StringIO
from unittest.mock import MagicMock, patch

from django.core.management import call_command
from django.test import SimpleTestCase

from apps.ia_dev.application.contracts.query_intelligence_contracts import (
    ResolvedQuerySpec,
    StructuredQueryIntent,
)
from apps.ia_dev.application.runtime.functional_validation_suite import (
    ValidationCase,
    _ausentismo_context,
    _period,
    run_functional_validation_suite,
)
from apps.ia_dev.services.runtime_governance_service import RuntimeGovernanceService
from apps.ia_dev.services.sql_store import IADevSqlStore


class Phase6ObservabilitySummaryTests(SimpleTestCase):
    def test_runtime_analytics_summary_aggregates_monitor_metrics_and_recommendations(self):
        store = IADevSqlStore()
        rows = [
            (
                "runtime_response_resolved",
                "ChatApplicationService",
                None,
                0,
                0,
                0.0,
                1710000000,
                json.dumps(
                    {
                        "domain_resolved": "ausentismo",
                        "response_flow": "sql_assisted",
                        "columns_detected": ["area", "dias_perdidos"],
                        "relations_used": [
                            "gestionh_ausentismo.cedula = cinco_base_de_personal.cedula"
                        ],
                        "satisfaction_review": {"satisfied": True},
                        "original_question": "Que areas tienen mas dias perdidos",
                    }
                ),
            ),
            (
                "runtime_response_resolved",
                "ChatApplicationService",
                None,
                0,
                0,
                0.0,
                1710000001,
                json.dumps(
                    {
                        "domain_resolved": "ausentismo",
                        "response_flow": "runtime_only_fallback",
                        "blocked_legacy_fallback": True,
                        "runtime_only_fallback_reason": "missing_dictionary_relation",
                        "sql_reason": "no_metric_column_declared",
                        "satisfaction_review": {"satisfied": False},
                        "original_question": "Que empleados tienen mas riesgo de ausentismo",
                    }
                ),
            ),
        ]
        with patch.object(store, "ensure_tables", return_value=None):
            with patch.object(store, "_fetchall", return_value=rows):
                summary = store.get_observability_summary(
                    window_seconds=3600,
                    limit=2000,
                    domain_code="ausentismo",
                )

        runtime = dict(summary.get("runtime_analytics") or {})
        self.assertEqual(int(runtime.get("total_analytics_queries") or 0), 2)
        self.assertEqual(int(runtime.get("sql_assisted_count") or 0), 1)
        self.assertEqual(int(runtime.get("runtime_only_fallback_count") or 0), 1)
        self.assertEqual(int(runtime.get("blocked_legacy_fallback_count") or 0), 1)
        self.assertEqual(int(runtime.get("missing_dictionary_relation_count") or 0), 1)
        self.assertEqual(int(runtime.get("no_metric_column_declared_count") or 0), 1)
        self.assertEqual(int(runtime.get("satisfaction_review_failed_count") or 0), 1)
        self.assertTrue(list(runtime.get("improvement_recommendations") or []))


class Phase6GovernanceServiceTests(SimpleTestCase):
    def test_dictionary_audit_reports_missing_assets_and_yaml_leaks(self):
        dictionary_service = MagicMock()
        dictionary_service.get_domain_context.side_effect = [
            {
                "fields": [
                    {"campo_logico": "area", "column_name": "area", "supports_metric": False},
                ],
                "relations": [],
                "synonyms": [{"termino": "area", "sinonimo": "areas"}],
                "rules": [],
            }
        ]
        context_loader = MagicMock()
        context_loader.load_from_files.return_value = {
            "ausentismo": {
                "columns": [
                    {
                        "nombre_columna_logico": "cargo",
                        "column_name": "cargo",
                    }
                ],
                "relationships": [
                    {
                        "nombre_relacion": "ausentismo_empleado",
                        "condicion": "gestionh_ausentismo.cedula = cinco_base_de_personal.cedula",
                    }
                ],
                "reglas_negocio": [{"codigo": "regla_prioridad_rrhh"}],
                "yaml_fields_ignored": ["columns", "relationships"],
                "yaml_fields_removed": ["columns", "relationships"],
            }
        }
        case = ValidationCase(
            case_id="audit_case",
            question="Que areas tienen mas dias perdidos",
            resolved_query=ResolvedQuerySpec(
                intent=StructuredQueryIntent(
                    raw_query="Que areas tienen mas dias perdidos",
                    domain_code="ausentismo",
                    operation="aggregate",
                    template_id="aggregate_by_group_and_period",
                    group_by=["area"],
                    metrics=["sum:dias_perdidos"],
                ),
                semantic_context=_ausentismo_context(),
                normalized_period=_period(),
            ),
            expected_domain="ausentismo",
            expected_runtime_flow="sql_assisted",
            expected_compiler="join_aware_pilot",
            expected_task_status="completed",
            expected_fallback=False,
            required_tables=("gestionh_ausentismo",),
            required_columns=("area", "dias_perdidos"),
            required_relations=("gestionh_ausentismo.cedula = cinco_base_de_personal.cedula",),
        )

        service = RuntimeGovernanceService(
            dictionary_service=dictionary_service,
            context_loader=context_loader,
            deduplication_service=MagicMock(analyze=MagicMock(return_value={"duplicates": []})),
        )
        with patch(
            "apps.ia_dev.services.runtime_governance_service.build_functional_validation_cases",
            return_value=[case],
        ):
            summary = service.audit_dictionary(domain="ausentismo", with_empleados=False)

        self.assertIn("dias_perdidos", list(summary.get("missing_columns") or []))
        self.assertIn("dias_perdidos", list(summary.get("missing_metrics") or []))
        self.assertIn(
            "gestionh_ausentismo.cedula = cinco_base_de_personal.cedula",
            list(summary.get("missing_relations") or []),
        )
        self.assertTrue(list(summary.get("missing_synonyms") or []))
        self.assertTrue(list(summary.get("yaml_structural_leaks") or []))
        self.assertTrue(list(summary.get("yaml_fields_ignored") or []))
        self.assertTrue(list(summary.get("yaml_fields_removed") or []))
        self.assertTrue(list(summary.get("missing_dictionary_metadata") or []))

    def test_dictionary_audit_ignores_self_duplicate_signals_and_cross_table_names(self):
        dictionary_service = MagicMock()
        dictionary_service.get_domain_context.side_effect = [
            {
                "fields": [
                    {
                        "campo_logico": "cedula",
                        "column_name": "cedula",
                        "table_name": "gestionh_ausentismo",
                        "supports_metric": False,
                    },
                    {
                        "campo_logico": "cedula_empleado",
                        "column_name": "cedula",
                        "table_name": "cinco_base_de_personal",
                        "supports_metric": False,
                    },
                    {
                        "campo_logico": "area",
                        "column_name": "area",
                        "table_name": "cinco_base_de_personal",
                        "supports_metric": False,
                    },
                ],
                "relations": [],
                "synonyms": [],
                "rules": [],
            }
        ]
        context_loader = MagicMock()
        context_loader.load_from_files.return_value = {
            "ausentismo": {
                "columns": [
                    {
                        "table_name": "cinco_base_de_personal",
                        "nombre_columna_logico": "area",
                        "column_name": "area",
                    }
                ],
                "relationships": [],
                "reglas_negocio": [],
            }
        }

        service = RuntimeGovernanceService(
            dictionary_service=dictionary_service,
            context_loader=context_loader,
            deduplication_service=MagicMock(analyze=MagicMock(return_value={"duplicates": []})),
        )
        summary = service.audit_dictionary(domain="ausentismo", with_empleados=False)

        self.assertEqual(list(summary.get("duplicated_definitions") or []), [])

    def test_monitor_command_prints_aggregated_runtime_metrics(self):
        fake_summary = {
            "domain": "ausentismo",
            "days": 7,
            "volumen_consultas": 12,
            "sql_assisted_count": 9,
            "sql_assisted_pct": 75.0,
            "handler_count": 2,
            "handler_pct": 16.67,
            "runtime_only_fallback_count": 1,
            "blocked_legacy_fallback_count": 1,
            "unsafe_sql_plan_count": 0,
            "no_metric_column_declared_count": 1,
            "no_allowed_dimension_count": 0,
            "missing_dictionary_relation_count": 1,
            "missing_dictionary_column_count": 0,
            "satisfaction_review_failed_count": 1,
            "top_preguntas_fallidas": [{"question": "Que empleados tienen mas riesgo", "count": 1}],
            "top_columnas_usadas": [{"column": "area", "count": 9}],
            "top_relaciones_usadas": [{"relation": "ausentismo_empleado", "count": 8}],
            "recomendaciones": ["Registrar joins faltantes en ai_dictionary.dd_relaciones."],
        }
        out = StringIO()
        with patch(
            "apps.ia_dev.management.commands.ia_runtime_monitor.RuntimeGovernanceService.build_monitor_summary",
            return_value=fake_summary,
        ):
            call_command(
                "ia_runtime_monitor",
                "--domain",
                "ausentismo",
                "--days",
                "7",
                stdout=out,
            )
        printed = out.getvalue()
        self.assertIn("volumen_consultas=12", printed)
        self.assertIn("sql_assisted=9 (75.0%)", printed)
        self.assertIn("Que empleados tienen mas riesgo", printed)
        self.assertIn("ai_dictionary.dd_relaciones", printed)


class Phase6RealDataDiagnoseTests(SimpleTestCase):
    def test_real_data_mode_reports_success_empty_and_critical_nulls(self):
        case = ValidationCase(
            case_id="real_data_case",
            question="Que areas tienen mas ausentismo",
            resolved_query=ResolvedQuerySpec(
                intent=StructuredQueryIntent(
                    raw_query="Que areas tienen mas ausentismo",
                    domain_code="ausentismo",
                    operation="aggregate",
                    template_id="aggregate_by_group_and_period",
                    group_by=["area"],
                    metrics=["count"],
                ),
                semantic_context=_ausentismo_context(),
                normalized_period=_period(),
            ),
            expected_domain="ausentismo",
            expected_runtime_flow="sql_assisted",
            expected_compiler="join_aware_pilot",
            expected_task_status="completed",
            expected_fallback=False,
            required_tables=("gestionh_ausentismo", "cinco_base_de_personal"),
            required_columns=("area",),
            required_relations=("gestionh_ausentismo.cedula = cinco_base_de_personal.cedula",),
        )

        def _fake_execute_sql_assisted(self, *, run_context, resolved_query, execution_plan, observability=None):
            response = self._build_sql_response(
                run_context=run_context,
                resolved_query=resolved_query,
                execution_plan=execution_plan,
                sql_query=str(execution_plan.sql_query or ""),
                rows=[{"area": None, "total_ausentismos": 4}],
                columns=["area", "total_ausentismos"],
                duration_ms=11,
                db_alias="mock_db",
            )
            return {"ok": True, "response": response}

        with patch(
            "apps.ia_dev.application.runtime.functional_validation_suite.build_functional_validation_cases",
            return_value=[case],
        ):
            with patch(
                "apps.ia_dev.application.semantic.query_execution_planner.QueryExecutionPlanner.execute_sql_assisted",
                new=_fake_execute_sql_assisted,
            ):
                summary = run_functional_validation_suite(
                    domain="ausentismo",
                    with_empleados=False,
                    real_data=True,
                )

        real_data = dict(summary.get("real_data_validation") or {})
        self.assertTrue(bool(summary.get("real_data")))
        self.assertEqual(int(real_data.get("queries_exitosas") or 0), 1)
        self.assertEqual(int(real_data.get("errores_sql") or 0), 0)
        self.assertEqual(
            str((list(real_data.get("columnas_nulas_criticas") or [{}])[0]).get("column") or ""),
            "area",
        )
