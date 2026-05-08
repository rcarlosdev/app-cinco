from __future__ import annotations

from django.test import SimpleTestCase

from apps.ia_dev.application.contracts.query_intelligence_contracts import (
    QueryExecutionPlan,
    ResolvedQuerySpec,
    StructuredQueryIntent,
)
from apps.ia_dev.application.reasoning.diagnostic_orchestrator import (
    DiagnosticOrchestrator,
)


class DiagnosticOrchestratorTests(SimpleTestCase):
    @staticmethod
    def _resolved_query() -> ResolvedQuerySpec:
        intent = StructuredQueryIntent(
            raw_query="informacion tiran462",
            domain_code="empleados",
            operation="detail",
            template_id="employee_detail_by_identifier",
            filters={"movil": "TIRAN462", "estado": "ACTIVO"},
            confidence=0.9,
            source="rules",
        )
        return ResolvedQuerySpec(
            intent=intent,
            normalized_filters={"movil": "TIRAN462", "estado": "ACTIVO"},
            normalized_period={},
            semantic_context={},
            mapped_columns={},
        )

    @staticmethod
    def _execution_plan(*, strategy: str = "capability") -> QueryExecutionPlan:
        return QueryExecutionPlan(
            strategy=strategy,
            reason="test",
            domain_code="empleados",
            capability_id="empleados.detail.v1",
            requires_context=(strategy == "ask_context"),
            constraints={"filters": {"movil": "TIRAN462", "estado": "ACTIVO"}},
        )

    def test_empty_result_with_identifier_creates_diagnostic_and_matches_memory(self):
        orchestrator = DiagnosticOrchestrator()
        diagnostics = orchestrator.analyze(
            message="informacion tiran462",
            resolved_query=self._resolved_query(),
            execution_plan=self._execution_plan(),
            response={"data": {"table": {"columns": [], "rows": [], "rowcount": 0}}},
            planned_capability={"capability_id": "empleados.detail.v1"},
            route={"reason": "capability"},
            execution_meta={"ok": True, "satisfied": False, "satisfaction_reason": "empty_rows"},
            memory_hints={
                "reasoning_patterns": [
                    {
                        "signature": "empty_result_with_identifier",
                        "domain_code": "empleados",
                        "capability_id": "empleados.detail.v1",
                        "pattern_strength": 0.91,
                    }
                ]
            },
            query_intelligence={},
        )

        self.assertTrue(bool(diagnostics.get("activated")))
        top = (diagnostics.get("items") or [])[0]
        self.assertEqual(top.get("signature"), "empty_result_with_identifier")
        self.assertTrue(bool(top.get("matched_memory_patterns")))

    def test_ask_context_with_identifier_creates_planner_gap_signature(self):
        orchestrator = DiagnosticOrchestrator()
        diagnostics = orchestrator.analyze(
            message="tiran462",
            resolved_query=self._resolved_query(),
            execution_plan=self._execution_plan(strategy="ask_context"),
            response={"data": {"table": {"columns": [], "rows": [], "rowcount": 0}}},
            planned_capability={"capability_id": "empleados.detail.v1"},
            route={"reason": "ask_context"},
            execution_meta={},
            memory_hints={},
            query_intelligence={},
        )

        signatures = {str(item.get("signature") or "") for item in diagnostics.get("items") or []}
        self.assertIn("ask_context_despite_identifier", signatures)

    def test_valid_sql_assisted_authority_does_not_emit_semantic_runtime_divergence(self):
        orchestrator = DiagnosticOrchestrator()
        diagnostics = orchestrator.analyze(
            message="personal con certificado de alturas proximo a vencer",
            resolved_query=self._resolved_query(),
            execution_plan=QueryExecutionPlan(
                strategy="sql_assisted",
                reason="employee_heights_certificate_summary_json",
                domain_code="empleados",
                capability_id="empleados.count.active.v1",
                sql_query="SELECT 1",
                constraints={"filters": {"estado": "ACTIVO"}},
                policy={"allowed": True},
            ),
            response={"orchestrator": {"classifier_source": "query_intelligence_sql_assisted"}},
            planned_capability={"capability_id": "empleados.count.active.v1"},
            route={
                "reason": "query_execution_planner_sql_assisted_authority",
                "execute_capability": False,
                "runtime_authority": "query_execution_planner",
            },
            execution_meta={"ok": True, "satisfied": True, "used_legacy": False},
            memory_hints={},
            query_intelligence={
                "canonical_resolution": {"comparison": {"differences_count": 1, "differences": ["capability_shadow"]}},
                "semantic_normalization": {"comparison": {"differences_count": 1, "differences": ["capability_shadow"]}},
            },
        )

        signatures = {str(item.get("signature") or "") for item in diagnostics.get("items") or []}
        self.assertNotIn("semantic_runtime_divergence", signatures)

