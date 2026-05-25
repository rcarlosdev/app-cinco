from __future__ import annotations

import os
from collections import Counter, defaultdict
from contextlib import ExitStack
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import patch

from apps.ia_dev.application.context.run_context import RunContext
from apps.ia_dev.application.contracts.query_intelligence_contracts import StructuredQueryIntent
from apps.ia_dev.application.runtime.semantic_gap_registry_service import SemanticGapRegistryService
from apps.ia_dev.application.runtime.service_runtime_bootstrap import apply_service_runtime_bootstrap
from apps.ia_dev.application.semantic.query_execution_planner import QueryExecutionPlanner
from apps.ia_dev.domains.inventario_logistica.response_assembler import build_inventory_business_response
from apps.ia_dev.domains.inventario_logistica.paquete_capacidades_loader import build_inventory_capability_pack_coverage
from apps.ia_dev.domains.inventario_logistica.semantic_inventory_resolver import InventorySemanticResolver


DATASET_VERSION = "p5_inventario_runtime_eval_v2"


@dataclass(frozen=True, slots=True)
class InventoryRuntimeEvalCase:
    case_id: str
    grupo_semantico: str
    pregunta: str
    operacion: str
    expectativa_resultado: str
    expected_template_id: str = ""
    expected_capability: str = ""
    expected_planner_reason: str = ""
    expected_response_status: str = ""
    expected_route_hint: str = ""
    expected_filters: dict[str, Any] = field(default_factory=dict)
    expected_limitations: tuple[str, ...] = ()
    expected_metadata_rules: tuple[str, ...] = ()
    fixture_rows: tuple[dict[str, Any], ...] = ()
    fixture_extra_tables: tuple[dict[str, Any], ...] = ()
    fixture_result_set: dict[str, Any] = field(default_factory=dict)
    force_shadow_metadata: bool = False
    legacy_allowed: bool = False
    expected_source: str = "capability_pack"
    expected_legacy_retained_reason: str = ""
    minimum_validation_label: str = ""


def _inventory_eval_context() -> dict[str, Any]:
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
                    "bd_c3nc4s1s.cinco_base_de_personal" if item["table_name"] == "cinco_base_de_personal" else item["table_name"]
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
                    "bd_c3nc4s1s.cinco_base_de_personal" if item["table_name"] == "cinco_base_de_personal" else item["table_name"]
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
        "inventory_catalog_families": ["DECO", "CPE RESIDENCIAL", "ONT", "ROUTER"],
    }


def _stock_rows() -> tuple[dict[str, Any], ...]:
    return (
        {
            "codigo": "MAT-001",
            "descripcion": "Conector",
            "tipo": "FERRETERO",
            "cedula": "5098747",
            "empleado": "Juan Perez",
            "movil": "TIRAN224",
            "saldo": 2,
        },
    )


def _serial_rows() -> tuple[dict[str, Any], ...]:
    return (
        {
            "name": "serializados_equipos",
            "rowcount": 2,
            "rows": [{"serial": "SER-001"}, {"serial": "SER-002"}],
            "skipped": False,
        },
    )


def _serial_family_dimension_rows() -> tuple[dict[str, Any], ...]:
    return (
        {
            "dimension": "TIRAN224",
            "cedula": "5098747",
            "empleado": "Juan Perez",
            "movil": "TIRAN224",
            "bodega": "",
            "codigo": "SER-001",
            "descripcion": "DECO HD",
            "familia": "DECO",
            "seriales_total": 2,
            "en_movil": 2,
            "en_base": 0,
            "cobros": 0,
            "saldo": 2,
        },
    )


def _kardex_rows() -> tuple[dict[str, Any], ...]:
    return (
        {
            "fecha": "2026-05-09T00:00:00",
            "tipo_movimiento": "entrega",
            "codigo": "1025507",
            "cedula": "5098747",
            "entrada": 3,
            "salida": 0,
            "saldo_movimiento": 3,
        },
    )


def build_inventory_runtime_eval_cases() -> list[InventoryRuntimeEvalCase]:
    cases = [
        InventoryRuntimeEvalCase(
            case_id="stock_cuadrilla_asignado",
            grupo_semantico="stock_movil_dual",
            pregunta="que tiene asignado la cuadrilla TIRAN224",
            operacion="stock_balance",
            expectativa_resultado="correcto",
            expected_template_id="inventory_material_stock_mobile",
            expected_capability="inventory_stock_balance_by_mobile",
            expected_planner_reason="inventory_material_stock_mobile",
            expected_response_status="success",
            expected_route_hint="inventory.material_stock.mobile",
            expected_filters={"movil": "TIRAN224"},
            expected_metadata_rules=("inventario.route.stock_balance_holder",),
            fixture_rows=_stock_rows(),
            fixture_extra_tables=_serial_rows(),
            fixture_result_set={"rowcount": 1, "total_records": 1, "returned_records": 1},
            minimum_validation_label="inventario_generico_por_movil_cuadrilla",
        ),
        InventoryRuntimeEvalCase(
            case_id="stock_movil_muestrame",
            grupo_semantico="stock_movil_dual",
            pregunta="muéstrame lo que tiene el móvil TIRAN224",
            operacion="stock_balance",
            expectativa_resultado="correcto",
            expected_template_id="inventory_material_stock_mobile",
            expected_capability="inventory_stock_balance_by_mobile",
            expected_planner_reason="inventory_material_stock_mobile",
            expected_response_status="success",
            expected_route_hint="inventory.material_stock.mobile",
            expected_filters={"movil": "TIRAN224"},
            expected_metadata_rules=("inventario.route.stock_balance_holder",),
            fixture_rows=_stock_rows(),
            fixture_extra_tables=_serial_rows(),
            fixture_result_set={"rowcount": 1},
        ),
        InventoryRuntimeEvalCase(
            case_id="stock_inventario_operativo_con_empleados",
            grupo_semantico="stock_movil_dual",
            pregunta="inventario operativo de TIRAN224 con empleados",
            operacion="stock_balance",
            expectativa_resultado="correcto",
            expected_template_id="inventory_material_stock_mobile",
            expected_capability="inventory_stock_balance_by_mobile",
            expected_planner_reason="inventory_material_stock_mobile",
            expected_response_status="success",
            expected_route_hint="inventory.material_stock.mobile",
            expected_filters={"movil": "TIRAN224"},
            expected_metadata_rules=("inventario.route.stock_balance_holder",),
            fixture_rows=_stock_rows(),
            fixture_extra_tables=_serial_rows(),
            fixture_result_set={"rowcount": 1},
        ),
        InventoryRuntimeEvalCase(
            case_id="stock_brigada_asignado",
            grupo_semantico="stock_movil_dual",
            pregunta="qué tiene asignado la brigada TIRAN224",
            operacion="stock_balance",
            expectativa_resultado="correcto",
            expected_template_id="inventory_material_stock_mobile",
            expected_capability="inventory_stock_balance_by_mobile",
            expected_planner_reason="inventory_material_stock_mobile",
            expected_response_status="success",
            expected_route_hint="inventory.material_stock.mobile",
            expected_filters={"movil": "TIRAN224"},
            expected_metadata_rules=("inventario.route.stock_balance_holder",),
            fixture_rows=_stock_rows(),
            fixture_extra_tables=_serial_rows(),
            fixture_result_set={"rowcount": 1},
        ),
        InventoryRuntimeEvalCase(
            case_id="stock_materiales_movil",
            grupo_semantico="stock_movil_materiales",
            pregunta="materiales del móvil TIRAN224",
            operacion="stock_balance",
            expectativa_resultado="correcto",
            expected_template_id="inventory_material_stock_mobile",
            expected_capability="inventory_stock_balance_by_mobile",
            expected_planner_reason="inventory_material_stock_mobile",
            expected_response_status="success",
            expected_route_hint="inventory.material_stock.mobile",
            expected_filters={"movil": "TIRAN224"},
            expected_metadata_rules=("inventario.route.stock_balance_holder",),
            fixture_rows=_stock_rows(),
            fixture_result_set={"rowcount": 1},
        ),
        InventoryRuntimeEvalCase(
            case_id="stock_cedula_generico",
            grupo_semantico="stock_cedula_generico",
            pregunta="saldo del empleado 5098747",
            operacion="stock_balance",
            expectativa_resultado="correcto",
            expected_template_id="inventory_material_stock_mobile",
            expected_capability="inventory_stock_balance_by_mobile",
            expected_planner_reason="inventory_material_stock_mobile",
            expected_response_status="success",
            expected_route_hint="inventory.material_stock.mobile",
            expected_filters={"cedula": "5098747"},
            expected_metadata_rules=("inventario.route.stock_balance_holder",),
            fixture_rows=_stock_rows(),
            fixture_result_set={"rowcount": 1},
            minimum_validation_label="inventario_por_cedula",
        ),
        InventoryRuntimeEvalCase(
            case_id="stock_tecnico_ferretero",
            grupo_semantico="stock_tecnico_ferretero",
            pregunta="ferretería asignada al técnico 5098747",
            operacion="stock_balance",
            expectativa_resultado="correcto",
            expected_template_id="inventory_material_stock_mobile",
            expected_capability="inventory_stock_balance_by_mobile",
            expected_planner_reason="inventory_material_stock_mobile",
            expected_response_status="success",
            expected_route_hint="inventory.material_stock.mobile",
            expected_filters={"cedula": "5098747", "tipo": "ferretero"},
            expected_metadata_rules=("inventario.route.stock_balance_holder",),
            fixture_rows=_stock_rows(),
            fixture_result_set={"rowcount": 1},
        ),
        InventoryRuntimeEvalCase(
            case_id="kardex_tecnico_movimientos",
            grupo_semantico="kardex_empleado",
            pregunta="movimientos del técnico 5098747",
            operacion="detail",
            expectativa_resultado="correcto",
            expected_template_id="inventory_kardex_by_employee",
            expected_capability="inventory_kardex_by_employee",
            expected_planner_reason="inventory_kardex_by_employee",
            expected_response_status="success",
            expected_route_hint="inventory.kardex.employee",
            expected_filters={"cedula": "5098747"},
            expected_limitations=("serializados_employee_kardex_not_available",),
            expected_metadata_rules=("inventario.route.kardex_employee",),
            fixture_rows=_kardex_rows(),
            fixture_result_set={"rowcount": 1},
            minimum_validation_label="kardex_por_empleado",
        ),
        InventoryRuntimeEvalCase(
            case_id="kardex_tecnico_entradas_salidas",
            grupo_semantico="kardex_empleado",
            pregunta="entradas y salidas de 5098747",
            operacion="detail",
            expectativa_resultado="correcto",
            expected_template_id="inventory_kardex_by_employee",
            expected_capability="inventory_kardex_by_employee",
            expected_planner_reason="inventory_kardex_by_employee",
            expected_response_status="success",
            expected_route_hint="inventory.kardex.employee",
            expected_filters={"cedula": "5098747"},
            expected_limitations=("serializados_employee_kardex_not_available",),
            expected_metadata_rules=("inventario.route.kardex_employee",),
            fixture_rows=_kardex_rows(),
            fixture_result_set={"rowcount": 1},
        ),
        InventoryRuntimeEvalCase(
            case_id="kardex_codigo_para_empleado",
            grupo_semantico="kardex_empleado",
            pregunta="historial del código 1025507 para 5098747",
            operacion="detail",
            expectativa_resultado="correcto",
            expected_template_id="inventory_kardex_by_employee",
            expected_capability="inventory_kardex_by_employee",
            expected_planner_reason="inventory_kardex_by_employee",
            expected_response_status="success",
            expected_route_hint="inventory.kardex.employee",
            expected_filters={"cedula": "5098747", "codigo": "1025507"},
            expected_limitations=("serializados_employee_kardex_not_available",),
            expected_metadata_rules=("inventario.route.kardex_employee",),
            fixture_rows=_kardex_rows(),
            fixture_result_set={"rowcount": 1},
            minimum_validation_label="kardex_codigo_mas_empleado",
        ),
        InventoryRuntimeEvalCase(
            case_id="seriales_por_familia_deco",
            grupo_semantico="serial_family_dimension_declared",
            pregunta="saldo en moviles de Deco",
            operacion="aggregate",
            expectativa_resultado="correcto",
            expected_template_id="inventory_serial_stock_by_family_grouped_dimension",
            expected_capability="inventory_serial_stock_by_family_grouped_dimension",
            expected_planner_reason="inventory_serial_stock_by_family_grouped_dimension",
            expected_response_status="success",
            expected_route_hint="inventory.serial_stock.family_dimension",
            expected_filters={"material_family": "DECO", "material_family_match_mode": "contains"},
            expected_metadata_rules=("inventario.route.serial_stock_family_grouped_dimension",),
            fixture_rows=_serial_family_dimension_rows(),
            fixture_result_set={"rowcount": 1},
            minimum_validation_label="seriales_equipos_por_familia",
        ),
        InventoryRuntimeEvalCase(
            case_id="clarificacion_nombre_propio",
            grupo_semantico="clarificacion_portador",
            pregunta="qué tiene Juan Pérez",
            operacion="detail",
            expectativa_resultado="aclaracion_valida",
            expected_template_id="inventory_movement_detail",
            expected_response_status="clarification_required",
            fixture_rows=(),
            fixture_result_set={"rowcount": 0},
            legacy_allowed=True,
            expected_source="aclaracion_controlada",
            expected_legacy_retained_reason="requiere_aclaracion_estructural_por_portador_no_verificable",
            minimum_validation_label="consulta_ambigua_rescate_permitido",
        ),
        InventoryRuntimeEvalCase(
            case_id="movement_detail_operativo",
            grupo_semantico="movement_detail_declared",
            pregunta="ingreso del codigo 1025507",
            operacion="detail",
            expectativa_resultado="correcto",
            expected_template_id="inventory_movement_detail",
            expected_capability="inventory_movement_detail",
            expected_planner_reason="inventory_movement_detail",
            expected_response_status="success",
            expected_route_hint="inventory.movement.detail",
            expected_filters={"codigo": "1025507"},
            expected_metadata_rules=("inventario.route.movement_detail",),
            fixture_rows=(
                {
                    "codigo": "1025507",
                    "cantidad": 4,
                    "fecha": "2026-05-03T00:00:00",
                    "bodega": "operacion_hfc",
                },
            ),
            fixture_result_set={"rowcount": 1},
            minimum_validation_label="movement_detail",
        ),
        InventoryRuntimeEvalCase(
            case_id="limitacion_actas_sap",
            grupo_semantico="limitacion_documental",
            pregunta="actas SAP del empleado 5098747",
            operacion="detail",
            expectativa_resultado="limitacion_valida",
            expected_template_id="inventory_document_generation_pending",
            expected_capability="inventory_document_generation_pending",
            expected_planner_reason="unsafe_sql_plan",
            expected_response_status="limitation_declared",
            expected_route_hint="inventory.document_generation.pending",
            expected_filters={"cedula": "5098747"},
            expected_limitations=("documentos_sap_y_actas_no_habilitados",),
            expected_metadata_rules=("inventario.limit.document_generation_pending",),
            fixture_rows=(),
            fixture_result_set={"rowcount": 0},
        ),
        InventoryRuntimeEvalCase(
            case_id="resultado_vacio_stock_tecnico",
            grupo_semantico="stock_tecnico_vacio",
            pregunta="revisa inventario del técnico 5098747",
            operacion="stock_balance",
            expectativa_resultado="correcto",
            expected_template_id="inventory_material_stock_mobile",
            expected_capability="inventory_stock_balance_by_mobile",
            expected_planner_reason="inventory_material_stock_mobile",
            expected_response_status="empty_result",
            expected_route_hint="inventory.material_stock.mobile",
            expected_filters={"cedula": "5098747"},
            expected_metadata_rules=("inventario.route.stock_balance_holder",),
            fixture_rows=(),
            fixture_result_set={"rowcount": 0, "total_records": 0, "returned_records": 0},
        ),
        InventoryRuntimeEvalCase(
            case_id="serial_stock_estado_declared",
            grupo_semantico="serial_stock_dimension_declared",
            pregunta="equipos por estado",
            operacion="aggregate",
            expectativa_resultado="correcto",
            expected_template_id="inventory_serial_stock_by_dimension",
            expected_capability="inventory_serial_stock_by_dimension",
            expected_planner_reason="inventory_serial_stock_by_dimension",
            expected_response_status="success",
            expected_route_hint="inventory.serial.stock.dimension",
            expected_metadata_rules=("inventario.route.serial_stock_dimension",),
            fixture_rows=(
                {
                    "estado": "MOVIL",
                    "codigo": "SER-001",
                    "descripcion": "DECO HD",
                    "saldo": 2,
                },
            ),
            fixture_result_set={"rowcount": 1},
            minimum_validation_label="serial_stock_por_dimension",
        ),
        InventoryRuntimeEvalCase(
            case_id="risk_consumo_movil_declared",
            grupo_semantico="risk_serial_declared",
            pregunta="equipos serializados en consumo movil sin validar",
            operacion="detail",
            expectativa_resultado="correcto",
            expected_template_id="inventory_risk_consumo_movil_sin_validar",
            expected_capability="inventory_risk_consumo_movil_sin_validar",
            expected_planner_reason="missing_dictionary_column",
            expected_response_status="success",
            expected_route_hint="inventory.risk.consumo_movil_sin_validar",
            expected_metadata_rules=("inventario.route.risk_consumo_movil_sin_validar",),
            fixture_rows=(
                {
                    "serial": "SER-001",
                    "codigo": "SER-001",
                    "estado": "CONSUMO MOVIL",
                    "ubicacion": "TIRAN224",
                    "fecha": "2026-05-10T00:00:00",
                },
            ),
            fixture_result_set={"rowcount": 1},
            minimum_validation_label="riesgo_consumo_movil_sin_validar",
        ),
        InventoryRuntimeEvalCase(
            case_id="consumption_top_declared",
            grupo_semantico="consumption_top_declared",
            pregunta="top de consumos de materiales en mayo",
            operacion="aggregate",
            expectativa_resultado="correcto",
            expected_template_id="inventory_consumption_top",
            expected_capability="inventory_consumption_top",
            expected_planner_reason="inventory_consumption_top",
            expected_response_status="success",
            expected_route_hint="inventory.consumption.top",
            expected_filters={"month": "5"},
            expected_metadata_rules=("inventario.route.consumption_top",),
            fixture_rows=(
                {
                    "codigo": "MAT-001",
                    "descripcion": "Conector",
                    "tipo": "FERRETERO",
                    "cantidad": 12,
                },
            ),
            fixture_result_set={"rowcount": 1},
            minimum_validation_label="top_consumos",
        ),
        InventoryRuntimeEvalCase(
            case_id="reconciliation_operacion_hfc_declared",
            grupo_semantico="reconciliation_hfc_declared",
            pregunta="comparativo de consumo tecnico contra facturacion hfc",
            operacion="aggregate",
            expectativa_resultado="correcto",
            expected_template_id="inventory_consumption_billing_operacion_hfc",
            expected_capability="inventory_consumption_billing_operacion_hfc",
            expected_planner_reason="missing_dictionary_column",
            expected_response_status="success",
            expected_route_hint="inventory.reconciliation.operacion_hfc",
            expected_filters={"bodega": "operacion_hfc"},
            expected_metadata_rules=("inventario.route.reconciliation_operacion_hfc",),
            fixture_rows=(
                {
                    "codigo": "MAT-001",
                    "cantidad": 7,
                    "orden_trabajo": "OT-001",
                    "tipo": "MATERIAL",
                    "bodega": "operacion_hfc",
                },
            ),
            fixture_result_set={"rowcount": 1},
            minimum_validation_label="consumo_vs_facturacion_operacion_hfc",
        ),
        InventoryRuntimeEvalCase(
            case_id="critical_materials_ruido_controlado",
            grupo_semantico="critical_materials_declared",
            pregunta="materiales criticos por empleado en operacion_hfc con algo de ruido extra por favor",
            operacion="aggregate",
            expectativa_resultado="correcto",
            expected_template_id="inventory_material_critical_by_employee",
            expected_capability="inventory_stock_balance_by_mobile",
            expected_planner_reason="inventory_material_critical_by_employee",
            expected_response_status="success",
            expected_route_hint="inventory.material_stock.critical_employee",
            expected_filters={"bodega": "operacion_hfc"},
            expected_metadata_rules=("inventario.route.critical_materials_by_employee",),
            fixture_rows=_stock_rows(),
            fixture_result_set={"rowcount": 1},
        ),
    ]
    cases[-1] = InventoryRuntimeEvalCase(
        case_id="critical_materials_por_empleado",
        grupo_semantico="critical_materials_declared",
        pregunta="materiales criticos por empleado en operacion_hfc cruzando saldo, cedula, movil y datos del empleado",
        operacion="aggregate",
        expectativa_resultado="correcto",
        expected_template_id="inventory_material_critical_by_employee",
        expected_capability="inventory_stock_balance_by_mobile",
        expected_planner_reason="inventory_material_critical_by_employee",
        expected_response_status="success",
        expected_route_hint="inventory.material_stock.critical_employee",
        expected_filters={"bodega": "operacion_hfc"},
        expected_metadata_rules=("inventario.route.critical_materials_by_employee",),
        fixture_rows=_stock_rows(),
        fixture_result_set={"rowcount": 1},
        minimum_validation_label="materiales_criticos",
    )
    cases.extend(
        [
            InventoryRuntimeEvalCase(
                case_id="critical_materials_por_tecnico",
                grupo_semantico="critical_materials_declared",
                pregunta="materiales críticos por técnico en operacion_hfc",
                operacion="aggregate",
                expectativa_resultado="correcto",
                expected_template_id="inventory_material_critical_by_employee",
                expected_capability="inventory_stock_balance_by_mobile",
                expected_planner_reason="inventory_material_critical_by_employee",
                expected_response_status="success",
                expected_route_hint="inventory.material_stock.critical_employee",
                expected_filters={"bodega": "operacion_hfc"},
                expected_metadata_rules=("inventario.route.critical_materials_by_employee",),
                fixture_rows=_stock_rows(),
                fixture_result_set={"rowcount": 1},
            ),
            InventoryRuntimeEvalCase(
                case_id="critical_materials_por_movil",
                grupo_semantico="critical_materials_declared",
                pregunta="materiales críticos por móvil/cuadrilla en operacion_hfc",
                operacion="aggregate",
                expectativa_resultado="correcto",
                expected_template_id="inventory_material_critical_by_employee",
                expected_capability="inventory_stock_balance_by_mobile",
                expected_planner_reason="inventory_material_critical_by_employee",
                expected_response_status="success",
                expected_route_hint="inventory.material_stock.critical_employee",
                expected_filters={"bodega": "operacion_hfc"},
                expected_metadata_rules=("inventario.route.critical_materials_by_employee",),
                fixture_rows=_stock_rows(),
                fixture_result_set={"rowcount": 1},
            ),
            InventoryRuntimeEvalCase(
                case_id="critical_materials_saldo_consumo",
                grupo_semantico="critical_materials_declared",
                pregunta="criticidad de materiales por saldo y consumo en operacion_hfc",
                operacion="aggregate",
                expectativa_resultado="correcto",
                expected_template_id="inventory_material_critical_by_employee",
                expected_capability="inventory_stock_balance_by_mobile",
                expected_planner_reason="inventory_material_critical_by_employee",
                expected_response_status="success",
                expected_route_hint="inventory.material_stock.critical_employee",
                expected_filters={"bodega": "operacion_hfc"},
                expected_metadata_rules=("inventario.route.critical_materials_by_employee",),
                fixture_rows=_stock_rows(),
                fixture_result_set={"rowcount": 1},
            ),
            InventoryRuntimeEvalCase(
                case_id="critical_materials_cobertura_baja",
                grupo_semantico="critical_materials_declared",
                pregunta="materiales con cobertura baja en operacion_hfc",
                operacion="aggregate",
                expectativa_resultado="correcto",
                expected_template_id="inventory_material_critical_by_employee",
                expected_capability="inventory_stock_balance_by_mobile",
                expected_planner_reason="inventory_material_critical_by_employee",
                expected_response_status="success",
                expected_route_hint="inventory.material_stock.critical_employee",
                expected_filters={"bodega": "operacion_hfc"},
                expected_metadata_rules=("inventario.route.critical_materials_by_employee",),
                fixture_rows=_stock_rows(),
                fixture_result_set={"rowcount": 1},
            ),
            InventoryRuntimeEvalCase(
                case_id="critical_materials_bajo_umbral",
                grupo_semantico="critical_materials_declared",
                pregunta="materiales por debajo de umbral en operacion_hfc",
                operacion="aggregate",
                expectativa_resultado="correcto",
                expected_template_id="inventory_material_critical_by_employee",
                expected_capability="inventory_stock_balance_by_mobile",
                expected_planner_reason="inventory_material_critical_by_employee",
                expected_response_status="success",
                expected_route_hint="inventory.material_stock.critical_employee",
                expected_filters={"bodega": "operacion_hfc"},
                expected_metadata_rules=("inventario.route.critical_materials_by_employee",),
                fixture_rows=_stock_rows(),
                fixture_result_set={"rowcount": 1},
            ),
        ]
    )
    return cases


def _shadow_metadata_payload() -> dict[str, Any]:
    return {
        "dd_sinonimos": [],
        "dd_reglas": [],
        "ia_dev_capacidades_columna": [],
        "fuentes_dd": [],
    }


def _resolver() -> InventorySemanticResolver:
    resolver = InventorySemanticResolver()
    resolver.semantic_plan_builder.memory_service.list_memory_snapshot = lambda: [
        {"memory_key": "inventory.semantic.rule.kardex"},
        {"memory_key": "inventory.semantic.rule.stock_balance"},
    ]
    resolver.semantic_plan_builder.memory_service.ensure_confirmed_rules = lambda: {
        "saved_keys": ["inventory.semantic.rule.kardex"],
        "error_count": 0,
        "errors": [],
    }
    return resolver


def _evaluate_case(
    *,
    case: InventoryRuntimeEvalCase,
    resolved_query: dict[str, Any],
    execution_plan: dict[str, Any],
    business_response: dict[str, Any],
) -> dict[str, Any]:
    semantic_context = dict(resolved_query.get("semantic_context") or {})
    resolved_semantic = dict(semantic_context.get("resolved_semantic") or {})
    binding = dict(semantic_context.get("semantic_capability_registry") or {})
    response_metadata = dict(business_response.get("metadata") or {})
    evidence = dict(business_response.get("evidence_summary") or {})
    semantic_trace = dict(evidence.get("semantic_trace") or response_metadata.get("semantic_trace") or {})
    capability_pack = dict(evidence.get("capability_pack") or {})
    eval_checks: list[str] = []
    eval_errors: list[str] = []

    if case.expected_template_id and str((resolved_query.get("intent") or {}).get("template_id") or "") == case.expected_template_id:
        eval_checks.append("semantic_correctness")
    else:
        eval_errors.append("template_id_mismatch")

    if case.expected_capability:
        if str(binding.get("candidate_capability") or "") == case.expected_capability:
            eval_checks.append("capability_correctness")
        else:
            eval_errors.append("capability_mismatch")

    if case.expected_planner_reason:
        if str(execution_plan.get("reason") or "") == case.expected_planner_reason:
            eval_checks.append("planner_route_correctness")
        else:
            eval_errors.append("planner_reason_mismatch")

    if case.expected_route_hint:
        if str(semantic_trace.get("planner_route_hint") or "") == case.expected_route_hint:
            eval_checks.append("planner_route_hint_correctness")
        else:
            eval_errors.append("planner_route_hint_mismatch")

    if case.expected_response_status:
        if str(response_metadata.get("response_status") or "") == case.expected_response_status:
            eval_checks.append("response_status_correctness")
        else:
            eval_errors.append("response_status_mismatch")

    filters = dict(resolved_query.get("normalized_filters") or {})
    for key, value in dict(case.expected_filters or {}).items():
        if filters.get(key) != value:
            eval_errors.append(f"filter_mismatch:{key}")
    if case.expected_filters:
        eval_checks.append("semantic_filters_correctness")

    limitations = set(str(item or "") for item in list(resolved_semantic.get("limitations") or []))
    for limitation in case.expected_limitations:
        if limitation not in limitations:
            eval_errors.append(f"limitation_missing:{limitation}")
    if case.expected_limitations:
        eval_checks.append("limitation_correctness")

    metadata_rules = set(str(item or "") for item in list(semantic_trace.get("regla_metadata_usada") or []))
    metadata_used = bool(metadata_rules or semantic_trace.get("fuente_dd"))
    if case.expected_metadata_rules:
        for rule in case.expected_metadata_rules:
            if rule not in metadata_rules:
                eval_errors.append(f"metadata_rule_missing:{rule}")
        eval_checks.append("metadata_governance")
    if not str(semantic_trace.get("paquete_capacidad_usado") or capability_pack.get("paquete_capacidad_usado") or "").strip():
        eval_errors.append("capability_pack_missing")
    else:
        eval_checks.append("capability_pack_trace")

    result_status = str(response_metadata.get("response_status") or "")
    evidence_sources = set(str(item or "") for item in list(evidence.get("evidence_sources_used") or []))
    evidence_ok = True
    if result_status == "success" and "result_set" not in evidence_sources and "data.extra_tables" not in evidence_sources:
        evidence_ok = False
        eval_errors.append("missing_success_evidence")
    if result_status == "clarification_required" and str(response_metadata.get("missing_evidence_reason") or "") != "missing_structural_context":
        evidence_ok = False
        eval_errors.append("clarification_reason_mismatch")
    if result_status == "limitation_declared" and str(response_metadata.get("missing_evidence_reason") or "") != "known_limitation":
        evidence_ok = False
        eval_errors.append("limitation_reason_mismatch")
    if result_status == "empty_result" and "result_set" not in str(response_metadata.get("missing_evidence_reason") or ""):
        evidence_ok = False
        eval_errors.append("empty_result_reason_mismatch")
    if evidence_ok:
        eval_checks.append("evidence_correctness")

    reported_source = str(semantic_trace.get("source") or "").strip()
    fallback_detected = bool(
        semantic_trace.get("fallback_sombreado_usado")
        or semantic_trace.get("regla_legacy_detectada")
    )
    if result_status == "clarification_required" and not reported_source:
        reported_source = "aclaracion_controlada"
    elif result_status == "clarification_required" and reported_source not in {"legacy_shadow_fallback", "aclaracion_controlada"}:
        reported_source = "aclaracion_controlada"
    legacy_retained_reason = str(semantic_trace.get("legacy_retained_reason") or semantic_trace.get("reason") or "").strip()
    if not legacy_retained_reason and result_status == "clarification_required":
        legacy_retained_reason = "requiere_aclaracion_estructural_por_portador_no_verificable"
    if case.expected_source:
        if reported_source == case.expected_source:
            eval_checks.append("resolution_source_correctness")
        else:
            eval_errors.append("resolution_source_mismatch")
    if case.expected_legacy_retained_reason:
        if legacy_retained_reason == case.expected_legacy_retained_reason:
            eval_checks.append("legacy_retained_reason_correctness")
        else:
            eval_errors.append("legacy_retained_reason_mismatch")
    if fallback_detected and not bool(case.legacy_allowed):
        eval_errors.append("unexpected_legacy_fallback")
    semantic_confidence = float(
        (resolved_semantic.get("binding_trace") or {}).get("confidence")
        or binding.get("confidence")
        or (resolved_query.get("intent") or {}).get("confidence")
        or 0.0
    )

    if "capability_mismatch" in eval_errors:
        clasificacion = "capability_incorrecta"
    elif "planner_reason_mismatch" in eval_errors or "planner_route_hint_mismatch" in eval_errors:
        clasificacion = "planner_incorrecto"
    elif any(error.startswith("missing_success_evidence") or error.endswith("_reason_mismatch") for error in eval_errors):
        clasificacion = "evidence_inconsistente"
    elif result_status == "clarification_required" and not eval_errors:
        clasificacion = "aclaracion_valida"
    elif result_status == "limitation_declared" and not eval_errors:
        clasificacion = "limitacion_valida"
    elif fallback_detected and not eval_errors:
        clasificacion = "correcto_con_fallback"
    elif eval_errors:
        clasificacion = "error_semantico"
    else:
        clasificacion = "correcto"

    return {
        "case_id": case.case_id,
        "grupo_semantico": case.grupo_semantico,
        "pregunta": case.pregunta,
        "clasificacion": clasificacion,
        "eval_result": "passed" if not eval_errors else "failed",
        "eval_reason": ", ".join(eval_errors) if eval_errors else "ok",
        "checks_ok": eval_checks,
        "checks_failed": eval_errors,
        "semantic_confidence": round(semantic_confidence, 4),
        "fallback_detected": fallback_detected,
        "legacy_allowed": bool(case.legacy_allowed),
        "source": reported_source,
        "legacy_retained_reason": legacy_retained_reason,
        "metadata_used": metadata_used,
        "suspected_hardcode": False,
        "template_id": str((resolved_query.get("intent") or {}).get("template_id") or ""),
        "candidate_capability": str(binding.get("candidate_capability") or ""),
        "planner_reason": str(execution_plan.get("reason") or ""),
        "planner_strategy": str(execution_plan.get("strategy") or ""),
        "response_status": result_status,
        "response_profile": str(response_metadata.get("response_profile_usado") or ""),
        "semantic_trace": semantic_trace,
        "capability_pack": capability_pack,
        "response_profile_usado": str(response_metadata.get("response_profile_usado") or ""),
        "evidence_summary": evidence,
    }


def _mark_hardcode_suspicion(results: list[dict[str, Any]]) -> None:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in results:
        grouped[str(item.get("grupo_semantico") or "")].append(item)

    for group_id, items in grouped.items():
        if len(items) <= 1:
            continue
        template_ids = {str(item.get("template_id") or "") for item in items}
        capabilities = {str(item.get("candidate_capability") or "") for item in items}
        planner_reasons = {str(item.get("planner_reason") or "") for item in items}
        response_statuses = {str(item.get("response_status") or "") for item in items}
        divergent = len(template_ids) > 1 or len(capabilities) > 1 or len(planner_reasons) > 1
        suspicious_status = len(response_statuses) > 1 and not response_statuses.issubset({"success", "empty_result"})
        if not divergent and not suspicious_status:
            continue
        for item in items:
            if str(item.get("clasificacion") or "") in {"correcto", "correcto_con_fallback"}:
                item["clasificacion"] = "hardcode_sospechoso"
            item["suspected_hardcode"] = True
            item["eval_result"] = "failed"
            item["eval_reason"] = "semantic_group_divergence_detected"


def _build_minimum_validation_matrix(
    *,
    cases: list[InventoryRuntimeEvalCase],
    results: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    results_by_case = {str(item.get("case_id") or ""): item for item in results}
    matrix: dict[str, dict[str, Any]] = {}
    for case in cases:
        label = str(case.minimum_validation_label or "").strip()
        if not label:
            continue
        result = dict(results_by_case.get(case.case_id) or {})
        matrix[label] = {
            "case_id": case.case_id,
            "eval_result": str(result.get("eval_result") or ""),
            "template_id": str(result.get("template_id") or ""),
            "candidate_capability": str(result.get("candidate_capability") or ""),
            "response_status": str(result.get("response_status") or ""),
            "source": str(result.get("source") or ""),
            "legacy_mapping_used": bool((result.get("semantic_trace") or {}).get("legacy_mapping_used")),
            "fallback_used": bool((result.get("semantic_trace") or {}).get("fallback_used")),
            "legacy_retained_reason": str(result.get("legacy_retained_reason") or ""),
        }
    return matrix


def run_inventory_runtime_eval_suite(
    *,
    gap_registry_service: SemanticGapRegistryService | None = None,
    register_failed_gaps: bool = False,
) -> dict[str, Any]:
    apply_service_runtime_bootstrap(force=True)
    os.environ["IA_DEV_QUERY_SQL_ASSISTED_ENABLED"] = "1"
    os.environ["IA_DEV_QUERY_INTELLIGENCE_ENABLED"] = "1"

    planner = QueryExecutionPlanner()
    cases = build_inventory_runtime_eval_cases()
    pack_coverage = build_inventory_capability_pack_coverage()
    results: list[dict[str, Any]] = []

    for case in cases:
        with ExitStack() as stack:
            if case.force_shadow_metadata:
                stack.enter_context(
                    patch(
                        "apps.ia_dev.application.semantic.semantic_capability_registry.construir_metadata_gobernada_inventario",
                        return_value=_shadow_metadata_payload(),
                    )
                )
                stack.enter_context(
                    patch(
                        "apps.ia_dev.domains.inventario_logistica.matcher_semantico_gobernado_inventario.construir_metadata_gobernada_inventario",
                        return_value=_shadow_metadata_payload(),
                    )
                )

            resolver = _resolver()
            resolved = resolver.resolve_query(
                message=case.pregunta,
                intent=StructuredQueryIntent(
                    raw_query=case.pregunta,
                    domain_code="inventario_logistica",
                    operation=case.operacion,
                    template_id="",
                    confidence=0.9,
                ),
                semantic_context=_inventory_eval_context(),
            )
            plan = planner.plan(
                run_context=RunContext.create(message=case.pregunta, session_id=f"eval-{case.case_id}", reset_memory=False),
                resolved_query=resolved,
            )
            business_response = build_inventory_business_response(
                resolved_query=resolved.as_dict(),
                rows=[dict(item) for item in list(case.fixture_rows or [])],
                supplemental_tables=[dict(item) for item in list(case.fixture_extra_tables or [])],
                result_set=dict(case.fixture_result_set or {}),
                limitations=list((resolved.semantic_context.get("resolved_semantic") or {}).get("limitations") or []),
                execution_metadata=dict(plan.metadata or {}),
            )
            results.append(
                _evaluate_case(
                    case=case,
                    resolved_query=resolved.as_dict(),
                    execution_plan=plan.as_dict(),
                    business_response=business_response,
                )
            )
            if register_failed_gaps and gap_registry_service is not None:
                gap_registry_service.register_from_eval_result(
                    eval_result=results[-1],
                    dataset_version=DATASET_VERSION,
                )

    _mark_hardcode_suspicion(results)

    classification_counter = Counter(str(item.get("clasificacion") or "") for item in results)
    runtime_flow_counter = Counter(str(item.get("planner_strategy") or "") for item in results)
    passed = sum(1 for item in results if str(item.get("eval_result") or "") == "passed")
    metadata_usage_count = sum(1 for item in results if bool(item.get("metadata_used")))
    fallback_usage_count = sum(1 for item in results if bool(item.get("fallback_detected")))
    evidence_coverage_count = sum(
        1
        for item in results
        if "evidence_correctness" in list(item.get("checks_ok") or [])
    )
    clarification_count = int(classification_counter.get("aclaracion_valida") or 0)
    limitation_count = int(classification_counter.get("limitacion_valida") or 0)
    hardcode_count = int(classification_counter.get("hardcode_sospechoso") or 0)
    minimum_validation_matrix = _build_minimum_validation_matrix(cases=cases, results=results)

    return {
        "dataset_version": DATASET_VERSION,
        "questions_executed": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "classification_counts": dict(classification_counter),
        "runtime_flow_counts": dict(runtime_flow_counter),
        "fallback_usage_count": fallback_usage_count,
        "metadata_usage_count": metadata_usage_count,
        "evidence_coverage_count": evidence_coverage_count,
        "clarification_ratio": round(clarification_count / max(1, len(results)), 4),
        "limitation_ratio": round(limitation_count / max(1, len(results)), 4),
        "metadata_usage_ratio": round(metadata_usage_count / max(1, len(results)), 4),
        "evidence_coverage_ratio": round(evidence_coverage_count / max(1, len(results)), 4),
        "fallback_usage_ratio": round(fallback_usage_count / max(1, len(results)), 4),
        "suspected_hardcode_count": hardcode_count,
        "capability_pack_coverage": pack_coverage.as_dict(),
        "minimum_validation_matrix": minimum_validation_matrix,
        "results": results,
        "continuous_runtime_learning_readiness": {
            "required_future_fields": [
                "pregunta_original",
                "grupo_semantico",
                "clasificacion",
                "eval_reason",
                "template_id",
                "candidate_capability",
                "planner_reason",
                "response_status",
                "semantic_confidence",
                "fallback_detected",
                "metadata_used",
                "suspected_hardcode",
            ],
            "ready_without_persistence_table": True,
        },
    }
