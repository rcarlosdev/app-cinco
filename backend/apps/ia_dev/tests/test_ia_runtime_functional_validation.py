from __future__ import annotations

from unittest.mock import patch

from django.test import SimpleTestCase

from apps.ia_dev.application.context.run_context import RunContext
from apps.ia_dev.application.contracts.query_intelligence_contracts import (
    ResolvedQuerySpec,
    StructuredQueryIntent,
)
from apps.ia_dev.application.runtime.functional_validation_suite import (
    run_functional_validation_suite,
)
from apps.ia_dev.application.semantic.query_execution_planner import QueryExecutionPlanner


class RuntimeFunctionalValidationTests(SimpleTestCase):
    def test_suite_summary_covers_real_questions_and_surfaces_gaps(self):
        summary = run_functional_validation_suite(domain="ausentismo", with_empleados=True)

        self.assertEqual(int(summary.get("questions_executed") or 0), 10)
        self.assertEqual(int(summary.get("passed") or 0), 10)
        self.assertEqual(int(summary.get("failed") or 0), 0)
        self.assertGreaterEqual(int(summary.get("sql_assisted_count") or 0), 9)
        self.assertEqual(int(summary.get("handler_count") or 0), 1)
        self.assertEqual(int(summary.get("legacy_count") or 0), 0)
        self.assertEqual(list(summary.get("errors_or_blockers") or []), [])

    def test_suite_summary_stays_green_when_phase5_cleanup_flag_is_enabled(self):
        with patch.dict(
            "os.environ",
            {"IA_DEV_DISABLE_LEGACY_ANALYTICS_FALLBACK": "1"},
            clear=False,
        ):
            summary = run_functional_validation_suite(domain="ausentismo", with_empleados=True)

        self.assertEqual(int(summary.get("passed") or 0), 10)
        self.assertEqual(int(summary.get("failed") or 0), 0)
        self.assertEqual(int(summary.get("fallback_count") or 0), 0)
        self.assertEqual(int(summary.get("sql_assisted_count") or 0), 9)
        self.assertEqual(int(summary.get("handler_count") or 0), 1)
        self.assertEqual(int(summary.get("legacy_count") or 0), 0)

    def test_planner_uses_specific_fallback_reason_when_domain_missing(self):
        planner = QueryExecutionPlanner()
        resolved = ResolvedQuerySpec(
            intent=StructuredQueryIntent(
                raw_query="Que alertas deberia revisar talento humano",
                domain_code="",
                operation="summary",
                template_id="summary_alerts",
            ),
            semantic_context={"tables": []},
        )

        plan = planner.plan(
            run_context=RunContext.create(message="Que alertas deberia revisar talento humano"),
            resolved_query=resolved,
        )

        self.assertEqual(plan.strategy, "fallback")
        self.assertEqual(str(plan.reason or ""), "no_domain_resolved")

    def test_reason_normalizer_maps_missing_relation_to_specific_fallback(self):
        planner = QueryExecutionPlanner()
        self.assertEqual(
            planner._normalize_fallback_reason(
                domain_code="ausentismo",
                capability_id=None,
                capability_available=False,
                sql_policy_allowed=True,
                sql_reason="pilot_relation_missing",
            ),
            "no_declared_relation",
        )

    def test_reason_normalizer_maps_metric_and_dimension_failures(self):
        planner = QueryExecutionPlanner()
        self.assertEqual(
            planner._normalize_fallback_reason(
                domain_code="ausentismo",
                capability_id=None,
                capability_available=False,
                sql_policy_allowed=True,
                sql_reason="no_metric_column_declared",
            ),
            "no_metric_column_declared",
        )
        self.assertEqual(
            planner._normalize_fallback_reason(
                domain_code="ausentismo",
                capability_id=None,
                capability_available=False,
                sql_policy_allowed=True,
                sql_reason="no_allowed_dimension",
            ),
            "no_allowed_dimension",
        )
        self.assertEqual(
            planner._normalize_fallback_reason(
                domain_code="ausentismo",
                capability_id=None,
                capability_available=False,
                sql_policy_allowed=True,
                sql_reason="max_dimensions_exceeded",
            ),
            "max_dimensions_exceeded",
        )

    def test_reason_normalizer_maps_disabled_handler_to_specific_fallback(self):
        planner = QueryExecutionPlanner()
        self.assertEqual(
            planner._normalize_fallback_reason(
                domain_code="empleados",
                capability_id="empleados.detail.v1",
                capability_available=False,
                sql_policy_allowed=False,
                sql_reason="",
            ),
            "handler_not_available",
        )
