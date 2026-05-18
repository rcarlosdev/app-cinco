from __future__ import annotations

from django.test import SimpleTestCase

from apps.ia_dev.application.contracts.query_intelligence_contracts import StructuredQueryIntent
from apps.ia_dev.application.semantic.semantic_capability_registry import (
    SemanticBindingRequest,
    SemanticCapabilityRegistry,
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
        self.assertEqual(str(payload.get("source") or ""), "governed_template")
        self.assertFalse(bool(payload.get("fallback_used")))
        self.assertIn("inventario.route.stock_balance_holder", list(payload.get("regla_metadata_usada") or []))
        self.assertFalse(bool(payload.get("fallback_sombreado_usado")))
        self.assertTrue(bool(payload.get("regla_migrada")))
        self.assertEqual(str(payload.get("paquete_capacidad_usado") or ""), "inventario_logistica")
        self.assertEqual(str(payload.get("version_paquete") or ""), "1.0.0")
        self.assertIn("inventory.stock.mobile.detail", list(payload.get("perfiles_respuesta") or []))
        self.assertIn("inventario_runtime_eval_v1", list(payload.get("evaluaciones_asociadas") or []))

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
        self.assertEqual(str(trace.get("source") or ""), "governed_template")
        self.assertIn("inventario.route.stock_balance_holder", list(trace.get("regla_metadata_usada") or []))
        self.assertIn("ai_dictionary.dd_reglas", list(trace.get("fuente_dd") or []))
        self.assertEqual(str(trace.get("paquete_capacidad_usado") or ""), "inventario_logistica")
        self.assertEqual(str(trace.get("version_paquete") or ""), "1.0.0")
