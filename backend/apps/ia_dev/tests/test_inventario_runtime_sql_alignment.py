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
    fields = [
        {"table_name": "logistica_base_seriales", "campo_logico": "serial", "column_name": "serial", "is_identifier": True, "es_filtro": True},
        {"table_name": "logistica_base_seriales", "campo_logico": "codigo", "column_name": "codigo", "es_filtro": True},
        {"table_name": "logistica_base_seriales", "campo_logico": "estado", "column_name": "estado", "es_group_by": True},
        {"table_name": "logistica_base_seriales", "campo_logico": "ubicacion", "column_name": "ubicacion", "es_group_by": True},
        {"table_name": "logistica_base_seriales", "campo_logico": "responsable", "column_name": "responsable", "es_group_by": True},
        {"table_name": "logistica_base_seriales", "campo_logico": "movimiento", "column_name": "movimiento", "es_filtro": True},
        {"table_name": "logistica_base_seriales", "campo_logico": "validado", "column_name": "validado", "es_filtro": True},
        {"table_name": "logistica_base_seriales", "campo_logico": "fecha", "column_name": "fecha", "is_date": True, "es_filtro": True},
        {"table_name": "logistica_movimientos_consumo", "campo_logico": "codigo", "column_name": "codigo", "es_filtro": True},
        {"table_name": "logistica_movimientos_consumo", "campo_logico": "cantidad", "column_name": "cantidad", "es_metrica": True},
        {"table_name": "logistica_movimientos_consumo", "campo_logico": "fecha", "column_name": "fecha", "is_date": True, "es_filtro": True},
        {"table_name": "logistica_movimientos_traslado", "campo_logico": "bodega_destino", "column_name": "bodega_destino", "es_group_by": True},
        {"table_name": "logistica_movimientos_traslado", "campo_logico": "cantidad", "column_name": "cantidad", "es_metrica": True},
        {"table_name": "logistica_movimientos_entrada", "campo_logico": "fecha", "column_name": "fecha", "is_date": True, "es_filtro": True},
        {"table_name": "logistica_movimientos_entrada", "campo_logico": "cantidad", "column_name": "cantidad", "es_metrica": True},
        {"table_name": "logistica_seriales_asociados", "campo_logico": "serial", "column_name": "serial", "es_filtro": True},
        {"table_name": "logistica_seriales_asociados", "campo_logico": "bodega_salida", "column_name": "bodega_salida", "es_filtro": True},
    ]
    return {
        "domain_status": "partial",
        "supports_sql_assisted": True,
        "source_of_truth": {"pilot_sql_assisted_enabled": True},
        "tables": [
            {"table_name": "logistica_base_seriales", "table_fqn": "logistica_base_seriales", "es_principal": True},
            {"table_name": "logistica_movimientos_consumo", "table_fqn": "logistica_movimientos_consumo"},
            {"table_name": "logistica_movimientos_traslado", "table_fqn": "logistica_movimientos_traslado"},
            {"table_name": "logistica_movimientos_entrada", "table_fqn": "logistica_movimientos_entrada"},
            {"table_name": "logistica_seriales_asociados", "table_fqn": "logistica_seriales_asociados"},
        ],
        "columns": [
            {"table_name": item["table_name"], "column_name": item["column_name"], "nombre_columna_logico": item["campo_logico"]}
            for item in fields
        ],
        "column_profiles": [
            {
                "table_name": item["table_name"],
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
            "logistica_movimientos_consumo",
            "logistica_movimientos_traslado",
            "logistica_movimientos_entrada",
            "logistica_seriales_asociados",
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

    def test_planner_blocks_stock_until_business_validation(self):
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

        self.assertEqual(plan.strategy, "fallback")
        self.assertEqual(str(plan.reason or ""), "inventory_stock_requires_business_validation")

    def test_planner_builds_transfer_sql_when_dimension_is_safe(self):
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

        self.assertEqual(plan.strategy, "sql_assisted")
        self.assertIn("bodega_destino", str(plan.sql_query or ""))
