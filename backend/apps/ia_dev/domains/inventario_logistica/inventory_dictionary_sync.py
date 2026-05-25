from __future__ import annotations

import json
from typing import Any

from django.db import connections, transaction

from .inventory_dictionary_audit import InventoryDictionaryAuditService
from .yaml_agent_loader import (
    get_business_concepts,
    get_business_rules,
    get_examples_as_query_patterns,
    get_fields_for_dictionary,
    get_governed_column_capabilities,
    get_governed_rules_for_dictionary,
    get_governed_synonyms_for_dictionary,
    get_groupable_dimensions,
    get_relationships_for_dictionary,
    get_runtime_domain_code,
    get_synonyms_for_dictionary,
    get_tables_for_dictionary,
    load_inventory_agent_yaml,
)


class InventoryDictionarySyncService:
    def __init__(self, *, audit_service: InventoryDictionaryAuditService | None = None):
        self.audit_service = audit_service or InventoryDictionaryAuditService()
        self._column_cache: dict[tuple[str, str, str], set[str]] = {}

    def build_preview(
        self,
        *,
        agent_code: str = "inventario_logistica",
        yaml_path: str | None = None,
    ) -> dict[str, Any]:
        config = load_inventory_agent_yaml(yaml_path)
        business_concepts = get_business_concepts(config)
        business_rules = get_business_rules(config)
        groupable_dimensions = get_groupable_dimensions(config)
        query_patterns = get_examples_as_query_patterns(config)
        preview = {
            "agent": str(agent_code or get_runtime_domain_code(config)),
            "runtime_domain_code": get_runtime_domain_code(config),
            "dd_tablas": get_tables_for_dictionary(config),
            "dd_campos": get_fields_for_dictionary(config),
            "dd_relaciones": get_relationships_for_dictionary(config),
            "dd_sinonimos": self._merge_preview_rows(
                [*get_synonyms_for_dictionary(config), *get_governed_synonyms_for_dictionary(config)],
                key_builder=lambda row: (
                    str((row or {}).get("synonym") or "").strip().lower(),
                    str((row or {}).get("canonical_value") or "").strip().lower(),
                    str((row or {}).get("target_type") or "").strip().lower(),
                ),
            ),
            "dd_reglas": self._merge_preview_rows(
                get_governed_rules_for_dictionary(config),
                key_builder=lambda row: str((row or {}).get("codigo") or (row or {}).get("rule_name") or "").strip().lower(),
            ),
            "ia_dev_capacidades_columna": self._merge_preview_rows(
                get_governed_column_capabilities(config),
                key_builder=lambda row: (
                    str((row or {}).get("campo_logico") or "").strip().lower(),
                    str((row or {}).get("table_name") or "").strip().lower(),
                    str((row or {}).get("column_name") or "").strip().lower(),
                ),
            ),
            "query_patterns": query_patterns,
            "semantic_metadata": {
                "business_concepts": business_concepts,
                "business_rules": business_rules,
                "groupable_dimensions": groupable_dimensions,
            },
        }
        return preview

    def sync(
        self,
        *,
        agent_code: str = "inventario_logistica",
        mode: str = "dry_run",
        yaml_path: str | None = None,
        database_alias: str = "default",
    ) -> dict[str, Any]:
        normalized_mode = str(mode or "dry_run").strip().lower()
        preview = self.build_preview(agent_code=agent_code, yaml_path=yaml_path)
        audit = self.audit_service.audit(
            agent_code=agent_code,
            database_alias="logistica_cinco",
            yaml_path=yaml_path,
        )
        warnings = list(audit.get("warnings") or [])
        if normalized_mode == "audit_only":
            return {
                "agent": agent_code,
                "mode": "audit_only",
                "dd_tablas_preview_count": len(list(preview.get("dd_tablas") or [])),
                "dd_campos_preview_count": len(list(preview.get("dd_campos") or [])),
                "dd_relaciones_preview_count": len(list(preview.get("dd_relaciones") or [])),
                "dd_sinonimos_preview_count": len(list(preview.get("dd_sinonimos") or [])),
                "dd_reglas_preview_count": len(list(preview.get("dd_reglas") or [])),
                "ia_dev_capacidades_columna_preview_count": len(list(preview.get("ia_dev_capacidades_columna") or [])),
                "query_patterns_preview_count": len(list(preview.get("query_patterns") or [])),
                "warnings": warnings,
                "status": str(audit.get("status") or "warning"),
                "audit": audit,
            }

        payload = {
            "agent": agent_code,
            "mode": "apply" if normalized_mode == "apply" else "dry_run",
            "dd_tablas_preview_count": len(list(preview.get("dd_tablas") or [])),
            "dd_campos_preview_count": len(list(preview.get("dd_campos") or [])),
            "dd_relaciones_preview_count": len(list(preview.get("dd_relaciones") or [])),
            "dd_sinonimos_preview_count": len(list(preview.get("dd_sinonimos") or [])),
            "dd_reglas_preview_count": len(list(preview.get("dd_reglas") or [])),
            "ia_dev_capacidades_columna_preview_count": len(list(preview.get("ia_dev_capacidades_columna") or [])),
            "query_patterns_preview_count": len(list(preview.get("query_patterns") or [])),
            "warnings": warnings,
            "status": "passed" if str(audit.get("status") or "") != "failed" else "failed",
            "preview": preview,
            "audit": audit,
        }
        if normalized_mode != "apply":
            return payload

        apply_result = self._apply_preview(preview=preview, database_alias=database_alias)
        payload["apply_result"] = apply_result
        if not bool(apply_result.get("ok")):
            payload["status"] = "failed"
            payload["warnings"] = [*warnings, *list(apply_result.get("warnings") or [])]
        return payload

    def _apply_preview(self, *, preview: dict[str, Any], database_alias: str) -> dict[str, Any]:
        schema = "ai_dictionary"
        inserted = {
            "dd_dominios": 0,
            "dd_tablas": 0,
            "dd_campos": 0,
            "dd_relaciones": 0,
            "dd_sinonimos": 0,
            "dd_reglas": 0,
            "ia_dev_capacidades_columna": 0,
        }
        updated = {
            "dd_dominios": 0,
            "dd_tablas": 0,
            "dd_campos": 0,
            "dd_relaciones": 0,
            "dd_sinonimos": 0,
            "dd_reglas": 0,
            "ia_dev_capacidades_columna": 0,
        }
        warnings: list[str] = []
        connection = connections[database_alias]
        try:
            with transaction.atomic(using=database_alias):
                with connection.cursor() as cursor:
                    cursor.execute(
                        f"""
                        INSERT INTO {schema}.dd_dominios (codigo, nombre, descripcion)
                        SELECT %s, %s, %s
                        WHERE NOT EXISTS (
                            SELECT 1 FROM {schema}.dd_dominios WHERE UPPER(COALESCE(codigo, '')) = UPPER(%s)
                        )
                        """,
                        [
                            preview.get("runtime_domain_code") or "inventario_logistica",
                            "Inventario Logistica",
                            "Dominio hibrido de inventario y logistica",
                            preview.get("runtime_domain_code") or "inventario_logistica",
                        ],
                    )
                    inserted["dd_dominios"] += int(getattr(cursor, "rowcount", 0) or 0)
                    cursor.execute(
                        f"""
                        UPDATE {schema}.dd_dominios
                        SET nombre = %s, descripcion = %s
                        WHERE UPPER(COALESCE(codigo, '')) = UPPER(%s)
                        """,
                        [
                            "Inventario Logistica",
                            "Dominio hibrido de inventario y logistica",
                            preview.get("runtime_domain_code") or "inventario_logistica",
                        ],
                    )
                    updated["dd_dominios"] += int(getattr(cursor, "rowcount", 0) or 0)

                    domain_code = str(preview.get("runtime_domain_code") or "inventario_logistica")
                    cursor.execute(
                        f"SELECT id FROM {schema}.dd_dominios WHERE UPPER(COALESCE(codigo, '')) = UPPER(%s) LIMIT 1",
                        [domain_code],
                    )
                    row = cursor.fetchone()
                    if not row:
                        return {"ok": False, "warnings": ["No fue posible resolver dominio en ai_dictionary."]}
                    domain_id = int(row[0] or 0)

                    tabla_ids: dict[str, int] = {}
                    for table in list(preview.get("dd_tablas") or []):
                        cursor.execute(
                            f"""
                            INSERT INTO {schema}.dd_tablas (dominio_id, schema_name, table_name, alias_negocio, descripcion)
                            SELECT %s, %s, %s, %s, %s
                            WHERE NOT EXISTS (
                                SELECT 1 FROM {schema}.dd_tablas
                                WHERE dominio_id = %s
                                  AND LOWER(COALESCE(schema_name, '')) = LOWER(%s)
                                  AND LOWER(COALESCE(table_name, '')) = LOWER(%s)
                            )
                            """,
                            [
                                domain_id,
                                table.get("schema_name") or "",
                                table.get("table_name"),
                                table.get("business_name"),
                                table.get("description"),
                                domain_id,
                                table.get("schema_name") or "",
                                table.get("table_name"),
                            ],
                        )
                        inserted["dd_tablas"] += int(getattr(cursor, "rowcount", 0) or 0)
                        cursor.execute(
                            f"""
                            UPDATE {schema}.dd_tablas
                            SET alias_negocio = %s, descripcion = %s
                            WHERE dominio_id = %s
                              AND LOWER(COALESCE(schema_name, '')) = LOWER(%s)
                              AND LOWER(COALESCE(table_name, '')) = LOWER(%s)
                            """,
                            [
                                table.get("business_name"),
                                table.get("description"),
                                domain_id,
                                table.get("schema_name") or "",
                                table.get("table_name"),
                            ],
                        )
                        updated["dd_tablas"] += int(getattr(cursor, "rowcount", 0) or 0)
                        cursor.execute(
                            f"""
                            SELECT id FROM {schema}.dd_tablas
                            WHERE dominio_id = %s
                              AND LOWER(COALESCE(schema_name, '')) = LOWER(%s)
                              AND LOWER(COALESCE(table_name, '')) = LOWER(%s)
                            LIMIT 1
                            """,
                            [domain_id, table.get("schema_name") or "", table.get("table_name")],
                        )
                        tabla_row = cursor.fetchone()
                        if tabla_row:
                            tabla_ids[str(table.get("table_name") or "")] = int(tabla_row[0] or 0)

                    dd_campos_columns = self._get_table_columns(
                        database_alias=database_alias,
                        schema=schema,
                        table_name="dd_campos",
                    )
                    for field in list(preview.get("dd_campos") or []):
                        if not bool(field.get("sync_to_dd_campos", True)):
                            continue
                        tabla_id = tabla_ids.get(str(field.get("table_name") or ""))
                        if not tabla_id:
                            warnings.append(f"No se pudo vincular campo a tabla: {field.get('table_name')}.{field.get('column_name')}")
                            continue
                        field_payload = self._build_field_payload(
                            field=field,
                            tabla_id=tabla_id,
                            available_columns=dd_campos_columns,
                        )
                        field_result = self._upsert_row(
                            cursor=cursor,
                            schema=schema,
                            table_name="dd_campos",
                            payload=field_payload,
                            key_columns=["tabla_id", "column_name"],
                        )
                        inserted["dd_campos"] += field_result["inserted"]
                        updated["dd_campos"] += field_result["updated"]

                    dd_relaciones_columns = self._get_table_columns(
                        database_alias=database_alias,
                        schema=schema,
                        table_name="dd_relaciones",
                    )
                    for relation in list(preview.get("dd_relaciones") or []):
                        if not bool(relation.get("sync_to_dd_relaciones", True)):
                            continue
                        tabla_origen_id = tabla_ids.get(str(relation.get("from_table") or ""))
                        tabla_destino_id = tabla_ids.get(str(relation.get("to_table") or ""))
                        if not tabla_origen_id or not tabla_destino_id:
                            warnings.append(
                                f"No se pudo vincular relacion: {relation.get('code')} ({relation.get('from_table')}->{relation.get('to_table')})"
                            )
                            continue
                        relation_payload = self._build_relation_payload(
                            relation=relation,
                            tabla_origen_id=tabla_origen_id,
                            tabla_destino_id=tabla_destino_id,
                            available_columns=dd_relaciones_columns,
                        )
                        relation_result = self._upsert_row(
                            cursor=cursor,
                            schema=schema,
                            table_name="dd_relaciones",
                            payload=relation_payload,
                            key_columns=["tabla_origen_id", "tabla_destino_id", "nombre_relacion"],
                        )
                        inserted["dd_relaciones"] += relation_result["inserted"]
                        updated["dd_relaciones"] += relation_result["updated"]

                    dd_sinonimos_columns = self._get_table_columns(
                        database_alias=database_alias,
                        schema=schema,
                        table_name="dd_sinonimos",
                    )
                    for synonym in list(preview.get("dd_sinonimos") or []):
                        synonym_payload = self._build_synonym_payload(
                            synonym=synonym,
                            domain_id=domain_id,
                            available_columns=dd_sinonimos_columns,
                        )
                        synonym_result = self._upsert_row(
                            cursor=cursor,
                            schema=schema,
                            table_name="dd_sinonimos",
                            payload=synonym_payload,
                            key_columns=["termino", "sinonimo"],
                        )
                        inserted["dd_sinonimos"] += synonym_result["inserted"]
                        updated["dd_sinonimos"] += synonym_result["updated"]

                    dd_reglas_columns = self._get_table_columns(
                        database_alias=database_alias,
                        schema=schema,
                        table_name="dd_reglas",
                    )
                    for rule in list(preview.get("dd_reglas") or []):
                        rule_payload = self._build_rule_payload(
                            rule=rule,
                            domain_id=domain_id,
                            agent_code=str(preview.get("agent") or preview.get("runtime_domain_code") or "inventario_logistica"),
                            available_columns=dd_reglas_columns,
                        )
                        rule_result = self._upsert_row(
                            cursor=cursor,
                            schema=schema,
                            table_name="dd_reglas",
                            payload=rule_payload,
                            key_columns=["dominio_id", "codigo"],
                        )
                        inserted["dd_reglas"] += rule_result["inserted"]
                        updated["dd_reglas"] += rule_result["updated"]

                    capability_columns = self._get_table_columns(
                        database_alias=database_alias,
                        schema=schema,
                        table_name="ia_dev_capacidades_columna",
                    )
                    for capability in list(preview.get("ia_dev_capacidades_columna") or []):
                        capability_payload = self._build_column_capability_payload(
                            capability=capability,
                            fields=list(preview.get("dd_campos") or []),
                            tabla_ids=tabla_ids,
                            database_alias=database_alias,
                            schema=schema,
                            available_columns=capability_columns,
                        )
                        capability_result = self._upsert_row(
                            cursor=cursor,
                            schema=schema,
                            table_name="ia_dev_capacidades_columna",
                            payload=capability_payload,
                            key_columns=["campo_id"],
                        )
                        inserted["ia_dev_capacidades_columna"] += capability_result["inserted"]
                        updated["ia_dev_capacidades_columna"] += capability_result["updated"]
        except Exception as exc:
            return {"ok": False, "warnings": [str(exc)], "inserted": inserted, "updated": updated}
        return {"ok": True, "warnings": warnings, "inserted": inserted, "updated": updated}

    @staticmethod
    def _merge_preview_rows(rows: list[dict[str, Any]], *, key_builder) -> list[dict[str, Any]]:
        merged: dict[Any, dict[str, Any]] = {}
        for row in rows:
            if not isinstance(row, dict):
                continue
            key = key_builder(row)
            if not key:
                continue
            merged[key] = {**dict(merged.get(key) or {}), **dict(row)}
        return list(merged.values())

    def _get_table_columns(self, *, database_alias: str, schema: str, table_name: str) -> set[str]:
        cache_key = (database_alias, schema, table_name)
        cached = self._column_cache.get(cache_key)
        if cached is not None:
            return cached
        with connections[database_alias].cursor() as cursor:
            cursor.execute(
                """
                SELECT COLUMN_NAME
                FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
                """,
                [schema, table_name],
            )
            columns = {str(row[0] or "").strip() for row in cursor.fetchall() if str(row[0] or "").strip()}
        self._column_cache[cache_key] = columns
        return columns

    def _build_field_payload(
        self,
        *,
        field: dict[str, Any],
        tabla_id: int,
        available_columns: set[str],
    ) -> dict[str, Any]:
        technical_type = str(field.get("data_type") or "").strip() or "string"
        payload = {
            "tabla_id": tabla_id,
            "campo_logico": field.get("semantic_role") or field.get("column_name"),
            "column_name": field.get("column_name"),
            "tipo_campo": self._normalize_field_storage_type(technical_type),
            "tipo_dato_tecnico": technical_type,
            "definicion_negocio": self._json_text(
                {
                    "semantic_role": field.get("semantic_role"),
                    "business_concepts": field.get("business_concepts"),
                    "allowed_operations": field.get("allowed_operations"),
                    "synonyms": field.get("synonyms"),
                    "note": field.get("note"),
                }
            ),
            "valores_permitidos": self._json_text(field.get("allowed_operations") or []),
            "ejemplo_valor": self._first_non_empty(
                [
                    field.get("column_name"),
                    *(list(field.get("synonyms") or [])),
                ]
            ),
            "es_clave": 1 if field.get("required") else 0,
            "activo": 1,
        }
        return {key: value for key, value in payload.items() if key in available_columns}

    def _build_relation_payload(
        self,
        *,
        relation: dict[str, Any],
        tabla_origen_id: int,
        tabla_destino_id: int,
        available_columns: set[str],
    ) -> dict[str, Any]:
        payload = {
            "tabla_origen_id": tabla_origen_id,
            "tabla_destino_id": tabla_destino_id,
            "nombre_relacion": relation.get("code"),
            "join_sql": relation.get("join_sql"),
            "cardinalidad": self._normalize_cardinality(relation.get("relationship_type")),
            "descripcion": relation.get("join_purpose"),
            "activa": 1 if relation.get("allowed", True) else 0,
        }
        return {key: value for key, value in payload.items() if key in available_columns}

    def _build_synonym_payload(
        self,
        *,
        synonym: dict[str, Any],
        domain_id: int,
        available_columns: set[str],
    ) -> dict[str, Any]:
        payload = {
            "dominio_id": domain_id,
            "termino": synonym.get("canonical_value"),
            "sinonimo": synonym.get("synonym"),
            "activo": 1,
        }
        return {key: value for key, value in payload.items() if key in available_columns}

    def _build_rule_payload(
        self,
        *,
        rule: dict[str, Any],
        domain_id: int,
        agent_code: str,
        available_columns: set[str],
    ) -> dict[str, Any]:
        rule_name = str(rule.get("rule_name") or "").strip() or "regla_sin_nombre"
        payload = {
            "dominio_id": domain_id,
            "codigo": rule_name,
            "nombre": rule_name,
            "condicion_sql": self._first_non_empty(
                [
                    rule.get("condition_sql"),
                    rule.get("description"),
                ]
            ),
            "resultado_funcional": self._json_text(rule),
            "tablas_relacionadas": self._json_text(rule.get("related_tables") or []),
            "agente_creador": agent_code,
            "estado": "activa",
            "prioridad": int(rule.get("priority") or 100),
            "activo": 1,
        }
        return {key: value for key, value in payload.items() if key in available_columns}

    def _build_column_capability_payload(
        self,
        *,
        capability: dict[str, Any],
        fields: list[dict[str, Any]],
        tabla_ids: dict[str, int],
        database_alias: str,
        schema: str,
        available_columns: set[str],
    ) -> dict[str, Any]:
        campo_id = self._resolve_dictionary_field_id(
            fields=fields,
            tabla_ids=tabla_ids,
            table_name=str(capability.get("table_name") or ""),
            column_name=str(capability.get("column_name") or ""),
            database_alias=database_alias,
            schema=schema,
        )
        if not campo_id:
            return {}
        payload = {
            "campo_id": campo_id,
            "supports_filter": 1 if capability.get("supports_filter") else 0,
            "supports_group_by": 1 if capability.get("supports_group_by") else 0,
            "supports_metric": 1 if capability.get("supports_metric") else 0,
            "supports_dimension": 1 if capability.get("supports_dimension") else 0,
            "is_date": 1 if capability.get("is_date") else 0,
            "is_identifier": 1 if capability.get("is_identifier") else 0,
            "is_chart_dimension": 1 if capability.get("is_chart_dimension") else 0,
            "is_chart_measure": 1 if capability.get("is_chart_measure") else 0,
            "allowed_operators_json": self._json_text(capability.get("capabilities_compatibles") or []),
            "allowed_aggregations_json": self._json_text(capability.get("capabilities_compatibles") or []),
            "normalization_strategy": capability.get("normalization_strategy"),
            "priority": int(capability.get("priority") or 90),
            "active": 1 if capability.get("active", True) else 0,
        }
        return {key: value for key, value in payload.items() if key in available_columns}

    def _resolve_dictionary_field_id(
        self,
        *,
        fields: list[dict[str, Any]],
        tabla_ids: dict[str, int],
        table_name: str,
        column_name: str,
        database_alias: str,
        schema: str,
    ) -> int:
        tabla_id = tabla_ids.get(str(table_name or ""))
        if not tabla_id:
            return 0
        field_exists = any(
            str(item.get("table_name") or "") == str(table_name or "")
            and str(item.get("column_name") or "") == str(column_name or "")
            for item in list(fields or [])
            if isinstance(item, dict)
        )
        if not field_exists:
            return 0
        with connections[database_alias].cursor() as cursor:
            cursor.execute(
                f"""
                SELECT id
                FROM {schema}.dd_campos
                WHERE tabla_id = %s AND LOWER(COALESCE(column_name, '')) = LOWER(%s)
                LIMIT 1
                """,
                [tabla_id, column_name],
            )
            row = cursor.fetchone()
        return int((row or [0])[0] or 0)

    def _upsert_row(
        self,
        *,
        cursor: Any,
        schema: str,
        table_name: str,
        payload: dict[str, Any],
        key_columns: list[str],
    ) -> dict[str, int]:
        filtered_payload = {
            key: value
            for key, value in payload.items()
            if value is not None and str(key or "").strip()
        }
        filtered_key_columns = [column for column in key_columns if column in filtered_payload]
        if not filtered_payload or len(filtered_key_columns) != len(key_columns):
            return {"inserted": 0, "updated": 0}

        insert_columns = list(filtered_payload.keys())
        insert_sql = ", ".join(insert_columns)
        insert_placeholders = ", ".join(["%s"] * len(insert_columns))
        where_sql = " AND ".join(
            f"LOWER(COALESCE({column}, '')) = LOWER(%s)" if self._is_textual_value(filtered_payload[column]) else f"{column} = %s"
            for column in filtered_key_columns
        )
        insert_params = [filtered_payload[column] for column in insert_columns]
        where_params = [filtered_payload[column] for column in filtered_key_columns]
        cursor.execute(
            f"""
            INSERT INTO {schema}.{table_name} ({insert_sql})
            SELECT {insert_placeholders}
            WHERE NOT EXISTS (
                SELECT 1 FROM {schema}.{table_name}
                WHERE {where_sql}
            )
            """,
            [*insert_params, *where_params],
        )
        inserted = int(getattr(cursor, "rowcount", 0) or 0)

        update_columns = [column for column in insert_columns if column not in filtered_key_columns]
        updated = 0
        if update_columns:
            update_set_sql = ", ".join(f"{column} = %s" for column in update_columns)
            cursor.execute(
                f"""
                UPDATE {schema}.{table_name}
                SET {update_set_sql}
                WHERE {where_sql}
                """,
                [*[filtered_payload[column] for column in update_columns], *where_params],
            )
            updated = int(getattr(cursor, "rowcount", 0) or 0)
        return {"inserted": inserted, "updated": updated}

    @staticmethod
    def _normalize_field_storage_type(technical_type: str) -> str:
        normalized = str(technical_type or "").strip().lower()
        if normalized in {"json", "jsonb", "dict", "object"}:
            return "JSON"
        return "LITERAL"

    @staticmethod
    def _normalize_cardinality(relationship_type: Any) -> str:
        normalized = str(relationship_type or "").strip().lower()
        mapping = {
            "many_to_one": "N:1",
            "one_to_many": "1:N",
            "one_to_one": "1:1",
            "many_to_many": "N:N",
        }
        return mapping.get(normalized, str(relationship_type or "N:1"))

    @staticmethod
    def _json_text(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False)

    @staticmethod
    def _first_non_empty(values: list[Any]) -> Any:
        for value in values:
            if value is None:
                continue
            if isinstance(value, str) and not value.strip():
                continue
            return value
        return None

    @staticmethod
    def _is_textual_value(value: Any) -> bool:
        return isinstance(value, str)
