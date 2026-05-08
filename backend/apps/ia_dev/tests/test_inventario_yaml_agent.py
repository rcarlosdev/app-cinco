from __future__ import annotations

from django.test import SimpleTestCase

from apps.ia_dev.domains.inventario_logistica.yaml_agent_loader import (
    get_examples_as_query_patterns,
    get_runtime_domain_code,
    load_inventory_agent_yaml,
    validate_yaml_integrity,
)


class InventarioYamlAgentTests(SimpleTestCase):
    def test_inventario_materiales_yaml_carga_correctamente(self):
        config = load_inventory_agent_yaml()

        self.assertEqual(str(((config.get("agent") or {}).get("code") or "")), "inventario_materiales_agent")
        self.assertEqual(str(((config.get("business_domain") or {}).get("code") or "")), "inventario_materiales")
        self.assertEqual(str(get_runtime_domain_code(config) or ""), "inventario_logistica")
        self.assertTrue(bool(dict(config.get("tables") or {})))
        self.assertTrue(bool(list(config.get("examples") or [])))

    def test_validate_yaml_integrity_passes_for_current_blueprint(self):
        config = load_inventory_agent_yaml()

        result = validate_yaml_integrity(config)

        self.assertTrue(bool(result.get("ok")))
        self.assertEqual(str(result.get("status") or ""), "passed")

    def test_examples_are_exposed_as_query_patterns(self):
        examples = get_examples_as_query_patterns(load_inventory_agent_yaml())

        self.assertGreater(len(examples), 0)
        self.assertTrue(all(str(item.get("id") or "").strip() for item in examples))
        self.assertTrue(all(str((item.get("expected") or {}).get("intent") or "").strip() for item in examples))

    def test_yaml_expone_capacidades_semanticas_nuevas(self):
        config = load_inventory_agent_yaml()

        concepts = dict(config.get("business_concepts") or {})
        rules = dict(config.get("business_rules") or {})
        dimensions = dict(config.get("groupable_dimensions") or {})
        intents = dict(config.get("intent_taxonomy") or {})
        external_sources = dict(config.get("external_sources") or {})

        for concept_name in (
            "historial_movimientos_completo",
            "kardex_consolidado",
            "log_consolidado",
            "consumo_tecnico",
            "facturacion_materiales",
            "consumo_vs_facturacion",
            "conciliacion_logistica",
            "conciliacion_sap_kardex",
            "acta_logistica",
            "documento_spa",
            "promedios_cpe_eri",
            "ingreso_compras_logistica",
            "entrega_consumo_facturacion",
            "distribucion_asignacion",
            "reporte_saldos_area",
            "alerta_ferretero_compras",
        ):
            self.assertIn(concept_name, concepts)

        for rule_name in (
            "consolidated_kardex_rule",
            "stock_balance_rule",
            "ingreso_stock_movil_facturacion_rule",
            "consumo_tecnico_facturacion_rule",
            "sap_kardex_reconciliation_rule",
            "document_generation_rule",
            "purchasing_arrival_notification_rule",
            "ferretero_purchase_alert_rule",
            "area_balance_report_rule",
        ):
            self.assertIn(rule_name, rules)

        for dimension_name in (
            "proyecto",
            "area",
            "tecnico",
            "cedula",
            "proveedor",
            "compra",
            "factura",
            "documento",
            "tipo_movimiento",
            "origen",
            "destino",
        ):
            self.assertIn(dimension_name, dimensions)

        for intent_name in (
            "report_generation",
            "reconciliation_query",
            "document_generation",
            "alert_query",
            "notification_query",
            "assignment_distribution_query",
            "external_reconciliation_query",
        ):
            self.assertIn(intent_name, intents)

        self.assertEqual(str((external_sources.get("SAP") or {}).get("status") or ""), "pending_integration")
        self.assertEqual(str((external_sources.get("Compras") or {}).get("status") or ""), "pending_integration")

    def test_yaml_examples_cubren_los_nuevos_casos(self):
        examples = {str(item.get("id") or ""): dict(item.get("expected") or {}) for item in get_examples_as_query_patterns(load_inventory_agent_yaml())}

        self.assertEqual(str((examples.get("inv_011") or {}).get("business_concept") or ""), "historial_movimientos_completo")
        self.assertEqual(str((examples.get("inv_013") or {}).get("business_concept") or ""), "kardex_consolidado")
        self.assertEqual(str((examples.get("inv_016") or {}).get("expected_runtime_flow") or ""), "external_source_pending")
        self.assertEqual(str((examples.get("inv_017") or {}).get("expected_runtime_flow") or ""), "document_generation_pending")
        self.assertEqual(str((examples.get("inv_022") or {}).get("implementation_status") or ""), "pending_db_validation")
        self.assertTrue(bool((examples.get("inv_025") or {}).get("requires_threshold_metadata")))
