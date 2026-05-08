from __future__ import annotations

import json
import os
import re
from typing import Any

from django.db import connections

from apps.ia_dev.application.taxonomia_dominios import normalizar_codigo_dominio
from apps.ia_dev.services.sql_store import IADevSqlStore


_SAFE_TABLE_RE = re.compile(r"^[A-Za-z0-9_.]+$")
_SAFE_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9_]+$")


class DictionaryToolService:
    def __init__(self):
        self.db_alias = os.getenv("IA_DEV_DB_ALIAS", "default")
        self.dictionary_table = os.getenv(
            "IA_DEV_DICTIONARY_TABLE",
            "ai_dictionary.dd_dominios",
        )
        self.base_schema = (
            self.dictionary_table.split(".", 1)[0]
            if "." in self.dictionary_table
            else "ai_dictionary"
        )
        self.sql_store = IADevSqlStore()

    def _safe_table(self) -> str:
        if not _SAFE_TABLE_RE.match(self.dictionary_table):
            raise ValueError("Invalid IA_DEV_DICTIONARY_TABLE value")
        return self.dictionary_table

    def _safe_schema(self) -> str:
        schema = str(self.base_schema or "").strip()
        if not _SAFE_IDENTIFIER_RE.match(schema):
            raise ValueError("Invalid dictionary schema")
        return schema

    @staticmethod
    def _to_bool(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return value != 0
        text = str(value or "").strip().lower()
        return text in {"1", "true", "yes", "on", "si"}

    @staticmethod
    def _to_json(value: Any, default: Any) -> Any:
        if value is None:
            return default
        if isinstance(value, (dict, list)):
            return value
        raw = str(value or "").strip()
        if not raw:
            return default
        try:
            return json.loads(raw)
        except Exception:
            return default

    @staticmethod
    def _parse_allowed_values(value: Any) -> list[str]:
        text = str(value or "").strip()
        if not text:
            return []
        for sep in ("|", ";"):
            text = text.replace(sep, ",")
        parsed = [item.strip().upper() for item in text.split(",") if item.strip()]
        return sorted(dict.fromkeys(parsed))

    @staticmethod
    def _semantic_role_for_field(*, logical_name: str, column_name: str) -> str:
        key = str(logical_name or column_name or "").strip().lower()
        if key in {"fecha_nacimiento", "fnacimiento"}:
            return "person_birth_date"
        if key in {"fecha_ingreso", "fingreso"}:
            return "employment_start_date"
        if key in {"fecha_egreso", "fecha_retiro", "fretiro"}:
            return "employment_end_date"
        if key in {
            "area",
            "cargo",
            "supervisor",
            "sede",
            "zona_nodo",
            "carpeta",
            "tipo_labor",
            "tipo",
            "centro_costo",
        }:
            return "organizational_dimension"
        return ""

    @classmethod
    def _business_concepts_for_role(cls, role: str, *, logical_name: str) -> list[str]:
        normalized_role = str(role or "").strip().lower()
        normalized_logical = str(logical_name or "").strip().lower()
        if normalized_role == "person_birth_date":
            return ["birthday", "age"]
        if normalized_role == "employment_start_date":
            return ["tenure"]
        if normalized_role == "employment_end_date":
            return ["turnover"]
        if normalized_role == "organizational_dimension":
            return [normalized_logical] if normalized_logical else ["organizational_dimension"]
        return []

    @classmethod
    def _allowed_operations_for_profile(
        cls,
        *,
        logical_name: str,
        column_name: str,
        supports_filter: bool,
        supports_group_by: bool,
        supports_metric: bool,
        is_date: bool,
    ) -> list[str]:
        role = cls._semantic_role_for_field(logical_name=logical_name, column_name=column_name)
        if role == "person_birth_date":
            operations = ["list", "count", "filter_by_month", "group_by_month"]
            if supports_filter:
                operations.append("filter")
            return operations
        if role in {"employment_start_date", "employment_end_date"}:
            operations = ["list", "count", "filter_by_month", "group_by_month"]
            if supports_filter:
                operations.append("filter")
            return operations
        operations: list[str] = []
        if supports_filter:
            operations.append("filter")
            operations.append("select")
        if supports_group_by:
            operations.append("group_by")
        if supports_metric:
            operations.extend(["aggregate", "metric"])
        if is_date:
            operations.append("date_part")
        return list(dict.fromkeys(operations))

    def _table_exists(self, *, cursor, schema: str, table_name: str) -> bool:
        cursor.execute(
            """
            SELECT COUNT(*)
            FROM information_schema.tables
            WHERE table_schema = %s
              AND table_name = %s
            """,
            [schema, table_name],
        )
        return int(cursor.fetchone()[0] or 0) > 0

    def _table_columns(self, *, cursor, schema: str, table_name: str) -> set[str]:
        cursor.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = %s
              AND table_name = %s
            """,
            [schema, table_name],
        )
        return {
            str(row[0] or "").strip().lower()
            for row in cursor.fetchall()
            if row and row[0]
        }

    def _resolve_profile_table_name(self, *, cursor, schema: str) -> str | None:
        preferred = (
            "ia_dev_capacidades_columna",
            "dd_capacidades_campo",
            "dd_campos_semantic_profile",
        )
        for table_name in preferred:
            if self._table_exists(cursor=cursor, schema=schema, table_name=table_name):
                return table_name
        return None

    def _consolidate_profile_tables(self) -> dict[str, Any]:
        drop_legacy = str(
            os.getenv("IA_DEV_DROP_LEGACY_COLUMN_PROFILE_TABLE", "1") or "1"
        ).strip().lower() in {"1", "true", "yes", "on"}
        return self.sql_store.consolidate_column_capability_tables(
            drop_legacy_table=drop_legacy,
        )

    @staticmethod
    def _active_filter(*, alias: str, available_columns: set[str]) -> str:
        if "activo" in available_columns:
            return f"{alias}.activo = 1"
        if "activa" in available_columns:
            return f"{alias}.activa = 1"
        if "active" in available_columns:
            return f"{alias}.active = 1"
        return "1 = 1"

    def check_connection(self) -> dict:
        table = self._safe_table()

        with connections[self.db_alias].cursor() as cursor:
            cursor.execute("SELECT 1")
            ping = cursor.fetchone()[0]
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            count = cursor.fetchone()[0]

        return {
            "ok": bool(ping == 1),
            "table": table,
            "rows": int(count or 0),
            "db_alias": self.db_alias,
        }

    def get_dictionary_snapshot(self) -> dict:
        table = self._safe_table()
        schema = self._safe_schema()
        consolidation: dict[str, Any] = {}
        try:
            consolidation = self._consolidate_profile_tables()
        except Exception:
            # Si no hay permisos DDL, continuamos en modo lectura.
            pass
        with connections[self.db_alias].cursor() as cursor:
            cursor.execute(f"SELECT COUNT(*) FROM {schema}.dd_dominios")
            domains = int(cursor.fetchone()[0] or 0)
            cursor.execute(f"SELECT COUNT(*) FROM {schema}.dd_tablas")
            tables = int(cursor.fetchone()[0] or 0)
            cursor.execute(f"SELECT COUNT(*) FROM {schema}.dd_campos")
            fields = int(cursor.fetchone()[0] or 0)
            cursor.execute(f"SELECT COUNT(*) FROM {schema}.dd_reglas")
            rules = int(cursor.fetchone()[0] or 0)
            cursor.execute(f"SELECT COUNT(*) FROM {schema}.dd_relaciones")
            relations = int(cursor.fetchone()[0] or 0)
            cursor.execute(f"SELECT COUNT(*) FROM {schema}.dd_sinonimos")
            synonyms = int(cursor.fetchone()[0] or 0)

            profile_table_name = self._resolve_profile_table_name(cursor=cursor, schema=schema)
            field_profiles = 0
            if profile_table_name:
                cursor.execute(f"SELECT COUNT(*) FROM {schema}.{profile_table_name}")
                field_profiles = int(cursor.fetchone()[0] or 0)
            canonical_count = 0
            compat_count = 0
            legacy_count = 0
            if self._table_exists(cursor=cursor, schema=schema, table_name="ia_dev_capacidades_columna"):
                cursor.execute(f"SELECT COUNT(*) FROM {schema}.ia_dev_capacidades_columna")
                canonical_count = int(cursor.fetchone()[0] or 0)
            if self._table_exists(cursor=cursor, schema=schema, table_name="dd_capacidades_campo"):
                cursor.execute(f"SELECT COUNT(*) FROM {schema}.dd_capacidades_campo")
                compat_count = int(cursor.fetchone()[0] or 0)
            if self._table_exists(cursor=cursor, schema=schema, table_name="dd_campos_semantic_profile"):
                cursor.execute(f"SELECT COUNT(*) FROM {schema}.dd_campos_semantic_profile")
                legacy_count = int(cursor.fetchone()[0] or 0)

        return {
            "dictionary_table": table,
            "schema": schema,
            "consolidation": consolidation,
            "profile_table_name": profile_table_name,
            "counts": {
                "dd_dominios": domains,
                "dd_tablas": tables,
                "dd_campos": fields,
                "dd_reglas": rules,
                "dd_relaciones": relations,
                "dd_sinonimos": synonyms,
                "column_capabilities": field_profiles,
                "ia_dev_capacidades_columna": canonical_count,
                "dd_capacidades_campo": compat_count,
                "dd_campos_semantic_profile": legacy_count,
            },
        }

    def get_domain_context(self, domain: str, *, limit: int = 8) -> dict:
        table = self._safe_table()
        schema = self._safe_schema()
        safe_limit = max(1, min(int(limit), 20))
        consolidation: dict[str, Any] = {}
        try:
            consolidation = self._consolidate_profile_tables()
        except Exception:
            # No bloqueamos lectura semantica si no se puede crear estructura.
            pass
        domain_key = normalizar_codigo_dominio(domain or "general")
        code_map = {
            "ausentismo": "AUSENTISMOS",
            "empleados": "EMPLEADOS",
            "transport": "TRANSPORTE",
            "transporte": "TRANSPORTE",
            "general": "GENERAL",
            "knowledge": "GENERAL",
            "legacy": "GENERAL",
        }
        domain_code = code_map.get(domain_key, "GENERAL")

        with connections[self.db_alias].cursor() as cursor:
            domain_columns = self._table_columns(cursor=cursor, schema=schema, table_name="dd_dominios")
            tables_columns = self._table_columns(cursor=cursor, schema=schema, table_name="dd_tablas")
            fields_columns = self._table_columns(cursor=cursor, schema=schema, table_name="dd_campos")
            rules_columns = self._table_columns(cursor=cursor, schema=schema, table_name="dd_reglas")
            relations_columns = self._table_columns(cursor=cursor, schema=schema, table_name="dd_relaciones")
            synonyms_columns = self._table_columns(cursor=cursor, schema=schema, table_name="dd_sinonimos")
            profile_table_name = self._resolve_profile_table_name(cursor=cursor, schema=schema)
            has_profile_table = bool(profile_table_name)
            profile_columns = (
                self._table_columns(cursor=cursor, schema=schema, table_name=str(profile_table_name or ""))
                if has_profile_table
                else set()
            )

            domain_active_filter = self._active_filter(alias="d", available_columns=domain_columns)
            cursor.execute(
                f"""
                SELECT id, codigo, nombre, descripcion
                FROM {schema}.dd_dominios AS d
                WHERE {domain_active_filter}
                  AND (
                    UPPER(COALESCE(codigo, '')) = %s
                    OR UPPER(COALESCE(nombre, '')) LIKE %s
                    OR UPPER(COALESCE(descripcion, '')) LIKE %s
                  )
                ORDER BY CASE WHEN UPPER(COALESCE(codigo, '')) = %s THEN 0 ELSE 1 END, id
                LIMIT 1
                """,
                [domain_code.upper(), f"%{domain_code.upper()}%", f"%{domain_code.upper()}%", domain_code.upper()],
            )
            domain_row = cursor.fetchone()

            if not domain_row:
                return {
                    "dictionary_table": table,
                    "schema": schema,
                    "domain": {
                        "code": domain_code,
                        "matched": False,
                    },
                    "tables": [],
                    "fields": [],
                    "field_profiles": [],
                    "rules": [],
                    "relations": [],
                    "synonyms": [],
                }

            dominio_id, codigo, nombre, descripcion = domain_row
            tables_active_filter = self._active_filter(alias="t", available_columns=tables_columns)
            cursor.execute(
                f"""
                SELECT id, schema_name, table_name, alias_negocio, clave_negocio, descripcion
                FROM {schema}.dd_tablas AS t
                WHERE {tables_active_filter}
                  AND dominio_id = %s
                ORDER BY table_name
                LIMIT %s
                """,
                [dominio_id, safe_limit],
            )
            table_rows = cursor.fetchall()
            table_ids = [int(row[0]) for row in table_rows if row[0] is not None]

            rules_active_filter = self._active_filter(alias="r", available_columns=rules_columns)
            cursor.execute(
                f"""
                SELECT codigo, nombre, resultado_funcional, prioridad
                FROM {schema}.dd_reglas AS r
                WHERE {rules_active_filter}
                  AND dominio_id = %s
                ORDER BY prioridad, codigo
                LIMIT %s
                """,
                [dominio_id, safe_limit * 20],
            )
            rule_rows = cursor.fetchall()

            field_rows: list[tuple[Any, ...]] = []
            relation_rows: list[tuple[Any, ...]] = []
            related_table_rows: list[tuple[Any, ...]] = []
            if table_ids:
                in_clause = ", ".join(["%s"] * len(table_ids))
                join_profile = ""
                profile_active_filter = "1 = 1"
                if has_profile_table:
                    join_profile = f"LEFT JOIN {schema}.{profile_table_name} AS p ON p.campo_id = c.id"
                    if "activo" in profile_columns:
                        profile_active_filter = "(p.activo = 1 OR p.campo_id IS NULL)"
                    elif "activa" in profile_columns:
                        profile_active_filter = "(p.activa = 1 OR p.campo_id IS NULL)"
                    elif "active" in profile_columns:
                        profile_active_filter = "(p.active = 1 OR p.campo_id IS NULL)"

                def fexpr(column_name: str, alias_name: str, table_alias: str = "c") -> str:
                    if column_name in fields_columns:
                        return f"{table_alias}.{column_name} AS {alias_name}"
                    return f"NULL AS {alias_name}"

                def pexpr(column_name: str, alias_name: str) -> str:
                    if has_profile_table and column_name in profile_columns:
                        return f"p.{column_name} AS {alias_name}"
                    return f"NULL AS {alias_name}"

                def pexpr_any(candidates: tuple[str, ...], alias_name: str) -> str:
                    for item in candidates:
                        if has_profile_table and item in profile_columns:
                            return f"p.{item} AS {alias_name}"
                    return f"NULL AS {alias_name}"

                cursor.execute(
                    f"""
                    SELECT
                        t.schema_name AS schema_name,
                        t.table_name AS table_name,
                        c.id AS campo_id,
                        {fexpr("campo_logico", "campo_logico")},
                        {fexpr("column_name", "column_name")},
                        {fexpr("tipo_campo", "tipo_campo")},
                        {fexpr("tipo_dato_tecnico", "tipo_dato_tecnico")},
                        {fexpr("definicion_negocio", "definicion_negocio")},
                        {fexpr("es_clave", "es_clave")},
                        {fexpr("valores_permitidos", "valores_permitidos")},
                        {fexpr("es_filtro", "es_filtro")},
                        {fexpr("es_group_by", "es_group_by")},
                        {fexpr("es_metrica", "es_metrica")},
                        {pexpr_any(("supports_filter", "soporta_filtro"), "p_supports_filter")},
                        {pexpr_any(("supports_group_by", "soporta_group_by"), "p_supports_group_by")},
                        {pexpr_any(("supports_metric", "soporta_metrica"), "p_supports_metric")},
                        {pexpr_any(("supports_dimension", "soporta_dimension"), "p_supports_dimension")},
                        {pexpr_any(("is_date", "es_fecha"), "p_is_date")},
                        {pexpr_any(("is_identifier", "es_identificador"), "p_is_identifier")},
                        {pexpr_any(("is_chart_dimension", "es_chart_dimension"), "p_is_chart_dimension")},
                        {pexpr_any(("is_chart_measure", "es_chart_measure"), "p_is_chart_measure")},
                        {pexpr_any(("allowed_operators_json", "operadores_permitidos_json"), "p_allowed_operators_json")},
                        {pexpr_any(("allowed_aggregations_json", "agregaciones_permitidas_json"), "p_allowed_aggregations_json")},
                        {pexpr_any(("normalization_strategy", "estrategia_normalizacion"), "p_normalization_strategy")},
                        {pexpr_any(("priority", "prioridad"), "p_priority")}
                    FROM {schema}.dd_campos AS c
                    JOIN {schema}.dd_tablas AS t ON t.id = c.tabla_id
                    {join_profile}
                    WHERE {self._active_filter(alias="c", available_columns=fields_columns)}
                      AND c.tabla_id IN ({in_clause})
                      AND ({profile_active_filter})
                    ORDER BY t.table_name, c.id
                    LIMIT %s
                    """,
                    [*table_ids, safe_limit * 20],
                )
                field_rows = cursor.fetchall()

                relations_active_filter = self._active_filter(alias="r", available_columns=relations_columns)
                cursor.execute(
                    f"""
                    SELECT r.nombre_relacion, r.join_sql, r.cardinalidad, r.descripcion
                    FROM {schema}.dd_relaciones AS r
                    WHERE {relations_active_filter}
                      AND (
                        r.tabla_origen_id IN ({in_clause})
                        OR r.tabla_destino_id IN ({in_clause})
                      )
                    ORDER BY r.nombre_relacion
                    LIMIT %s
                    """,
                    [*table_ids, *table_ids, safe_limit],
                )
                relation_rows = cursor.fetchall()
                if domain_key in {"ausentismo", "attendance"}:
                    cursor.execute(
                        f"""
                        SELECT DISTINCT t.id, t.schema_name, t.table_name, t.alias_negocio, t.clave_negocio, t.descripcion
                        FROM {schema}.dd_relaciones AS r
                        JOIN {schema}.dd_tablas AS t
                          ON t.id = CASE
                            WHEN r.tabla_origen_id IN ({in_clause}) THEN r.tabla_destino_id
                            ELSE r.tabla_origen_id
                          END
                        WHERE {relations_active_filter}
                          AND (
                            r.tabla_origen_id IN ({in_clause})
                            OR r.tabla_destino_id IN ({in_clause})
                          )
                        ORDER BY t.table_name, t.id
                        LIMIT %s
                        """,
                        [*table_ids, *table_ids, *table_ids, safe_limit],
                    )
                    related_table_rows = [
                        row
                        for row in cursor.fetchall()
                        if int(row[0] or 0) not in table_ids
                    ]

            synonyms_active_filter = self._active_filter(alias="s", available_columns=synonyms_columns)
            cursor.execute(
                f"""
                SELECT termino, sinonimo
                FROM {schema}.dd_sinonimos AS s
                WHERE {synonyms_active_filter}
                  AND dominio_id = %s
                ORDER BY termino, sinonimo
                LIMIT %s
                """,
                [dominio_id, safe_limit * 6],
            )
            synonym_rows = cursor.fetchall()

        tables = [
            {
                "id": int(row[0]),
                "schema_name": str(row[1] or ""),
                "table_name": str(row[2] or ""),
                "alias_negocio": str(row[3] or ""),
                "clave_negocio": str(row[4] or ""),
                "descripcion": str(row[5] or ""),
            }
            for row in table_rows
        ]
        tables.extend(
            [
                {
                    "id": int(row[0]),
                    "schema_name": str(row[1] or ""),
                    "table_name": str(row[2] or ""),
                    "alias_negocio": str(row[3] or ""),
                    "clave_negocio": str(row[4] or ""),
                    "descripcion": str(row[5] or ""),
                }
                for row in related_table_rows
            ]
        )
        fields: list[dict[str, Any]] = []
        field_profiles: list[dict[str, Any]] = []
        for row in field_rows:
            allowed_values = self._parse_allowed_values(row[9])
            supports_filter = self._to_bool(row[13]) or self._to_bool(row[10]) or bool(allowed_values)
            supports_group_by = self._to_bool(row[14]) or self._to_bool(row[11])
            supports_metric = self._to_bool(row[15]) or self._to_bool(row[12])
            schema_name = str(row[0] or "")
            table_name = str(row[1] or "")
            logical_name = str(row[3] or "")
            column_name = str(row[4] or "")
            table_fqn = f"{schema_name}.{table_name}" if schema_name and table_name else table_name
            semantic_role = self._semantic_role_for_field(
                logical_name=logical_name,
                column_name=column_name,
            )
            profile = {
                "schema_name": schema_name,
                "table_name": table_name,
                "table_fqn": table_fqn,
                "campo_id": int(row[2] or 0),
                "campo_logico": logical_name,
                "column_name": column_name,
                "tipo_campo": str(row[5] or ""),
                "tipo_dato_tecnico": str(row[6] or ""),
                "definicion_negocio": str(row[7] or ""),
                "es_clave": self._to_bool(row[8]),
                "valores_permitidos": str(row[9] or ""),
                "allowed_values": allowed_values,
                "es_filtro": supports_filter,
                "es_group_by": supports_group_by,
                "es_metrica": supports_metric,
                "supports_filter": supports_filter,
                "supports_group_by": supports_group_by,
                "supports_metric": supports_metric,
                "supports_dimension": self._to_bool(row[16]) or supports_group_by,
                "is_date": self._to_bool(row[17]),
                "is_identifier": self._to_bool(row[18]),
                "is_chart_dimension": self._to_bool(row[19]) or supports_group_by,
                "is_chart_measure": self._to_bool(row[20]) or supports_metric,
                "allowed_operators": self._to_json(row[21], []),
                "allowed_aggregations": self._to_json(row[22], []),
                "normalization_strategy": str(row[23] or ""),
                "priority": int(row[24] or 0),
                "semantic_role": semantic_role,
                "business_concepts": self._business_concepts_for_role(
                    semantic_role,
                    logical_name=logical_name,
                ),
                "allowed_operations": self._allowed_operations_for_profile(
                    logical_name=logical_name,
                    column_name=column_name,
                    supports_filter=supports_filter,
                    supports_group_by=supports_group_by,
                    supports_metric=supports_metric,
                    is_date=self._to_bool(row[17]),
                ),
            }
            fields.append(profile)
            field_profiles.append(profile)

        rules = [
            {
                "codigo": str(row[0] or ""),
                "nombre": str(row[1] or ""),
                "resultado_funcional": str(row[2] or ""),
                "prioridad": int(row[3] or 0),
            }
            for row in rule_rows
        ]
        relations = [
            {
                "nombre_relacion": str(row[0] or ""),
                "join_sql": str(row[1] or ""),
                "cardinalidad": str(row[2] or ""),
                "descripcion": str(row[3] or ""),
            }
            for row in relation_rows
        ]
        synonyms = [
            {
                "termino": str(row[0] or ""),
                "sinonimo": str(row[1] or ""),
            }
            for row in synonym_rows
        ]

        return {
            "dictionary_table": table,
            "schema": schema,
            "domain": {
                "id": int(dominio_id),
                "code": str(codigo or ""),
                "name": str(nombre or ""),
                "description": str(descripcion or ""),
                "matched": True,
            },
            "tables": tables,
            "fields": fields,
            "field_profiles": field_profiles,
            "profile_table_name": profile_table_name,
            "consolidation": consolidation,
            "rules": rules,
            "relations": relations,
            "synonyms": synonyms,
        }

    def get_semantic_field_profiles(self, domain: str, *, limit: int = 20) -> list[dict[str, Any]]:
        context = self.get_domain_context(domain, limit=limit)
        return list(context.get("field_profiles") or [])

    def get_table_field_profiles(
        self,
        table_names: list[str] | tuple[str, ...],
        *,
        limit: int = 80,
    ) -> list[dict[str, Any]]:
        schema = self._safe_schema()
        requested = [
            str(item or "").strip().lower()
            for item in list(table_names or [])
            if str(item or "").strip()
        ]
        requested = list(
            dict.fromkeys(
                [
                    item
                    for item in requested
                    if all(_SAFE_IDENTIFIER_RE.match(part) for part in item.split("."))
                ]
            )
        )
        if not requested:
            return []
        requested_fqns = {item for item in requested if "." in item}
        requested_table_names = {item.split(".")[-1] for item in requested}

        safe_limit = max(1, min(int(limit), 500))
        with connections[self.db_alias].cursor() as cursor:
            fields_columns = self._table_columns(cursor=cursor, schema=schema, table_name="dd_campos")
            profile_table_name = self._resolve_profile_table_name(cursor=cursor, schema=schema)
            has_profile_table = bool(profile_table_name)
            profile_columns = (
                self._table_columns(cursor=cursor, schema=schema, table_name=str(profile_table_name or ""))
                if has_profile_table
                else set()
            )

            join_profile = ""
            profile_active_filter = "1 = 1"
            if has_profile_table:
                join_profile = f"LEFT JOIN {schema}.{profile_table_name} AS p ON p.campo_id = c.id"
                if "activo" in profile_columns:
                    profile_active_filter = "(p.activo = 1 OR p.campo_id IS NULL)"
                elif "activa" in profile_columns:
                    profile_active_filter = "(p.activa = 1 OR p.campo_id IS NULL)"
                elif "active" in profile_columns:
                    profile_active_filter = "(p.active = 1 OR p.campo_id IS NULL)"

            def fexpr(column_name: str, alias_name: str, table_alias: str = "c") -> str:
                if column_name in fields_columns:
                    return f"{table_alias}.{column_name} AS {alias_name}"
                return f"NULL AS {alias_name}"

            def pexpr_any(candidates: tuple[str, ...], alias_name: str) -> str:
                for item in candidates:
                    if has_profile_table and item in profile_columns:
                        return f"p.{item} AS {alias_name}"
                return f"NULL AS {alias_name}"

            in_clause = ", ".join(["%s"] * len(requested_table_names))
            cursor.execute(
                f"""
                SELECT
                    t.schema_name AS schema_name,
                    t.table_name AS table_name,
                    c.id AS campo_id,
                    {fexpr("campo_logico", "campo_logico")},
                    {fexpr("column_name", "column_name")},
                    {fexpr("tipo_campo", "tipo_campo")},
                    {fexpr("tipo_dato_tecnico", "tipo_dato_tecnico")},
                    {fexpr("definicion_negocio", "definicion_negocio")},
                    {fexpr("es_clave", "es_clave")},
                    {fexpr("valores_permitidos", "valores_permitidos")},
                    {fexpr("es_filtro", "es_filtro")},
                    {fexpr("es_group_by", "es_group_by")},
                    {fexpr("es_metrica", "es_metrica")},
                    {pexpr_any(("supports_filter", "soporta_filtro"), "p_supports_filter")},
                    {pexpr_any(("supports_group_by", "soporta_group_by"), "p_supports_group_by")},
                    {pexpr_any(("supports_metric", "soporta_metrica"), "p_supports_metric")},
                    {pexpr_any(("supports_dimension", "soporta_dimension"), "p_supports_dimension")},
                    {pexpr_any(("is_date", "es_fecha"), "p_is_date")},
                    {pexpr_any(("is_identifier", "es_identificador"), "p_is_identifier")},
                    {pexpr_any(("is_chart_dimension", "es_chart_dimension"), "p_is_chart_dimension")},
                    {pexpr_any(("is_chart_measure", "es_chart_measure"), "p_is_chart_measure")},
                    {pexpr_any(("allowed_operators_json", "operadores_permitidos_json"), "p_allowed_operators_json")},
                    {pexpr_any(("allowed_aggregations_json", "agregaciones_permitidas_json"), "p_allowed_aggregations_json")},
                    {pexpr_any(("normalization_strategy", "estrategia_normalizacion"), "p_normalization_strategy")},
                    {pexpr_any(("priority", "prioridad"), "p_priority")}
                FROM {schema}.dd_campos AS c
                JOIN {schema}.dd_tablas AS t ON t.id = c.tabla_id
                {join_profile}
                WHERE {self._active_filter(alias="c", available_columns=fields_columns)}
                  AND LOWER(COALESCE(t.table_name, '')) IN ({in_clause})
                  AND ({profile_active_filter})
                ORDER BY t.table_name, c.id
                LIMIT %s
                """,
                [*sorted(requested_table_names), safe_limit],
            )
            rows = cursor.fetchall()

        profiles: list[dict[str, Any]] = []
        for row in rows:
            allowed_values = self._parse_allowed_values(row[9])
            supports_filter = self._to_bool(row[13]) or self._to_bool(row[10]) or bool(allowed_values)
            supports_group_by = self._to_bool(row[14]) or self._to_bool(row[11])
            supports_metric = self._to_bool(row[15]) or self._to_bool(row[12])
            schema_name = str(row[0] or "")
            table_name = str(row[1] or "")
            logical_name = str(row[3] or "")
            column_name = str(row[4] or "")
            table_fqn = f"{schema_name}.{table_name}" if schema_name and table_name else table_name
            normalized_table_fqn = table_fqn.strip().lower()
            normalized_table_name = table_name.strip().lower()
            if requested_fqns:
                if normalized_table_fqn not in requested_fqns:
                    continue
            elif normalized_table_name not in requested_table_names:
                continue
            semantic_role = self._semantic_role_for_field(
                logical_name=logical_name,
                column_name=column_name,
            )
            profiles.append(
                {
                    "schema_name": schema_name,
                    "table_name": table_name,
                    "table_fqn": table_fqn,
                    "campo_id": int(row[2] or 0),
                    "campo_logico": logical_name,
                    "column_name": column_name,
                    "tipo_campo": str(row[5] or ""),
                    "tipo_dato_tecnico": str(row[6] or ""),
                    "definicion_negocio": str(row[7] or ""),
                    "es_clave": self._to_bool(row[8]),
                    "valores_permitidos": str(row[9] or ""),
                    "allowed_values": allowed_values,
                    "es_filtro": supports_filter,
                    "es_group_by": supports_group_by,
                    "es_metrica": supports_metric,
                    "supports_filter": supports_filter,
                    "supports_group_by": supports_group_by,
                    "supports_metric": supports_metric,
                    "supports_dimension": self._to_bool(row[16]) or supports_group_by,
                    "is_date": self._to_bool(row[17]),
                    "is_identifier": self._to_bool(row[18]),
                    "is_chart_dimension": self._to_bool(row[19]) or supports_group_by,
                    "is_chart_measure": self._to_bool(row[20]) or supports_metric,
                    "allowed_operators": self._to_json(row[21], []),
                    "allowed_aggregations": self._to_json(row[22], []),
                    "normalization_strategy": str(row[23] or ""),
                    "priority": int(row[24] or 0),
                    "semantic_role": semantic_role,
                    "business_concepts": self._business_concepts_for_role(
                        semantic_role,
                        logical_name=logical_name,
                    ),
                    "allowed_operations": self._allowed_operations_for_profile(
                        logical_name=logical_name,
                        column_name=column_name,
                        supports_filter=supports_filter,
                        supports_group_by=supports_group_by,
                        supports_metric=supports_metric,
                        is_date=self._to_bool(row[17]),
                    ),
                }
            )
        return profiles

    def ensure_rrhh_status_synonyms_seed(self) -> dict[str, Any]:
        """
        Seed idempotente de sinonimos RRHH para estados laborales.
        No falla el runtime: devuelve estado aplicado/skipped/error.
        """
        schema = self._safe_schema()
        synonyms_seed = [
            ("empleados", "personal"),
            ("empleado", "colaborador"),
            ("empleados", "colaboradores"),
            ("empleados", "personas"),
            ("empleado", "persona"),
            ("empleado", "trabajador"),
            ("empleados", "trabajadores"),
            ("empleados", "dotacion"),
            ("empleados", "nomina"),
            ("empleados", "plantilla"),
            ("empleados", "planta"),
            ("activo", "habilitado"),
            ("activo", "habilitados"),
            ("activo", "habilitada"),
            ("activo", "habilitadas"),
            ("activo", "vigente"),
            ("activo", "vigentes"),
            ("activo", "disponible"),
            ("activo", "disponibles"),
            ("inactivo", "deshabilitado"),
            ("inactivo", "deshabilitados"),
            ("inactivo", "deshabilitada"),
            ("inactivo", "deshabilitadas"),
            ("fecha_nacimiento", "nacimiento"),
            ("fecha_nacimiento", "fecha de nacimiento"),
            ("fecha_nacimiento", "cumpleanos"),
            ("fecha_nacimiento", "cumpleanos de empleados"),
            ("fecha_nacimiento", "cumple"),
            ("fecha_nacimiento", "cumple anos"),
            ("fecha_nacimiento", "cumpleaneros"),
            ("fecha_ingreso", "antiguedad"),
            ("fecha_ingreso", "fecha de ingreso"),
            ("fecha_egreso", "retiro"),
            ("fecha_egreso", "salida"),
            ("fecha_egreso", "fecha de retiro"),
            ("area", "dependencia"),
            ("area", "dependencias"),
            ("area", "departamento"),
            ("area", "departamentos"),
            ("area", "unidad"),
            ("area", "unidades"),
            ("cargo", "puesto"),
            ("cargo", "puestos"),
            ("cargo", "rol"),
            ("supervisor", "jefe"),
            ("supervisor", "lider"),
        ]
        result: dict[str, Any] = {
            "ok": True,
            "status": "skipped",
            "domain_code": "EMPLEADOS",
            "inserted": 0,
            "skipped": 0,
            "seed_size": len(synonyms_seed),
            "errors": [],
        }
        try:
            with connections[self.db_alias].cursor() as cursor:
                domain_columns = self._table_columns(cursor=cursor, schema=schema, table_name="dd_dominios")
                synonyms_columns = self._table_columns(cursor=cursor, schema=schema, table_name="dd_sinonimos")
                if "termino" not in synonyms_columns or "sinonimo" not in synonyms_columns:
                    return {
                        **result,
                        "ok": False,
                        "status": "error",
                        "errors": ["dd_sinonimos_missing_required_columns"],
                    }

                domain_active_filter = self._active_filter(alias="d", available_columns=domain_columns)
                cursor.execute(
                    f"""
                    SELECT id
                    FROM {schema}.dd_dominios AS d
                    WHERE {domain_active_filter}
                      AND (
                        UPPER(COALESCE(codigo, '')) = %s
                        OR UPPER(COALESCE(nombre, '')) LIKE %s
                        OR UPPER(COALESCE(descripcion, '')) LIKE %s
                      )
                    ORDER BY id
                    LIMIT 1
                    """,
                    ["EMPLEADOS", "%EMPLEAD%", "%EMPLEAD%"],
                )
                domain_row = cursor.fetchone()
                if not domain_row:
                    return {
                        **result,
                        "ok": False,
                        "status": "error",
                        "errors": ["dd_dominios_empleados_not_found"],
                    }
                domain_id = int(domain_row[0] or 0)
                if domain_id <= 0:
                    return {
                        **result,
                        "ok": False,
                        "status": "error",
                        "errors": ["dd_dominios_empleados_invalid_id"],
                    }

                has_domain_fk = "dominio_id" in synonyms_columns
                has_activo = "activo" in synonyms_columns
                has_activa = "activa" in synonyms_columns
                has_active = "active" in synonyms_columns
                has_created_at = "creado_en" in synonyms_columns

                for canonical_term, synonym_term in synonyms_seed:
                    if has_domain_fk:
                        cursor.execute(
                            f"""
                            SELECT 1
                            FROM {schema}.dd_sinonimos AS s
                            WHERE s.dominio_id = %s
                              AND LOWER(COALESCE(s.termino, '')) = %s
                              AND LOWER(COALESCE(s.sinonimo, '')) = %s
                            LIMIT 1
                            """,
                            [domain_id, canonical_term.lower(), synonym_term.lower()],
                        )
                    else:
                        cursor.execute(
                            f"""
                            SELECT 1
                            FROM {schema}.dd_sinonimos AS s
                            WHERE LOWER(COALESCE(s.termino, '')) = %s
                              AND LOWER(COALESCE(s.sinonimo, '')) = %s
                            LIMIT 1
                            """,
                            [canonical_term.lower(), synonym_term.lower()],
                        )
                    if cursor.fetchone():
                        result["skipped"] = int(result.get("skipped") or 0) + 1
                        continue

                    columns: list[str] = ["termino", "sinonimo"]
                    values: list[Any] = [canonical_term.lower(), synonym_term.lower()]
                    placeholders: list[str] = ["%s", "%s"]

                    if has_domain_fk:
                        columns.append("dominio_id")
                        values.append(domain_id)
                        placeholders.append("%s")
                    if has_activo:
                        columns.append("activo")
                        values.append(1)
                        placeholders.append("%s")
                    elif has_activa:
                        columns.append("activa")
                        values.append(1)
                        placeholders.append("%s")
                    elif has_active:
                        columns.append("active")
                        values.append(1)
                        placeholders.append("%s")
                    if has_created_at:
                        columns.append("creado_en")
                        values.append(None)
                        placeholders.append("COALESCE(%s, NOW())")

                    cursor.execute(
                        f"""
                        INSERT INTO {schema}.dd_sinonimos ({", ".join(columns)})
                        VALUES ({", ".join(placeholders)})
                        """,
                        values,
                    )
                    result["inserted"] = int(result.get("inserted") or 0) + 1

            if int(result.get("inserted") or 0) > 0:
                result["status"] = "applied"
            else:
                result["status"] = "skipped"
            return result
        except Exception as exc:
            return {
                **result,
                "ok": False,
                "status": "error",
                "errors": [str(exc)],
            }
