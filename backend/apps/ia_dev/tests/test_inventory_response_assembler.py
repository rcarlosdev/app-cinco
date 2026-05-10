from __future__ import annotations

from django.test import SimpleTestCase

from apps.ia_dev.domains.inventario_logistica.response_assembler import (
    build_inventory_business_response,
)


class InventoryResponseAssemblerTests(SimpleTestCase):
    def test_employee_inventory_balance_response_preserves_codigo_detail(self):
        payload = build_inventory_business_response(
            resolved_query={
                "semantic_context": {
                    "inventory_semantic_inference": {
                        "filters": {"bodega": "operacion_hfc"},
                    },
                },
                "intent": {
                    "raw_query": "inventario por cuadrilla mostrando movil, cedula del empleado, nombre y saldo total",
                    "template_id": "inventory_material_stock_mobile",
                },
            },
            rows=[
                {
                    "codigo": "MAT-001",
                    "descripcion": "Conector",
                    "tipo": "FERRETERO",
                    "cedula": "123",
                    "empleado": "Ana P",
                    "movil": "TIRAN224",
                    "entregas": 10,
                    "devoluciones": 2,
                    "consumos": 5,
                    "cobros": 1,
                    "saldo": 2,
                }
            ],
        )

        self.assertIn("codigo", str(payload.get("hallazgo") or "").lower())
        self.assertIn("empleado y codigo", str(payload.get("dato") or "").lower())
        self.assertIn("saldo agregado", str(payload.get("riesgo") or "").lower())
