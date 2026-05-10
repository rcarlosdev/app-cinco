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

    def _resolve(self, message: str, operation: str = "detail"):
        return self.resolver.resolve_query(
            message=message,
            intent=StructuredQueryIntent(
                raw_query=message,
                domain_code="inventario_logistica",
                operation=operation,
                template_id="",
                confidence=0.8,
            ),
            semantic_context={},
        )

    def test_trazabilidad_del_serial(self):
        resolved = self._resolve("trazabilidad del serial ABC123")

        self.assertEqual(str(resolved.intent.domain_code or ""), "inventario_logistica")
        self.assertEqual(str(resolved.intent.template_id or ""), "inventory_traceability_by_serial")
        self.assertEqual(str(resolved.normalized_filters.get("serial") or ""), "ABC123")
        self.assertEqual(
            str(((resolved.semantic_context.get("inventory_semantic_inference") or {}).get("intent") or "")),
            "traceability_query",
        )

    def test_consumo_movil_sin_validar(self):
        resolved = self._resolve("equipos serializados en consumo movil sin validar")

        inference = dict(resolved.semantic_context.get("inventory_semantic_inference") or {})
        self.assertEqual(str(inference.get("intent") or ""), "risk_detection")
        self.assertEqual(str(inference.get("business_concept") or ""), "consumo_movil_sin_validar")
        self.assertEqual(str(resolved.intent.template_id or ""), "inventory_risk_consumo_movil_sin_validar")

    def test_materiales_mas_consumidos_en_mayo(self):
        resolved = self._resolve("materiales mas consumidos en mayo", operation="aggregate")

        self.assertEqual(str(resolved.intent.template_id or ""), "inventory_consumption_top")
        self.assertIn("material", list(resolved.intent.group_by or []))
        self.assertEqual(str(resolved.normalized_filters.get("month") or ""), "5")

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

    def test_materiales_criticos_por_empleado_resuelve_template_dedicado(self):
        resolved = self._resolve(
            "materiales criticos por empleado en operacion_hfc cruzando saldo, cedula, movil y datos del empleado",
            operation="aggregate",
        )

        self.assertEqual(str(resolved.intent.template_id or ""), "inventory_material_critical_by_employee")
        self.assertEqual(str(resolved.normalized_filters.get("bodega") or ""), "operacion_hfc")

    def test_equipos_cargados_a_movil_numerica_resuelve_serial_por_operador(self):
        resolved = self._resolve("equipos cargados a la movil 98562719", operation="detail")

        self.assertEqual(str(resolved.intent.template_id or ""), "inventory_serial_by_operational_holder")
        self.assertEqual(str(resolved.normalized_filters.get("cedula") or ""), "98562719")

    def test_consumo_vs_facturacion_solo_sql_para_operacion_hfc(self):
        resolved = self._resolve("consumo vs facturacion operacion_hfc", operation="aggregate")

        self.assertEqual(str(resolved.intent.template_id or ""), "inventory_consumption_billing_operacion_hfc")
        self.assertEqual(str(resolved.normalized_filters.get("bodega") or ""), "operacion_hfc")

    def test_equipos_por_estado_usa_saldo_serializado_validado(self):
        resolved = self._resolve("equipos por estado", operation="aggregate")

        self.assertEqual(str(resolved.intent.template_id or ""), "inventory_serial_stock_by_dimension")
        self.assertEqual(list(resolved.intent.group_by or []), ["estado"])
        self.assertNotIn("inventario_stock_pendiente_validacion_db_ai_dictionary", list(resolved.warnings or []))

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
