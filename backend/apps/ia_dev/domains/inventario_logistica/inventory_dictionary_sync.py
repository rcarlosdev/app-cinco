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
            "dd_sinonimos": get_synonyms_for_dictionary(config),
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
                            INSERT INTO {schema}.dd_tablas (dominio_id, table_name, alias_negocio, descripcion)
                            SELECT %s, %s, %s, %s
                            WHERE NOT EXISTS (
                                SELECT 1 FROM {schema}.dd_tablas
                                WHERE dominio_id = %s AND LOWER(COALESCE(table_name, '')) = LOWER(%s)
                            )
                            """,
                            [
                                domain_id,
                                table.get("table_name"),
                                table.get("business_name"),
                                table.get("description"),
                                domain_id,
                                table.get("table_name"),
                            ],
                        )
                        inserted["dd_tablas"] += int(getattr(cursor, "rowcount", 0) or 0)
                        cursor.execute(
                            f"""
                            SELECT id FROM {schema}.dd_tablas
                            WHERE dominio_id = %s AND LOWER(COALESCE(table_name, '')) = LOWER(%s)
                            LIMIT 1
                            """,
                            [domain_id, table.get("table_name")],
                        )
                        tabla_row = cursor.fetchone()
                        if tabla_row:
                            tabla_ids[str(table.get("table_name") or "")] = int(tabla_row[0] or 0)

                    for field in list(preview.get("dd_campos") or []):
                        tabla_id = tabla_ids.get(str(field.get("table_name") or ""))
                        if not tabla_id:
                            warnings.append(f"No se pudo vincular campo a tabla: {field.get('table_name')}.{field.get('column_name')}")
                            continue
                        cursor.execute(
                            f"""
                            INSERT INTO {schema}.dd_campos (
                                tabla_id, campo_logico, column_name, tipo_campo, definicion_negocio,
                                es_filtro, es_group_by, es_metrica
                            )
                            SELECT %s, %s, %s, %s, %s, %s, %s, %s
                            WHERE NOT EXISTS (
                                SELECT 1 FROM {schema}.dd_campos
                                WHERE tabla_id = %s AND LOWER(COALESCE(column_name, '')) = LOWER(%s)
                            )
                            """,
                            [
                                tabla_id,
                                field.get("semantic_role") or field.get("column_name"),
                                field.get("column_name"),
                                field.get("data_type"),
                                json.dumps(
                                    {
                                        "semantic_role": field.get("semantic_role"),
                                        "business_concepts": field.get("business_concepts"),
                                        "allowed_operations": field.get("allowed_operations"),
                                    },
                                    ensure_ascii=False,
                                ),
                                1 if field.get("is_filterable") else 0,
                                1 if field.get("is_groupable") else 0,
                                1 if field.get("is_metric") else 0,
                                tabla_id,
                                field.get("column_name"),
                            ],
                        )
                        inserted["dd_campos"] += int(getattr(cursor, "rowcount", 0) or 0)

                    for relation in list(preview.get("dd_relaciones") or []):
                        cursor.execute(
                            f"""
                            INSERT INTO {schema}.dd_relaciones (dominio_id, nombre_relacion, condicion_join_sql, cardinalidad, descripcion)
                            SELECT %s, %s, %s, %s, %s
                            WHERE NOT EXISTS (
                                SELECT 1 FROM {schema}.dd_relaciones
                                WHERE dominio_id = %s AND LOWER(COALESCE(nombre_relacion, '')) = LOWER(%s)
                            )
                            """,
                            [
                                domain_id,
                                relation.get("code"),
                                relation.get("join_sql"),
                                relation.get("relationship_type"),
                                relation.get("join_purpose"),
                                domain_id,
                                relation.get("code"),
                            ],
                        )
                        inserted["dd_relaciones"] += int(getattr(cursor, "rowcount", 0) or 0)

                    for synonym in list(preview.get("dd_sinonimos") or []):
                        cursor.execute(
                            f"""
                            INSERT INTO {schema}.dd_sinonimos (dominio_id, termino, sinonimo)
                            SELECT %s, %s, %s
                            WHERE NOT EXISTS (
                                SELECT 1 FROM {schema}.dd_sinonimos
                                WHERE dominio_id = %s
                                  AND LOWER(COALESCE(termino, '')) = LOWER(%s)
                                  AND LOWER(COALESCE(sinonimo, '')) = LOWER(%s)
                            )
                            """,
                            [
                                domain_id,
                                synonym.get("canonical_value"),
                                synonym.get("synonym"),
                                domain_id,
                                synonym.get("canonical_value"),
                                synonym.get("synonym"),
                            ],
                        )
                        inserted["dd_sinonimos"] += int(getattr(cursor, "rowcount", 0) or 0)

                    for rule in list((preview.get("semantic_metadata") or {}).get("business_rules") or []):
                        cursor.execute(
                            f"""
                            INSERT INTO {schema}.dd_reglas (dominio_id, codigo, nombre, resultado_funcional)
                            SELECT %s, %s, %s, %s
                            WHERE NOT EXISTS (
                                SELECT 1 FROM {schema}.dd_reglas
                                WHERE dominio_id = %s AND LOWER(COALESCE(codigo, '')) = LOWER(%s)
                            )
                            """,
                            [
                                domain_id,
                                rule.get("rule_name"),
                                rule.get("rule_name"),
                                json.dumps(rule, ensure_ascii=False),
                                domain_id,
                                rule.get("rule_name"),
                            ],
                        )
                        inserted["dd_reglas"] += int(getattr(cursor, "rowcount", 0) or 0)
        except Exception as exc:
            return {"ok": False, "warnings": [str(exc)], "inserted": inserted}
        return {"ok": True, "warnings": warnings, "inserted": inserted}
