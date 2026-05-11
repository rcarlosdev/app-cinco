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
        self.assertIn("positivos, cero y negativos", str(payload.get("hallazgo") or "").lower())

    def test_employee_inventory_balance_response_renames_material_as_material_claro(self):
        payload = build_inventory_business_response(
            resolved_query={
                "semantic_context": {
                    "inventory_semantic_inference": {
                        "filters": {"cedula": "5098747", "tipo": "material"},
                    },
                },
                "intent": {
                    "raw_query": "saldo material claro empleado 5098747",
                    "template_id": "inventory_material_stock_mobile",
                },
            },
            rows=[
                {
                    "codigo": "MAT-001",
                    "descripcion": "Conector",
                    "tipo": "material",
                    "cedula": "5098747",
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

        self.assertIn("material claro", str(payload.get("dato") or "").lower())
        self.assertIn("tipo", str(payload.get("hallazgo") or "").lower())

    def test_employee_inventory_balance_response_mentions_material_claro_y_ferretero_for_generic_material(self):
        payload = build_inventory_business_response(
            resolved_query={
                "semantic_context": {
                    "inventory_semantic_inference": {
                        "filters": {"cedula": "5098747", "tipo": ["material", "ferretero"]},
                    },
                },
                "intent": {
                    "raw_query": "saldo material empleado 5098747",
                    "template_id": "inventory_material_stock_mobile",
                },
            },
            rows=[
                {
                    "codigo": "MAT-001",
                    "descripcion": "Conector",
                    "tipo": "material",
                    "cedula": "5098747",
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

        self.assertIn("material claro y ferretero", str(payload.get("dato") or "").lower())

    def test_employee_kardex_response_uses_business_message_and_mentions_entrada_salida(self):
        payload = build_inventory_business_response(
            resolved_query={
                "semantic_context": {
                    "inventory_semantic_inference": {
                        "filters": {"cedula": "5098747", "codigo": "1025507"},
                    },
                },
                "intent": {
                    "raw_query": "kardex del codigo 1025507 para el empleado 5098747",
                    "template_id": "inventory_kardex_by_employee",
                    "filters": {"cedula": "5098747", "codigo": "1025507"},
                },
            },
            rows=[
                {
                    "fecha": "2026-05-09T00:00:00",
                    "tipo_movimiento": "entrega",
                    "codigo": "1025507",
                    "descripcion": "Cable",
                    "tipo": "material",
                    "cedula": "5098747",
                    "empleado": "Ana P",
                    "movil": "TIRAN224",
                    "estado_empleado": "ACTIVO",
                    "bodega": "operacion_hfc",
                    "entrada": 100,
                    "salida": 0,
                    "cantidad": 100,
                    "efecto": "suma",
                    "saldo_movimiento": 100,
                }
            ],
        )

        self.assertEqual(
            str(payload.get("dato") or ""),
            "Se consolido el kardex del codigo 1025507 para el empleado 5098747.",
        )
        self.assertIn("entrada, salida", str(payload.get("hallazgo") or "").lower())
        self.assertIn("cronologica ascendente", str(payload.get("riesgo") or "").lower())
