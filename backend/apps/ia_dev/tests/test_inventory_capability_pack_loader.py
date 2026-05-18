from __future__ import annotations

from django.test import SimpleTestCase

from apps.ia_dev.application.runtime.tool_registry_service import ToolRegistryService
from apps.ia_dev.domains.inventario_logistica.paquete_capacidades_loader import (
    capability_pack_trace_payload,
    load_inventory_capability_pack,
)


class InventoryCapabilityPackLoaderTests(SimpleTestCase):
    def test_load_inventory_capability_pack_validates_contract_and_registry_links(self):
        bundle = load_inventory_capability_pack(
            tool_registry_service=ToolRegistryService()
        )

        self.assertEqual(bundle.domain, "inventario_logistica")
        self.assertEqual(bundle.pack_name, "inventario_logistica")
        self.assertEqual(bundle.version, "1.0.0")
        self.assertTrue(bundle.validation.ok, msg=str(bundle.validation.errors))
        self.assertIn("inventory_material_stock_mobile", bundle.capabilities_by_template)
        self.assertIn("inventory.stock.mobile.detail", bundle.response_profiles_by_id)
        self.assertIn("inventario.limit.document_generation_pending", bundle.rules_by_id)
        self.assertIn("inventario_runtime_eval_v1", bundle.evaluations_by_id)

    def test_capability_pack_trace_payload_exposes_governed_trace_fields(self):
        bundle = load_inventory_capability_pack()

        trace = capability_pack_trace_payload(bundle)
        self.assertEqual(str(trace.get("paquete_capacidad_usado") or ""), "inventario_logistica")
        self.assertEqual(str(trace.get("version_paquete") or ""), "1.0.0")
        self.assertIn("inventory_stock_balance_by_mobile", list(trace.get("capacidades_declaradas") or []))
        self.assertIn("inventario.route.stock_balance_holder", list(trace.get("reglas_declaradas") or []))
        self.assertIn("inventory.stock.mobile.detail", list(trace.get("perfiles_respuesta") or []))
        self.assertIn("inventario_runtime_eval_v1", list(trace.get("evaluaciones_asociadas") or []))
