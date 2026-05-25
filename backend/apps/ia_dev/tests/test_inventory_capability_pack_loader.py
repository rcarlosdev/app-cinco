from __future__ import annotations

from copy import deepcopy

from django.test import SimpleTestCase

from apps.ia_dev.application.runtime.tool_registry_service import ToolRegistryService
from apps.ia_dev.domains.inventario_logistica.paquete_capacidades_loader import (
    build_inventory_capability_pack_coverage,
    capability_pack_trace_payload,
    load_inventory_capability_pack,
    validate_inventory_capability_pack,
)


class InventoryCapabilityPackLoaderTests(SimpleTestCase):
    def test_load_inventory_capability_pack_validates_contract_and_registry_links(self):
        bundle = load_inventory_capability_pack(
            tool_registry_service=ToolRegistryService()
        )

        self.assertEqual(bundle.domain, "inventario_logistica")
        self.assertEqual(bundle.pack_name, "inventario_logistica")
        self.assertEqual(bundle.version, "1.2.0")
        self.assertTrue(bundle.validation.ok, msg=str(bundle.validation.errors))
        self.assertIn("inventory_material_stock_mobile", bundle.semantic_bindings_by_template)
        self.assertIn("inventory_material_critical_by_employee", bundle.semantic_bindings_by_template)
        self.assertIn("inventory_movement_detail", bundle.semantic_bindings_by_template)
        self.assertIn("inventory_serial_stock_by_dimension", bundle.semantic_bindings_by_template)
        self.assertIn("inventory_risk_consumo_movil_sin_validar", bundle.semantic_bindings_by_template)
        self.assertIn("inventory_consumption_top", bundle.semantic_bindings_by_template)
        self.assertIn("inventory_consumption_billing_operacion_hfc", bundle.semantic_bindings_by_template)
        self.assertIn("inventory_material_stock_mobile", bundle.capabilities_by_template)
        self.assertIn("inventory_material_critical_by_employee", bundle.capabilities_by_template)
        self.assertIn("inventory_movement_detail", bundle.capabilities_by_template)
        self.assertIn("inventory_serial_stock_by_dimension", bundle.capabilities_by_template)
        self.assertIn("inventory_risk_consumo_movil_sin_validar", bundle.capabilities_by_template)
        self.assertIn("inventory_consumption_top", bundle.capabilities_by_template)
        self.assertIn("inventory_consumption_billing_operacion_hfc", bundle.capabilities_by_template)
        self.assertTrue(bool(bundle.semantic_bindings_by_template["inventory_material_stock_mobile"].get("selection_rules")))
        self.assertTrue(
            bool(bundle.semantic_bindings_by_template["inventory_material_critical_by_employee"].get("selection_rules"))
        )
        self.assertIn("inventory.stock.mobile.detail", bundle.response_profiles_by_id)
        self.assertIn("inventory.stock.critical.employee", bundle.response_profiles_by_id)
        self.assertIn("inventory.movement.detail", bundle.response_profiles_by_id)
        self.assertIn("inventory.serial.dimension.summary", bundle.response_profiles_by_id)
        self.assertIn("inventory.risk.serial.detail", bundle.response_profiles_by_id)
        self.assertIn("inventory.consumption.top.summary", bundle.response_profiles_by_id)
        self.assertIn("inventory.reconciliation.operacion_hfc", bundle.response_profiles_by_id)
        self.assertIn("inventario.limit.document_generation_pending", bundle.rules_by_id)
        self.assertIn("inventario.route.critical_materials_by_employee", bundle.rules_by_id)
        self.assertIn("inventario.route.movement_detail", bundle.rules_by_id)
        self.assertIn("inventario.route.serial_stock_dimension", bundle.rules_by_id)
        self.assertIn("inventario.route.risk_consumo_movil_sin_validar", bundle.rules_by_id)
        self.assertIn("inventario.route.consumption_top", bundle.rules_by_id)
        self.assertIn("inventario.route.reconciliation_operacion_hfc", bundle.rules_by_id)
        self.assertIn("inventario_runtime_eval_v1", bundle.evaluations_by_id)

    def test_capability_pack_trace_payload_exposes_governed_trace_fields(self):
        bundle = load_inventory_capability_pack()

        trace = capability_pack_trace_payload(bundle)
        self.assertEqual(str(trace.get("paquete_capacidad_usado") or ""), "inventario_logistica")
        self.assertEqual(str(trace.get("version_paquete") or ""), "1.2.0")
        self.assertIn("inventory_stock_balance_by_mobile", list(trace.get("capacidades_declaradas") or []))
        self.assertIn("inventario.route.critical_materials_by_employee", list(trace.get("reglas_declaradas") or []))
        self.assertIn("inventario.route.stock_balance_holder", list(trace.get("reglas_declaradas") or []))
        self.assertIn("inventory.stock.mobile.detail", list(trace.get("perfiles_respuesta") or []))
        self.assertIn("inventory.stock.critical.employee", list(trace.get("perfiles_respuesta") or []))
        self.assertIn("inventario_runtime_eval_v1", list(trace.get("evaluaciones_asociadas") or []))
        self.assertEqual(float(trace.get("capability_pack_coverage") or 0.0), 1.0)
        self.assertGreater(int(trace.get("templates_pack_driven_count") or 0), 0)
        self.assertEqual(int(trace.get("templates_legacy_allowed_count") or 0), 0)
        self.assertEqual(list(trace.get("templates_missing_selection_rules") or []), [])

    def test_capability_pack_coverage_reports_pending_legacy_templates_used_by_tests_and_evals(self):
        bundle = load_inventory_capability_pack()

        coverage = build_inventory_capability_pack_coverage(bundle)

        self.assertIn("inventory_material_stock_mobile", coverage.templates_declared)
        self.assertIn("inventory_material_stock_mobile", coverage.templates_with_selection_rules)
        self.assertIn("inventory_material_stock_mobile", coverage.templates_used_by_tests)
        self.assertIn("inventory_material_stock_mobile", coverage.templates_used_by_evals)
        self.assertIn("inventory_movement_detail", coverage.templates_with_selection_rules)
        self.assertIn("inventory_serial_stock_by_dimension", coverage.templates_with_selection_rules)
        self.assertIn("inventory_risk_consumo_movil_sin_validar", coverage.templates_with_selection_rules)
        self.assertIn("inventory_consumption_top", coverage.templates_with_selection_rules)
        self.assertIn("inventory_consumption_billing_operacion_hfc", coverage.templates_with_selection_rules)
        self.assertEqual(coverage.templates_used_by_legacy, [])
        self.assertEqual(coverage.templates_pending_migration, [])
        self.assertEqual(coverage.templates_legacy_allowed, [])
        self.assertEqual(coverage.capability_pack_coverage, 1.0)
        self.assertGreater(coverage.templates_pack_driven_count, 0)
        self.assertEqual(coverage.templates_legacy_allowed_count, 0)
        self.assertFalse(coverage.errors, msg=str(coverage.errors))

    def test_validation_fails_when_binding_points_to_capability_or_profile_missing_or_without_route_hint(self):
        bundle = load_inventory_capability_pack()
        package_payload = deepcopy(bundle.package_payload)
        capabilities = deepcopy(list(bundle.capabilities_by_template.values()))
        semantic_bindings = deepcopy(bundle.semantic_bindings)
        target_binding = semantic_bindings[0]
        target_binding["candidate_capability"] = "inventory_capability_inexistente"
        target_binding["response_profile"] = "inventory.response_profile.inexistente"
        target_binding["planner_route_hint"] = ""

        validation = validate_inventory_capability_pack(
            package_payload=package_payload,
            rules_by_id=deepcopy(bundle.rules_by_id),
            response_profiles_by_id=deepcopy(bundle.response_profiles_by_id),
            approval_policies_by_id=deepcopy(bundle.approval_policies_by_id),
            evaluations_by_id=deepcopy(bundle.evaluations_by_id),
            capabilities=capabilities,
            semantic_bindings=semantic_bindings,
            tool_registry_service=ToolRegistryService(),
        )

        self.assertFalse(validation.ok)
        self.assertIn(
            "semantic_binding inventory_material_stock_mobile: candidate_capability no declarado -> inventory_capability_inexistente",
            validation.errors,
        )
        self.assertIn(
            "semantic_binding inventory_material_stock_mobile: response_profile no declarado -> inventory.response_profile.inexistente",
            validation.errors,
        )
        self.assertIn(
            "semantic_binding inventory_material_stock_mobile: planner_route_hint obligatorio",
            validation.errors,
        )
