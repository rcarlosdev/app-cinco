from __future__ import annotations

from unittest.mock import Mock

from django.test import SimpleTestCase

from apps.ia_dev.domains.inventario_logistica.business_query_semantic_plan import (
    CONFIRMED_INVENTORY_MEMORY_RULES,
    INVENTORY_SEMANTIC_MATRIX,
    InventoryBusinessQueryPlanner,
    InventorySemanticMemoryService,
)


class InventoryBusinessQuerySemanticPlanTests(SimpleTestCase):
    def test_semantic_matrix_covers_core_families(self):
        families = {str(item.get("family") or "") for item in INVENTORY_SEMANTIC_MATRIX}

        self.assertIn("saldo_empleado", families)
        self.assertIn("saldo_movil", families)
        self.assertIn("kardex_empleado", families)
        self.assertIn("kardex_codigo", families)
        self.assertIn("serializados", families)

    def test_memory_service_persists_confirmed_rules(self):
        repository = Mock()
        service = InventorySemanticMemoryService(repository=repository)

        result = service.ensure_confirmed_rules()

        self.assertEqual(repository.set_business_memory.call_count, len(CONFIRMED_INVENTORY_MEMORY_RULES))
        self.assertEqual(repository.add_audit_event.call_count, len(CONFIRMED_INVENTORY_MEMORY_RULES))
        self.assertEqual(int(result.get("error_count") or 0), 0)
        self.assertGreaterEqual(len(list(result.get("saved_keys") or [])), 5)

    def test_planner_marks_generic_inventory_for_serialized_supplement(self):
        planner = InventoryBusinessQueryPlanner()
        planner.memory_service.list_memory_snapshot = lambda: []

        plan = planner.build_plan(
            message="inventario cuadrilla TIRAN224",
            inference={
                "intent": "stock_balance",
                "material_family": "materiales",
                "filters": {"movil": "TIRAN224", "stock_scope": "movil"},
                "group_by": [],
                "limitations": [],
                "business_concept": "stock_movil",
            },
            template_id="inventory_material_stock_mobile",
            semantic_context={"dictionary": {"fields": [{"campo_logico": "movil", "column_name": "movil"}]}},
        )

        payload = plan.as_dict()
        self.assertEqual(str(payload.get("candidate_capability") or ""), "inventory_stock_balance_by_mobile")
        self.assertTrue(bool((payload.get("scope") or {}).get("include_serialized")))
        self.assertEqual(str((payload.get("entity") or {}).get("field") or ""), "movil")
