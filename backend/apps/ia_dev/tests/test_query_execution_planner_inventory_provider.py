from __future__ import annotations

from django.test import SimpleTestCase
from unittest.mock import patch

from apps.ia_dev.application.contracts.query_intelligence_contracts import (
    ResolvedQuerySpec,
    StructuredQueryIntent,
)
from apps.ia_dev.application.context.run_context import RunContext
from apps.ia_dev.application.semantic.query_execution_planner import QueryExecutionPlanner


class QueryExecutionPlannerInventoryProviderTests(SimpleTestCase):
    def test_provider_serial_validation_prefers_governed_handler_when_attachment_exists(self):
        planner = QueryExecutionPlanner()
        run_context = RunContext.create(
            message="Valida los seriales adjuntos, dados por el proveedor",
            session_id="sess-provider-plan",
            reset_memory=False,
        )
        resolved_query = ResolvedQuerySpec(
            intent=StructuredQueryIntent(
                raw_query="Valida los seriales adjuntos, dados por el proveedor",
                domain_code="inventario_logistica",
                operation="validate_file",
                template_id="inventory_provider_serial_validation",
                filters={"source_kind": "provider_file", "serial_scope": "external_inventory_validation"},
                confidence=0.94,
                source="rules",
            ),
            semantic_context={
                "runtime_attachment_summary": {
                    "present": True,
                    "count": 1,
                    "names": ["seriales_proveedor.xlsx"],
                }
            },
            normalized_filters={
                "source_kind": "provider_file",
                "serial_scope": "external_inventory_validation",
            },
            normalized_period={},
            mapped_columns={},
            warnings=[],
        )

        with patch.object(
            QueryExecutionPlanner,
            "_resolve_capability_id",
            return_value="inventory_provider_serial_validation",
        ), patch.object(
            QueryExecutionPlanner,
            "_is_capability_rollout_enabled",
            return_value=True,
        ):
            plan = planner.plan(run_context=run_context, resolved_query=resolved_query)

        self.assertEqual(plan.strategy, "capability")
        self.assertEqual(plan.capability_id, "inventory_provider_serial_validation")
        self.assertEqual(str((plan.metadata or {}).get("template_id") or ""), "inventory_provider_serial_validation")
