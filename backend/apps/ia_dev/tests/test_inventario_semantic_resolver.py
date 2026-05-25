from __future__ import annotations

from unittest.mock import patch

from django.test import SimpleTestCase

from apps.ia_dev.application.contracts.query_intelligence_contracts import StructuredQueryIntent
from apps.ia_dev.domains.inventario_logistica.semantic_inventory_resolver import (
    InventorySemanticResolver,
)
from apps.ia_dev.services.employee_identifier_service import EmployeeIdentifierService
from apps.ia_dev.services.intent_arbitration_service import IntentArbitrationService


class InventarioSemanticResolverTests(SimpleTestCase):
    def setUp(self):
        self.resolver = InventorySemanticResolver()
        self.resolver.semantic_plan_builder.memory_service.list_memory_snapshot = lambda: [
            {"memory_key": "inventory.semantic.rule.material_claro"},
            {"memory_key": "inventory.semantic.rule.kardex"},
        ]
        self.resolver.semantic_plan_builder.memory_service.ensure_confirmed_rules = lambda: {
            "saved_keys": ["inventory.semantic.rule.material_claro"],
            "error_count": 0,
            "errors": [],
        }

    def _resolve(self, message: str, operation: str = "detail"):
        return self._resolve_with_context(
            message=message,
            operation=operation,
            semantic_context={"inventory_catalog_families": ["DECO", "CPE RESIDENCIAL", "ONT", "ROUTER"]},
        )

    def _resolve_with_context(self, *, message: str, operation: str = "detail", semantic_context: dict | None = None):
        return self.resolver.resolve_query(
            message=message,
            intent=StructuredQueryIntent(
                raw_query=message,
                domain_code="inventario_logistica",
                operation=operation,
                template_id="",
                confidence=0.8,
            ),
            semantic_context=semantic_context or {},
        )

    def _resolve_with_attachment(self, *, message: str, operation: str = "detail"):
        return self._resolve_with_context(
            message=message,
            operation=operation,
            semantic_context={
                "inventory_catalog_families": ["DECO", "CPE RESIDENCIAL", "ONT", "ROUTER"],
                "runtime_attachment_summary": {
                    "present": True,
                    "count": 1,
                    "names": ["seriales_proveedor.xlsx"],
                },
            },
        )

    def _semantic_plan(self, resolved):
        return dict(resolved.semantic_context.get("business_query_semantic_plan") or {})

    def test_semantic_plan_familia_saldo_empleado(self):
        cases = [
            "saldo empleado 5098747",
            "saldo del tecnico 5098747",
            "saldo de inventario del empleado 5098747",
            "saldo material empleado 5098747",
            "saldo material claro empleado 5098747",
            "saldo ferretero empleado 5098747",
        ]

        for message in cases:
            with self.subTest(message=message):
                resolved = self._resolve(message, operation="stock_balance")
                plan = self._semantic_plan(resolved)

                self.assertEqual(str(resolved.intent.domain_code or ""), "inventario_logistica")
                self.assertEqual(str(plan.get("intent") or ""), "stock_balance")
                self.assertEqual(str((plan.get("entity") or {}).get("type") or ""), "empleado")
                self.assertEqual(str((plan.get("entity") or {}).get("identifier") or ""), "5098747")
                self.assertEqual(str((plan.get("entity") or {}).get("field") or ""), "cedula")
                self.assertEqual(str(plan.get("candidate_capability") or ""), "inventory_stock_balance_by_mobile")
                self.assertEqual(str((plan.get("output") or {}).get("grain") or ""), "saldo_por_codigo")
                self.assertFalse(bool((plan.get("scope") or {}).get("include_serialized")))
                self.assertEqual(str((plan.get("execution") or {}).get("capability") or ""), "inventory_stock_balance_by_mobile")

    def test_semantic_plan_familia_kardex_empleado(self):
        cases = [
            "kardex empleado 5098747",
            "kardex del tecnico 5098747",
            "movimientos del empleado 5098747",
            "entradas y salidas del tecnico 5098747",
        ]

        for message in cases:
            with self.subTest(message=message):
                resolved = self._resolve(message, operation="detail")
                plan = self._semantic_plan(resolved)

                self.assertEqual(str(plan.get("intent") or ""), "movement_history")
                self.assertEqual(str((plan.get("entity") or {}).get("type") or ""), "empleado")
                self.assertEqual(str((plan.get("entity") or {}).get("identifier") or ""), "5098747")
                self.assertEqual(str((plan.get("entity") or {}).get("field") or ""), "cedula")
                self.assertEqual(str(plan.get("candidate_capability") or ""), "inventory_kardex_by_employee")
                self.assertEqual(str((plan.get("output") or {}).get("grain") or ""), "movimiento_por_codigo")
                self.assertFalse(bool((plan.get("scope") or {}).get("include_serialized")))

    def test_semantic_plan_familia_movil_cuadrilla(self):
        cases = [
            ("inventario cuadrilla TIRAN224", True),
            ("saldo movil TIRAN224", True),
            ("inventario de la movil TIRAN314", True),
            ("materiales de la cuadrilla TIRAN224", False),
        ]

        for message, include_serialized in cases:
            with self.subTest(message=message):
                resolved = self._resolve(message, operation="stock_balance")
                plan = self._semantic_plan(resolved)

                self.assertEqual(str(plan.get("intent") or ""), "stock_balance")
                self.assertEqual(str((plan.get("entity") or {}).get("type") or ""), "movil")
                self.assertTrue(str((plan.get("entity") or {}).get("identifier") or "").startswith("TIRAN"))
                self.assertEqual(str((plan.get("entity") or {}).get("field") or ""), "movil")
                self.assertEqual(str(plan.get("candidate_capability") or ""), "inventory_stock_balance_by_mobile")
                self.assertEqual(bool((plan.get("scope") or {}).get("include_serialized")), include_serialized)

    def test_semantic_plan_familia_codigo(self):
        cases = [
            "kardex codigo 1020498",
            "movimientos codigo 1020498",
            "saldo codigo 1020498",
        ]

        for message in cases:
            with self.subTest(message=message):
                resolved = self._resolve(message, operation="detail")
                plan = self._semantic_plan(resolved)

                self.assertEqual(str((plan.get("entity") or {}).get("type") or ""), "codigo")
                self.assertEqual(str((plan.get("entity") or {}).get("identifier") or ""), "1020498")
                self.assertEqual(str((plan.get("entity") or {}).get("field") or ""), "codigo")
                self.assertEqual(str((plan.get("normalized_filters") or {}).get("codigo") or ""), "1020498")
                self.assertNotIn("legacy", str(resolved.intent.template_id or ""))
                self.assertNotIn("fallback", str(resolved.intent.template_id or ""))

    def test_semantic_plan_familia_serializados(self):
        cases = [
            ("movimiento serial 254429139509", "serial"),
            ("equipos cargados al empleado 98562719", "empleado"),
            ("seriales perdidos", "serial"),
            ("equipos en garantia", "serial"),
        ]

        for message, expected_entity in cases:
            with self.subTest(message=message):
                resolved = self._resolve(message, operation="detail")
                plan = self._semantic_plan(resolved)

                self.assertEqual(str(plan.get("inventory_family") or ""), "serializados")
                self.assertTrue(bool((plan.get("scope") or {}).get("include_serialized")))
                self.assertEqual(str(plan.get("candidate_capability") or ""), str((plan.get("execution") or {}).get("capability") or ""))
                self.assertIn("serializados", list((plan.get("scope") or {}).get("families") or []))
                if expected_entity == "empleado":
                    self.assertEqual(str((plan.get("entity") or {}).get("field") or ""), "cedula")
                else:
                    self.assertIn(str((plan.get("entity") or {}).get("field") or ""), {"serial", ""})

    def test_trazabilidad_del_serial(self):
        resolved = self._resolve("trazabilidad del serial ABC123")

        self.assertEqual(str(resolved.intent.domain_code or ""), "inventario_logistica")
        self.assertEqual(str(resolved.intent.template_id or ""), "inventory_traceability_by_serial")
        self.assertEqual(str(resolved.normalized_filters.get("serial") or ""), "ABC123")
        self.assertEqual(
            str(((resolved.semantic_context.get("inventory_semantic_inference") or {}).get("intent") or "")),
            "traceability_query",
        )

    def test_valida_seriales_adjuntos_proveedor_resuelve_capability_gobernada(self):
        resolved = self._resolve_with_attachment(
            message="Valida los seriales adjuntos, dados por el proveedor",
            operation="validate_file",
        )

        self.assertEqual(str(resolved.intent.template_id or ""), "inventory_provider_serial_validation")
        self.assertEqual(str(resolved.intent.operation or ""), "validate_file")
        self.assertEqual(
            str(((resolved.semantic_context.get("inventory_semantic_inference") or {}).get("business_concept") or "")),
            "validacion_seriales_externos_contra_inventario_propio",
        )
        self.assertEqual(
            str(((resolved.semantic_context.get("semantic_capability_registry") or {}).get("candidate_capability") or "")),
            "inventory_provider_serial_validation",
        )

    def test_revisa_seriales_del_proveedor_con_adjunto_resuelve_capability_gobernada(self):
        resolved = self._resolve_with_attachment(
            message="Revisa estos seriales del proveedor",
            operation="validate_file",
        )

        self.assertEqual(str(resolved.intent.template_id or ""), "inventory_provider_serial_validation")
        self.assertEqual(str(resolved.intent.operation or ""), "validate_file")
        self.assertEqual(
            str(((resolved.semantic_context.get("inventory_semantic_inference") or {}).get("expected_runtime_flow") or "")),
            "handler",
        )

    def test_valida_seriales_con_adjunto_sin_repetir_proveedor_resuelve_capability_gobernada(self):
        resolved = self._resolve_with_attachment(
            message="Validar los seriales",
            operation="validate_file",
        )

        self.assertEqual(str(resolved.intent.template_id or ""), "inventory_provider_serial_validation")
        self.assertEqual(str(resolved.intent.operation or ""), "validate_file")
        self.assertEqual(
            str(((resolved.semantic_context.get("semantic_capability_registry") or {}).get("candidate_capability") or "")),
            "inventory_provider_serial_validation",
        )

    def test_valida_seriales_sin_adjunto_no_fuerza_ruta_de_proveedor(self):
        resolved = self._resolve("Valida los seriales", operation="detail")

        self.assertNotEqual(str(resolved.intent.template_id or ""), "inventory_provider_serial_validation")

    def test_consumo_movil_sin_validar(self):
        cases = ["equipos serializados en consumo movil sin validar"]

        for message in cases:
            with self.subTest(message=message):
                resolved = self._resolve(message)
                inference = dict(resolved.semantic_context.get("inventory_semantic_inference") or {})
                trace = dict(((resolved.semantic_context.get("resolved_semantic") or {}).get("binding_trace") or {}))

                self.assertEqual(str(inference.get("intent") or ""), "risk_detection")
                self.assertEqual(str(inference.get("business_concept") or ""), "consumo_movil_sin_validar")
                self.assertEqual(str(resolved.intent.template_id or ""), "inventory_risk_consumo_movil_sin_validar")
                self.assertEqual(str(trace.get("source") or ""), "capability_pack")
                self.assertFalse(bool(trace.get("fallback_sombreado_usado")))
                self.assertFalse(bool(trace.get("legacy_mapping_used")))
                self.assertFalse(bool(trace.get("fallback_used")))

    def test_materiales_mas_consumidos_en_mayo(self):
        cases = [
            "materiales mas consumidos en mayo",
            "top de consumos de materiales en mayo",
        ]

        for message in cases:
            with self.subTest(message=message):
                resolved = self._resolve(message, operation="aggregate")
                trace = dict(((resolved.semantic_context.get("resolved_semantic") or {}).get("binding_trace") or {}))

                self.assertEqual(str(resolved.intent.template_id or ""), "inventory_consumption_top")
                if "materiales mas consumidos" in message:
                    self.assertIn("material", list(resolved.intent.group_by or []))
                self.assertEqual(str(resolved.normalized_filters.get("month") or ""), "5")
                self.assertEqual(str(trace.get("source") or ""), "capability_pack")
                self.assertFalse(bool(trace.get("legacy_mapping_used")))
                self.assertFalse(bool(trace.get("fallback_used")))

    def test_consumos_de_movil_en_mayo_resuelven_consumption_dimension_desde_capability_pack(self):
        resolved = self._resolve("consumos de la movil TIRAN314 el 05 de mayo", operation="aggregate")
        trace = dict(((resolved.semantic_context.get("resolved_semantic") or {}).get("binding_trace") or {}))

        self.assertEqual(str(resolved.intent.template_id or ""), "inventory_consumption_by_dimension")
        self.assertEqual(str(resolved.normalized_filters.get("movil") or ""), "TIRAN314")
        self.assertEqual(str(resolved.normalized_filters.get("month") or ""), "5")
        self.assertEqual(str(trace.get("source") or ""), "capability_pack")
        self.assertFalse(bool(trace.get("legacy_mapping_used")))
        self.assertFalse(bool(trace.get("fallback_used")))

    def test_ingreso_del_codigo_resuelve_movement_detail_desde_capability_pack(self):
        resolved = self._resolve("ingreso del codigo 1025507", operation="detail")
        trace = dict(((resolved.semantic_context.get("resolved_semantic") or {}).get("binding_trace") or {}))

        self.assertEqual(str(resolved.intent.template_id or ""), "inventory_movement_detail")
        self.assertEqual(str(resolved.normalized_filters.get("codigo") or ""), "1025507")
        self.assertEqual(str(trace.get("source") or ""), "capability_pack")
        self.assertFalse(bool(trace.get("legacy_mapping_used")))
        self.assertFalse(bool(trace.get("fallback_used")))

    def test_traslados_por_bodega_destino(self):
        resolved = self._resolve("traslados por bodega destino", operation="aggregate")

        self.assertEqual(str(resolved.intent.template_id or ""), "inventory_transfer_destination_not_available")
        self.assertEqual(list(resolved.intent.group_by or []), ["bodega_destino"])
        self.assertIn("missing_physical_column:bodega_destino", list((resolved.semantic_context.get("resolved_semantic") or {}).get("limitations") or []))

    def test_stock_de_materiales_por_bodega_usa_saldo_validado(self):
        resolved = self._resolve("stock de materiales por bodega", operation="aggregate")

        self.assertEqual(str(resolved.intent.template_id or ""), "inventory_material_stock_by_warehouse")
        self.assertNotIn("inventario_stock_pendiente_validacion_db_ai_dictionary", list(resolved.warnings or []))

    def test_saldo_bodega_operacion_hfc_extrae_filtro_fuerte(self):
        resolved = self._resolve("saldo bodega operacion_hfc", operation="stock_balance")
        inference = dict(resolved.semantic_context.get("inventory_semantic_inference") or {})

        self.assertEqual(str(inference.get("intent") or ""), "stock_balance")
        self.assertEqual(str(resolved.intent.operation or ""), "stock_balance")
        self.assertEqual(str(resolved.intent.template_id or ""), "inventory_material_stock_by_warehouse")
        self.assertEqual(str(resolved.normalized_filters.get("bodega") or ""), "operacion_hfc")
        self.assertEqual(str(resolved.normalized_filters.get("stock_scope") or ""), "bodega")
        self.assertIn("bodega", list(resolved.intent.group_by or []))

    def test_saldo_movil_materiales_resuelve_template_movil(self):
        resolved = self._resolve("saldo movil de materiales", operation="aggregate")

        self.assertEqual(str(resolved.intent.template_id or ""), "inventory_material_stock_mobile")
        self.assertEqual(str(resolved.normalized_filters.get("stock_scope") or ""), "movil")

    def test_saldo_en_moviles_de_material_resuelve_dimension_agrupada_por_descripcion(self):
        resolved = self._resolve("saldo en moviles de CONECTOR RJ 45", operation="aggregate")

        self.assertEqual(str(resolved.intent.template_id or ""), "inventory_material_stock_grouped_dimension")
        self.assertEqual(str(resolved.normalized_filters.get("descripcion") or ""), "CONECTOR RJ 45")
        self.assertEqual(list(resolved.intent.group_by or []), ["movil"])
        self.assertEqual(str(resolved.normalized_filters.get("grouping_dimension") or ""), "movil")

    def test_saldo_por_movil_del_codigo_resuelve_dimension_agrupada_por_codigo(self):
        resolved = self._resolve("saldo por movil del codigo 1025507", operation="aggregate")

        self.assertEqual(str(resolved.intent.template_id or ""), "inventory_material_stock_grouped_dimension")
        self.assertEqual(str(resolved.normalized_filters.get("codigo") or ""), "1025507")
        self.assertEqual(list(resolved.intent.group_by or []), ["movil"])

    def test_inventario_de_material_por_cuadrilla_usa_dimension_movil(self):
        resolved = self._resolve("inventario de CONECTOR RJ 45 por cuadrilla", operation="aggregate")

        self.assertEqual(str(resolved.intent.template_id or ""), "inventory_material_stock_grouped_dimension")
        self.assertEqual(str(resolved.normalized_filters.get("descripcion") or ""), "CONECTOR RJ 45")
        self.assertEqual(list(resolved.intent.group_by or []), ["movil"])

    def test_saldo_en_moviles_de_deco_resuelve_familia_serializada_por_movil(self):
        resolved = self._resolve("saldo en moviles de Deco", operation="aggregate")

        self.assertEqual(str(resolved.intent.template_id or ""), "inventory_serial_stock_by_family_grouped_dimension")
        self.assertEqual(str(resolved.normalized_filters.get("material_family") or ""), "DECO")
        self.assertEqual(str(resolved.normalized_filters.get("material_family_match_mode") or ""), "contains")
        self.assertEqual(list(resolved.intent.group_by or []), ["movil"])

    def test_inventario_de_deco_por_cuadrilla_resuelve_familia_serializada(self):
        resolved = self._resolve("inventario de Deco por cuadrilla", operation="aggregate")

        self.assertEqual(str(resolved.intent.template_id or ""), "inventory_serial_stock_by_family_grouped_dimension")
        self.assertEqual(str(resolved.normalized_filters.get("material_family") or ""), "DECO")
        self.assertEqual(list(resolved.intent.group_by or []), ["movil"])

    def test_equipos_deco_en_moviles_resuelve_familia_serializada(self):
        resolved = self._resolve("equipos Deco en moviles", operation="aggregate")

        self.assertEqual(str(resolved.intent.template_id or ""), "inventory_serial_stock_by_family_grouped_dimension")
        self.assertEqual(str(resolved.normalized_filters.get("material_family") or ""), "DECO")
        self.assertEqual(list(resolved.intent.group_by or []), ["movil"])

    def test_saldo_en_moviles_de_cpe_residencial_resuelve_concepto_serializado_gobernado(self):
        resolved = self._resolve("saldo en moviles de CPE residencial", operation="aggregate")

        self.assertEqual(str(resolved.intent.template_id or ""), "inventory_serial_stock_by_family_grouped_dimension")
        self.assertEqual(str(resolved.normalized_filters.get("material_family") or ""), "CPE RESIDENCIAL")
        self.assertEqual(list(resolved.intent.group_by or []), ["movil"])

    def test_saldo_en_moviles_de_deco_usa_busqueda_parcial_en_catalogo_serializado(self):
        resolved = self._resolve_with_context(
            message="saldo en moviles de Deco",
            operation="aggregate",
            semantic_context={"inventory_catalog_families": ["DECO HD", "DECO IPTV", "ONT", "ROUTER"]},
        )

        self.assertEqual(str(resolved.intent.template_id or ""), "inventory_serial_stock_by_family_grouped_dimension")
        self.assertEqual(str(resolved.normalized_filters.get("material_family") or ""), "DECO")
        self.assertEqual(str(resolved.normalized_filters.get("material_family_match_mode") or ""), "contains")

    def test_existencias_de_ferretero_por_movil_resuelve_dimension_por_familia(self):
        resolved = self._resolve("existencias de ferretero por movil", operation="aggregate")

        self.assertEqual(str(resolved.intent.template_id or ""), "inventory_material_stock_grouped_dimension")
        self.assertEqual(str(resolved.normalized_filters.get("tipo") or ""), "ferretero")
        self.assertEqual(list(resolved.intent.group_by or []), ["movil"])

    def test_saldo_empleado_resuelve_stock_movil_por_cedula(self):
        resolved = self._resolve("saldo empleado 98672304", operation="stock_balance")

        self.assertEqual(str(resolved.intent.domain_code or ""), "inventario_logistica")
        self.assertEqual(str(resolved.intent.operation or ""), "stock_balance")
        self.assertEqual(str(resolved.intent.template_id or ""), "inventory_material_stock_mobile")
        self.assertEqual(str(resolved.normalized_filters.get("cedula") or ""), "98672304")
        self.assertEqual(str(resolved.normalized_filters.get("stock_scope") or ""), "movil")

    def test_inventario_cuadrilla_textual_resuelve_movil_y_no_serial(self):
        resolved = self._resolve("inventario de la cuadrilla TIRAN224", operation="stock_balance")

        self.assertEqual(str(resolved.intent.template_id or ""), "inventory_material_stock_mobile")
        self.assertEqual(str(resolved.normalized_filters.get("movil") or ""), "TIRAN224")
        self.assertEqual(str(resolved.normalized_filters.get("stock_scope") or ""), "movil")
        self.assertFalse(bool(resolved.normalized_filters.get("serial")))

    def test_materiales_del_tecnico_numeric_prioriza_cedula(self):
        resolved = self._resolve("materiales del tecnico 1214730857 con datos del empleado", operation="detail")

        self.assertEqual(str(resolved.intent.template_id or ""), "inventory_material_stock_mobile")
        self.assertEqual(str(resolved.normalized_filters.get("cedula") or ""), "1214730857")

    def test_kardex_del_tecnico_numeric_resuelve_kardex_operativo_por_cedula(self):
        resolved = self._resolve("kardex del tecnico 5098747", operation="detail")
        inference = dict(resolved.semantic_context.get("inventory_semantic_inference") or {})

        self.assertEqual(str(resolved.intent.domain_code or ""), "inventario_logistica")
        self.assertEqual(str(resolved.intent.template_id or ""), "inventory_kardex_by_employee")
        self.assertEqual(str(resolved.intent.operation or ""), "detail")
        self.assertEqual(str(resolved.normalized_filters.get("cedula") or ""), "5098747")
        self.assertEqual(str(inference.get("business_concept") or ""), "kardex_operativo_por_empleado")

    def test_kardex_del_empleado_numeric_resuelve_kardex_operativo_por_cedula(self):
        resolved = self._resolve("kardex del empleado 5098747", operation="detail")

        self.assertEqual(str(resolved.intent.template_id or ""), "inventory_kardex_by_employee")
        self.assertEqual(str(resolved.normalized_filters.get("cedula") or ""), "5098747")
        self.assertIn(
            "serializados_employee_kardex_not_available",
            list((resolved.semantic_context.get("resolved_semantic") or {}).get("limitations") or []),
        )

    def test_kardex_codigo_para_empleado_prioriza_kardex_por_empleado(self):
        resolved = self._resolve("kardex del codigo 1025507 para el empleado 5098747", operation="detail")

        self.assertEqual(str(resolved.intent.template_id or ""), "inventory_kardex_by_employee")
        self.assertEqual(str(resolved.normalized_filters.get("cedula") or ""), "5098747")
        self.assertEqual(str(resolved.normalized_filters.get("codigo") or ""), "1025507")

    def test_variacion_que_tiene_asignado_cuadrilla_resuelve_movil_con_bloque_dual(self):
        resolved = self._resolve("qué tiene asignado la cuadrilla TIRAN224", operation="stock_balance")
        plan = self._semantic_plan(resolved)

        self.assertEqual(str(resolved.intent.template_id or ""), "inventory_material_stock_mobile")
        self.assertEqual(str(resolved.normalized_filters.get("movil") or ""), "TIRAN224")
        self.assertEqual(str((plan.get("entity") or {}).get("field") or ""), "movil")
        self.assertTrue(bool((plan.get("scope") or {}).get("include_serialized")))

    def test_variacion_muestrame_lo_que_tiene_el_movil_resuelve_movil_con_bloque_dual(self):
        resolved = self._resolve("muéstrame lo que tiene el móvil TIRAN224", operation="stock_balance")
        plan = self._semantic_plan(resolved)

        self.assertEqual(str(resolved.normalized_filters.get("movil") or ""), "TIRAN224")
        self.assertTrue(bool((plan.get("scope") or {}).get("include_serialized")))

    def test_variacion_movimientos_del_tecnico_prioriza_cedula(self):
        resolved = self._resolve("movimientos del técnico 5098747", operation="detail")

        self.assertEqual(str(resolved.intent.template_id or ""), "inventory_kardex_by_employee")
        self.assertEqual(str(resolved.normalized_filters.get("cedula") or ""), "5098747")

    def test_variacion_entradas_y_salidas_de_cedula_prioriza_kardex_empleado(self):
        resolved = self._resolve("entradas y salidas de 5098747", operation="detail")

        self.assertEqual(str(resolved.intent.template_id or ""), "inventory_kardex_by_employee")
        self.assertEqual(str(resolved.normalized_filters.get("cedula") or ""), "5098747")

    def test_variacion_material_de_claro_para_movil_resuelve_tipo_material(self):
        resolved = self._resolve("solo material de claro de TIRAN224", operation="stock_balance")
        plan = self._semantic_plan(resolved)

        self.assertEqual(str(resolved.normalized_filters.get("movil") or ""), "TIRAN224")
        self.assertEqual(str(resolved.normalized_filters.get("tipo") or ""), "material")
        self.assertFalse(bool((plan.get("scope") or {}).get("include_serialized")))

    def test_variacion_ferreteria_asignada_al_tecnico_resuelve_tipo_ferretero(self):
        resolved = self._resolve("ferretería asignada al técnico 5098747", operation="stock_balance")

        self.assertEqual(str(resolved.normalized_filters.get("cedula") or ""), "5098747")
        self.assertEqual(str(resolved.normalized_filters.get("tipo") or ""), "ferretero")

    def test_variacion_nombre_propio_sin_identificador_queda_bloqueada_para_aclaracion(self):
        resolved = self._resolve("qué tiene Juan Pérez", operation="detail")
        inference = dict(resolved.semantic_context.get("inventory_semantic_inference") or {})

        self.assertEqual(str(inference.get("intent") or ""), "needs_clarification")
        self.assertTrue(any("cédula" in item.lower() or "móvil" in item.lower() for item in list(resolved.warnings or [])))

    def test_variacion_actas_sap_declara_limitacion(self):
        resolved = self._resolve("actas SAP del empleado 5098747", operation="detail")
        inference = dict(resolved.semantic_context.get("inventory_semantic_inference") or {})

        self.assertEqual(str(resolved.intent.template_id or ""), "inventory_document_generation_pending")
        self.assertIn("documentos_sap_y_actas_no_habilitados", list(inference.get("limitations") or []))

    def test_saldo_material_claro_empleado_resuelve_tipo_material(self):
        resolved = self._resolve("saldo material claro empleado 5098747", operation="stock_balance")

        self.assertEqual(str(resolved.intent.template_id or ""), "inventory_material_stock_mobile")
        self.assertEqual(str(resolved.normalized_filters.get("cedula") or ""), "5098747")
        self.assertEqual(str(resolved.normalized_filters.get("tipo") or ""), "material")
        self.assertFalse(bool(resolved.normalized_filters.get("codigo")))

    def test_saldo_material_de_claro_empleado_resuelve_tipo_material(self):
        resolved = self._resolve("saldo material de claro empleado 5098747", operation="stock_balance")

        self.assertEqual(str(resolved.normalized_filters.get("cedula") or ""), "5098747")
        self.assertEqual(str(resolved.normalized_filters.get("tipo") or ""), "material")
        self.assertFalse(bool(resolved.normalized_filters.get("codigo")))

    def test_saldo_ferretero_empleado_resuelve_tipo_ferretero(self):
        resolved = self._resolve("saldo ferretero empleado 5098747", operation="stock_balance")

        self.assertEqual(str(resolved.normalized_filters.get("cedula") or ""), "5098747")
        self.assertEqual(str(resolved.normalized_filters.get("tipo") or ""), "ferretero")

    def test_saldo_material_generico_empleado_incluye_material_y_ferretero(self):
        resolved = self._resolve("saldo material empleado 5098747", operation="stock_balance")

        self.assertEqual(str(resolved.normalized_filters.get("cedula") or ""), "5098747")
        self.assertEqual(list(resolved.normalized_filters.get("tipo") or []), ["material", "ferretero"])
        self.assertFalse(bool(resolved.normalized_filters.get("codigo")))

    def test_saldo_por_tecnico_en_operacion_hfc_prioriza_stock_movil(self):
        resolved = self._resolve(
            "saldo por tecnico en operacion_hfc mostrando cedula, nombre, movil y total de materiales",
            operation="aggregate",
        )

        self.assertEqual(str(resolved.intent.template_id or ""), "inventory_material_stock_mobile")
        self.assertEqual(str(resolved.normalized_filters.get("bodega") or ""), "operacion_hfc")
        self.assertIn("cedula", list(resolved.intent.group_by or []))
        self.assertIn("codigo", list(resolved.intent.group_by or []))

    def test_inventario_por_cuadrilla_conserva_codigo_movil_y_cedula(self):
        resolved = self._resolve(
            "inventario por cuadrilla mostrando movil, cedula del empleado, nombre y saldo total",
            operation="aggregate",
        )

        self.assertEqual(str(resolved.intent.template_id or ""), "inventory_material_stock_mobile")
        self.assertIn("movil", list(resolved.intent.group_by or []))
        self.assertIn("cedula", list(resolved.intent.group_by or []))
        self.assertIn("codigo", list(resolved.intent.group_by or []))

    def test_materiales_criticos_por_empleado_resuelve_template_dedicado_en_variaciones_semanticas(self):
        cases = [
            (
                "materiales criticos por empleado en operacion_hfc cruzando saldo, cedula, movil y datos del empleado",
                "operacion_hfc",
                ["cedula"],
            ),
            ("materiales críticos por técnico en operacion_hfc", "operacion_hfc", ["cedula"]),
            ("materiales críticos por móvil/cuadrilla en operacion_hfc", "operacion_hfc", ["movil"]),
            ("criticidad de materiales por saldo y consumo en operacion_hfc", "operacion_hfc", []),
            ("materiales con cobertura baja en operacion_hfc", "operacion_hfc", []),
            ("materiales por debajo de umbral en operacion_hfc", "operacion_hfc", []),
        ]

        for message, expected_bodega, expected_group_by in cases:
            with self.subTest(message=message):
                resolved = self._resolve(message, operation="aggregate")
                inference = dict(resolved.semantic_context.get("inventory_semantic_inference") or {})

                self.assertEqual(str(resolved.intent.template_id or ""), "inventory_material_critical_by_employee")
                self.assertEqual(str(resolved.normalized_filters.get("bodega") or ""), expected_bodega)
                self.assertEqual(str(inference.get("business_concept") or ""), "materiales_criticos_por_empleado")
                self.assertEqual(list(resolved.intent.group_by or []), expected_group_by)

    def test_equipos_cargados_a_movil_numerica_resuelve_serial_por_operador(self):
        resolved = self._resolve("equipos cargados a la movil 98562719", operation="detail")

        self.assertEqual(str(resolved.intent.template_id or ""), "inventory_serial_by_operational_holder")
        self.assertEqual(str(resolved.normalized_filters.get("cedula") or ""), "98562719")

    def test_consumo_vs_facturacion_solo_sql_para_operacion_hfc(self):
        cases = [
            "consumo vs facturacion operacion_hfc",
            "comparativo de consumo tecnico contra facturacion hfc",
        ]

        for message in cases:
            with self.subTest(message=message):
                resolved = self._resolve(message, operation="aggregate")
                trace = dict(((resolved.semantic_context.get("resolved_semantic") or {}).get("binding_trace") or {}))

                self.assertEqual(str(resolved.intent.template_id or ""), "inventory_consumption_billing_operacion_hfc")
                self.assertEqual(str(resolved.normalized_filters.get("bodega") or ""), "operacion_hfc")
                self.assertEqual(str(trace.get("source") or ""), "capability_pack")
                self.assertFalse(bool(trace.get("legacy_mapping_used")))
                self.assertFalse(bool(trace.get("fallback_used")))

    def test_equipos_por_estado_usa_saldo_serializado_validado(self):
        cases = [("equipos por estado", ["estado"])]

        for message, expected_group_by in cases:
            with self.subTest(message=message):
                resolved = self._resolve(message, operation="aggregate")
                trace = dict(((resolved.semantic_context.get("resolved_semantic") or {}).get("binding_trace") or {}))

                self.assertEqual(str(resolved.intent.template_id or ""), "inventory_serial_stock_by_dimension")
                self.assertEqual(list(resolved.intent.group_by or []), expected_group_by)
                self.assertNotIn("inventario_stock_pendiente_validacion_db_ai_dictionary", list(resolved.warnings or []))
                self.assertEqual(str(trace.get("source") or ""), "capability_pack")
                self.assertFalse(bool(trace.get("legacy_mapping_used")))
                self.assertFalse(bool(trace.get("fallback_used")))

    def test_trace_de_cobertura_del_pack_queda_publicada_en_binding_trace(self):
        resolved = self._resolve("muÃ©strame lo que tiene el mÃ³vil TIRAN224", operation="stock_balance")

        trace = dict(((resolved.semantic_context.get("resolved_semantic") or {}).get("binding_trace") or {}))
        self.assertEqual(float(trace.get("capability_pack_coverage") or 0.0), 1.0)
        self.assertGreater(int(trace.get("templates_pack_driven_count") or 0), 0)
        self.assertEqual(int(trace.get("templates_legacy_allowed_count") or 0), 0)
        self.assertEqual(list(trace.get("templates_missing_selection_rules") or []), [])

    def test_saldo_actual_de_cedula_no_inventa_responsable(self):
        resolved = self._resolve("saldo actual de la cÃ©dula 123456789", operation="aggregate")

        self.assertEqual(str(resolved.normalized_filters.get("cedula") or ""), "123456789")
        self.assertNotIn("cedula_o_responsable_no_validado_en_dictionary", list(resolved.warnings or []))

    def test_casos_nuevos_de_semantica_inventario_logistica(self):
        cases = [
            {
                "message": "historial completo del codigo ABC",
                "intent": "movement_history",
                "business_concept": "historial_movimientos_completo",
                "runtime_flow": "sql_assisted",
            },
            {
                "message": "kardex consolidado del material ABC",
                "intent": "movement_history",
                "business_concept": "kardex_consolidado",
                "runtime_flow": "sql_assisted",
            },
            {
                "message": "historial de consumos tecnicos y facturacion",
                "intent": "reconciliation_query",
                "business_concept": "consumo_vs_facturacion",
                "runtime_flow": "external_source_pending",
                "requires_external_source": True,
            },
            {
                "message": "comparativo ingreso stock bodega movil facturacion",
                "intent": "reconciliation_query",
                "business_concept": "conciliacion_logistica",
                "runtime_flow": "semantic_report",
                "implementation_status": "semantic_limitation_only",
            },
            {
                "message": "cruce saldos SAP contra kardex consumo",
                "intent": "external_reconciliation_query",
                "business_concept": "conciliacion_sap_kardex",
                "runtime_flow": "external_source_pending",
                "requires_external_source": True,
            },
            {
                "message": "generar acta de traslado interno",
                "intent": "document_generation",
                "business_concept": "acta_logistica",
                "runtime_flow": "document_generation_pending",
            },
            {
                "message": "promedios y CPEs proyecto ERI",
                "intent": "report_generation",
                "business_concept": "promedios_cpe_eri",
                "runtime_flow": "semantic_report",
                "missing_metadata": "cpe",
            },
            {
                "message": "consolidado de kardex y log",
                "intent": "movement_history",
                "business_concept": "log_consolidado",
                "runtime_flow": "sql_assisted",
            },
            {
                "message": "ingresos de compras con notificacion a logistica",
                "intent": "notification_query",
                "business_concept": "ingreso_compras_logistica",
                "runtime_flow": "external_source_pending",
                "requires_external_source": True,
            },
            {
                "message": "entrega consumo tecnico facturacion",
                "intent": "reconciliation_query",
                "business_concept": "entrega_consumo_facturacion",
                "runtime_flow": "external_source_pending",
            },
            {
                "message": "distribucion y asignacion por tecnico",
                "intent": "assignment_distribution_query",
                "business_concept": "distribucion_asignacion",
                "runtime_flow": "semantic_report",
                "implementation_status": "pending_db_validation",
            },
            {
                "message": "generar SPA de ingreso",
                "intent": "document_generation",
                "business_concept": "documento_spa",
                "runtime_flow": "document_generation_pending",
            },
            {
                "message": "reporte de saldos a las areas",
                "intent": "report_generation",
                "business_concept": "reporte_saldos_area",
                "runtime_flow": "semantic_report",
            },
            {
                "message": "alerta ferretero para compras y directores",
                "intent": "alert_query",
                "business_concept": "alerta_ferretero_compras",
                "runtime_flow": "semantic_report",
                "requires_threshold_metadata": True,
            },
        ]

        for case in cases:
            with self.subTest(message=case["message"]):
                resolved = self._resolve(case["message"], operation="aggregate")
                inference = dict(resolved.semantic_context.get("inventory_semantic_inference") or {})

                self.assertEqual(str(inference.get("intent") or ""), str(case["intent"]))
                self.assertEqual(str(inference.get("business_concept") or ""), str(case["business_concept"]))
                self.assertEqual(
                    str(((resolved.semantic_context.get("resolved_semantic") or {}).get("runtime_flow_hint") or "")),
                    str(case["runtime_flow"]),
                )
                if "requires_external_source" in case:
                    self.assertEqual(bool(inference.get("requires_external_source")), bool(case["requires_external_source"]))
                if "requires_business_validation" in case:
                    self.assertEqual(
                        bool(inference.get("requires_business_validation")),
                        bool(case["requires_business_validation"]),
                    )
                if "missing_metadata" in case:
                    self.assertIn(str(case["missing_metadata"]), list(inference.get("missing_metadata") or []))
                if "implementation_status" in case:
                    self.assertEqual(
                        str(inference.get("implementation_status") or ""),
                        str(case["implementation_status"]),
                    )
                if "requires_threshold_metadata" in case:
                    self.assertEqual(
                        bool(inference.get("requires_threshold_metadata")),
                        bool(case["requires_threshold_metadata"]),
                    )


class InventarioIntentArbitrationTests(SimpleTestCase):
    @staticmethod
    def _service() -> IntentArbitrationService:
        with patch.dict("os.environ", {"IA_DEV_USE_OPENAI_INTENT_ARBITRATION": "0"}, clear=False):
            return IntentArbitrationService()

    def test_arbitration_exposes_inventory_semantics(self):
        service = self._service()

        result = service.arbitrate(
            original_question="trazabilidad del serial ABC123",
            candidate_domain="inventario_logistica",
            heuristic_intent={"intent": "general_question", "domain": "inventario_logistica", "confidence": 0.42},
            llm_intent=StructuredQueryIntent(
                raw_query="trazabilidad del serial ABC123",
                domain_code="inventario_logistica",
                operation="trace",
                template_id="inventory_traceability_by_serial",
                confidence=0.88,
                source="rules",
            ),
            candidate_capabilities=[],
            ai_dictionary_context={
                "fields": [
                    {"logical_name": "serial", "table_name": "logistica_base_seriales"},
                    {"logical_name": "codigo", "table_name": "logistica_base_seriales"},
                ],
                "relations": [{"nombre_relacion": "serial_asociado_to_serial_base"}],
                "rules": [],
                "synonyms": [],
            },
            action_risk={"level": "low"},
            knowledge_governance_signals={"explicit_change_request": False, "explicit_apply_request": False},
        )

        self.assertEqual(str(result.get("final_intent") or ""), "analytics_query")
        self.assertEqual(str(result.get("candidate_domain") or ""), "inventario_logistica")
        self.assertEqual(str(result.get("intent") or ""), "traceability_query")
        self.assertTrue(bool(result.get("should_use_sql_assisted")))


class EmployeeIdentifierServiceTests(SimpleTestCase):
    def test_extract_movil_identifier_descarta_prefijos_semanticos_genericos(self):
        self.assertEqual(
            EmployeeIdentifierService.extract_movil_identifier("información empleado 98672304"),
            "",
        )

    def test_extract_movil_identifier_conserva_movil_operativa_real(self):
        self.assertEqual(
            EmployeeIdentifierService.extract_movil_identifier("información de TIRAN462"),
            "TIRAN462",
        )
