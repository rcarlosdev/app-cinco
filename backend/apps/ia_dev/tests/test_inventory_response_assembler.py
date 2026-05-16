from __future__ import annotations

from django.test import SimpleTestCase

from apps.ia_dev.domains.inventario_logistica.response_assembler import (
    build_inventory_business_response,
)


class InventoryResponseAssemblerTests(SimpleTestCase):
    def test_employee_inventory_balance_response_preserves_evidence_profile(self):
        payload = build_inventory_business_response(
            resolved_query={
                "semantic_context": {
                    "business_query_semantic_plan": {
                        "entity": {"type": "movil", "field": "movil", "identifier": "TIRAN224"},
                        "scope": {"families": ["material_claro", "ferretero"]},
                    },
                    "semantic_capability_registry": {
                        "template_id": "inventory_material_stock_mobile",
                        "candidate_capability": "inventory_stock_balance_by_mobile",
                        "planner_route_hint": "inventory.material_stock.mobile",
                        "response_profile": "inventory.stock.mobile.detail",
                        "output_profile": {
                            "columns": [
                                "codigo",
                                "descripcion",
                                "tipo",
                                "cedula",
                                "empleado",
                                "movil",
                                "saldo",
                            ]
                        },
                        "regla_metadata_usada": ["inventario.cap.stock_balance.mobile"],
                        "fuente_dd": ["ai_dictionary.dd_reglas"],
                    },
                    "resolved_semantic": {
                        "final_filters": {"movil": "TIRAN224", "tipo": ["material", "ferretero"]},
                        "consulted_sources": ["semantic_context"],
                    },
                    "inventory_semantic_inference": {
                        "filters": {"movil": "TIRAN224", "tipo": ["material", "ferretero"]},
                    },
                },
                "intent": {
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
                    "saldo": 2,
                }
            ],
            result_set={"rowcount": 1, "total_records": 1, "returned_records": 1},
        )

        metadata = dict(payload.get("metadata") or {})
        evidence = dict(payload.get("evidence_summary") or {})
        self.assertIn("material claro y ferretero", str(payload.get("dato") or "").lower())
        self.assertEqual(str(metadata.get("response_status") or ""), "success")
        self.assertEqual(str(metadata.get("response_profile_usado") or ""), "inventory.stock.mobile.detail")
        self.assertEqual(str(metadata.get("paquete_capacidad_usado") or ""), "")
        self.assertFalse(bool(metadata.get("fallback_narrativo_usado")))
        self.assertIn("result_set", list(evidence.get("evidence_sources_used") or []))

    def test_employee_kardex_response_uses_response_profile_and_execution_evidence(self):
        payload = build_inventory_business_response(
            resolved_query={
                "semantic_context": {
                    "business_query_semantic_plan": {
                        "entity": {"type": "empleado", "field": "cedula", "identifier": "5098747"},
                    },
                    "semantic_capability_registry": {
                        "template_id": "inventory_kardex_by_employee",
                        "candidate_capability": "inventory_kardex_by_employee",
                        "planner_route_hint": "inventory.kardex.employee",
                        "response_profile": "inventory.kardex.employee.detail",
                        "output_profile": {
                            "columns": [
                                "fecha",
                                "tipo_movimiento",
                                "codigo",
                                "cedula",
                                "entrada",
                                "salida",
                                "saldo_movimiento",
                            ]
                        },
                    },
                    "resolved_semantic": {
                        "final_filters": {"cedula": "5098747", "codigo": "1025507"},
                    },
                    "inventory_semantic_inference": {
                        "filters": {"cedula": "5098747", "codigo": "1025507"},
                    },
                },
                "intent": {
                    "template_id": "inventory_kardex_by_employee",
                    "filters": {"cedula": "5098747", "codigo": "1025507"},
                },
            },
            rows=[
                {
                    "fecha": "2026-05-09T00:00:00",
                    "tipo_movimiento": "entrega",
                    "codigo": "1025507",
                    "cedula": "5098747",
                    "entrada": 100,
                    "salida": 0,
                    "saldo_movimiento": 100,
                }
            ],
            result_set={"rowcount": 1},
        )

        self.assertEqual(
            str(payload.get("dato") or ""),
            "Se consolido el kardex del codigo 1025507 para el empleado 5098747.",
        )
        self.assertIn("tipo_movimiento", str(payload.get("hallazgo") or "").lower())
        self.assertIn("corrida cronologica", str(payload.get("riesgo") or "").lower())

    def test_inventory_response_declares_clarification_from_structural_missing_context(self):
        payload = build_inventory_business_response(
            resolved_query={
                "semantic_context": {
                    "inventory_governed_match": {
                        "pregunta_aclaracion": "Necesito la cedula, movil o cuadrilla para identificar a Juan Perez.",
                    },
                    "semantic_capability_registry": {
                        "response_profile": "inventory.stock.mobile.detail",
                    },
                },
                "intent": {
                    "warnings": ["Necesito la cedula, movil o cuadrilla para identificar a Juan Perez."],
                },
            },
            rows=[],
        )

        metadata = dict(payload.get("metadata") or {})
        self.assertEqual(str(metadata.get("response_status") or ""), "clarification_required")
        self.assertIn("juan perez", str(payload.get("dato") or "").lower())
        self.assertEqual(str(metadata.get("missing_evidence_reason") or ""), "missing_structural_context")

    def test_inventory_response_declares_limitation_for_sap_scope(self):
        payload = build_inventory_business_response(
            resolved_query={
                "semantic_context": {
                    "semantic_capability_registry": {
                        "response_profile": "inventory.document_generation.pending",
                    },
                    "resolved_semantic": {
                        "limitations": ["external_source_pending:sap"],
                    },
                }
            },
            rows=[],
            limitations=["external_source_pending:sap"],
        )

        metadata = dict(payload.get("metadata") or {})
        self.assertEqual(str(metadata.get("response_status") or ""), "limitation_declared")
        self.assertIn("sap", str(payload.get("hallazgo") or "").lower())
        self.assertIn("no esta habilitada", str(payload.get("hallazgo") or "").lower())

    def test_inventory_response_empty_result_explains_from_evidence_not_intuition(self):
        payload = build_inventory_business_response(
            resolved_query={
                "semantic_context": {
                    "semantic_capability_registry": {
                        "template_id": "inventory_material_stock_mobile",
                        "response_profile": "inventory.stock.mobile.detail",
                    },
                    "resolved_semantic": {
                        "final_filters": {"cedula": "5098747"},
                    },
                },
                "intent": {
                    "template_id": "inventory_material_stock_mobile",
                },
            },
            rows=[],
            result_set={"rowcount": 0, "total_records": 0, "returned_records": 0},
        )

        metadata = dict(payload.get("metadata") or {})
        self.assertEqual(str(metadata.get("response_status") or ""), "empty_result")
        self.assertIn("no devolvio filas", str(payload.get("dato") or "").lower())
        self.assertIn("result_set", str(metadata.get("missing_evidence_reason") or "").lower())
        self.assertNotIn("activo", str(payload.get("hallazgo") or "").lower())

    def test_inventory_response_dual_block_uses_extra_tables_as_evidence(self):
        payload = build_inventory_business_response(
            resolved_query={
                "semantic_context": {
                    "business_query_semantic_plan": {
                        "entity": {"type": "movil", "field": "movil", "identifier": "TIRAN224"},
                        "scope": {"families": ["material_claro", "ferretero"]},
                    },
                    "semantic_capability_registry": {
                        "template_id": "inventory_material_stock_mobile",
                        "response_profile": "inventory.stock.mobile.dual_block",
                        "output_profile": {"columns": ["codigo", "movil", "saldo"]},
                    },
                    "resolved_semantic": {
                        "final_filters": {"movil": "TIRAN224"},
                    },
                },
            },
            rows=[{"codigo": "MAT-1", "movil": "TIRAN224", "saldo": 1}],
            supplemental_tables=[
                {"name": "serializados_equipos", "rowcount": 3, "rows": [{"serial": "S1"}], "skipped": False}
            ],
            result_set={"rowcount": 1},
        )

        evidence = dict(payload.get("evidence_summary") or {})
        self.assertIn("serializados/equipos", str(payload.get("dato") or "").lower())
        self.assertIn("data.extra_tables", list(evidence.get("evidence_sources_used") or []))

    def test_inventory_response_preserves_capability_pack_trace(self):
        payload = build_inventory_business_response(
            resolved_query={
                "semantic_context": {
                    "business_query_semantic_plan": {
                        "entity": {"type": "movil", "field": "movil", "identifier": "TIRAN224"},
                        "scope": {"families": ["material_claro", "ferretero"]},
                    },
                    "semantic_capability_registry": {
                        "template_id": "inventory_material_stock_mobile",
                        "response_profile": "inventory.stock.mobile.detail",
                        "output_profile": {"columns": ["codigo", "saldo"]},
                        "paquete_capacidad_usado": "inventario_logistica",
                        "version_paquete": "1.0.0",
                        "capacidades_declaradas": ["inventory_stock_balance_by_mobile"],
                        "reglas_declaradas": ["inventario.route.stock_balance_holder"],
                        "perfiles_respuesta": ["inventory.stock.mobile.detail"],
                        "evaluaciones_asociadas": ["inventario_runtime_eval_v1"],
                    },
                    "resolved_semantic": {
                        "final_filters": {"movil": "TIRAN224"},
                    },
                },
            },
            rows=[{"codigo": "MAT-1", "saldo": 1}],
            result_set={"rowcount": 1},
        )

        metadata = dict(payload.get("metadata") or {})
        evidence = dict(payload.get("evidence_summary") or {})
        semantic_trace = dict(evidence.get("semantic_trace") or {})
        capability_pack = dict(evidence.get("capability_pack") or {})
        self.assertEqual(str(metadata.get("paquete_capacidad_usado") or ""), "inventario_logistica")
        self.assertEqual(str(metadata.get("version_paquete") or ""), "1.0.0")
        self.assertEqual(str(semantic_trace.get("paquete_capacidad_usado") or ""), "inventario_logistica")
        self.assertIn("inventory.stock.mobile.detail", list(capability_pack.get("perfiles_respuesta") or []))
