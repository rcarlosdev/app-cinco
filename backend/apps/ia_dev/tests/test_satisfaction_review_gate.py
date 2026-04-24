from __future__ import annotations

from django.test import SimpleTestCase

from apps.ia_dev.application.contracts.query_intelligence_contracts import (
    ResolvedQuerySpec,
    StructuredQueryIntent,
)
from apps.ia_dev.application.semantic.satisfaction_review_gate import (
    SatisfactionReviewGate,
)


class SatisfactionReviewGateTests(SimpleTestCase):
    def setUp(self):
        self.gate = SatisfactionReviewGate()

    @staticmethod
    def _resolved_intent(*, domain: str, operation: str) -> ResolvedQuerySpec:
        intent = StructuredQueryIntent(
            raw_query="cantidad empleados activos",
            domain_code=domain,
            operation=operation,
            template_id="count_entities_by_status",
            filters={"estado": "ACTIVO"},
            period={},
            group_by=[],
            metrics=["count"],
            confidence=0.9,
            source="rules",
            warnings=[],
        )
        return ResolvedQuerySpec(
            intent=intent,
            semantic_context={},
            normalized_filters={"estado": "ACTIVO"},
            normalized_period={},
            mapped_columns={},
            warnings=[],
        )

    def test_correct_case_is_approved(self):
        resolved = self._resolved_intent(domain="empleados", operation="count")
        result = self.gate.evaluate(
            raw_query="cantidad empleados activos",
            canonical_resolution={
                "domain_code": "empleados",
                "intent_code": "count",
                "capability_code": "empleados.count.active.v1",
                "confidence": 0.92,
            },
            runtime_intent=resolved.intent,
            resolved_query=resolved,
            execution_result={"ok": True, "used_legacy": False, "fallback_reason": ""},
            candidate_response={
                "reply": "El total de empleados activos es 120.",
                "data": {"kpis": {"total_activos": 120}, "table": {"rows": [], "rowcount": 0}},
            },
            strategy="capability",
            planned_capability={"capability_id": "empleados.count.active.v1"},
            loop_metadata={"iteration": 1},
            legacy_validation={"satisfied": True, "reason": "ok", "checks": {}},
            runtime_flags={"active": True, "shadow": False, "llm_reviewer_enabled": False},
        )
        payload = result.as_dict()
        self.assertTrue(bool(payload.get("approved")))
        self.assertTrue(bool(payload.get("answered_user_goal")))
        self.assertEqual(len(list(payload.get("issues") or [])), 0)

    def test_wrong_domain_issue_detected(self):
        resolved = self._resolved_intent(domain="attendance", operation="summary")
        result = self.gate.evaluate(
            raw_query="cantidad empleados activos",
            canonical_resolution={
                "domain_code": "empleados",
                "intent_code": "count",
                "capability_code": "",
                "confidence": 0.9,
            },
            runtime_intent=resolved.intent,
            resolved_query=resolved,
            execution_result={"ok": True},
            candidate_response={"reply": "ok", "data": {"table": {"rows": [{"total": 1}], "rowcount": 1}}},
            strategy="capability",
            planned_capability={"capability_id": "attendance.unjustified.summary.v1"},
            loop_metadata={},
            legacy_validation={"satisfied": True, "reason": "ok", "checks": {}},
            runtime_flags={},
        )
        issues = [str(item.get("code") or "") for item in list(result.issues or [])]
        self.assertIn("wrong_domain", issues)

    def test_wrong_capability_issue_detected(self):
        resolved = self._resolved_intent(domain="empleados", operation="count")
        result = self.gate.evaluate(
            raw_query="cantidad empleados activos",
            canonical_resolution={
                "domain_code": "empleados",
                "intent_code": "count",
                "capability_code": "empleados.count.active.v1",
                "confidence": 0.95,
            },
            runtime_intent=resolved.intent,
            resolved_query=resolved,
            execution_result={"ok": True},
            candidate_response={"reply": "ok", "data": {"table": {"rows": [{"total": 1}], "rowcount": 1}}},
            strategy="capability",
            planned_capability={"capability_id": "transport.departures.summary.v1"},
            loop_metadata={},
            legacy_validation={"satisfied": True, "reason": "ok", "checks": {}},
            runtime_flags={},
        )
        issues = [str(item.get("code") or "") for item in list(result.issues or [])]
        self.assertIn("wrong_capability", issues)

    def test_technical_leak_issue_detected(self):
        resolved = self._resolved_intent(domain="empleados", operation="count")
        result = self.gate.evaluate(
            raw_query="cantidad empleados activos",
            canonical_resolution={
                "domain_code": "empleados",
                "intent_code": "count",
                "capability_code": "empleados.count.active.v1",
                "confidence": 0.9,
            },
            runtime_intent=resolved.intent,
            resolved_query=resolved,
            execution_result={"ok": True},
            candidate_response={
                "reply": "SELECT cedula FROM cinco_base_de_personal WHERE estado='ACTIVO'",
                "data": {"table": {"rows": [{"total": 1}], "rowcount": 1}},
            },
            strategy="capability",
            planned_capability={"capability_id": "empleados.count.active.v1"},
            loop_metadata={},
            legacy_validation={"satisfied": True, "reason": "ok", "checks": {}},
            runtime_flags={},
        )
        self.assertTrue(bool(result.technical_leak_detected))
        issues = [str(item.get("code") or "") for item in list(result.issues or [])]
        self.assertIn("technical_leak", issues)

    def test_low_evidence_issue_detected(self):
        resolved = self._resolved_intent(domain="empleados", operation="count")
        result = self.gate.evaluate(
            raw_query="cantidad empleados activos",
            canonical_resolution={
                "domain_code": "empleados",
                "intent_code": "count",
                "capability_code": "empleados.count.active.v1",
                "confidence": 0.9,
            },
            runtime_intent=resolved.intent,
            resolved_query=resolved,
            execution_result={"ok": True},
            candidate_response={"reply": "ok", "data": {"kpis": {}, "table": {"rows": [], "rowcount": 0}}},
            strategy="capability",
            planned_capability={"capability_id": "empleados.count.active.v1"},
            loop_metadata={},
            legacy_validation={"satisfied": True, "reason": "ok", "checks": {}},
            runtime_flags={},
        )
        self.assertFalse(bool(result.evidence_sufficient))
        issues = [str(item.get("code") or "") for item in list(result.issues or [])]
        self.assertIn("low_evidence", issues)

    def test_ausentismo_alias_aligns_legacy_capability_domain(self):
        resolved = self._resolved_intent(domain="ausentismo", operation="aggregate")
        result = self.gate.evaluate(
            raw_query="ausentismos por jefe directo",
            canonical_resolution={
                "domain_code": "ausentismo",
                "intent_code": "aggregate",
                "capability_code": "attendance.summary.by_supervisor.v1",
                "confidence": 0.93,
            },
            runtime_intent=resolved.intent,
            resolved_query=resolved,
            execution_result={"ok": True, "used_legacy": False, "fallback_reason": ""},
            candidate_response={
                "reply": "Resumen de ausentismos por supervisor.",
                "data": {"table": {"rows": [{"supervisor": "A", "total": 3}], "rowcount": 1}},
            },
            strategy="capability",
            planned_capability={"capability_id": "attendance.summary.by_supervisor.v1"},
            loop_metadata={},
            legacy_validation={"satisfied": True, "reason": "ok", "checks": {}},
            runtime_flags={},
        )
        self.assertTrue(bool(result.domain_alignment))
        self.assertTrue(bool(result.intent_alignment))
        issues = [str(item.get("code") or "") for item in list(result.issues or [])]
        self.assertNotIn("wrong_domain", issues)
        self.assertNotIn("semantic_mismatch", issues)

