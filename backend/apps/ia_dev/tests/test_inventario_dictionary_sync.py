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
        return {
            "base_codigos": InventoryTableMetadata(
                table_name="base_codigos",
                columns={
                    "codigo": "varchar",
                    "descripcion": "varchar",
                },
            ),
            "logistica_movimientos_entrada": InventoryTableMetadata(
                table_name="logistica_movimientos_entrada",
                columns={
                    "id": "int",
                    "codigo": "varchar",
                    "cantidad": "decimal",
                    "fecha": "date",
                    "bodega": "varchar",
                    "responsable": "varchar",
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
