from __future__ import annotations

from django.test import SimpleTestCase

from apps.ia_dev.application.contracts.query_intelligence_contracts import StructuredQueryIntent
from apps.ia_dev.application.semantic.semantic_capability_registry import (
    SemanticBindingRequest,
    SemanticCapabilityRegistry,
)
from apps.ia_dev.domains.inventario_logistica.paquete_capacidades_loader import (
    load_inventory_capability_pack,
)
from apps.ia_dev.domains.empleados.paquete_capacidades_loader import (
    load_employee_capability_pack,
)
from apps.ia_dev.domains.inventario_logistica.matcher_semantico_gobernado_inventario import (
    MatcherSemanticoGobernadoInventario,
)
from apps.ia_dev.domains.inventario_logistica.semantic_inventory_resolver import (
    InventorySemanticResolver,
)


class SemanticCapabilityRegistryTests(SimpleTestCase):
    def setUp(self):
        self.registry = SemanticCapabilityRegistry()
        self.matcher = MatcherSemanticoGobernadoInventario()

    def test_inventory_movil_binding_resolves_capability_tool_route_and_response_profile(self):
        decision = self.registry.resolve(
            SemanticBindingRequest(
                domain="inventario_logistica",
                message="que tiene asignado la cuadrilla TIRAN224",
                intent="stock_balance",
                normalized_filters={"movil": "TIRAN224", "stock_scope": "movil"},
                source_hints={
                    "governed_match": {
                        "coincidencia_gobernada": True,
                        "template_id": "inventory_material_stock_mobile",
                        "capacidad_candidata": "inventory_stock_balance_by_mobile",
                        "incluye_serializados": True,
                    }
                },
            )
        )

        payload = decision.as_dict()
        self.assertEqual(str(payload.get("template_id") or ""), "inventory_material_stock_mobile")
        self.assertEqual(str(payload.get("candidate_capability") or ""), "inventory_stock_balance_by_mobile")
        self.assertEqual(str(payload.get("planner_route_hint") or ""), "inventory.material_stock.mobile")
        self.assertEqual(str(payload.get("response_profile") or ""), "inventory.stock.mobile.dual_block")
        self.assertEqual(str(payload.get("tool_id") or ""), "inventory_stock_balance_by_mobile")
        self.assertEqual(str(payload.get("source") or ""), "capability_pack")
        self.assertFalse(bool(payload.get("fallback_used")))
        self.assertIn("inventario.route.stock_balance_holder", list(payload.get("regla_metadata_usada") or []))
        self.assertFalse(bool(payload.get("fallback_sombreado_usado")))
        self.assertTrue(bool(payload.get("regla_migrada")))
        self.assertEqual(str(payload.get("paquete_capacidad_usado") or ""), "inventario_logistica")
        self.assertEqual(str(payload.get("version_paquete") or ""), "1.2.0")
        self.assertIn("inventory.stock.mobile.detail", list(payload.get("perfiles_respuesta") or []))
        self.assertIn("inventario_runtime_eval_v1", list(payload.get("evaluaciones_asociadas") or []))
        self.assertEqual(float(payload.get("capability_pack_coverage") or 0.0), 1.0)
        self.assertGreater(int(payload.get("templates_pack_driven_count") or 0), 0)
        self.assertEqual(int(payload.get("templates_legacy_allowed_count") or 0), 0)
        self.assertEqual(list(payload.get("templates_missing_selection_rules") or []), [])

    def test_inventory_kardex_employee_binding_prefers_employee_route(self):
        decision = self.registry.resolve(
            SemanticBindingRequest(
                domain="inventario_logistica",
                message="movimientos del tecnico 5098747",
                intent="movement_history",
                normalized_filters={"cedula": "5098747"},
                source_hints={"inventory_inference": {"business_concept": "kardex_operativo_por_empleado"}},
            )
        )

        payload = decision.as_dict()
        self.assertEqual(str(payload.get("template_id") or ""), "inventory_kardex_by_employee")
        self.assertEqual(str(payload.get("candidate_capability") or ""), "inventory_kardex_by_employee")
        self.assertEqual(str(payload.get("response_profile") or ""), "inventory.kardex.employee.detail")
        self.assertIn("inventario.route.kardex_employee", list(payload.get("matched_rules") or []))
        self.assertIn("inventario.route.kardex_employee", list(payload.get("regla_metadata_usada") or []))

    def test_inventory_grouped_material_binding_resolves_dimension_summary_route(self):
        decision = self.registry.resolve(
            SemanticBindingRequest(
                domain="inventario_logistica",
                message="saldo en moviles de CONECTOR RJ 45",
                intent="stock_balance",
                normalized_filters={
                    "descripcion": "CONECTOR RJ 45",
                    "grouping_dimension": "movil",
                },
                group_by=["movil"],
                source_hints={
                    "governed_match": {
                        "coincidencia_gobernada": True,
                        "template_id": "inventory_material_stock_grouped_dimension",
                        "capacidad_candidata": "inventory_stock_balance_by_material_dimension",
                    }
                },
            )
        )

        payload = decision.as_dict()
        self.assertEqual(str(payload.get("template_id") or ""), "inventory_material_stock_grouped_dimension")
        self.assertEqual(str(payload.get("candidate_capability") or ""), "inventory_stock_balance_by_material_dimension")
        self.assertEqual(str(payload.get("planner_route_hint") or ""), "inventory.material_stock.dimension")
        self.assertEqual(str(payload.get("response_profile") or ""), "inventory.stock.dimension.summary")
        self.assertEqual(str(payload.get("tool_id") or ""), "query_execution_planner.sql_assisted")
        self.assertIn(
            "inventario.route.stock_balance_material_grouped_dimension",
            list(payload.get("regla_metadata_usada") or []),
        )

    def test_inventory_grouped_serial_family_binding_resolves_serial_dimension_route(self):
        decision = self.registry.resolve(
            SemanticBindingRequest(
                domain="inventario_logistica",
                message="saldo en moviles de Deco",
                intent="stock_balance",
                normalized_filters={
                    "material_family": "DECO",
                    "material_family_match_mode": "contains",
                    "grouping_dimension": "movil",
                },
                group_by=["movil"],
                source_hints={
                    "inventory_inference": {"material_family": "serializados"},
                    "governed_match": {
                        "coincidencia_gobernada": True,
                        "template_id": "inventory_serial_stock_by_family_grouped_dimension",
                        "capacidad_candidata": "inventory_serial_stock_by_family_grouped_dimension",
                    },
                },
            )
        )

        payload = decision.as_dict()
        self.assertEqual(str(payload.get("template_id") or ""), "inventory_serial_stock_by_family_grouped_dimension")
        self.assertEqual(str(payload.get("candidate_capability") or ""), "inventory_serial_stock_by_family_grouped_dimension")
        self.assertEqual(str(payload.get("planner_route_hint") or ""), "inventory.serial_stock.family_dimension")
        self.assertEqual(str(payload.get("response_profile") or ""), "inventory.serial.stock.dimension.detail")
        self.assertEqual(str(payload.get("tool_id") or ""), "query_execution_planner.sql_assisted")
        self.assertIn(
            "inventario.route.serial_stock_family_grouped_dimension",
            list(payload.get("regla_metadata_usada") or []),
        )

    def test_inventory_grouped_serial_family_binding_ignores_stale_material_dimension_template(self):
        decision = self.registry.resolve(
            SemanticBindingRequest(
                domain="inventario_logistica",
                message="saldo en moviles de Deco",
                intent="stock_balance",
                normalized_filters={
                    "material_family": "DECO",
                    "grouping_dimension": "movil",
                },
                group_by=["movil"],
                source_hints={
                    "template_id": "inventory_material_stock_grouped_dimension",
                    "inventory_inference": {"material_family": "serializados"},
                    "governed_match": {
                        "coincidencia_gobernada": True,
                        "template_id": "inventory_serial_stock_by_family_grouped_dimension",
                        "capacidad_candidata": "inventory_serial_stock_by_family_grouped_dimension",
                    },
                },
            )
        )

        payload = decision.as_dict()
        self.assertEqual(str(payload.get("template_id") or ""), "inventory_serial_stock_by_family_grouped_dimension")
        self.assertEqual(str(payload.get("response_profile") or ""), "inventory.serial.stock.dimension.detail")
        self.assertEqual(str(dict(payload.get("normalized_filters") or {}).get("material_family_match_mode") or ""), "contains")

    def test_inventory_movement_detail_binding_resolves_from_capability_pack(self):
        decision = self.registry.resolve(
            SemanticBindingRequest(
                domain="inventario_logistica",
                message="ingreso del codigo 1025507",
                intent="movement_query",
                normalized_filters={"codigo": "1025507"},
                source_hints={"inventory_inference": {"operation": "list"}},
            )
        )

        payload = decision.as_dict()
        self.assertEqual(str(payload.get("template_id") or ""), "inventory_movement_detail")
        self.assertEqual(str(payload.get("candidate_capability") or ""), "inventory_movement_detail")
        self.assertEqual(str(payload.get("planner_route_hint") or ""), "inventory.movement.detail")
        self.assertEqual(str(payload.get("response_profile") or ""), "inventory.movement.detail")
        self.assertEqual(str(payload.get("source") or ""), "capability_pack")
        self.assertFalse(bool(payload.get("fallback_used")))
        self.assertFalse(bool(payload.get("legacy_mapping_used")))
        self.assertIn("inventario.route.movement_detail", list(payload.get("regla_metadata_usada") or []))

    def test_inventory_serial_stock_dimension_binding_resolves_from_capability_pack(self):
        decision = self.registry.resolve(
            SemanticBindingRequest(
                domain="inventario_logistica",
                message="equipos agrupados por estado",
                intent="stock_query",
                normalized_filters={},
                group_by=["estado"],
                source_hints={"inventory_inference": {"material_family": "serializados"}},
            )
        )

        payload = decision.as_dict()
        self.assertEqual(str(payload.get("template_id") or ""), "inventory_serial_stock_by_dimension")
        self.assertEqual(str(payload.get("candidate_capability") or ""), "inventory_serial_stock_by_dimension")
        self.assertEqual(str(payload.get("planner_route_hint") or ""), "inventory.serial.stock.dimension")
        self.assertEqual(str(payload.get("response_profile") or ""), "inventory.serial.dimension.summary")
        self.assertEqual(str(payload.get("source") or ""), "capability_pack")
        self.assertFalse(bool(payload.get("fallback_used")))
        self.assertFalse(bool(payload.get("legacy_mapping_used")))
        self.assertIn("inventario.route.serial_stock_dimension", list(payload.get("regla_metadata_usada") or []))

    def test_inventory_serial_risk_binding_resolves_from_capability_pack(self):
        decision = self.registry.resolve(
            SemanticBindingRequest(
                domain="inventario_logistica",
                message="riesgo de serializados en consumo movil sin validar",
                intent="risk_detection",
                normalized_filters={},
                source_hints={"inventory_inference": {"material_family": "serializados", "business_concept": "consumo_movil_sin_validar"}},
            )
        )

        payload = decision.as_dict()
        self.assertEqual(str(payload.get("template_id") or ""), "inventory_risk_consumo_movil_sin_validar")
        self.assertEqual(str(payload.get("candidate_capability") or ""), "inventory_risk_consumo_movil_sin_validar")
        self.assertEqual(str(payload.get("planner_route_hint") or ""), "inventory.risk.consumo_movil_sin_validar")
        self.assertEqual(str(payload.get("response_profile") or ""), "inventory.risk.serial.detail")
        self.assertEqual(str(payload.get("source") or ""), "capability_pack")
        self.assertFalse(bool(payload.get("fallback_used")))
        self.assertFalse(bool(payload.get("legacy_mapping_used")))
        self.assertIn("inventario.route.risk_consumo_movil_sin_validar", list(payload.get("regla_metadata_usada") or []))

    def test_inventory_consumption_top_binding_resolves_from_capability_pack(self):
        decision = self.registry.resolve(
            SemanticBindingRequest(
                domain="inventario_logistica",
                message="top de consumos de materiales del mes",
                intent="consumption_query",
                normalized_filters={"month": "5"},
                group_by=["material"],
                source_hints={"inventory_inference": {"business_concept": "materiales_mas_consumidos", "operation": "top"}},
            )
        )

        payload = decision.as_dict()
        self.assertEqual(str(payload.get("template_id") or ""), "inventory_consumption_top")
        self.assertEqual(str(payload.get("candidate_capability") or ""), "inventory_consumption_top")
        self.assertEqual(str(payload.get("planner_route_hint") or ""), "inventory.consumption.top")
        self.assertEqual(str(payload.get("response_profile") or ""), "inventory.consumption.top.summary")
        self.assertEqual(str(payload.get("source") or ""), "capability_pack")
        self.assertFalse(bool(payload.get("fallback_used")))
        self.assertFalse(bool(payload.get("legacy_mapping_used")))
        self.assertIn("inventario.route.consumption_top", list(payload.get("regla_metadata_usada") or []))

    def test_inventory_consumption_dimension_binding_resolves_from_capability_pack(self):
        decision = self.registry.resolve(
            SemanticBindingRequest(
                domain="inventario_logistica",
                message="consumos de la movil TIRAN314 el 05 de mayo",
                intent="consumption_query",
                normalized_filters={"movil": "TIRAN314", "month": "5"},
                source_hints={"inventory_inference": {"operation": "aggregate"}},
            )
        )

        payload = decision.as_dict()
        self.assertEqual(str(payload.get("template_id") or ""), "inventory_consumption_by_dimension")
        self.assertEqual(str(payload.get("candidate_capability") or ""), "inventory_consumption_by_dimension")
        self.assertEqual(str(payload.get("planner_route_hint") or ""), "inventory.consumption.dimension")
        self.assertEqual(str(payload.get("response_profile") or ""), "inventory.consumption.dimension.summary")
        self.assertEqual(str(payload.get("source") or ""), "capability_pack")
        self.assertFalse(bool(payload.get("fallback_used")))
        self.assertFalse(bool(payload.get("legacy_mapping_used")))
        self.assertIn("inventario.route.consumption_dimension", list(payload.get("regla_metadata_usada") or []))

    def test_inventory_reconciliation_operacion_hfc_binding_resolves_from_capability_pack(self):
        decision = self.registry.resolve(
            SemanticBindingRequest(
                domain="inventario_logistica",
                message="comparativo consumo y facturacion hfc",
                intent="reconciliation_query",
                normalized_filters={"bodega": "operacion_hfc"},
                source_hints={"inventory_inference": {"business_concept": "consumo_vs_facturacion"}},
            )
        )

        payload = decision.as_dict()
        self.assertEqual(str(payload.get("template_id") or ""), "inventory_consumption_billing_operacion_hfc")
        self.assertEqual(str(payload.get("candidate_capability") or ""), "inventory_consumption_billing_operacion_hfc")
        self.assertEqual(str(payload.get("planner_route_hint") or ""), "inventory.reconciliation.operacion_hfc")
        self.assertEqual(str(payload.get("response_profile") or ""), "inventory.reconciliation.operacion_hfc")
        self.assertEqual(str(payload.get("source") or ""), "capability_pack")
        self.assertFalse(bool(payload.get("fallback_used")))
        self.assertFalse(bool(payload.get("legacy_mapping_used")))
        self.assertIn("inventario.route.reconciliation_operacion_hfc", list(payload.get("regla_metadata_usada") or []))

    def test_inventory_legacy_shadow_fallback_no_longer_resolves_the_five_pack_migrated_templates(self):
        cases = [
            {
                "intent": "movement_query",
                "entity": {},
                "filters": {"codigo": "1025507"},
                "group_by": [],
                "inference": {"operation": "list"},
                "removed_template": "inventory_movement_detail",
            },
            {
                "intent": "stock_query",
                "entity": {},
                "filters": {},
                "group_by": ["estado"],
                "inference": {"material_family": "serializados"},
                "removed_template": "inventory_serial_stock_by_dimension",
            },
            {
                "intent": "risk_detection",
                "entity": {},
                "filters": {},
                "group_by": [],
                "inference": {"material_family": "serializados", "business_concept": "consumo_movil_sin_validar"},
                "removed_template": "inventory_risk_consumo_movil_sin_validar",
            },
            {
                "intent": "consumption_query",
                "entity": {},
                "filters": {"month": "5"},
                "group_by": ["material"],
                "inference": {"business_concept": "materiales_mas_consumidos", "operation": "top"},
                "removed_template": "inventory_consumption_top",
            },
            {
                "intent": "reconciliation_query",
                "entity": {},
                "filters": {"bodega": "operacion_hfc"},
                "group_by": [],
                "inference": {"business_concept": "consumo_vs_facturacion"},
                "removed_template": "inventory_consumption_billing_operacion_hfc",
            },
        ]

        for case in cases:
            with self.subTest(intent=case["intent"]):
                template_id = self.registry._resolve_inventory_template_legacy(
                    intent=case["intent"],
                    entity=case["entity"],
                    filters=case["filters"],
                    group_by=case["group_by"],
                    inference=case["inference"],
                )
                self.assertNotEqual(template_id, case["removed_template"])

    def test_inventory_semantic_binding_from_pack_shadows_legacy_mapping_for_migrated_template(self):
        capability_pack = load_inventory_capability_pack()
        binding, matched_rules = self.registry._binding_payload_from_template_or_rules(
            template_id="inventory_kardex_by_employee",
            governed_rules=[],
            capability_pack=capability_pack,
        )

        self.assertEqual(str(binding.get("candidate_capability") or ""), "inventory_kardex_by_employee")
        self.assertEqual(str(binding.get("planner_route_hint") or ""), "inventory.kardex.employee")
        self.assertEqual(str(binding.get("response_profile") or ""), "inventory.kardex.employee.detail")
        self.assertEqual(matched_rules, [])

    def test_inventory_document_pending_trace_is_governed(self):
        decision = self.registry.resolve(
            SemanticBindingRequest(
                domain="inventario_logistica",
                message="actas SAP del empleado 5098747",
                intent="document_generation",
                normalized_filters={"cedula": "5098747"},
            )
        )

        payload = decision.as_dict()
        self.assertEqual(str(payload.get("template_id") or ""), "inventory_document_generation_pending")
        self.assertEqual(str(payload.get("candidate_capability") or ""), "inventory_document_generation_pending")
        self.assertEqual(str(payload.get("planner_route_hint") or ""), "inventory.document_generation.pending")
        self.assertIn("ai_dictionary.dd_reglas", list(payload.get("consulted_metadata") or []))
        self.assertIn("inventario.limit.document_generation_pending", list(payload.get("regla_metadata_usada") or []))
        self.assertIn("ai_dictionary.ia_dev_capacidades_columna", list(payload.get("fuente_dd") or []))
        self.assertEqual(str(payload.get("source") or ""), "capability_pack")

    def test_inventory_registry_resolves_transfer_destination_limit_from_governed_metadata(self):
        decision = self.registry.resolve(
            SemanticBindingRequest(
                domain="inventario_logistica",
                message="traslados por bodega destino",
                intent="transfer_query",
                normalized_filters={},
                group_by=["bodega_destino"],
            )
        )

        payload = decision.as_dict()
        self.assertEqual(str(payload.get("template_id") or ""), "inventory_transfer_destination_not_available")
        self.assertEqual(str(payload.get("response_profile") or ""), "inventory.transfer.destination.blocked")
        self.assertIn("inventario.limit.transfer_destination_missing_metadata", list(payload.get("regla_metadata_usada") or []))
        self.assertFalse(bool(payload.get("regla_legacy_detectada")))
        self.assertEqual(str(payload.get("source") or ""), "capability_pack")

    def test_inventory_registry_resolves_critical_materials_from_capability_pack(self):
        for message, group_by in (
            ("materiales criticos por empleado en operacion_hfc", ["cedula"]),
            ("materiales críticos por técnico", ["cedula"]),
            ("materiales críticos por móvil/cuadrilla", ["movil"]),
            ("criticidad de materiales por saldo y consumo", []),
            ("materiales con cobertura baja", []),
            ("materiales por debajo de umbral", []),
        ):
            with self.subTest(message=message):
                decision = self.registry.resolve(
                    SemanticBindingRequest(
                        domain="inventario_logistica",
                        message=message,
                        intent="stock_balance",
                        normalized_filters={"bodega": "operacion_hfc", "stock_scope": "movil"},
                        group_by=group_by,
                        source_hints={
                            "inventory_inference": {"business_concept": "materiales_criticos_por_empleado"},
                        },
                    )
                )

                payload = decision.as_dict()
                self.assertEqual(str(payload.get("template_id") or ""), "inventory_material_critical_by_employee")
                self.assertEqual(str(payload.get("candidate_capability") or ""), "inventory_stock_balance_by_mobile")
                self.assertEqual(str(payload.get("planner_route_hint") or ""), "inventory.material_stock.critical_employee")
                self.assertEqual(str(payload.get("response_profile") or ""), "inventory.stock.critical.employee")
                self.assertEqual(str(payload.get("source") or ""), "capability_pack")
                self.assertFalse(bool(payload.get("fallback_used")))
                self.assertFalse(bool(payload.get("migration_pending")))
                self.assertFalse(bool(payload.get("legacy_mapping_used")))
                self.assertTrue(bool(payload.get("regla_migrada")))
                self.assertIn(
                    "inventario.route.critical_materials_by_employee",
                    list(payload.get("regla_metadata_usada") or []),
                )

    def test_inventory_matcher_reads_governed_synonyms_and_trace(self):
        result = self.matcher.resolver(mensaje="muéstrame lo que tiene el móvil TIRAN224", contexto_semantico={})

        self.assertTrue(bool(result.get("coincidencia_gobernada")))
        self.assertEqual(str(result.get("intencion") or ""), "stock_balance")
        self.assertEqual(str((result.get("filtros") or {}).get("movil") or ""), "TIRAN224")
        self.assertIn("inventario.route.stock_balance_holder", list(result.get("regla_metadata_usada") or []))
        self.assertIn("ai_dictionary.dd_sinonimos", list(result.get("fuente_dd") or []))

    def test_inventory_resolver_persists_registry_trace_in_semantic_context(self):
        resolver = InventorySemanticResolver()
        resolver.semantic_plan_builder.memory_service.list_memory_snapshot = lambda: []
        resolver.semantic_plan_builder.memory_service.ensure_confirmed_rules = lambda: {
            "saved_keys": [],
            "error_count": 0,
            "errors": [],
        }

        resolved = resolver.resolve_query(
            message="muestrame lo que tiene el movil TIRAN224",
            intent=StructuredQueryIntent(
                raw_query="muestrame lo que tiene el movil TIRAN224",
                domain_code="inventario_logistica",
                operation="stock_balance",
                template_id="",
                confidence=0.9,
            ),
            semantic_context={},
        )

        binding = dict(resolved.semantic_context.get("semantic_capability_registry") or {})
        trace = dict(((resolved.semantic_context.get("resolved_semantic") or {}).get("binding_trace") or {}))
        self.assertEqual(str(binding.get("template_id") or ""), "inventory_material_stock_mobile")
        self.assertEqual(str(binding.get("candidate_capability") or ""), "inventory_stock_balance_by_mobile")
        self.assertEqual(str(binding.get("planner_route_hint") or ""), "inventory.material_stock.mobile")
        self.assertEqual(str(binding.get("response_profile") or ""), "inventory.stock.mobile.dual_block")
        self.assertEqual(str(trace.get("source") or ""), "capability_pack")
        self.assertIn("inventario.route.stock_balance_holder", list(trace.get("regla_metadata_usada") or []))
        self.assertIn("ai_dictionary.dd_reglas", list(trace.get("fuente_dd") or []))
        self.assertEqual(str(trace.get("paquete_capacidad_usado") or ""), "inventario_logistica")
        self.assertEqual(str(trace.get("version_paquete") or ""), "1.2.0")
        self.assertEqual(float(trace.get("capability_pack_coverage") or 0.0), 1.0)
        self.assertGreater(int(trace.get("templates_pack_driven_count") or 0), 0)
        self.assertEqual(int(trace.get("templates_legacy_allowed_count") or 0), 0)
        self.assertEqual(list(trace.get("templates_missing_selection_rules") or []), [])

    def test_employee_capability_pack_loader_validates_first_phase_contract(self):
        bundle = load_employee_capability_pack()

        self.assertEqual(bundle.domain, "empleados")
        self.assertEqual(bundle.pack_name, "empleados")
        self.assertEqual(bundle.version, "0.4.0")
        self.assertTrue(bundle.validation.ok, msg=str(bundle.validation.errors))
        self.assertEqual(bundle.coverage.capability_pack_coverage, 1.0)
        self.assertEqual(bundle.coverage.templates_missing_selection_rules, [])
        self.assertEqual(bundle.coverage.templates_legacy_allowed_count, 0)
        self.assertIn("count_entities_by_status", bundle.semantic_bindings_by_template)
        self.assertIn("aggregate_by_group_and_period", bundle.semantic_bindings_by_template)
        self.assertIn("detail_by_entity_and_period", bundle.semantic_bindings_by_template)
        self.assertIn("count_records_by_period", bundle.semantic_bindings_by_template)
        self.assertIn("empleados.count.active.v1", bundle.capabilities_by_id)
        self.assertIn("empleados.detail.v1", bundle.capabilities_by_id)
        self.assertIn("empleados.count.active.summary", bundle.response_profiles_by_id)
        self.assertIn("empleados.detail.safe_table", bundle.response_profiles_by_id)
        self.assertIn("empleados.birthday.summary", bundle.response_profiles_by_id)

    def test_employee_active_population_binding_resolves_from_capability_pack(self):
        decision = self.registry.resolve(
            SemanticBindingRequest(
                domain="empleados",
                message="personal activo hoy",
                intent="count",
                normalized_filters={"estado": "ACTIVO"},
                group_by=[],
                semantic_context={},
                source_hints={"template_id": "count_entities_by_status", "metrics": ["count"]},
            )
        )

        payload = decision.as_dict()
        self.assertEqual(str(payload.get("template_id") or ""), "count_entities_by_status")
        self.assertEqual(str(payload.get("candidate_capability") or ""), "empleados.count.active.v1")
        self.assertEqual(str(payload.get("planner_route_hint") or ""), "empleados.population.count")
        self.assertEqual(str(payload.get("response_profile") or ""), "empleados.count.active.summary")
        self.assertEqual(str(payload.get("tool_id") or ""), "empleados.count.active.v1")
        self.assertEqual(str(payload.get("source") or ""), "capability_pack")
        self.assertFalse(bool(payload.get("fallback_used")))
        self.assertFalse(bool(payload.get("legacy_mapping_used")))
        self.assertIn("empleados.route.population_count", list(payload.get("regla_metadata_usada") or []))
        self.assertNotIn("celular_personal", list((payload.get("output_profile") or {}).get("columns") or []))
        self.assertEqual(float(payload.get("capability_pack_coverage") or 0.0), 1.0)
        self.assertEqual(list(payload.get("templates_missing_selection_rules") or []), [])

    def test_employee_grouped_population_by_area_resolves_from_capability_pack(self):
        decision = self.registry.resolve(
            SemanticBindingRequest(
                domain="empleados",
                message="empleados por area",
                intent="aggregate",
                normalized_filters={"estado": "ACTIVO"},
                group_by=["area"],
                semantic_context={},
                source_hints={"template_id": "aggregate_by_group_and_period", "metrics": ["count"]},
            )
        )

        payload = decision.as_dict()
        self.assertEqual(str(payload.get("template_id") or ""), "aggregate_by_group_and_period")
        self.assertEqual(str(payload.get("candidate_capability") or ""), "empleados.count.active.v1")
        self.assertEqual(str(payload.get("planner_route_hint") or ""), "empleados.population.grouped")
        self.assertEqual(str(payload.get("response_profile") or ""), "empleados.count.grouped.summary")
        self.assertEqual(str(payload.get("source") or ""), "capability_pack")
        self.assertFalse(bool(payload.get("fallback_used")))
        self.assertFalse(bool(payload.get("legacy_mapping_used")))
        self.assertIn("empleados.route.population_grouped_dimension", list(payload.get("regla_metadata_usada") or []))
        self.assertEqual(list((payload.get("output_profile") or {}).get("columns") or []), ["area", "cantidad"])

    def test_employee_grouped_population_by_movil_for_tecnicos_resolves_from_capability_pack(self):
        decision = self.registry.resolve(
            SemanticBindingRequest(
                domain="empleados",
                message="tecnicos por movil",
                intent="aggregate",
                normalized_filters={"estado": "ACTIVO", "tipo_labor": "OPERATIVO"},
                group_by=["movil"],
                semantic_context={},
                source_hints={"template_id": "aggregate_by_group_and_period", "metrics": ["count"]},
            )
        )

        payload = decision.as_dict()
        self.assertEqual(str(payload.get("source") or ""), "capability_pack")
        self.assertEqual(str(payload.get("template_id") or ""), "aggregate_by_group_and_period")
        self.assertEqual(list((payload.get("output_profile") or {}).get("columns") or []), ["movil", "cantidad"])

    def test_employee_detail_by_cedula_resolves_from_capability_pack(self):
        decision = self.registry.resolve(
            SemanticBindingRequest(
                domain="empleados",
                message="detalle del empleado 123456",
                intent="detail",
                normalized_filters={"cedula": "123456"},
                group_by=[],
                semantic_context={},
                source_hints={"template_id": "detail_by_entity_and_period"},
            )
        )

        payload = decision.as_dict()
        self.assertEqual(str(payload.get("template_id") or ""), "detail_by_entity_and_period")
        self.assertEqual(str(payload.get("candidate_capability") or ""), "empleados.detail.v1")
        self.assertEqual(str(payload.get("planner_route_hint") or ""), "empleados.population.detail")
        self.assertEqual(str(payload.get("response_profile") or ""), "empleados.detail.safe_table")
        self.assertEqual(str(payload.get("source") or ""), "capability_pack")
        self.assertFalse(bool(payload.get("fallback_used")))
        self.assertFalse(bool(payload.get("legacy_mapping_used")))
        self.assertIn("empleados.route.employee_detail", list(payload.get("regla_metadata_usada") or []))
        self.assertNotIn("codigo_sap", list((payload.get("output_profile") or {}).get("columns") or []))
        self.assertNotIn("link_foto", list((payload.get("output_profile") or {}).get("columns") or []))

    def test_employee_detail_by_supervisor_resolves_from_capability_pack(self):
        decision = self.registry.resolve(
            SemanticBindingRequest(
                domain="empleados",
                message="mostrar personal por supervisor",
                intent="detail",
                normalized_filters={"supervisor": "10203040", "estado": "ACTIVO"},
                group_by=[],
                semantic_context={},
                source_hints={"template_id": "detail_by_entity_and_period"},
            )
        )

        payload = decision.as_dict()
        self.assertEqual(str(payload.get("source") or ""), "capability_pack")
        self.assertEqual(str(payload.get("template_id") or ""), "detail_by_entity_and_period")
        self.assertEqual(str(payload.get("candidate_capability") or ""), "empleados.detail.v1")
        self.assertIn("supervisor", list((payload.get("output_profile") or {}).get("columns") or []))
        self.assertNotIn("password", list((payload.get("output_profile") or {}).get("columns") or []))

    def test_employee_detail_ambiguous_request_keeps_legacy_shadow_fallback_traced(self):
        decision = self.registry.resolve(
            SemanticBindingRequest(
                domain="empleados",
                message="informacion del empleado por cedula",
                intent="detail",
                normalized_filters={},
                group_by=[],
                semantic_context={},
                source_hints={"template_id": "detail_by_entity_and_period"},
            )
        )

        payload = decision.as_dict()
        self.assertEqual(str(payload.get("source") or ""), "legacy_shadow_fallback")
        self.assertTrue(bool(payload.get("fallback_used")))
        self.assertTrue(bool(payload.get("legacy_mapping_used")))
        self.assertEqual(str(payload.get("legacy_retained_reason") or ""), "empleados.limit.detail_ambiguous_request")

    def test_employee_detail_with_undeclared_filter_keeps_legacy_shadow_fallback_traced(self):
        decision = self.registry.resolve(
            SemanticBindingRequest(
                domain="empleados",
                message="detalle de empleados por codigo sap",
                intent="detail",
                normalized_filters={"codigo_sap": "SAP-11"},
                group_by=[],
                semantic_context={},
                source_hints={"template_id": "detail_by_entity_and_period"},
            )
        )

        payload = decision.as_dict()
        self.assertEqual(str(payload.get("source") or ""), "legacy_shadow_fallback")
        self.assertEqual(str(payload.get("legacy_retained_reason") or ""), "empleados.limit.detail_undeclared_filter")

    def test_employee_grouped_distribution_without_dimension_keeps_legacy_shadow_fallback_traced(self):
        decision = self.registry.resolve(
            SemanticBindingRequest(
                domain="empleados",
                message="distribucion de personal",
                intent="aggregate",
                normalized_filters={"estado": "ACTIVO"},
                group_by=[],
                semantic_context={},
                source_hints={"metrics": ["count"]},
            )
        )

        payload = decision.as_dict()
        self.assertEqual(str(payload.get("source") or ""), "legacy_shadow_fallback")
        self.assertTrue(bool(payload.get("fallback_used")))
        self.assertTrue(bool(payload.get("legacy_mapping_used")))
        self.assertEqual(str(payload.get("legacy_retained_reason") or ""), "empleados.limit.grouped_population_ambiguous_request")

    def test_employee_birthday_month_binding_resolves_from_capability_pack(self):
        decision = self.registry.resolve(
            SemanticBindingRequest(
                domain="empleados",
                message="cumpleanos de mayo",
                intent="count",
                normalized_filters={"fnacimiento_month": "5", "estado": "ACTIVO"},
                group_by=[],
                semantic_context={},
                source_hints={"template_id": "count_records_by_period", "metrics": ["count"]},
            )
        )

        payload = decision.as_dict()
        self.assertEqual(str(payload.get("template_id") or ""), "count_records_by_period")
        self.assertEqual(str(payload.get("candidate_capability") or ""), "empleados.count.active.v1")
        self.assertEqual(str(payload.get("planner_route_hint") or ""), "empleados.birthdays.count")
        self.assertEqual(str(payload.get("response_profile") or ""), "empleados.birthday.summary")
        self.assertEqual(str(payload.get("source") or ""), "capability_pack")
        self.assertFalse(bool(payload.get("fallback_used")))
        self.assertFalse(bool(payload.get("legacy_mapping_used")))
        self.assertIn("empleados.route.birthdays_count", list(payload.get("regla_metadata_usada") or []))
        self.assertIn("fecha_nacimiento", list((payload.get("output_profile") or {}).get("columns") or []))

    def test_employee_birthday_grouped_by_area_resolves_from_capability_pack(self):
        decision = self.registry.resolve(
            SemanticBindingRequest(
                domain="empleados",
                message="cumpleanos de mayo por area",
                intent="aggregate",
                normalized_filters={"fnacimiento_month": "5", "estado": "ACTIVO"},
                group_by=["area"],
                semantic_context={},
                source_hints={"template_id": "aggregate_by_group_and_period", "metrics": ["count"]},
            )
        )

        payload = decision.as_dict()
        self.assertEqual(str(payload.get("source") or ""), "capability_pack")
        self.assertEqual(str(payload.get("template_id") or ""), "aggregate_by_group_and_period")
        self.assertIn("empleados.route.birthdays_grouped_dimension", list(payload.get("regla_metadata_usada") or []))
        self.assertEqual(list((payload.get("output_profile") or {}).get("columns") or []), ["area", "cantidad"])

    def test_employee_birthday_today_keeps_legacy_shadow_fallback_traced(self):
        decision = self.registry.resolve(
            SemanticBindingRequest(
                domain="empleados",
                message="cumpleanos de hoy",
                intent="count",
                normalized_filters={"estado": "ACTIVO"},
                group_by=[],
                semantic_context={},
                source_hints={"template_id": "count_records_by_period", "metrics": ["count"]},
            )
        )

        payload = decision.as_dict()
        self.assertEqual(str(payload.get("template_id") or ""), "count_records_by_period")
        self.assertEqual(str(payload.get("source") or ""), "legacy_shadow_fallback")
        self.assertTrue(bool(payload.get("fallback_used")))
        self.assertTrue(bool(payload.get("legacy_mapping_used")))
        self.assertEqual(str(payload.get("legacy_retained_reason") or ""), "empleados.limit.birthday_ambiguous_period")

    def test_employee_heights_binding_keeps_modern_route_traced_as_pending_pack(self):
        decision = self.registry.resolve(
            SemanticBindingRequest(
                domain="empleados",
                message="certificados de altura proximos a vencer del personal activo operativo",
                intent="count",
                normalized_filters={"estado_empleado": "ACTIVO", "tipo_labor": "OPERATIVO"},
                group_by=[],
                semantic_context={"resolved_semantic": {"field_match": {"logical_name": "certificado_alturas_fecha_emision"}}},
                source_hints={"template_id": "count_entities_by_status", "metrics": ["count"]},
            )
        )

        payload = decision.as_dict()
        self.assertEqual(str(payload.get("source") or ""), "legacy_shadow_fallback")
        self.assertEqual(str(payload.get("candidate_capability") or ""), "empleados.count.active.v1")
        self.assertEqual(str(payload.get("legacy_retained_reason") or ""), "empleados.limit.heights_certificate_pending_pack")
        self.assertEqual(str(payload.get("response_profile") or ""), "empleados.certificados_alturas.summary")
