from __future__ import annotations

from django.test import SimpleTestCase

from apps.ia_dev.domains.inventario_logistica.response_assembler import (
    build_inventory_business_response,
)


class InventoryResponseAssemblerTests(SimpleTestCase):
    def test_dashboard_composition_generated_for_serialized_dimension_inventory(self):
        payload = build_inventory_business_response(
            resolved_query={
                "message": "saldo en moviles de Deco",
                "semantic_context": {
                    "business_query_semantic_plan": {
                        "inventory_family": "serializados",
                        "grouping_dimension": ["movil"],
                        "entity": {"type": "familia", "field": "familia", "identifier": "Deco"},
                        "scope": {"families": ["serializados"]},
                    },
                    "semantic_capability_registry": {
                        "template_id": "inventory_serial_stock_by_family_grouped_dimension",
                        "candidate_capability": "inventory_serial_stock_by_family_grouped_dimension",
                        "planner_route_hint": "inventory.serial.stock.dimension",
                        "response_profile": "inventory.serial.stock.dimension.detail",
                        "output_profile": {
                            "columns": [
                                "familia",
                                "codigo",
                                "descripcion",
                                "movil",
                                "cedula",
                                "nombre",
                                "apellido",
                                "saldo",
                                "seriales_total",
                                "en_movil",
                            ]
                        },
                    },
                    "resolved_semantic": {
                        "final_filters": {
                            "material_family": "Deco",
                            "grouping_dimension": "movil",
                        },
                    },
                },
                "intent": {
                    "template_id": "inventory_serial_stock_by_family_grouped_dimension",
                },
            },
            rows=[
                {
                    "familia": "DECO M5",
                    "codigo": "DEC-001",
                    "descripcion": "Nodo Deco",
                    "movil": "MOV-01",
                    "cedula": "1001",
                    "nombre": "Ana",
                    "apellido": "Perez",
                    "saldo": 4,
                    "seriales_total": 4,
                    "en_movil": 4,
                },
                {
                    "familia": "DECO M5",
                    "codigo": "DEC-001",
                    "descripcion": "Nodo Deco",
                    "movil": "MOV-02",
                    "cedula": "1002",
                    "nombre": "Luis",
                    "apellido": "Rojas",
                    "saldo": 3,
                    "seriales_total": 3,
                    "en_movil": 3,
                },
                {
                    "familia": "DECO X20",
                    "codigo": "DEC-002",
                    "descripcion": "Router Deco",
                    "movil": "MOV-01",
                    "cedula": "1001",
                    "nombre": "Ana",
                    "apellido": "Perez",
                    "saldo": 2,
                    "seriales_total": 2,
                    "en_movil": 2,
                },
            ],
            result_set={"rowcount": 3, "returned_records": 3, "total_records": 3},
        )

        composition = dict(payload.get("dashboard_composition") or {})
        self.assertEqual(
            str(((composition.get("evidence_contract") or {}).get("planner_id") or "")),
            "dashboard_composition.inventory.v1",
        )
        self.assertEqual(
            str(((composition.get("evidence_contract") or {}).get("supported_pattern") or "")),
            "inventory.serial.stock.dimension",
        )
        self.assertTrue(bool((composition.get("evidence_contract") or {}).get("validated")))
        primary_kpis = list(composition.get("primary_kpis") or [])
        saldo_total = next((item for item in primary_kpis if str(item.get("id") or "") == "saldo_total"), {})
        self.assertEqual(float(saldo_total.get("value") or 0), 9.0)
        ranked_breakdowns = list(composition.get("ranked_breakdowns") or [])
        top_codes = next((item for item in ranked_breakdowns if str(item.get("id") or "") == "top_codes_by_saldo"), {})
        top_code_rows = list(top_codes.get("rows") or [])
        self.assertEqual(str((top_code_rows[0] or {}).get("codigo") or ""), "DEC-001")
        self.assertEqual(float((top_code_rows[0] or {}).get("saldo_total") or 0), 7.0)
        top_dimensions = next((item for item in ranked_breakdowns if str(item.get("id") or "") == "top_dimensions_by_saldo"), {})
        top_dimension_rows = list(top_dimensions.get("rows") or [])
        self.assertEqual(str((top_dimension_rows[0] or {}).get("movil") or ""), "MOV-01")
        self.assertEqual(float((top_dimension_rows[0] or {}).get("saldo_total") or 0), 6.0)

    def test_dashboard_composition_supports_other_family_without_hardcode(self):
        payload = build_inventory_business_response(
            resolved_query={
                "message": "saldo en moviles de HGU",
                "semantic_context": {
                    "business_query_semantic_plan": {
                        "inventory_family": "serializados",
                        "grouping_dimension": ["movil"],
                    },
                    "semantic_capability_registry": {
                        "response_profile": "inventory.serial.stock.dimension.detail",
                    },
                    "resolved_semantic": {
                        "final_filters": {
                            "material_family": "HGU",
                            "grouping_dimension": "movil",
                        },
                    },
                },
            },
            rows=[
                {
                    "familia": "HGU GPON",
                    "codigo": "HGU-01",
                    "descripcion": "Equipo HGU",
                    "movil": "MOV-09",
                    "saldo": 5,
                    "seriales_total": 5,
                }
            ],
            result_set={"rowcount": 1},
        )

        composition = dict(payload.get("dashboard_composition") or {})
        executive_summary = dict(composition.get("executive_summary") or {})
        self.assertEqual(str(executive_summary.get("applied_family_filter") or ""), "HGU")
        self.assertTrue(bool(composition))

    def test_dashboard_composition_not_generated_without_saldo_column(self):
        payload = build_inventory_business_response(
            resolved_query={
                "semantic_context": {
                    "semantic_capability_registry": {
                        "response_profile": "inventory.serial.stock.dimension.detail",
                    },
                    "resolved_semantic": {
                        "final_filters": {
                            "material_family": "Deco",
                            "grouping_dimension": "movil",
                        },
                    },
                },
            },
            rows=[
                {
                    "familia": "DECO M5",
                    "codigo": "DEC-001",
                    "descripcion": "Nodo Deco",
                    "movil": "MOV-01",
                    "seriales_total": 4,
                }
            ],
            result_set={"rowcount": 1},
        )

        self.assertEqual(dict(payload.get("dashboard_composition") or {}), {})

    def test_dashboard_composition_not_generated_without_dimension_column(self):
        payload = build_inventory_business_response(
            resolved_query={
                "semantic_context": {
                    "semantic_capability_registry": {
                        "response_profile": "inventory.serial.stock.dimension.detail",
                    },
                    "resolved_semantic": {
                        "final_filters": {
                            "material_family": "Deco",
                            "grouping_dimension": "movil",
                        },
                    },
                },
            },
            rows=[
                {
                    "familia": "DECO M5",
                    "codigo": "DEC-001",
                    "descripcion": "Nodo Deco",
                    "saldo": 4,
                    "seriales_total": 4,
                }
            ],
            result_set={"rowcount": 1},
        )

        self.assertEqual(dict(payload.get("dashboard_composition") or {}), {})

    def test_dashboard_composition_not_generated_for_empty_evidence(self):
        payload = build_inventory_business_response(
            resolved_query={
                "semantic_context": {
                    "semantic_capability_registry": {
                        "response_profile": "inventory.serial.stock.dimension.detail",
                    },
                },
            },
            rows=[],
            result_set={"rowcount": 0},
        )

        self.assertEqual(dict(payload.get("dashboard_composition") or {}), {})

    def test_dashboard_composition_does_not_invent_missing_kpis(self):
        payload = build_inventory_business_response(
            resolved_query={
                "semantic_context": {
                    "semantic_capability_registry": {
                        "response_profile": "inventory.serial.stock.dimension.detail",
                    },
                    "resolved_semantic": {
                        "final_filters": {"grouping_dimension": "movil"},
                    },
                },
            },
            rows=[
                {
                    "familia": "DECO M5",
                    "codigo": "DEC-001",
                    "descripcion": "Nodo Deco",
                    "movil": "MOV-01",
                    "saldo": 4,
                }
            ],
            result_set={"rowcount": 1},
        )

        composition = dict(payload.get("dashboard_composition") or {})
        primary_kpis = list(composition.get("primary_kpis") or [])
        seriales_total = next((item for item in primary_kpis if str(item.get("id") or "") == "seriales_total"), {})
        self.assertEqual(float(seriales_total.get("value") or 0), 0.0)
        self.assertIn(
            "seriales_total",
            str((seriales_total.get("evidence") or {}).get("formula") or "").lower(),
        )

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

    def test_inventory_response_grouped_dimension_summarizes_business_request(self):
        payload = build_inventory_business_response(
            resolved_query={
                "semantic_context": {
                    "business_query_semantic_plan": {
                        "grouping_dimension": ["movil"],
                        "scope": {"families": ["material_claro", "ferretero"]},
                    },
                    "semantic_capability_registry": {
                        "template_id": "inventory_material_stock_grouped_dimension",
                        "response_profile": "inventory.stock.dimension.summary",
                        "output_profile": {"columns": ["movil", "codigo", "saldo"]},
                    },
                    "resolved_semantic": {
                        "final_filters": {
                            "descripcion": "CONECTOR RJ 45",
                            "grouping_dimension": "movil",
                        },
                    },
                },
            },
            rows=[
                {"movil": "TIRAN224", "codigo": "1025507", "saldo": 5},
                {"movil": "TIRAN314", "codigo": "1025507", "saldo": 3},
            ],
            result_set={"rowcount": 2},
        )

        self.assertIn("conector rj 45", str(payload.get("dato") or "").lower())
        self.assertIn("agrupado por móvil", str(payload.get("dato") or "").lower())
        self.assertIn("total general: 8", str(payload.get("dato") or "").lower())
        self.assertIn("2 fila", str(payload.get("hallazgo") or "").lower())

    def test_inventory_response_grouped_dimension_overrides_stale_mobile_detail_profile(self):
        payload = build_inventory_business_response(
            resolved_query={
                "semantic_context": {
                    "business_query_semantic_plan": {
                        "grouping_dimension": ["movil"],
                        "scope": {"families": ["material_claro"]},
                    },
                    "semantic_capability_registry": {
                        "template_id": "inventory_material_stock_mobile",
                        "response_profile": "inventory.stock.mobile.detail",
                        "output_profile": {"columns": ["movil", "codigo", "saldo"]},
                    },
                    "resolved_semantic": {
                        "final_filters": {
                            "codigo": "1025507",
                            "grouping_dimension": "movil",
                        },
                    },
                },
            },
            rows=[
                {"dimension": "TIRAN224", "movil": "TIRAN224", "codigo": "1025507", "saldo": 5},
                {"dimension": "TIRAN314", "movil": "TIRAN314", "codigo": "1025507", "saldo": 3},
            ],
            result_set={"rowcount": 2},
        )

        self.assertIn("1025507", str(payload.get("dato") or ""))
        self.assertIn("agrupado por", str(payload.get("dato") or "").lower())
        self.assertNotIn("empleado 1025507", str(payload.get("dato") or "").lower())

    def test_inventory_response_serial_family_grouped_dimension_explains_serial_scope(self):
        payload = build_inventory_business_response(
            resolved_query={
                "semantic_context": {
                    "business_query_semantic_plan": {
                        "inventory_family": "serializados",
                        "grouping_dimension": ["movil"],
                        "scope": {"families": ["serializados"]},
                    },
                    "semantic_capability_registry": {
                        "template_id": "inventory_serial_stock_by_family_grouped_dimension",
                        "response_profile": "inventory.serial.stock.dimension.detail",
                        "output_profile": {"columns": ["movil", "codigo", "familia", "seriales_total", "saldo"]},
                    },
                    "resolved_semantic": {
                        "final_filters": {
                            "material_family": "DECO",
                            "material_family_match_mode": "contains",
                            "grouping_dimension": "movil",
                        },
                    },
                },
            },
            rows=[
                {"cedula": "1001", "empleado": "Ana Perez", "movil": "TIRAN224", "codigo": "DEC-1", "familia": "DECO HD", "seriales_total": 2, "saldo": 2},
                {"cedula": "1002", "empleado": "Luis Rojas", "movil": "TIRAN314", "codigo": "DEC-1", "familia": "CPE DECO", "seriales_total": 1, "saldo": 1},
            ],
            result_set={"rowcount": 2},
        )

        self.assertIn("contienen deco", str(payload.get("dato") or "").lower())
        self.assertIn("empleado, movil y codigo", str(payload.get("dato") or "").lower())
        self.assertIn("estado_empleado", str(payload.get("hallazgo") or "").lower())
        self.assertIn("serial(es) en movil", str(payload.get("hallazgo") or "").lower())
        self.assertIn("conteo", str(payload.get("riesgo") or "").lower())

    def test_inventory_response_serial_family_empty_result_mentions_catalog(self):
        payload = build_inventory_business_response(
            resolved_query={
                "semantic_context": {
                    "business_query_semantic_plan": {
                        "inventory_family": "serializados",
                        "scope": {"families": ["serializados"]},
                    },
                    "semantic_capability_registry": {
                        "template_id": "inventory_serial_stock_by_family_grouped_dimension",
                        "response_profile": "inventory.serial.stock.dimension.detail",
                    },
                    "resolved_semantic": {
                        "final_filters": {
                            "material_family": "DECO",
                            "material_family_match_mode": "contains",
                            "grouping_dimension": "movil",
                        },
                    },
                },
            },
            rows=[],
            result_set={"rowcount": 0, "total_records": 0, "returned_records": 0},
        )

        self.assertIn("codigos del catalogo", str(payload.get("dato") or "").lower())
        self.assertIn("estado movil", str(payload.get("dato") or "").lower())
        self.assertIn("catalogo gobernado", str(payload.get("hallazgo") or "").lower())

    def test_inventory_response_hides_legacy_shadow_limitation_from_business_limitations(self):
        payload = build_inventory_business_response(
            resolved_query={
                "semantic_context": {
                    "semantic_capability_registry": {
                        "response_profile": "inventory.stock.dimension.summary",
                    },
                    "resolved_semantic": {
                        "limitations": ["legacy_semantic_binding_shadowed"],
                        "final_filters": {"descripcion": "CONECTOR RJ 45"},
                    },
                }
            },
            rows=[],
            result_set={"rowcount": 0},
        )

        self.assertNotIn("legacy_semantic_binding_shadowed", str(payload))

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
