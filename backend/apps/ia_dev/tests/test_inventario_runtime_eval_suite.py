from __future__ import annotations

from django.test import SimpleTestCase

from apps.ia_dev.application.runtime.inventario_runtime_eval_suite import (
    DATASET_VERSION,
    build_inventory_runtime_eval_cases,
    run_inventory_runtime_eval_suite,
)


class InventoryRuntimeEvalSuiteTests(SimpleTestCase):
    def test_runtime_eval_suite_covers_real_inventory_variations_and_metrics(self):
        summary = run_inventory_runtime_eval_suite()

        self.assertEqual(str(summary.get("dataset_version") or ""), DATASET_VERSION)
        self.assertEqual(int(summary.get("questions_executed") or 0), 13)
        self.assertEqual(int(summary.get("passed") or 0), 12)
        self.assertEqual(int(summary.get("failed") or 0), 1)
        self.assertEqual(int(summary.get("suspected_hardcode_count") or 0), 0)
        self.assertGreaterEqual(int(summary.get("metadata_usage_count") or 0), 11)
        self.assertGreaterEqual(int(summary.get("evidence_coverage_count") or 0), 12)
        self.assertGreaterEqual(int(summary.get("fallback_usage_count") or 0), 1)
        self.assertGreaterEqual(float(summary.get("clarification_ratio") or 0.0), 0.07)
        self.assertGreaterEqual(float(summary.get("limitation_ratio") or 0.0), 0.07)

    def test_runtime_eval_suite_marks_shadow_fallback_and_keeps_metadata_trace(self):
        summary = run_inventory_runtime_eval_suite()
        results = {str(item.get("case_id") or ""): item for item in list(summary.get("results") or [])}

        shadow = dict(results.get("fallback_sombreado_controlado") or {})
        self.assertEqual(str(shadow.get("clasificacion") or ""), "capability_incorrecta")
        self.assertTrue(bool(shadow.get("fallback_detected")))
        self.assertTrue(bool((shadow.get("semantic_trace") or {}).get("fallback_sombreado_usado")))
        self.assertTrue(bool((shadow.get("semantic_trace") or {}).get("regla_legacy_detectada")))
        self.assertFalse(bool(shadow.get("suspected_hardcode")))

    def test_runtime_eval_suite_detects_clarification_limitation_and_empty_result(self):
        summary = run_inventory_runtime_eval_suite()
        results = {str(item.get("case_id") or ""): item for item in list(summary.get("results") or [])}

        clarification = dict(results.get("clarificacion_nombre_propio") or {})
        limitation = dict(results.get("limitacion_actas_sap") or {})
        empty_result = dict(results.get("resultado_vacio_stock_tecnico") or {})

        self.assertEqual(str(clarification.get("clasificacion") or ""), "aclaracion_valida")
        self.assertEqual(str(clarification.get("response_status") or ""), "clarification_required")
        self.assertEqual(str((clarification.get("evidence_summary") or {}).get("missing_evidence_reason") or ""), "missing_structural_context")
        self.assertEqual(str(limitation.get("clasificacion") or ""), "limitacion_valida")
        self.assertEqual(str(limitation.get("response_status") or ""), "limitation_declared")
        self.assertEqual(str(empty_result.get("clasificacion") or ""), "correcto")
        self.assertEqual(str(empty_result.get("response_status") or ""), "empty_result")

    def test_runtime_eval_suite_preserves_same_intent_across_wording_variations(self):
        summary = run_inventory_runtime_eval_suite()
        results = [item for item in list(summary.get("results") or []) if str(item.get("grupo_semantico") or "") == "stock_movil_dual"]

        self.assertEqual(len(results), 4)
        self.assertEqual({str(item.get("template_id") or "") for item in results}, {"inventory_material_stock_mobile"})
        self.assertEqual({str(item.get("candidate_capability") or "") for item in results}, {"inventory_stock_balance_by_mobile"})
        self.assertEqual({str(item.get("planner_reason") or "") for item in results}, {"inventory_material_stock_mobile"})
        self.assertEqual({str(item.get("response_status") or "") for item in results}, {"success"})

    def test_runtime_eval_cases_are_versioned_and_use_non_canonical_wording(self):
        cases = build_inventory_runtime_eval_cases()
        preguntas = [str(item.pregunta or "") for item in cases]

        self.assertEqual(len(cases), 13)
        self.assertTrue(any("brigada" in pregunta.lower() for pregunta in preguntas))
        self.assertTrue(any("móvil" in pregunta.lower() or "movil" in pregunta.lower() for pregunta in preguntas))
        self.assertTrue(any("ferretería" in pregunta.lower() or "ferreteria" in pregunta.lower() for pregunta in preguntas))
        self.assertTrue(any("juan pérez" in pregunta.lower() or "juan perez" in pregunta.lower() for pregunta in preguntas))
