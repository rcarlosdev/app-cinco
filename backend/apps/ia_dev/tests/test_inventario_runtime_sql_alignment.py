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
        field("cinco_base_de_personal", "cedula", "cedula", group=True, identifier=True),
        field("cinco_base_de_personal", "nombre", "nombre"),
        field("cinco_base_de_personal", "apellido", "apellido"),
        field("cinco_base_de_personal", "movil", "movil", group=True),
        field("cinco_base_de_personal", "area", "area", group=True),
        field("cinco_base_de_personal", "carpeta", "carpeta", group=True),
        field("cinco_base_de_personal", "cargo", "cargo", group=True),
        field("cinco_base_de_personal", "tipo_labor", "tipo_labor", group=True),
        field("cinco_base_de_personal", "estado", "estado", group=True),
        field("cinco_base_de_personal", "codigo_sap", "codigo_sap"),
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
        field("logistica_base_seriales", "fecha_ingreso", "fecha_ingreso", date=True),
        field("logistica_base_seriales", "ticket", "ticket"),
        field("logistica_base_seriales", "fecha_edit", "fecha_edit", date=True),
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
                field(table_name, "cedula", "cedula", group=True),
                field(table_name, "movil", "movil", group=True),
            ]
        )
    fields.extend(
        [
            field("logistica_movimientos_entrada", "estado", "estado", group=True),
            field("logistica_movimientos_entrada", "movimiento", "movimiento", group=True),
            field("logistica_movimientos_entrega", "cedula", "cedula", group=True),
            field("logistica_movimientos_entrega", "movil", "movil", group=True),
            field("logistica_movimientos_devolucion", "cedula", "cedula", group=True),
            field("logistica_movimientos_consumo", "estado", "estado", group=True),
            field("logistica_movimientos_consumo", "orden_trabajo", "orden_trabajo", group=True),
            field("logistica_movimientos_consumo", "tipo", "tipo", group=True),
            field("logistica_movimientos_consumo", "movil", "movil", group=True),
            field("logistica_movimientos_consumo", "cedula", "cedula", group=True),
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
            {"table_name": "cinco_base_de_personal", "table_fqn": "bd_c3nc4s1s.cinco_base_de_personal"},
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
                "table_fqn": (
                    "bd_c3nc4s1s.facturacion_facturado_wfm"
                    if item["table_name"] == "facturacion_facturado_wfm"
                    else ("bd_c3nc4s1s.cinco_base_de_personal" if item["table_name"] == "cinco_base_de_personal" else item["table_name"])
                ),
                "column_name": item["column_name"],
                "nombre_columna_logico": item["campo_logico"],
            }
            for item in fields
        ],
        "column_profiles": [
            {
                "table_name": item["table_name"],
                "table_fqn": (
                    "bd_c3nc4s1s.facturacion_facturado_wfm"
                    if item["table_name"] == "facturacion_facturado_wfm"
                    else ("bd_c3nc4s1s.cinco_base_de_personal" if item["table_name"] == "cinco_base_de_personal" else item["table_name"])
                ),
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
        "dictionary": {
            "fields": fields,
            "relations": [
                {"join_sql": "logistica_movimientos_entrega.cedula = cinco_base_de_personal.cedula"},
                {"join_sql": "logistica_movimientos_entrega.movil = cinco_base_de_personal.movil"},
                {"join_sql": "logistica_movimientos_consumo.cedula = cinco_base_de_personal.cedula"},
                {"join_sql": "logistica_movimientos_consumo.movil = cinco_base_de_personal.movil"},
                {"join_sql": "logistica_movimientos_devolucion.cedula = cinco_base_de_personal.cedula"},
                {"join_sql": "logistica_movimientos_devolucion.movil = cinco_base_de_personal.movil"},
                {"join_sql": "logistica_movimientos_cobro.cedula = cinco_base_de_personal.cedula"},
                {"join_sql": "logistica_movimientos_cobro.movil = cinco_base_de_personal.movil"},
            ],
            "rules": [],
        },
        "allowed_tables": [
            "logistica_base_seriales",
            "base_codigos",
            "bd_c3nc4s1s.cinco_base_de_personal",
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


def _contexto_inventario_sin_movil_fisico() -> dict:
    context = _contexto_inventario()
    target_tables = {
        "logistica_movimientos_entrega",
        "logistica_movimientos_consumo",
        "logistica_movimientos_cobro",
        "logistica_movimientos_devolucion",
    }
    filtered_fields = []
    for item in list(((context.get("dictionary") or {}).get("fields") or [])):
        if str(item.get("table_name") or "") in target_tables and str(item.get("column_name") or "") == "movil":
            continue
        filtered_fields.append(item)
    context["dictionary"]["fields"] = filtered_fields

    filtered_columns = []
    filtered_profiles = []
    for item in list(context.get("columns") or []):
        if str(item.get("table_name") or "") in target_tables and str(item.get("column_name") or "") == "movil":
            continue
        filtered_columns.append(item)
    for item in list(context.get("column_profiles") or []):
        if str(item.get("table_name") or "") in target_tables and str(item.get("column_name") or "") == "movil":
            continue
        filtered_profiles.append(item)
    context["columns"] = filtered_columns
    context["column_profiles"] = filtered_profiles
    return context


class InventarioRuntimeSqlAlignmentTests(SimpleTestCase):
    def setUp(self):
        self.planner = QueryExecutionPlanner()
        self.resolver = InventorySemanticResolver()
        self.resolver.semantic_plan_builder.memory_service.list_memory_snapshot = lambda: [
            {"memory_key": "inventory.semantic.rule.kardex"},
            {"memory_key": "inventory.semantic.rule.saldo_inventario"},
        ]
        self.resolver.semantic_plan_builder.memory_service.ensure_confirmed_rules = lambda: {
            "saved_keys": ["inventory.semantic.rule.kardex"],
            "error_count": 0,
            "errors": [],
        }
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
        self.assertEqual(
            str((((plan.metadata or {}).get("semantic_trace") or {}).get("semantic_plan") or {}).get("candidate_capability") or ""),
            "inventory_traceability_by_serial",
        )

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
        self.assertEqual(
            str((((plan.metadata or {}).get("semantic_trace") or {}).get("semantic_plan") or {}).get("intent") or ""),
            "stock_balance",
        )
        self.assertIn(
            "ai_dictionary.dd_campos",
            list((((plan.metadata or {}).get("semantic_trace") or {}).get("consulted_sources") or [])),
        )
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
        self.assertEqual(
            str(((((plan.metadata or {}).get("semantic_trace") or {}).get("semantic_plan") or {}).get("entity") or {}).get("field") or ""),
            "bodega",
        )
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

    def test_mobile_stock_uses_personal_bridge_when_movement_tables_lack_movil(self):
        self.semantic_context = _contexto_inventario_sin_movil_fisico()
        resolved = self._plan_for("inventario de la cuadrilla TIRAN224")

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
        self.assertIn("EXISTS (SELECT 1 FROM bd_c3nc4s1s.cinco_base_de_personal AS p", str(plan.sql_query or ""))
        self.assertIn("p.movil = 'TIRAN224'", str(plan.sql_query or ""))
        self.assertEqual(str((plan.metadata or {}).get("analytics_router_decision") or ""), "join_aware_sql")

    def test_serial_holder_detail_does_not_require_movil_on_serial_base(self):
        resolved = self._plan_for("equipos cargados a la movil 98562719")

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
        self.assertEqual(str(plan.reason or ""), "inventory_serial_by_operational_holder")
        self.assertIn("s.cedula = '98562719'", str(plan.sql_query or ""))
        self.assertNotIn("s.movil AS movil", str(plan.sql_query or ""))

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

    def test_planner_aplica_filtro_operativo_en_stock_por_cuadrilla(self):
        resolved = self._plan_for("inventario de la cuadrilla TIRAN224")

        with patch.dict(
            "os.environ",
            {
                "IA_DEV_QUERY_SQL_ASSISTED_ENABLED": "1",
                "IA_DEV_QUERY_INTELLIGENCE_ENABLED": "1",
            },
            clear=False,
        ):
            plan = self.planner.plan(run_context=self.run_context, resolved_query=resolved)

        self.assertEqual(str(resolved.intent.template_id or ""), "inventory_material_stock_mobile")
        self.assertEqual(str(resolved.normalized_filters.get("movil") or ""), "TIRAN224")
        self.assertIn("TIRAN224", str(plan.sql_query or ""))
        self.assertIn("cinco_base_de_personal", str(plan.sql_query or ""))
        self.assertIn("estado_empleado", str(plan.sql_query or ""))

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
        self.assertIn("AS saldo", str(plan.sql_query or ""))
        self.assertIn("estado_empleado", str(plan.sql_query or ""))

    def test_materiales_del_tecnico_numeric_routes_mobile_stock_with_employee_join(self):
        resolved = self._plan_for("materiales del tecnico 1214730857 con datos del empleado")

        with patch.dict(
            "os.environ",
            {
                "IA_DEV_QUERY_SQL_ASSISTED_ENABLED": "1",
                "IA_DEV_QUERY_INTELLIGENCE_ENABLED": "1",
            },
            clear=False,
        ):
            plan = self.planner.plan(run_context=self.run_context, resolved_query=resolved)

        self.assertEqual(str(resolved.intent.template_id or ""), "inventory_material_stock_mobile")
        self.assertEqual(str(resolved.normalized_filters.get("cedula") or ""), "1214730857")
        self.assertIn("WHERE cedula = '1214730857'", str(plan.sql_query or ""))
        self.assertIn("FROM bd_c3nc4s1s.cinco_base_de_personal AS p WHERE p.cedula = '1214730857'", str(plan.sql_query or ""))
        self.assertIn("estado_empleado", str(plan.sql_query or ""))

    def test_kardex_del_tecnico_routes_employee_kardex_sql(self):
        resolved = self._plan_for("kardex del tecnico 5098747")

        with patch.dict(
            "os.environ",
            {
                "IA_DEV_QUERY_SQL_ASSISTED_ENABLED": "1",
                "IA_DEV_QUERY_INTELLIGENCE_ENABLED": "1",
            },
            clear=False,
        ):
            plan = self.planner.plan(run_context=self.run_context, resolved_query=resolved)

        self.assertEqual(str(resolved.intent.template_id or ""), "inventory_kardex_by_employee")
        self.assertEqual(str(resolved.normalized_filters.get("cedula") or ""), "5098747")
        self.assertEqual(plan.strategy, "sql_assisted")
        self.assertEqual(str(plan.capability_id or ""), "inventory_kardex_by_employee")
        self.assertIn("logistica_movimientos_entrega", str(plan.sql_query or ""))
        self.assertIn("logistica_movimientos_devolucion", str(plan.sql_query or ""))
        self.assertIn("logistica_movimientos_consumo", str(plan.sql_query or ""))
        self.assertIn("logistica_movimientos_cobro", str(plan.sql_query or ""))
        self.assertIn("PARTITION BY k.codigo, k.cedula", str(plan.sql_query or ""))
        self.assertIn("AS saldo_movimiento", str(plan.sql_query or ""))
        self.assertIn("AS tipo_movimiento", str(plan.sql_query or ""))
        self.assertNotIn("a_promedios_consumo", str(plan.sql_query or ""))
        self.assertEqual(str((plan.metadata or {}).get("balance_filter_policy") or ""), "include_positive_zero_negative")

    def test_kardex_del_empleado_routes_employee_kardex_sql(self):
        resolved = self._plan_for("kardex del empleado 5098747")

        with patch.dict(
            "os.environ",
            {
                "IA_DEV_QUERY_SQL_ASSISTED_ENABLED": "1",
                "IA_DEV_QUERY_INTELLIGENCE_ENABLED": "1",
            },
            clear=False,
        ):
            plan = self.planner.plan(run_context=self.run_context, resolved_query=resolved)

        self.assertEqual(str(resolved.intent.domain_code or ""), "inventario_logistica")
        self.assertEqual(str(plan.reason or ""), "inventory_kardex_by_employee")
        self.assertEqual(dict((plan.metadata or {}).get("filters_applied") or {}).get("cedula"), "5098747")
        self.assertIn("WHERE src.cedula = '5098747'", str(plan.sql_query or ""))
        self.assertIn("employee_detail_by_cedula", list((plan.metadata or {}).get("joins_used") or []))
        self.assertIn(
            "serializados_employee_kardex_not_available",
            list((plan.metadata or {}).get("limitations") or []),
        )

    def test_kardex_codigo_para_empleado_routes_employee_kardex_sql(self):
        resolved = self._plan_for("kardex del codigo 1025507 para el empleado 5098747")

        with patch.dict(
            "os.environ",
            {
                "IA_DEV_QUERY_SQL_ASSISTED_ENABLED": "1",
                "IA_DEV_QUERY_INTELLIGENCE_ENABLED": "1",
            },
            clear=False,
        ):
            plan = self.planner.plan(run_context=self.run_context, resolved_query=resolved)

        self.assertEqual(str(plan.capability_id or ""), "inventory_kardex_by_employee")
        self.assertEqual(str(plan.reason or ""), "inventory_kardex_by_employee")
        self.assertIn("CASE WHEN k.tipo_movimiento = 'entrega' THEN k.cantidad ELSE 0 END AS entrada", str(plan.sql_query or ""))
        self.assertIn("CASE WHEN k.tipo_movimiento IN ('devolucion', 'consumo', 'cobro') THEN k.cantidad ELSE 0 END AS salida", str(plan.sql_query or ""))
        self.assertIn("src.cedula = '5098747'", str(plan.sql_query or ""))
        self.assertIn("src.codigo = '1025507'", str(plan.sql_query or ""))
        self.assertEqual(dict((plan.metadata or {}).get("filters_applied") or {}).get("codigo"), "1025507")

    def test_kardex_consolidated_maps_entrega_as_entrada_and_devolucion_as_salida(self):
        resolved = self._plan_for("kardex codigo 1025507")

        with patch.dict(
            "os.environ",
            {
                "IA_DEV_QUERY_SQL_ASSISTED_ENABLED": "1",
                "IA_DEV_QUERY_INTELLIGENCE_ENABLED": "1",
            },
            clear=False,
        ):
            plan = self.planner.plan(run_context=self.run_context, resolved_query=resolved)

        sql_query = str(plan.sql_query or "")
        self.assertEqual(str(plan.capability_id or ""), "inventory_kardex_consolidated")
        self.assertIn("'entrega' AS movimiento, codigo AS codigo, CASE", sql_query)
        self.assertIn("AS entrada, 0 AS salida", sql_query)
        self.assertIn("'devolucion' AS movimiento, codigo AS codigo, 0 AS entrada, CASE", sql_query)
        self.assertIn("SUM(kardex.entrada - kardex.salida) OVER", sql_query)

    def test_equipos_cargados_a_movil_numerica_routes_serial_holder_detail(self):
        resolved = self._plan_for("equipos cargados a la movil 98562719")

        with patch.dict(
            "os.environ",
            {
                "IA_DEV_QUERY_SQL_ASSISTED_ENABLED": "1",
                "IA_DEV_QUERY_INTELLIGENCE_ENABLED": "1",
            },
            clear=False,
        ):
            plan = self.planner.plan(run_context=self.run_context, resolved_query=resolved)

        self.assertEqual(str(resolved.intent.template_id or ""), "inventory_serial_by_operational_holder")
        self.assertEqual(str(plan.capability_id or ""), "inventory_serial_by_operational_holder")
        self.assertIn("cedula = '98562719'", str(plan.sql_query or ""))
        self.assertIn("s.numero_serial AS numero_serial", str(plan.sql_query or ""))
        self.assertIn("s.fecha_ingreso AS fecha_ingreso", str(plan.sql_query or ""))
        self.assertIn("s.ticket AS ticket", str(plan.sql_query or ""))
        self.assertIn("s.fecha_edit AS fecha_edit", str(plan.sql_query or ""))
        self.assertNotIn("cantidad", str(plan.sql_query or ""))

    def test_inventory_by_quadrilla_with_employee_data_keeps_material_detail_and_mobile_context(self):
        resolved = self._plan_for("inventario de la cuadrilla TIRAN224 con datos del empleado")

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
        self.assertEqual(str(plan.capability_id or ""), "inventory_stock_balance_by_mobile")
        self.assertIn("GROUP BY mov.codigo, mov.cedula, COALESCE(emp.movil, '')", str(plan.sql_query or ""))
        self.assertIn("AS saldo", str(plan.sql_query or ""))
        self.assertIn("AS tipo", str(plan.sql_query or ""))
        self.assertIn("p.movil = 'TIRAN224'", str(plan.sql_query or ""))
        self.assertIn("estado_empleado", str(plan.sql_query or ""))
        supplemental = list((plan.metadata or {}).get("supplemental_queries") or [])
        self.assertEqual(len(supplemental), 1)
        self.assertIn("logistica_base_seriales", str(supplemental[0].get("query") or ""))
        self.assertIn("estado_empleado", str(supplemental[0].get("query") or ""))

    def test_saldo_por_tecnico_en_operacion_hfc_keeps_balance_by_codigo(self):
        resolved = self._plan_for("saldo por tecnico en operacion_hfc mostrando cedula, nombre, movil y total de materiales")

        with patch.dict(
            "os.environ",
            {
                "IA_DEV_QUERY_SQL_ASSISTED_ENABLED": "1",
                "IA_DEV_QUERY_INTELLIGENCE_ENABLED": "1",
            },
            clear=False,
        ):
            plan = self.planner.plan(run_context=self.run_context, resolved_query=resolved)

        self.assertEqual(str(resolved.intent.template_id or ""), "inventory_material_stock_mobile")
        self.assertEqual(str(plan.capability_id or ""), "inventory_stock_balance_by_mobile")
        self.assertIn("mov.codigo AS codigo", str(plan.sql_query or ""))
        self.assertIn("AS descripcion", str(plan.sql_query or ""))
        self.assertIn("AS tipo", str(plan.sql_query or ""))
        self.assertIn("AS empleado", str(plan.sql_query or ""))
        self.assertIn("AS estado_empleado", str(plan.sql_query or ""))
        self.assertIn("SUM(mov.entregas - mov.devoluciones - mov.consumos - mov.cobros) AS saldo", str(plan.sql_query or ""))
        self.assertIn("GROUP BY mov.codigo, mov.cedula, COALESCE(emp.movil, '')", str(plan.sql_query or ""))
        self.assertNotIn("WHERE mov.bodega = 'operacion_hfc'", str(plan.sql_query or ""))
        self.assertIn("bodega = 'operacion_hfc'", str(plan.sql_query or ""))
        self.assertNotIn("saldo_total_materiales", str(plan.sql_query or ""))
        self.assertFalse(bool((plan.metadata or {}).get("supplemental_queries")))

    def test_inventario_por_cuadrilla_mantiene_codigo_en_lugar_de_saldo_agregado(self):
        resolved = self._plan_for("inventario por cuadrilla mostrando movil, cedula del empleado, nombre y saldo total")

        with patch.dict(
            "os.environ",
            {
                "IA_DEV_QUERY_SQL_ASSISTED_ENABLED": "1",
                "IA_DEV_QUERY_INTELLIGENCE_ENABLED": "1",
            },
            clear=False,
        ):
            plan = self.planner.plan(run_context=self.run_context, resolved_query=resolved)

        self.assertEqual(str(resolved.intent.template_id or ""), "inventory_material_stock_mobile")
        self.assertEqual(plan.strategy, "sql_assisted")
        self.assertIn("mov.codigo AS codigo", str(plan.sql_query or ""))
        self.assertIn("AS descripcion", str(plan.sql_query or ""))
        self.assertIn("AS tipo", str(plan.sql_query or ""))
        self.assertIn("AS estado_empleado", str(plan.sql_query or ""))
        self.assertIn("GROUP BY mov.codigo, mov.cedula, COALESCE(emp.movil, '')", str(plan.sql_query or ""))
        self.assertNotIn("saldo_total_materiales", str(plan.sql_query or ""))
        supplemental = list((plan.metadata or {}).get("supplemental_queries") or [])
        self.assertEqual(len(supplemental), 1)
        self.assertEqual(str(supplemental[0].get("name") or ""), "serializados_equipos")
        self.assertNotIn("ACTIVO", str(supplemental[0].get("query") or ""))

    def test_saldo_del_empleado_5098747_no_filtra_ceros_ni_negativos(self):
        resolved = self._plan_for("SALDO DEL EMPLEADO 5098747")

        with patch.dict(
            "os.environ",
            {
                "IA_DEV_QUERY_SQL_ASSISTED_ENABLED": "1",
                "IA_DEV_QUERY_INTELLIGENCE_ENABLED": "1",
            },
            clear=False,
        ):
            plan = self.planner.plan(run_context=self.run_context, resolved_query=resolved)

        self.assertEqual(str(resolved.intent.domain_code or ""), "inventario_logistica")
        self.assertEqual(str(resolved.intent.template_id or ""), "inventory_material_stock_mobile")
        self.assertEqual(str(plan.capability_id or ""), "inventory_stock_balance_by_mobile")
        self.assertEqual(str(resolved.normalized_filters.get("cedula") or ""), "5098747")
        self.assertIn("WHERE cedula = '5098747'", str(plan.sql_query or ""))
        self.assertNotIn("HAVING saldo > 0", str(plan.sql_query or ""))
        self.assertNotIn("WHERE saldo > 0", str(plan.sql_query or ""))
        self.assertNotIn("HAVING saldo <> 0", str(plan.sql_query or ""))
        supplemental = list((plan.metadata or {}).get("supplemental_queries") or [])
        self.assertEqual(len(supplemental), 1)
        self.assertEqual(str(supplemental[0].get("name") or ""), "serializados_equipos")
        self.assertNotIn("HAVING saldo > 0", str(supplemental[0].get("query") or ""))
        self.assertNotIn("WHERE saldo > 0", str(supplemental[0].get("query") or ""))
        self.assertNotIn("HAVING saldo <> 0", str(supplemental[0].get("query") or ""))

    def test_saldo_material_claro_empleado_aplica_where_tipo_material(self):
        resolved = self._plan_for("saldo material claro empleado 5098747")

        with patch.dict(
            "os.environ",
            {
                "IA_DEV_QUERY_SQL_ASSISTED_ENABLED": "1",
                "IA_DEV_QUERY_INTELLIGENCE_ENABLED": "1",
            },
            clear=False,
        ):
            plan = self.planner.plan(run_context=self.run_context, resolved_query=resolved)

        self.assertEqual(str(resolved.normalized_filters.get("tipo") or ""), "material")
        self.assertIn("LOWER(COALESCE(cat.tipo, '')) = 'material'", str(plan.sql_query or ""))
        self.assertEqual(dict((plan.metadata or {}).get("filters_applied") or {}).get("tipo"), "material")

    def test_saldo_ferretero_empleado_aplica_where_tipo_ferretero(self):
        resolved = self._plan_for("saldo ferretero empleado 5098747")

        with patch.dict(
            "os.environ",
            {
                "IA_DEV_QUERY_SQL_ASSISTED_ENABLED": "1",
                "IA_DEV_QUERY_INTELLIGENCE_ENABLED": "1",
            },
            clear=False,
        ):
            plan = self.planner.plan(run_context=self.run_context, resolved_query=resolved)

        self.assertEqual(str(resolved.normalized_filters.get("tipo") or ""), "ferretero")
        self.assertIn("LOWER(COALESCE(cat.tipo, '')) = 'ferretero'", str(plan.sql_query or ""))
        self.assertEqual(dict((plan.metadata or {}).get("filters_applied") or {}).get("tipo"), "ferretero")

    def test_saldo_material_generico_empleado_aplica_where_tipo_in_material_y_ferretero(self):
        resolved = self._plan_for("saldo material empleado 5098747")

        with patch.dict(
            "os.environ",
            {
                "IA_DEV_QUERY_SQL_ASSISTED_ENABLED": "1",
                "IA_DEV_QUERY_INTELLIGENCE_ENABLED": "1",
            },
            clear=False,
        ):
            plan = self.planner.plan(run_context=self.run_context, resolved_query=resolved)

        self.assertEqual(list(resolved.normalized_filters.get("tipo") or []), ["material", "ferretero"])
        self.assertIn("LOWER(COALESCE(cat.tipo, '')) IN ('material', 'ferretero')", str(plan.sql_query or ""))
        self.assertEqual(dict((plan.metadata or {}).get("filters_applied") or {}).get("tipo"), ["material", "ferretero"])

    def test_materiales_criticos_por_empleado_en_operacion_hfc_uses_recent_consumption_threshold(self):
        resolved = self._plan_for(
            "materiales criticos por empleado en operacion_hfc cruzando saldo, cedula, movil y datos del empleado"
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

        self.assertEqual(str(resolved.intent.template_id or ""), "inventory_material_critical_by_employee")
        self.assertEqual(str(plan.capability_id or ""), "inventory_stock_balance_by_mobile")
        self.assertIn("DATE(f_consumo) >= DATE_SUB(CURDATE(), INTERVAL 8 DAY)", str(plan.sql_query or ""))
        self.assertIn("COALESCE(cons.consumo_ultimos_8_dias, 0) / 8", str(plan.sql_query or ""))
        self.assertIn("bal.saldo_actual < ((COALESCE(cons.consumo_ultimos_8_dias, 0) / 8) * 3)", str(plan.sql_query or ""))
        self.assertIn("AS estado_critico", str(plan.sql_query or ""))
        self.assertIn("AS estado_empleado", str(plan.sql_query or ""))

    def test_consumos_de_movil_aplican_filtro_operativo_y_mes(self):
        resolved = self._plan_for("consumos de la movil TIRAN314 el 05 de mayo")

        with patch.dict(
            "os.environ",
            {
                "IA_DEV_QUERY_SQL_ASSISTED_ENABLED": "1",
                "IA_DEV_QUERY_INTELLIGENCE_ENABLED": "1",
            },
            clear=False,
        ):
            plan = self.planner.plan(run_context=self.run_context, resolved_query=resolved)

        self.assertEqual(str(resolved.normalized_filters.get("movil") or ""), "TIRAN314")
        self.assertIn("MONTH(f_consumo) = 5", str(plan.sql_query or ""))
        self.assertIn("movil = 'TIRAN314'", str(plan.sql_query or ""))

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
