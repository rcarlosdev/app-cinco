from __future__ import annotations

from unittest.mock import patch

from django.test import SimpleTestCase

from apps.ia_dev.application.context.run_context import RunContext
from apps.ia_dev.application.contracts.query_intelligence_contracts import (
    ResolvedQuerySpec,
    StructuredQueryIntent,
)
from apps.ia_dev.application.semantic.query_execution_planner import QueryExecutionPlanner
from apps.ia_dev.domains.inventario_logistica.semantic_inventory_resolver import (
    InventorySemanticResolver,
)


def _contexto_inventario() -> dict:
    def field(table_name, logical_name, column_name, *, metric=False, group=False, date=False, identifier=False, filterable=True):
        return {
            "table_name": table_name,
            "campo_logico": logical_name,
            "column_name": column_name,
            "es_filtro": filterable,
            "es_group_by": group,
            "es_metrica": metric,
            "is_date": date,
            "is_identifier": identifier,
        }

    fields = [
        field("base_codigos", "codigo", "codigo", group=True),
        field("base_codigos", "descripcion", "descripcion", group=True),
        field("base_codigos", "tipo", "tipo", group=True),
        field("base_codigo_seriales", "codigo", "codigo", group=True),
        field("base_codigo_seriales", "descripcion", "descripcion", group=True),
        field("base_codigo_seriales", "familia", "familia", group=True),
        field("logistica_base_seriales", "serial", "numero_serial", identifier=True),
        field("logistica_base_seriales", "codigo", "codigo"),
        field("logistica_base_seriales", "estado", "estado", group=True),
        field("logistica_base_seriales", "ubicacion", "ubicacion_bodega", group=True),
        field("logistica_base_seriales", "bodega", "bodega", group=True),
        field("logistica_base_seriales", "tecnico_cedula", "cedula", group=True),
        field("logistica_base_seriales", "fecha", "fecha", date=True),
        field("logistica_seriales_asociados", "serial", "numero_serial"),
        field("logistica_seriales_asociados", "bodega_salida", "bodega", group=True),
        field("logistica_seriales_asociados", "estado", "estado", group=True),
        field("logistica_seriales_asociados", "fecha", "fecha", date=True),
        field("a_promedios_consumo", "codigo", "codigo"),
        field("a_promedios_consumo", "codigo_facturacion", "codigo_facturacion"),
        field("a_promedios_consumo", "promedio", "promedio", metric=True),
        field("facturacion_facturado_wfm", "idorden_de_trabajo", "idorden_de_trabajo"),
        field("facturacion_facturado_wfm", "codigo", "codigo"),
        field("facturacion_facturado_wfm", "cantidad_actividad", "cantidad_actividad", metric=True),
    ]
    for table_name in (
        "logistica_movimientos_entrada",
        "logistica_movimientos_entrega",
        "logistica_movimientos_devolucion",
        "logistica_movimientos_cobro",
        "logistica_movimientos_consumo",
        "logistica_movimientos_traslado",
    ):
        fields.extend(
            [
                field(table_name, "id", "id", identifier=True),
                field(table_name, "codigo", "codigo", group=True),
                field(table_name, "cantidad", "cantidad", metric=True),
                field(table_name, "fecha", "f_consumo", date=True),
                field(table_name, "bodega", "bodega", group=True),
            ]
        )
    fields.extend(
        [
            field("logistica_movimientos_entrada", "estado", "estado", group=True),
            field("logistica_movimientos_entrada", "movimiento", "movimiento", group=True),
            field("logistica_movimientos_consumo", "estado", "estado", group=True),
            field("logistica_movimientos_consumo", "orden_trabajo", "orden_trabajo", group=True),
            field("logistica_movimientos_consumo", "tipo", "tipo", group=True),
            field("logistica_movimientos_traslado", "movimiento", "movimiento", group=True),
            field("logistica_movimientos_traslado", "estado", "estado", group=True),
        ]
    )
    return {
        "domain_status": "partial",
        "supports_sql_assisted": True,
        "source_of_truth": {"pilot_sql_assisted_enabled": True},
        "tables": [
            {"table_name": "logistica_base_seriales", "table_fqn": "logistica_base_seriales", "es_principal": True},
            {"table_name": "base_codigos", "table_fqn": "base_codigos"},
            {"table_name": "base_codigo_seriales", "table_fqn": "base_codigo_seriales"},
            {"table_name": "logistica_movimientos_consumo", "table_fqn": "logistica_movimientos_consumo"},
            {"table_name": "logistica_movimientos_traslado", "table_fqn": "logistica_movimientos_traslado"},
            {"table_name": "logistica_movimientos_entrada", "table_fqn": "logistica_movimientos_entrada"},
            {"table_name": "logistica_movimientos_entrega", "table_fqn": "logistica_movimientos_entrega"},
            {"table_name": "logistica_movimientos_devolucion", "table_fqn": "logistica_movimientos_devolucion"},
            {"table_name": "logistica_movimientos_cobro", "table_fqn": "logistica_movimientos_cobro"},
            {"table_name": "logistica_seriales_asociados", "table_fqn": "logistica_seriales_asociados"},
            {"table_name": "a_promedios_consumo", "table_fqn": "a_promedios_consumo"},
            {"table_name": "facturacion_facturado_wfm", "table_fqn": "bd_c3nc4s1s.facturacion_facturado_wfm"},
        ],
        "columns": [
            {
                "table_name": item["table_name"],
                "table_fqn": "bd_c3nc4s1s.facturacion_facturado_wfm" if item["table_name"] == "facturacion_facturado_wfm" else item["table_name"],
                "column_name": item["column_name"],
                "nombre_columna_logico": item["campo_logico"],
            }
            for item in fields
        ],
        "column_profiles": [
            {
                "table_name": item["table_name"],
                "table_fqn": "bd_c3nc4s1s.facturacion_facturado_wfm" if item["table_name"] == "facturacion_facturado_wfm" else item["table_name"],
                "logical_name": item["campo_logico"],
                "column_name": item["column_name"],
                "supports_filter": bool(item.get("es_filtro")),
                "supports_group_by": bool(item.get("es_group_by")),
                "supports_metric": bool(item.get("es_metrica")),
                "supports_dimension": bool(item.get("es_group_by")),
                "is_date": bool(item.get("is_date")),
                "is_identifier": bool(item.get("is_identifier")),
            }
            for item in fields
        ],
        "dictionary": {"fields": fields, "relations": [], "rules": []},
        "allowed_tables": [
            "logistica_base_seriales",
            "base_codigos",
            "base_codigo_seriales",
            "logistica_movimientos_consumo",
            "logistica_movimientos_traslado",
            "logistica_movimientos_entrada",
            "logistica_movimientos_entrega",
            "logistica_movimientos_devolucion",
            "logistica_movimientos_cobro",
            "logistica_seriales_asociados",
            "a_promedios_consumo",
            "bd_c3nc4s1s.facturacion_facturado_wfm",
        ],
        "allowed_columns": sorted({str(item["column_name"]) for item in fields}),
        "aliases": {},
    }


class InventarioRuntimeSqlAlignmentTests(SimpleTestCase):
    def setUp(self):
        self.planner = QueryExecutionPlanner()
        self.resolver = InventorySemanticResolver()
        self.run_context = RunContext.create(message="demo inventario", session_id="inv-test")
        self.semantic_context = _contexto_inventario()

    def _plan_for(self, message: str) -> ResolvedQuerySpec:
        intent = StructuredQueryIntent(
            raw_query=message,
            domain_code="inventario_logistica",
            operation="detail",
            template_id="",
            confidence=0.9,
        )
        return self.resolver.resolve_query(
            message=message,
            intent=intent,
            semantic_context=self.semantic_context,
        )

    def test_planner_routes_traceability_to_sql_assisted(self):
        resolved = self._plan_for("trazabilidad del serial ABC123")

        with patch.dict(
            "os.environ",
            {
                "IA_DEV_QUERY_SQL_ASSISTED_ENABLED": "1",
                "IA_DEV_QUERY_INTELLIGENCE_ENABLED": "1",
            },
            clear=False,
        ):
            plan = self.planner.plan(run_context=self.run_context, resolved_query=resolved)

        self.assertEqual(plan.strategy, "sql_assisted")
        self.assertEqual(str((plan.metadata or {}).get("compiler") or ""), "inventory_semantic_sql")
        self.assertEqual(str((plan.metadata or {}).get("db_alias") or ""), "logistica_cinco")

    def test_planner_builds_material_stock_after_db_validation(self):
        resolved = self._plan_for("stock de materiales por bodega")

        with patch.dict(
            "os.environ",
            {
                "IA_DEV_QUERY_SQL_ASSISTED_ENABLED": "1",
                "IA_DEV_QUERY_INTELLIGENCE_ENABLED": "1",
            },
            clear=False,
        ):
            plan = self.planner.plan(run_context=self.run_context, resolved_query=resolved)

        self.assertEqual(plan.strategy, "sql_assisted")
        self.assertEqual(str(plan.reason or ""), "inventory_material_stock_by_warehouse")
        self.assertIn("logistica_movimientos_entrada", str(plan.sql_query or ""))
        self.assertIn("logistica_movimientos_entrega", str(plan.sql_query or ""))
        self.assertIn("logistica_movimientos_devolucion", str(plan.sql_query or ""))
        self.assertIn("logistica_movimientos_cobro", str(plan.sql_query or ""))
        self.assertIn("logistica_movimientos_traslado", str(plan.sql_query or ""))
        self.assertIn("REGEXP", str(plan.sql_query or ""))
        self.assertNotIn("facturacion_facturado_wfm", str(plan.sql_query or ""))

    def test_saldo_bodega_operacion_hfc_routes_sql_assisted_with_filter(self):
        resolved = self._plan_for("saldo bodega operacion_hfc")

        with patch.dict(
            "os.environ",
            {
                "IA_DEV_QUERY_SQL_ASSISTED_ENABLED": "1",
                "IA_DEV_QUERY_INTELLIGENCE_ENABLED": "1",
            },
            clear=False,
        ):
            plan = self.planner.plan(run_context=self.run_context, resolved_query=resolved)

        self.assertEqual(str(resolved.normalized_filters.get("bodega") or ""), "operacion_hfc")
        self.assertEqual(str(resolved.intent.operation or ""), "stock_balance")
        self.assertEqual(str(resolved.intent.template_id or ""), "inventory_material_stock_by_warehouse")
        self.assertEqual(plan.strategy, "sql_assisted")
        self.assertEqual(str(plan.reason or ""), "inventory_material_stock_by_warehouse")
        self.assertEqual(str((plan.metadata or {}).get("analytics_router_decision") or ""), "join_aware_sql")
        self.assertEqual(dict((plan.metadata or {}).get("filters_applied") or {}).get("bodega"), "operacion_hfc")
        self.assertIn("WHERE mov.bodega = 'operacion_hfc'", str(plan.sql_query or ""))
        self.assertIn("logistica_movimientos_entrada", str(plan.sql_query or ""))
        self.assertIn("logistica_movimientos_entrega", str(plan.sql_query or ""))
        self.assertIn("logistica_movimientos_devolucion", str(plan.sql_query or ""))
        self.assertIn("logistica_movimientos_cobro", str(plan.sql_query or ""))
        self.assertIn("logistica_movimientos_traslado", str(plan.sql_query or ""))
        self.assertIn("REGEXP", str(plan.sql_query or ""))
        self.assertNotIn("facturacion_facturado_wfm", str(plan.sql_query or ""))
        self.assertNotIn("bodega_destino", str(plan.sql_query or ""))
        self.assertNotEqual(str((plan.metadata or {}).get("runtime_only_fallback_reason") or ""), "missing_dictionary_column")

    def test_inventory_stock_fallback_blocks_legacy_when_dictionary_is_incomplete(self):
        intent = StructuredQueryIntent(
            raw_query="saldo bodega operacion_hfc",
            domain_code="inventario_logistica",
            operation="stock_balance",
            template_id="inventory_material_stock_by_warehouse",
            filters={"movil": "operacion_hfc", "stock_scope": "bodega"},
            group_by=[],
            metrics=["count"],
            confidence=0.9,
        )
        resolved = ResolvedQuerySpec(
            intent=intent,
            semantic_context={
                "supports_sql_assisted": True,
                "tables": [{"table_name": "base_codigos", "table_fqn": "base_codigos"}],
                "column_profiles": [
                    {"table_name": "base_codigos", "logical_name": "codigo", "column_name": "codigo"},
                    {"table_name": "base_codigos", "logical_name": "descripcion", "column_name": "descripcion"},
                    {"table_name": "base_codigos", "logical_name": "tipo", "column_name": "tipo"},
                ],
                "dictionary": {"fields": [], "relations": []},
                "allowed_tables": ["base_codigos"],
                "allowed_columns": ["codigo", "descripcion", "tipo"],
            },
            normalized_filters={"movil": "operacion_hfc", "stock_scope": "bodega"},
            normalized_period={},
            mapped_columns={},
            warnings=[],
        )

        with patch.dict(
            "os.environ",
            {
                "IA_DEV_QUERY_SQL_ASSISTED_ENABLED": "1",
                "IA_DEV_QUERY_INTELLIGENCE_ENABLED": "1",
            },
            clear=False,
        ):
            plan = self.planner.plan(run_context=self.run_context, resolved_query=resolved)

        self.assertEqual(plan.strategy, "fallback")
        self.assertTrue(bool((plan.metadata or {}).get("blocked_legacy_fallback")))
        self.assertEqual(str((plan.metadata or {}).get("analytics_router_decision") or ""), "runtime_only_fallback")
        self.assertEqual(str((plan.metadata or {}).get("runtime_only_fallback_reason") or ""), "missing_dictionary_column")

    def test_planner_blocks_transfer_destination_when_physical_column_is_missing(self):
        resolved = self._plan_for("traslados por bodega destino")

        with patch.dict(
            "os.environ",
            {
                "IA_DEV_QUERY_SQL_ASSISTED_ENABLED": "1",
                "IA_DEV_QUERY_INTELLIGENCE_ENABLED": "1",
            },
            clear=False,
        ):
            plan = self.planner.plan(run_context=self.run_context, resolved_query=resolved)

        self.assertEqual(plan.strategy, "fallback")
        self.assertEqual(str(plan.reason or ""), "missing_dictionary_column")
        self.assertEqual(str((plan.metadata or {}).get("sql_reason") or ""), "inventory_transfer_destination_missing_physical_column")
        self.assertTrue(bool((plan.metadata or {}).get("blocked_legacy_fallback")))
        self.assertNotIn("bodega_destino", str(plan.sql_query or ""))

    def test_planner_builds_serial_stock_by_estado_after_db_validation(self):
        resolved = self._plan_for("equipos por estado")

        with patch.dict(
            "os.environ",
            {
                "IA_DEV_QUERY_SQL_ASSISTED_ENABLED": "1",
                "IA_DEV_QUERY_INTELLIGENCE_ENABLED": "1",
            },
            clear=False,
        ):
            plan = self.planner.plan(run_context=self.run_context, resolved_query=resolved)

        self.assertEqual(plan.strategy, "sql_assisted")
        self.assertEqual(str((plan.metadata or {}).get("metric_used") or ""), "serial_count")
        self.assertIn("COUNT(DISTINCT numero_serial)", str(plan.sql_query or ""))
        self.assertIn("GROUP BY estado", str(plan.sql_query or ""))

    def test_planner_builds_material_stock_general_without_internal_transfer_entry(self):
        resolved = self._plan_for("saldo general de materiales")

        with patch.dict(
            "os.environ",
            {
                "IA_DEV_QUERY_SQL_ASSISTED_ENABLED": "1",
                "IA_DEV_QUERY_INTELLIGENCE_ENABLED": "1",
            },
            clear=False,
        ):
            plan = self.planner.plan(run_context=self.run_context, resolved_query=resolved)

        self.assertEqual(plan.strategy, "sql_assisted")
        self.assertEqual(str(plan.reason or ""), "inventory_material_stock_balance")
        self.assertIn("traslados_otro_aliado", str(plan.sql_query or ""))
        self.assertIn("COALESCE(estado, '') <> 'traslado_bodega'", str(plan.sql_query or ""))
        self.assertNotIn("bodega_destino", str(plan.sql_query or ""))

    def test_planner_builds_material_mobile_stock(self):
        resolved = self._plan_for("saldo movil de materiales")

        with patch.dict(
            "os.environ",
            {
                "IA_DEV_QUERY_SQL_ASSISTED_ENABLED": "1",
                "IA_DEV_QUERY_INTELLIGENCE_ENABLED": "1",
            },
            clear=False,
        ):
            plan = self.planner.plan(run_context=self.run_context, resolved_query=resolved)

        self.assertEqual(plan.strategy, "sql_assisted")
        self.assertEqual(str(plan.reason or ""), "inventory_material_stock_mobile")
        self.assertIn("logistica_movimientos_consumo", str(plan.sql_query or ""))
        self.assertIn("saldo_movil", str(plan.sql_query or ""))
        self.assertNotIn("facturacion_facturado_wfm", str(plan.sql_query or ""))

    def test_saldo_empleado_routes_mobile_stock_capability(self):
        resolved = self._plan_for("saldo empleado 98672304")

        with patch.dict(
            "os.environ",
            {
                "IA_DEV_QUERY_SQL_ASSISTED_ENABLED": "1",
                "IA_DEV_QUERY_INTELLIGENCE_ENABLED": "1",
            },
            clear=False,
        ):
            plan = self.planner.plan(run_context=self.run_context, resolved_query=resolved)

        self.assertEqual(str(resolved.normalized_filters.get("cedula") or ""), "98672304")
        self.assertEqual(str(resolved.intent.template_id or ""), "inventory_material_stock_mobile")
        self.assertEqual(plan.strategy, "sql_assisted")
        self.assertEqual(str(plan.capability_id or ""), "inventory_stock_balance_by_mobile")
        self.assertIn("saldo_movil", str(plan.sql_query or ""))

    def test_planner_builds_transfer_warehouse_without_destination_column(self):
        resolved = self._plan_for("traslado bodega por codigo")

        with patch.dict(
            "os.environ",
            {
                "IA_DEV_QUERY_SQL_ASSISTED_ENABLED": "1",
                "IA_DEV_QUERY_INTELLIGENCE_ENABLED": "1",
            },
            clear=False,
        ):
            plan = self.planner.plan(run_context=self.run_context, resolved_query=resolved)

        self.assertEqual(plan.strategy, "sql_assisted")
        self.assertEqual(str(plan.reason or ""), "inventory_transfer_warehouse")
        self.assertIn("TRASLADO_BODEGA", str(plan.sql_query or ""))
        self.assertNotIn("bodega_destino", str(plan.sql_query or ""))

    def test_planner_builds_transfer_other_ally(self):
        resolved = self._plan_for("traslados a otro aliado")

        with patch.dict(
            "os.environ",
            {
                "IA_DEV_QUERY_SQL_ASSISTED_ENABLED": "1",
                "IA_DEV_QUERY_INTELLIGENCE_ENABLED": "1",
            },
            clear=False,
        ):
            plan = self.planner.plan(run_context=self.run_context, resolved_query=resolved)

        self.assertEqual(plan.strategy, "sql_assisted")
        self.assertEqual(str(plan.reason or ""), "inventory_transfer_other_ally")
        self.assertIn("TRASLADOS_OTRO_ALIADO", str(plan.sql_query or ""))

    def test_planner_builds_consumption_vs_billing_only_operacion_hfc(self):
        resolved = self._plan_for("consumo vs facturacion operacion_hfc")

        with patch.dict(
            "os.environ",
            {
                "IA_DEV_QUERY_SQL_ASSISTED_ENABLED": "1",
                "IA_DEV_QUERY_INTELLIGENCE_ENABLED": "1",
            },
            clear=False,
        ):
            plan = self.planner.plan(run_context=self.run_context, resolved_query=resolved)

        self.assertEqual(plan.strategy, "sql_assisted")
        self.assertEqual(str(plan.reason or ""), "inventory_consumption_billing_operacion_hfc")
        self.assertIn("operacion_hfc", str(plan.sql_query or ""))
        self.assertIn("bd_c3nc4s1s.facturacion_facturado_wfm", str(plan.sql_query or ""))
        self.assertEqual(list((plan.metadata or {}).get("not_inventory_discount") or []), ["facturacion_facturado_wfm"])

    def test_planner_blocks_stock_when_confirmed_column_is_missing(self):
        resolved = self._plan_for("saldo general de materiales")
        resolved.semantic_context["column_profiles"] = [
            item for item in list(resolved.semantic_context.get("column_profiles") or [])
            if not (item.get("table_name") == "logistica_movimientos_entrada" and item.get("column_name") == "bodega")
        ]
        resolved.semantic_context["columns"] = [
            item for item in list(resolved.semantic_context.get("columns") or [])
            if not (item.get("table_name") == "logistica_movimientos_entrada" and item.get("column_name") == "bodega")
        ]
        resolved.semantic_context["dictionary"]["fields"] = [
            item for item in list((resolved.semantic_context.get("dictionary") or {}).get("fields") or [])
            if not (item.get("table_name") == "logistica_movimientos_entrada" and item.get("column_name") == "bodega")
        ]
        with patch.dict(
            "os.environ",
            {
                "IA_DEV_QUERY_SQL_ASSISTED_ENABLED": "1",
                "IA_DEV_QUERY_INTELLIGENCE_ENABLED": "1",
            },
            clear=False,
        ):
            plan = self.planner.plan(run_context=self.run_context, resolved_query=resolved)

        self.assertEqual(plan.strategy, "fallback")
        self.assertEqual(str(plan.reason or ""), "missing_dictionary_column")
        self.assertTrue(bool((plan.metadata or {}).get("blocked_legacy_fallback")))
        self.assertIn("inventory", str((plan.metadata or {}).get("sql_reason") or ""))

    def test_policy_rejects_write_sql_for_inventory(self):
        decision = self.planner.query_policy.validate_sql_query(
            query="UPDATE logistica_movimientos_entrada SET cantidad = 0 LIMIT 1",
            allowed_tables=list(self.semantic_context.get("allowed_tables") or []),
            allowed_columns=list(self.semantic_context.get("allowed_columns") or []),
            max_limit=1000,
        )

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, "sql_must_start_with_select")
