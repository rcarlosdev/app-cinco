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
        self.assertEqual(int(summary.get("questions_executed") or 0), 25)
        self.assertEqual(int(summary.get("passed") or 0), 25)
        self.assertEqual(int(summary.get("failed") or 0), 0)
        self.assertEqual(int(summary.get("suspected_hardcode_count") or 0), 0)
        self.assertGreaterEqual(int(summary.get("metadata_usage_count") or 0), 20)
        self.assertGreaterEqual(int(summary.get("evidence_coverage_count") or 0), 23)
        self.assertGreaterEqual(int(summary.get("fallback_usage_count") or 0), 0)
        self.assertGreaterEqual(float(summary.get("clarification_ratio") or 0.0), 0.04)
        self.assertGreaterEqual(float(summary.get("limitation_ratio") or 0.0), 0.04)
        coverage = dict(summary.get("capability_pack_coverage") or {})
        self.assertEqual(float(coverage.get("capability_pack_coverage") or 0.0), 1.0)
        self.assertGreater(int(coverage.get("templates_pack_driven_count") or 0), 0)
        self.assertEqual(int(coverage.get("templates_legacy_allowed_count") or 0), 0)
        self.assertEqual(list(coverage.get("templates_missing_selection_rules") or []), [])

    def test_runtime_eval_suite_marks_critical_materials_as_declared_and_without_fallback(self):
        summary = run_inventory_runtime_eval_suite()
        results = {str(item.get("case_id") or ""): item for item in list(summary.get("results") or [])}

        critical = dict(results.get("critical_materials_por_empleado") or {})
        self.assertEqual(str(critical.get("clasificacion") or ""), "correcto")
        self.assertFalse(bool(critical.get("fallback_detected")))
        self.assertFalse(bool((critical.get("semantic_trace") or {}).get("fallback_sombreado_usado")))
        self.assertFalse(bool((critical.get("semantic_trace") or {}).get("regla_legacy_detectada")))
        self.assertIn(
            "inventario.route.critical_materials_by_employee",
            list((critical.get("semantic_trace") or {}).get("regla_metadata_usada") or []),
        )
        self.assertFalse(bool(critical.get("suspected_hardcode")))

    def test_runtime_eval_suite_detects_clarification_limitation_and_empty_result(self):
        summary = run_inventory_runtime_eval_suite()
        results = {str(item.get("case_id") or ""): item for item in list(summary.get("results") or [])}

        clarification = dict(results.get("clarificacion_nombre_propio") or {})
        limitation = dict(results.get("limitacion_actas_sap") or {})
        empty_result = dict(results.get("resultado_vacio_stock_tecnico") or {})

        self.assertEqual(str(clarification.get("clasificacion") or ""), "aclaracion_valida")
        self.assertTrue(bool(clarification.get("legacy_allowed")))
        self.assertEqual(str(clarification.get("response_status") or ""), "clarification_required")
        self.assertEqual(str(clarification.get("source") or ""), "aclaracion_controlada")
        self.assertEqual(
            str(clarification.get("legacy_retained_reason") or ""),
            "requiere_aclaracion_estructural_por_portador_no_verificable",
        )
        self.assertEqual(str((clarification.get("evidence_summary") or {}).get("missing_evidence_reason") or ""), "missing_structural_context")
        self.assertEqual(str(limitation.get("clasificacion") or ""), "limitacion_valida")
        self.assertEqual(str(limitation.get("response_status") or ""), "limitation_declared")
        self.assertEqual(str(empty_result.get("clasificacion") or ""), "correcto")
        self.assertEqual(str(empty_result.get("response_status") or ""), "empty_result")

    def test_runtime_eval_suite_rejects_unexpected_legacy_fallbacks(self):
        summary = run_inventory_runtime_eval_suite()

        unexpected = [
            item
            for item in list(summary.get("results") or [])
            if bool(item.get("fallback_detected")) and not bool(item.get("legacy_allowed"))
        ]
        self.assertEqual(unexpected, [])

    def test_runtime_eval_suite_keeps_the_five_migrated_templates_out_of_legacy(self):
        summary = run_inventory_runtime_eval_suite()
        results = {str(item.get("case_id") or ""): item for item in list(summary.get("results") or [])}

        for case_id in (
            "movement_detail_operativo",
            "serial_stock_estado_declared",
            "risk_consumo_movil_declared",
            "consumption_top_declared",
            "reconciliation_operacion_hfc_declared",
        ):
            with self.subTest(case_id=case_id):
                result = dict(results.get(case_id) or {})
                semantic_trace = dict(result.get("semantic_trace") or {})
                capability_pack = dict(result.get("capability_pack") or {})
                self.assertFalse(bool(result.get("fallback_detected")))
                self.assertEqual(str(capability_pack.get("paquete_capacidad_usado") or ""), "inventario_logistica")
                self.assertFalse(bool(semantic_trace.get("legacy_mapping_used")))
                self.assertFalse(bool(semantic_trace.get("fallback_sombreado_usado")))
                self.assertFalse(bool(semantic_trace.get("regla_legacy_detectada")))

    def test_runtime_eval_suite_explicitly_validates_the_minimum_closure_matrix(self):
        summary = run_inventory_runtime_eval_suite()
        matrix = dict(summary.get("minimum_validation_matrix") or {})

        expected_pack_driven = (
            "inventario_generico_por_movil_cuadrilla",
            "inventario_por_cedula",
            "kardex_por_empleado",
            "kardex_codigo_mas_empleado",
            "seriales_equipos_por_familia",
            "consumo_vs_facturacion_operacion_hfc",
            "top_consumos",
            "movement_detail",
            "riesgo_consumo_movil_sin_validar",
            "serial_stock_por_dimension",
            "materiales_criticos",
        )
        for label in expected_pack_driven:
            with self.subTest(label=label):
                row = dict(matrix.get(label) or {})
                self.assertEqual(str(row.get("eval_result") or ""), "passed")
                self.assertEqual(str(row.get("source") or ""), "capability_pack")
                self.assertFalse(bool(row.get("legacy_mapping_used")))
                self.assertFalse(bool(row.get("fallback_used")))

        ambiguity = dict(matrix.get("consulta_ambigua_rescate_permitido") or {})
        self.assertEqual(str(ambiguity.get("eval_result") or ""), "passed")
        self.assertEqual(str(ambiguity.get("source") or ""), "aclaracion_controlada")
        self.assertEqual(
            str(ambiguity.get("legacy_retained_reason") or ""),
            "requiere_aclaracion_estructural_por_portador_no_verificable",
        )

    def test_runtime_eval_suite_preserves_same_intent_across_wording_variations(self):
        summary = run_inventory_runtime_eval_suite()
        results = [item for item in list(summary.get("results") or []) if str(item.get("grupo_semantico") or "") == "stock_movil_dual"]

        self.assertEqual(len(results), 4)
        self.assertEqual({str(item.get("template_id") or "") for item in results}, {"inventory_material_stock_mobile"})
        self.assertEqual({str(item.get("candidate_capability") or "") for item in results}, {"inventory_stock_balance_by_mobile"})
        self.assertEqual({str(item.get("planner_reason") or "") for item in results}, {"inventory_material_stock_mobile"})
        self.assertEqual({str(item.get("response_status") or "") for item in results}, {"success"})

    def test_runtime_eval_suite_preserves_declared_binding_across_critical_material_variations(self):
        summary = run_inventory_runtime_eval_suite()
        results = [
            item for item in list(summary.get("results") or []) if str(item.get("grupo_semantico") or "") == "critical_materials_declared"
        ]

        self.assertEqual(len(results), 6)
        self.assertEqual({str(item.get("template_id") or "") for item in results}, {"inventory_material_critical_by_employee"})
        self.assertEqual({str(item.get("candidate_capability") or "") for item in results}, {"inventory_stock_balance_by_mobile"})
        self.assertEqual({str(item.get("planner_reason") or "") for item in results}, {"inventory_material_critical_by_employee"})
        self.assertEqual({str(item.get("response_status") or "") for item in results}, {"success"})
        self.assertEqual({bool(item.get("fallback_detected")) for item in results}, {False})

    def test_runtime_eval_cases_are_versioned_and_use_non_canonical_wording(self):
        cases = build_inventory_runtime_eval_cases()
        preguntas = [str(item.pregunta or "") for item in cases]

        self.assertEqual(len(cases), 25)
        self.assertTrue(any("brigada" in pregunta.lower() for pregunta in preguntas))
        self.assertTrue(any("móvil" in pregunta.lower() or "movil" in pregunta.lower() for pregunta in preguntas))
        self.assertTrue(any("ferretería" in pregunta.lower() or "ferreteria" in pregunta.lower() for pregunta in preguntas))
        self.assertTrue(any("juan pérez" in pregunta.lower() or "juan perez" in pregunta.lower() for pregunta in preguntas))
        self.assertTrue(any("cobertura baja" in pregunta.lower() for pregunta in preguntas))
        self.assertTrue(any("debajo de umbral" in pregunta.lower() for pregunta in preguntas))
        self.assertTrue(any("facturacion hfc" in pregunta.lower() for pregunta in preguntas))
        self.assertTrue(any("consumo movil sin validar" in pregunta.lower() for pregunta in preguntas))
        self.assertTrue(any("saldo del empleado 5098747" in pregunta.lower() for pregunta in preguntas))
        self.assertTrue(any("saldo en moviles de deco" in pregunta.lower() for pregunta in preguntas))
