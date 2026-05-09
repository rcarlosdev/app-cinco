from __future__ import annotations

from django.test import SimpleTestCase

from apps.ia_dev.domains.inventario_logistica.inventory_dictionary_audit import (
    InventoryDictionaryAuditService,
    InventoryTableMetadata,
)
from apps.ia_dev.domains.inventario_logistica.inventory_dictionary_sync import (
    InventoryDictionarySyncService,
)


class _InspectorCompleto:
    def __init__(self, *, database_alias: str):
        self.database_alias = database_alias

    def get_tables(self):
        movement_columns = {
            "id": "int",
            "codigo": "varchar",
            "cantidad": "varchar",
            "f_consumo": "datetime",
            "orden_trabajo": "varchar",
            "tipo": "varchar",
            "serial": "varchar",
            "comentario": "text",
            "movimiento": "varchar",
            "documento": "varchar",
            "proveedor": "varchar",
            "bodega": "varchar",
            "cedula": "varchar",
            "estado": "varchar",
        }
        serial_columns = {
            "id": "int",
            "numero_serial": "varchar",
            "codigo": "varchar",
            "estado": "varchar",
            "cedula": "varchar",
            "fecha": "datetime",
            "ubicacion_bodega": "varchar",
            "movimiento_sap": "varchar",
            "bodega": "varchar",
            "historial": "longtext",
        }
        return {
            "base_codigos": InventoryTableMetadata(
                table_name="base_codigos",
                columns={
                    "codigo": "varchar",
                    "descripcion": "varchar",
                    "tipo": "varchar",
                    "medida": "varchar",
                },
            ),
            "base_codigo_seriales": InventoryTableMetadata(
                table_name="base_codigo_seriales",
                columns={
                    "codigo": "varchar",
                    "descripcion": "varchar",
                    "familia": "varchar",
                },
            ),
            "logistica_movimientos_entrada": InventoryTableMetadata(
                table_name="logistica_movimientos_entrada",
                columns=movement_columns,
            ),
            "logistica_movimientos_entrega": InventoryTableMetadata(
                table_name="logistica_movimientos_entrega",
                columns=movement_columns,
            ),
            "logistica_movimientos_devolucion": InventoryTableMetadata(
                table_name="logistica_movimientos_devolucion",
                columns=movement_columns,
            ),
            "logistica_movimientos_consumo": InventoryTableMetadata(
                table_name="logistica_movimientos_consumo",
                columns={**movement_columns, "datos": "json"},
            ),
            "logistica_movimientos_cobro": InventoryTableMetadata(
                table_name="logistica_movimientos_cobro",
                columns=movement_columns,
            ),
            "logistica_movimientos_traslado": InventoryTableMetadata(
                table_name="logistica_movimientos_traslado",
                columns=movement_columns,
            ),
            "logistica_base_seriales": InventoryTableMetadata(
                table_name="logistica_base_seriales",
                columns={**serial_columns, "notificacion": "json"},
            ),
            "logistica_seriales_asociados": InventoryTableMetadata(
                table_name="logistica_seriales_asociados",
                columns=serial_columns,
            ),
            "a_promedios_consumo": InventoryTableMetadata(
                table_name="a_promedios_consumo",
                columns={
                    "codigo": "int",
                    "familia_mat": "varchar",
                    "codigo_facturacion": "varchar",
                    "promedio": "decimal",
                },
            ),
            "facturacion_facturado_wfm": InventoryTableMetadata(
                table_name="facturacion_facturado_wfm",
                columns={
                    "idorden_de_trabajo": "int",
                    "codigo": "varchar",
                    "cantidad_actividad": "int",
                },
            ),
        }


class _InspectorConRelacionInvalida(_InspectorCompleto):
    def get_tables(self):
        payload = super().get_tables()
        payload.pop("base_codigos", None)
        return payload


class InventarioDictionarySyncTests(SimpleTestCase):
    def test_sync_dry_run_generates_preview_without_apply(self):
        service = InventoryDictionarySyncService(
            audit_service=InventoryDictionaryAuditService(inspector_class=_InspectorCompleto)
        )

        summary = service.sync(mode="dry_run")

        self.assertEqual(str(summary.get("mode") or ""), "dry_run")
        self.assertGreater(int(summary.get("dd_tablas_preview_count") or 0), 0)
        self.assertGreater(int(summary.get("dd_campos_preview_count") or 0), 0)
        self.assertGreater(int(summary.get("dd_relaciones_preview_count") or 0), 0)
        self.assertGreater(int(summary.get("dd_sinonimos_preview_count") or 0), 0)
        self.assertNotIn("apply_result", summary)

    def test_audit_reports_missing_columns_as_warning_when_allowed(self):
        audit = InventoryDictionaryAuditService(inspector_class=_InspectorCompleto)

        summary = audit.audit()

        self.assertEqual(str(summary.get("database") or ""), "logistica_cinco")
        self.assertTrue(bool(list(summary.get("columns_missing") or [])))
        self.assertTrue(
            any(bool(item.get("missing_metadata_allowed")) for item in list(summary.get("columns_missing") or []))
        )

    def test_audit_fails_when_relationship_points_to_missing_table(self):
        audit = InventoryDictionaryAuditService(inspector_class=_InspectorConRelacionInvalida)

        summary = audit.audit()

        self.assertEqual(str(summary.get("status") or ""), "failed")
        self.assertTrue(bool(list(summary.get("relationships_missing") or [])))
