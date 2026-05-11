from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.db import connections

from .yaml_agent_loader import (
    get_fields_for_dictionary,
    get_groupable_dimensions,
    get_relationships_for_dictionary,
    get_runtime_domain_code,
    get_tables_for_dictionary,
    load_inventory_agent_yaml,
    validate_yaml_integrity,
)


DATE_TYPE_HINTS = ("date", "datetime", "timestamp", "time")


@dataclass(slots=True)
class InventoryTableMetadata:
    table_name: str
    columns: dict[str, str]


class InventoryDatabaseInspector:
    def __init__(self, *, database_alias: str):
        self.database_alias = str(database_alias or "default").strip() or "default"

    def get_tables(self) -> dict[str, InventoryTableMetadata]:
        metadata: dict[str, InventoryTableMetadata] = {}
        connection = connections[self.database_alias]
        with connection.cursor() as cursor:
            for table_info in connection.introspection.get_table_list(cursor):
                table_name = str(getattr(table_info, "name", "") or "").strip()
                if not table_name:
                    continue
                columns: dict[str, str] = {}
                try:
                    description = connection.introspection.get_table_description(cursor, table_name)
                except Exception:
                    description = []
                for column in description:
                    column_name = str(getattr(column, "name", "") or "").strip()
                    type_name = str(
                        getattr(column, "type_code", "")
                        or getattr(column, "internal_size", "")
                        or ""
                    ).strip().lower()
                    columns[column_name] = type_name
                metadata[table_name] = InventoryTableMetadata(table_name=table_name, columns=columns)
        return metadata

    def get_tables_for_schemas(self, schemas: set[str], table_names: set[str] | None = None) -> dict[str, InventoryTableMetadata]:
        requested = {str(item or "").strip() for item in set(schemas or set()) if str(item or "").strip()}
        if not requested:
            return {}
        requested_tables = {
            str(item or "").strip()
            for item in set(table_names or set())
            if str(item or "").strip()
        }
        metadata: dict[str, InventoryTableMetadata] = {}
        connection = connections[self.database_alias]
        with connection.cursor() as cursor:
            placeholders = ", ".join(["%s"] * len(requested))
            params: list[str] = sorted(requested)
            table_filter = ""
            if requested_tables:
                table_placeholders = ", ".join(["%s"] * len(requested_tables))
                table_filter = f" AND TABLE_NAME IN ({table_placeholders})"
                params.extend(sorted(requested_tables))
            cursor.execute(
                f"""
                SELECT TABLE_NAME, COLUMN_NAME, COLUMN_TYPE
                FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_SCHEMA IN ({placeholders}){table_filter}
                ORDER BY TABLE_SCHEMA, TABLE_NAME, ORDINAL_POSITION
                """,
                params,
            )
            for table_name, column_name, column_type in cursor.fetchall():
                clean_table = str(table_name or "").strip()
                clean_column = str(column_name or "").strip()
                if not clean_table or not clean_column:
                    continue
                metadata.setdefault(clean_table, InventoryTableMetadata(table_name=clean_table, columns={}))
                metadata[clean_table].columns[clean_column] = str(column_type or "").strip().lower()
        return metadata


class InventoryDictionaryAuditService:
    def __init__(self, *, inspector_class=InventoryDatabaseInspector):
        self.inspector_class = inspector_class

    @staticmethod
    def _is_date_compatible(type_name: str) -> bool:
        normalized = str(type_name or "").strip().lower()
        if not normalized:
            return False
        if normalized in {"7", "10", "11", "12"}:
            return True
        return any(token in normalized for token in DATE_TYPE_HINTS)

    def audit(
        self,
        *,
        agent_code: str = "inventario_logistica",
        database_alias: str = "logistica_cinco",
        yaml_path: str | None = None,
    ) -> dict[str, Any]:
        config = load_inventory_agent_yaml(yaml_path)
        integrity = validate_yaml_integrity(config)
        tables_declared = get_tables_for_dictionary(config)
        fields_declared = get_fields_for_dictionary(config)
        relationships_declared = get_relationships_for_dictionary(config)
        groupable_declared = get_groupable_dimensions(config)
        try:
            inspector = self.inspector_class(database_alias=database_alias)
            tables_metadata = inspector.get_tables()
            extra_schemas = {
                str(table.get("schema_name") or "").strip()
                for table in tables_declared
                if str(table.get("schema_name") or "").strip()
            }
            if extra_schemas and hasattr(inspector, "get_tables_for_schemas"):
                extra_table_names = {
                    str(table.get("table_name") or "").strip()
                    for table in tables_declared
                    if str(table.get("schema_name") or "").strip()
                }
                tables_metadata.update(inspector.get_tables_for_schemas(extra_schemas, extra_table_names))
        except Exception as exc:
            return {
                "agent": str(agent_code or get_runtime_domain_code(config)),
                "database": database_alias,
                "tables_ok": [],
                "tables_missing": [],
                "columns_ok": [],
                "columns_missing": [],
                "relationships_ok": [],
                "relationships_missing": [],
                "groupable_ok": [],
                "groupable_missing": [],
                "warnings": [f"database_connection_unavailable:{exc}"],
                "status": "failed",
                "yaml_integrity": integrity,
            }

        tables_ok: list[str] = []
        tables_missing: list[str] = []
        columns_ok: list[str] = []
        columns_missing: list[dict[str, Any]] = []
        relationships_ok: list[str] = []
        relationships_missing: list[dict[str, Any]] = []
        groupable_ok: list[str] = []
        groupable_missing: list[dict[str, Any]] = []
        warnings: list[str] = list(integrity.get("warnings") or [])

        for table in tables_declared:
            table_name = str(table.get("table_name") or "")
            if table_name in tables_metadata:
                tables_ok.append(table_name)
            else:
                tables_missing.append(table_name)

        for field in fields_declared:
            table_name = str(field.get("table_name") or "")
            column_name = str(field.get("column_name") or "")
            metadata = tables_metadata.get(table_name)
            if metadata and column_name in metadata.columns:
                columns_ok.append(f"{table_name}.{column_name}")
                if str(field.get("data_type") or "").strip().lower() == "date":
                    real_type = str(metadata.columns.get(column_name) or "")
                    if real_type and not self._is_date_compatible(real_type):
                        warnings.append(
                            f"Campo declarado date no parece compatible: {table_name}.{column_name} ({real_type})"
                        )
                continue
            payload = {
                "table": table_name,
                "column": column_name,
                "missing_metadata_allowed": bool(field.get("missing_metadata_allowed")),
            }
            columns_missing.append(payload)
            if bool(field.get("missing_metadata_allowed")):
                warnings.append(f"Metadata faltante permitida: {table_name}.{column_name}")

        for relationship in relationships_declared:
            from_table = str(relationship.get("from_table") or "")
            to_table = str(relationship.get("to_table") or "")
            from_column = str(relationship.get("from_column") or "")
            to_column = str(relationship.get("to_column") or "")
            from_exists = from_table in tables_metadata and from_column in tables_metadata[from_table].columns
            to_exists = to_table in tables_metadata and to_column in tables_metadata[to_table].columns
            if from_exists and to_exists:
                relationships_ok.append(str(relationship.get("code") or ""))
            else:
                relationships_missing.append(
                    {
                        "code": str(relationship.get("code") or ""),
                        "from_table": from_table,
                        "from_column": from_column,
                        "to_table": to_table,
                        "to_column": to_column,
                    }
                )

        for dimension in groupable_declared:
            dimension_name = str(dimension.get("dimension_name") or "")
            unresolved: list[str] = []
            for field_ref in list(dimension.get("canonical_fields") or []):
                table_name, _, column_name = str(field_ref or "").partition(".")
                if not table_name or not column_name:
                    unresolved.append(str(field_ref))
                    continue
                if table_name not in tables_metadata or column_name not in tables_metadata[table_name].columns:
                    unresolved.append(str(field_ref))
            if unresolved:
                groupable_missing.append({"dimension": dimension_name, "missing_fields": unresolved})
            else:
                groupable_ok.append(dimension_name)

        failed = bool(tables_missing)
        failed = failed or any(not bool(item.get("missing_metadata_allowed")) for item in columns_missing)
        failed = failed or bool(relationships_missing)
        if failed:
            status = "failed"
        elif warnings:
            status = "warning"
        else:
            status = "passed"

        return {
            "agent": str(agent_code or get_runtime_domain_code(config)),
            "database": database_alias,
            "tables_ok": sorted(tables_ok),
            "tables_missing": sorted(tables_missing),
            "columns_ok": sorted(columns_ok),
            "columns_missing": columns_missing,
            "relationships_ok": sorted(relationships_ok),
            "relationships_missing": relationships_missing,
            "groupable_ok": sorted(groupable_ok),
            "groupable_missing": groupable_missing,
            "warnings": warnings,
            "status": status,
            "yaml_integrity": integrity,
        }
