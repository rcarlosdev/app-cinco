import os
import re
import unicodedata
from datetime import date
from typing import Any

from django.db import connections


_SAFE_TABLE_RE = re.compile(r"^[A-Za-z0-9_.]+$")
_SAFE_COLUMN_RE = re.compile(r"^[A-Za-z0-9_]+$")


class AusentismoToolService:
    """
    Servicio legacy de analytics/consultas operativas de ausentismo.
    Sigue activo como wrapper temporal de compatibilidad y no debe ser la ruta
    primaria del piloto analytics cuando IA_DEV_DISABLE_LEGACY_ANALYTICS_FALLBACK=1.
    """

    _ATTENDANCE_REASON_PATTERNS = {
        "VACACIONES": ("VACACION", "VACACIONES", "VACACIÓN", "VACACIONES"),
        "INCAPACIDAD": ("INCAPACIDAD", "INCAPACIDADES", "INCAP"),
        "LICENCIA": ("LICENCIA", "LICENCIAS"),
        "PERMISO": ("PERMISO", "PERMISOS"),
        "CALAMIDAD": ("CALAMIDAD",),
    }

    def __init__(self):
        self.table = os.getenv(
            "IA_DEV_AUSENTISMO_TABLE",
            os.getenv("IA_DEV_ATTENDANCE_TABLE", "cincosas_cincosas.gestionh_ausentismo"),
        )
        self.db_alias = os.getenv("IA_DEV_DB_ALIAS", "default")
        self.dictionary_table = os.getenv("IA_DEV_DICTIONARY_TABLE", "ai_dictionary.dd_dominios")
        self.dictionary_schema = (
            self.dictionary_table.split(".", 1)[0]
            if "." in self.dictionary_table
            else "ai_dictionary"
        )
        self.use_dd_tablas_mapping = (
            os.getenv("IA_DEV_USE_DD_TABLAS_MAPPING", "1").strip().lower()
            in ("1", "true", "yes", "on")
        )
        self.personal_table = os.getenv(
            "IA_DEV_PERSONAL_TABLE",
            "cincosas_cincosas.cinco_base_de_personal",
        )
        self.table_source = "env"
        self.personal_table_source = "env"
        self.table = self._resolve_table_from_dictionary(
            configured_table=self.table,
            preferred_domain_code="AUSENTISMOS",
        )
        self.personal_table = self._resolve_table_from_dictionary(
            configured_table=self.personal_table,
            preferred_domain_code="EMPLEADOS",
        )

    def _safe_table(self) -> str:
        if not _SAFE_TABLE_RE.match(self.table):
            raise ValueError("Invalid IA_DEV_AUSENTISMO_TABLE value")
        return self.table

    def _safe_personal_table(self) -> str:
        if not _SAFE_TABLE_RE.match(self.personal_table):
            raise ValueError("Invalid IA_DEV_PERSONAL_TABLE value")
        return self.personal_table

    @staticmethod
    def _split_qualified_table(value: str) -> tuple[str | None, str]:
        clean = str(value or "").strip()
        if "." not in clean:
            return None, clean
        schema, table = clean.split(".", 1)
        return schema, table

    def _resolve_table_from_dictionary(
        self,
        *,
        configured_table: str,
        preferred_domain_code: str | None = None,
    ) -> str:
        clean = str(configured_table or "").strip()
        if not self.use_dd_tablas_mapping or not clean:
            return clean

        schema, table_name = self._split_qualified_table(clean)
        if not _SAFE_COLUMN_RE.match(table_name):
            return clean
        if schema and not _SAFE_COLUMN_RE.match(schema):
            return clean
        if not _SAFE_COLUMN_RE.match(self.dictionary_schema):
            return clean

        base_query = f"""
            SELECT t.schema_name, t.table_name, COALESCE(d.codigo, '')
            FROM {self.dictionary_schema}.dd_tablas AS t
            LEFT JOIN {self.dictionary_schema}.dd_dominios AS d ON d.id = t.dominio_id
            WHERE t.activo = 1
              AND UPPER(t.table_name) = UPPER(%s)
        """
        params: list[Any] = [table_name]
        order = " ORDER BY t.id ASC LIMIT 1"
        if preferred_domain_code:
            order = (
                " ORDER BY CASE WHEN UPPER(COALESCE(d.codigo, '')) = UPPER(%s) THEN 0 ELSE 1 END, t.id ASC LIMIT 1"
            )
            params.append(preferred_domain_code)
        query = base_query + order

        try:
            with connections[self.db_alias].cursor() as cursor:
                cursor.execute(query, params)
                row = cursor.fetchone()
            if not row:
                return clean
            resolved_schema = str(row[0] or "").strip()
            resolved_table = str(row[1] or "").strip()
            if not resolved_schema or not resolved_table:
                return clean
            if not (_SAFE_COLUMN_RE.match(resolved_schema) and _SAFE_COLUMN_RE.match(resolved_table)):
                return clean
            resolved = f"{resolved_schema}.{resolved_table}"
            if table_name.lower() == "gestionh_ausentismo":
                self.table_source = "dd_tablas"
            if table_name.lower() == "cinco_base_de_personal":
                self.personal_table_source = "dd_tablas"
            return resolved
        except Exception:
            return clean

    @staticmethod
    def _normalized_id_sql(column_expr: str) -> str:
        # Normaliza cedulas removiendo prefijos, espacios, puntos, guiones y ceros a la izquierda.
        base = "UPPER(TRIM(COALESCE(" + column_expr + ", '')))"
        without_doc_prefix = (
            "REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE("
            + base
            + ", 'C.C.', ''), 'C.C', ''), 'CC', ''), 'TI', ''), 'CE', ''), 'NIT', ''), '#', '')"
        )
        without_spaces = "REPLACE(" + without_doc_prefix + ", ' ', '')"
        without_decimal = (
            "(CASE WHEN "
            + without_spaces
            + " REGEXP '^[0-9]+\\\\.0+$' THEN SUBSTRING_INDEX("
            + without_spaces
            + ", '.', 1) ELSE "
            + without_spaces
            + " END)"
        )
        digits_like = "REPLACE(REPLACE(" + without_decimal + ", '.', ''), '-', '')"
        return "NULLIF(TRIM(LEADING '0' FROM " + digits_like + "), '')"

    @staticmethod
    def _normalize_id_value(value: Any) -> str:
        raw = str(value or "").strip().upper()
        if not raw:
            return ""
        for token in ("C.C.", "C.C", "CC", "TI", "CE", "NIT", "#"):
            raw = raw.replace(token, "")
        raw = raw.replace(" ", "").replace("-", "")
        if re.fullmatch(r"\d+\.0+", raw):
            raw = raw.split(".", 1)[0]
        raw = raw.replace(".", "")
        raw = raw.lstrip("0")
        return raw

    @staticmethod
    def _normalize_text(value: Any) -> str:
        lowered = str(value or "").strip().lower()
        normalized = unicodedata.normalize("NFKD", lowered)
        return "".join(ch for ch in normalized if not unicodedata.combining(ch))

    @classmethod
    def _resolve_attendance_reason_patterns(cls, value: str | None) -> tuple[str, list[str]]:
        normalized = cls._normalize_text(value).upper()
        if not normalized:
            return "", []
        for canonical, patterns in cls._ATTENDANCE_REASON_PATTERNS.items():
            normalized_patterns = [cls._normalize_text(item).upper() for item in patterns]
            if normalized == canonical or normalized in normalized_patterns:
                return canonical, list(dict.fromkeys([item for item in patterns if str(item or "").strip()]))
        return normalized, [normalized]

    @classmethod
    def _build_reason_clause(cls, *, column_expr: str, reason_filter: str | None) -> tuple[str, list[Any], str]:
        canonical, patterns = cls._resolve_attendance_reason_patterns(reason_filter)
        if not patterns:
            return "", [], ""
        safe_patterns = [str(item or "").strip().upper() for item in patterns if str(item or "").strip()]
        if not safe_patterns:
            return "", [], ""
        like_clauses = [f"UPPER(TRIM(COALESCE({column_expr}, ''))) LIKE %s" for _ in safe_patterns]
        params = [f"%{item}%" for item in safe_patterns]
        return f" AND ({' OR '.join(like_clauses)})", params, canonical

    @staticmethod
    def _build_focus_clause(*, column_expr: str, focus: str | None) -> str:
        safe_focus = str(focus or "all").strip().lower()
        if safe_focus != "unjustified":
            return ""
        return (
            f" AND ({column_expr} IS NULL"
            f" OR TRIM({column_expr}) = ''"
            f" OR UPPER(TRIM({column_expr})) = 'SIN JUSTIFICAR')"
        )

    @staticmethod
    def _split_table_name(qualified_table: str) -> tuple[str | None, str]:
        if "." not in qualified_table:
            return None, qualified_table
        schema, table = qualified_table.split(".", 1)
        return schema, table

    @staticmethod
    def _chunked(items: list[str], chunk_size: int = 300) -> list[list[str]]:
        return [items[i : i + chunk_size] for i in range(0, len(items), chunk_size)]

    @staticmethod
    def _resolve_status_filter(status: str | None) -> str:
        value = str(status or "all").strip().lower()
        if value in ("activos", "activo", "active"):
            return "activos"
        if value in ("inactivos", "inactivo", "inactive"):
            return "inactivos"
        return "all"

    def _get_personal_columns(self) -> set[str]:
        table = self._safe_personal_table()
        schema, table_name = self._split_table_name(table)
        if not _SAFE_COLUMN_RE.match(table_name):
            return set()

        if schema and not _SAFE_COLUMN_RE.match(schema):
            return set()

        if schema:
            query = """
                SELECT COLUMN_NAME
                FROM information_schema.columns
                WHERE table_schema = %s
                  AND table_name = %s
            """
            params = [schema, table_name]
        else:
            query = """
                SELECT COLUMN_NAME
                FROM information_schema.columns
                WHERE table_schema = DATABASE()
                  AND table_name = %s
            """
            params = [table_name]

        with connections[self.db_alias].cursor() as cursor:
            cursor.execute(query, params)
            return {str(row[0]) for row in cursor.fetchall() if row and row[0]}

    def _get_attendance_columns(self) -> set[str]:
        table = self._safe_table()
        schema, table_name = self._split_table_name(table)
        if not _SAFE_COLUMN_RE.match(table_name):
            return set()

        if schema and not _SAFE_COLUMN_RE.match(schema):
            return set()

        if schema:
            query = """
                SELECT COLUMN_NAME
                FROM information_schema.columns
                WHERE table_schema = %s
                  AND table_name = %s
            """
            params = [schema, table_name]
        else:
            query = """
                SELECT COLUMN_NAME
                FROM information_schema.columns
                WHERE table_schema = DATABASE()
                  AND table_name = %s
            """
            params = [table_name]

        with connections[self.db_alias].cursor() as cursor:
            cursor.execute(query, params)
            return {str(row[0]) for row in cursor.fetchall() if row and row[0]}

    @staticmethod
    def _resolve_justified_detail_extra_columns(*, canonical_reason: str | None, focus: str | None) -> list[str]:
        if not str(canonical_reason or "").strip():
            return []
        if str(focus or "all").strip().lower() == "unjustified":
            return []
        columns = ["ini_incapa", "fin_incapa"]
        if str(canonical_reason or "").strip().upper() == "INCAPACIDAD":
            columns.extend(["causa_aus", "ini_inca", "tipo_inca", "codigo_inca", "desc_inca"])
        return columns

    @staticmethod
    def _resolve_status_column(columns: set[str]) -> str | None:
        candidates = ["estado", "status", "activo", "is_active", "estatus", "estado_empleado"]
        for item in candidates:
            if item in columns:
                return item
        return None

    @staticmethod
    def _compose_full_name(nombre: str, apellido: str) -> str:
        return f"{str(nombre or '').strip()} {str(apellido or '').strip()}".strip()

    def get_data_employers(
        self,
        columns: list[str],
        employes: list[str],
        *,
        status: str = "all",
    ) -> dict:
        """
        Devuelve catalogo de personal por cedula normalizada.
        status: all | activos | inactivos
        """
        personal_table = self._safe_personal_table()
        available_columns = self._get_personal_columns()
        status_filter = self._resolve_status_filter(status)
        status_column = self._resolve_status_column(available_columns)

        requested = [c for c in (columns or []) if _SAFE_COLUMN_RE.match(str(c or ""))]
        safe_columns = [c for c in requested if c in available_columns]
        for required in ("cedula", "nombre", "apellido", "supervisor"):
            if required in available_columns and required not in safe_columns:
                safe_columns.append(required)

        if "cedula" not in safe_columns:
            return {
                "by_cedula": {},
                "status_filter": status_filter,
                "status_column": status_column,
                "catalog_count": 0,
            }

        normalized_ids: list[str] = []
        seen: set[str] = set()
        for item in employes or []:
            norm = self._normalize_id_value(item)
            if not norm or norm in seen:
                continue
            seen.add(norm)
            normalized_ids.append(norm)

        if not normalized_ids:
            return {
                "by_cedula": {},
                "status_filter": status_filter,
                "status_column": status_column,
                "catalog_count": 0,
            }

        norm_expr = self._normalized_id_sql("p.cedula")
        status_clause = ""
        if status_filter != "all" and status_column:
            status_expr = f"UPPER(TRIM(COALESCE(CAST(p.{status_column} AS CHAR), '')))"
            if status_filter == "activos":
                status_clause = (
                    f" AND {status_expr} IN ('1','SI','TRUE','ACTIVO','ACTIVA','A')"
                )
            elif status_filter == "inactivos":
                status_clause = (
                    f" AND {status_expr} IN ('0','NO','FALSE','INACTIVO','INACTIVA','I')"
                )

        select_cols = ", ".join([f"p.{col}" for col in safe_columns])
        by_cedula: dict[str, dict] = {}

        for chunk in self._chunked(normalized_ids, chunk_size=250):
            placeholders = ", ".join(["%s"] * len(chunk))
            query = f"""
                SELECT {select_cols}, {norm_expr} AS _cedula_norm
                FROM {personal_table} AS p
                WHERE {norm_expr} IN ({placeholders})
                {status_clause}
            """
            with connections[self.db_alias].cursor() as cursor:
                cursor.execute(query, chunk)
                rows = cursor.fetchall()

            for db_row in rows:
                values = list(db_row)
                cedula_norm = self._normalize_id_value(values[-1])
                if not cedula_norm:
                    continue
                payload = {safe_columns[i]: values[i] for i in range(len(safe_columns))}
                payload["_cedula_norm"] = cedula_norm

                previous = by_cedula.get(cedula_norm)
                if not previous:
                    by_cedula[cedula_norm] = payload
                    continue

                prev_score = sum(1 for key in ("nombre", "apellido", "area", "cargo", "supervisor") if str(previous.get(key) or "").strip())
                new_score = sum(1 for key in ("nombre", "apellido", "area", "cargo", "supervisor") if str(payload.get(key) or "").strip())
                if new_score > prev_score:
                    by_cedula[cedula_norm] = payload

        return {
            "by_cedula": by_cedula,
            "status_filter": status_filter,
            "status_column": status_column,
            "catalog_count": len(by_cedula),
        }

    def _attendance_base_unjustified(
        self,
        start_date: date,
        end_date: date,
        limit: int,
        *,
        cedula: str | None = None,
    ) -> list[tuple]:
        table = self._safe_table()
        safe_limit = max(1, min(int(limit), 500))
        normalized_cedula = self._normalize_id_value(cedula)
        cedula_clause = ""
        params: list[Any] = [start_date, end_date]
        if normalized_cedula:
            cedula_clause = f" AND {self._normalized_id_sql('g.cedula')} = %s"
            params.append(normalized_cedula)
        query = f"""
            SELECT
                g.cedula,
                DATE(g.fecha_edit) AS fecha_ausentismo,
                COALESCE(g.justificacion, '') AS justificacion
            FROM {table} AS g
            WHERE DATE(g.fecha_edit) BETWEEN %s AND %s
            {cedula_clause}
              AND UPPER(TRIM(g.ausentismo)) = 'SI'
              AND (
                    g.justificacion IS NULL
                    OR TRIM(g.justificacion) = ''
                    OR UPPER(TRIM(g.justificacion)) = 'SIN JUSTIFICAR'
              )
            ORDER BY DATE(g.fecha_edit) DESC, g.cedula
            LIMIT %s
        """
        params.append(safe_limit)
        with connections[self.db_alias].cursor() as cursor:
            cursor.execute(query, params)
            return cursor.fetchall()

    def get_summary(self, start_date: date, end_date: date, *, cedula: str | None = None) -> dict:
        table = self._safe_table()
        normalized_cedula = self._normalize_id_value(cedula)
        cedula_clause = ""
        params: list[Any] = [start_date, end_date, start_date, end_date]
        if normalized_cedula:
            cedula_clause = f" AND {self._normalized_id_sql('g.cedula')} = %s"
            params.append(normalized_cedula)
        sql = f"""
            SELECT
                %s AS periodo_inicio,
                %s AS periodo_fin,
                COALESCE(SUM(CASE WHEN UPPER(TRIM(g.ausentismo)) = 'SI' THEN 1 ELSE 0 END), 0) AS total_ausentismos,
                COALESCE(SUM(
                    CASE
                        WHEN UPPER(TRIM(g.ausentismo)) = 'SI'
                         AND g.justificacion IS NOT NULL
                         AND TRIM(g.justificacion) <> ''
                         AND UPPER(TRIM(g.justificacion)) <> 'SIN JUSTIFICAR'
                        THEN 1 ELSE 0
                    END
                ), 0) AS justificados,
                COALESCE(SUM(
                    CASE
                        WHEN UPPER(TRIM(g.ausentismo)) = 'SI'
                         AND (
                            g.justificacion IS NULL
                            OR TRIM(g.justificacion) = ''
                            OR UPPER(TRIM(g.justificacion)) = 'SIN JUSTIFICAR'
                         )
                        THEN 1 ELSE 0
                    END
                ), 0) AS injustificados
            FROM {table} AS g
            WHERE DATE(g.fecha_edit) BETWEEN %s AND %s
            {cedula_clause}
        """

        with connections[self.db_alias].cursor() as cursor:
            cursor.execute(sql, params)
            row = cursor.fetchone()

        if not row:
            return {
                "periodo_inicio": start_date.isoformat(),
                "periodo_fin": end_date.isoformat(),
                "total_ausentismos": 0,
                "justificados": 0,
                "injustificados": 0,
            }

        return {
            "periodo_inicio": str(row[0]),
            "periodo_fin": str(row[1]),
            "total_ausentismos": int(row[2] or 0),
            "justificados": int(row[3] or 0),
            "injustificados": int(row[4] or 0),
        }

    def get_attendance_summary(
        self,
        start_date: date,
        end_date: date,
        *,
        cedula: str | None = None,
        focus: str = "all",
        justificacion_filter: str | None = None,
    ) -> dict:
        table = self._safe_table()
        normalized_cedula = self._normalize_id_value(cedula)
        cedula_clause = ""
        params: list[Any] = [start_date, end_date, start_date, end_date]
        if normalized_cedula:
            cedula_clause = f" AND {self._normalized_id_sql('g.cedula')} = %s"
            params.append(normalized_cedula)
        reason_clause, reason_params, canonical_reason = self._build_reason_clause(
            column_expr="g.justificacion",
            reason_filter=justificacion_filter,
        )
        focus_clause = self._build_focus_clause(column_expr="g.justificacion", focus=focus)
        sql = f"""
            SELECT
                %s AS periodo_inicio,
                %s AS periodo_fin,
                COUNT(*) AS total_ausentismos,
                COALESCE(SUM(
                    CASE
                        WHEN g.justificacion IS NOT NULL
                         AND TRIM(g.justificacion) <> ''
                         AND UPPER(TRIM(g.justificacion)) <> 'SIN JUSTIFICAR'
                        THEN 1 ELSE 0
                    END
                ), 0) AS justificados,
                COALESCE(SUM(
                    CASE
                        WHEN g.justificacion IS NULL
                          OR TRIM(g.justificacion) = ''
                          OR UPPER(TRIM(g.justificacion)) = 'SIN JUSTIFICAR'
                        THEN 1 ELSE 0
                    END
                ), 0) AS injustificados
            FROM {table} AS g
            WHERE DATE(g.fecha_edit) BETWEEN %s AND %s
              AND UPPER(TRIM(COALESCE(g.ausentismo, ''))) = 'SI'
              {cedula_clause}
              {reason_clause}
              {focus_clause}
        """
        with connections[self.db_alias].cursor() as cursor:
            cursor.execute(sql, [*params, *reason_params])
            row = cursor.fetchone()

        if not row:
            return {
                "periodo_inicio": start_date.isoformat(),
                "periodo_fin": end_date.isoformat(),
                "total_ausentismos": 0,
                "justificados": 0,
                "injustificados": 0,
                "justificacion_filter": canonical_reason,
            }

        return {
            "periodo_inicio": str(row[0]),
            "periodo_fin": str(row[1]),
            "total_ausentismos": int(row[2] or 0),
            "justificados": int(row[3] or 0),
            "injustificados": int(row[4] or 0),
            "justificacion_filter": canonical_reason,
        }

    def get_unjustified_table(
        self,
        start_date: date,
        end_date: date,
        limit: int = 100,
        *,
        cedula: str | None = None,
    ) -> dict:
        rows = []
        base_rows = self._attendance_base_unjustified(start_date, end_date, limit, cedula=cedula)
        for cedula, fecha_ausentismo, justificacion in base_rows:
            rows.append(
                {
                    "cedula": str(cedula),
                    "fecha_ausentismo": str(fecha_ausentismo),
                    "justificacion": str(justificacion or ""),
                }
            )

        safe_limit = max(1, min(int(limit), 500))
        return {
            "periodo_inicio": start_date.isoformat(),
            "periodo_fin": end_date.isoformat(),
            "rows": rows,
            "rowcount": len(rows),
            "truncated": len(rows) == safe_limit,
        }

    def get_unjustified_with_personal(
        self,
        start_date: date,
        end_date: date,
        limit: int = 100,
        *,
        personal_status: str = "all",
        cedula: str | None = None,
        extra_personal_columns: list[str] | None = None,
    ) -> dict:
        base_rows = self._attendance_base_unjustified(start_date, end_date, limit, cedula=cedula)
        cedulas = [str(row[0] or "") for row in base_rows]
        personal_columns = [
            "cedula",
            "nombre",
            "apellido",
            "supervisor",
            "area",
            "cargo",
            "carpeta",
            *[
                str(item or "").strip().lower()
                for item in list(extra_personal_columns or [])
                if str(item or "").strip()
            ],
        ]
        personal_columns = list(dict.fromkeys(personal_columns))
        employer_catalog = self.get_data_employers(
            personal_columns,
            cedulas,
            status=personal_status,
        )
        by_cedula = employer_catalog["by_cedula"]

        supervisor_ids = [
            str(item.get("supervisor") or "")
            for item in by_cedula.values()
            if str(item.get("supervisor") or "").strip()
        ]
        supervisor_catalog = self.get_data_employers(
            ["cedula", "nombre", "apellido"],
            supervisor_ids,
            status="all",
        )
        supervisors = supervisor_catalog["by_cedula"]

        rows: list[dict] = []
        for cedula, fecha_ausentismo, justificacion in base_rows:
            cedula_raw = str(cedula or "")
            cedula_norm = self._normalize_id_value(cedula_raw)
            emp = by_cedula.get(cedula_norm)

            nombre = str((emp or {}).get("nombre") or "").strip()
            apellido = str((emp or {}).get("apellido") or "").strip()
            empleado = self._compose_full_name(nombre, apellido)
            if not empleado:
                empleado = f"Cedula {cedula_raw}"

            supervisor_cedula_raw = str((emp or {}).get("supervisor") or "").strip()
            supervisor_norm = self._normalize_id_value(supervisor_cedula_raw)
            sup = supervisors.get(supervisor_norm)
            supervisor_nombre = self._compose_full_name(
                str((sup or {}).get("nombre") or ""),
                str((sup or {}).get("apellido") or ""),
            )
            supervisor = supervisor_nombre or supervisor_cedula_raw or "N/D"

            rows.append(
                {
                    "cedula": cedula_raw,
                    "fecha_ausentismo": str(fecha_ausentismo),
                    "nombre": nombre,
                    "apellido": apellido,
                    "empleado": empleado,
                    "supervisor_cedula": supervisor_cedula_raw,
                    "area": str((emp or {}).get("area") or ""),
                    "cargo": str((emp or {}).get("cargo") or ""),
                    "carpeta": str((emp or {}).get("carpeta") or ""),
                    "supervisor": supervisor,
                    "personal_match": bool(emp),
                    "justificacion": str(justificacion or ""),
                    "estado_justificacion": "INJUSTIFICADO",
                }
            )
            for extra_key in personal_columns:
                if extra_key in {"cedula", "nombre", "apellido", "supervisor", "area", "cargo", "carpeta"}:
                    continue
                rows[-1][extra_key] = str((emp or {}).get(extra_key) or "")

        matched = sum(1 for row in rows if row.get("personal_match"))
        unmatched = max(0, len(rows) - matched)
        safe_limit = max(1, min(int(limit), 500))

        return {
            "periodo_inicio": start_date.isoformat(),
            "periodo_fin": end_date.isoformat(),
            "rows": rows,
            "rowcount": len(rows),
            "matched_personal": matched,
            "unmatched_personal": unmatched,
            "personal_status_filter": employer_catalog.get("status_filter", "all"),
            "personal_status_column": employer_catalog.get("status_column"),
            "personal_catalog_count": employer_catalog.get("catalog_count", 0),
            "personal_table": self.personal_table,
            "personal_table_source": self.personal_table_source,
            "attendance_table": self.table,
            "attendance_table_source": self.table_source,
            "truncated": len(rows) == safe_limit,
        }

    def get_detail_with_personal(
        self,
        start_date: date,
        end_date: date,
        *,
        limit: int = 150,
        personal_status: str = "all",
        cedula: str | None = None,
        extra_personal_columns: list[str] | None = None,
        justificacion_filter: str | None = None,
        focus: str = "all",
    ) -> dict:
        table = self._safe_table()
        safe_limit = max(1, min(int(limit), 500))
        normalized_cedula = self._normalize_id_value(cedula)
        cedula_clause = ""
        params: list[Any] = [start_date, end_date]
        if normalized_cedula:
            cedula_clause = f" AND {self._normalized_id_sql('g.cedula')} = %s"
            params.append(normalized_cedula)
        reason_clause, reason_params, canonical_reason = self._build_reason_clause(
            column_expr="g.justificacion",
            reason_filter=justificacion_filter,
        )
        focus_clause = self._build_focus_clause(column_expr="g.justificacion", focus=focus)
        attendance_columns = self._get_attendance_columns()
        justified_extra_columns = [
            column
            for column in self._resolve_justified_detail_extra_columns(
                canonical_reason=canonical_reason,
                focus=focus,
            )
            if column in attendance_columns and _SAFE_COLUMN_RE.match(column)
        ]
        justified_extra_select = "".join(
            f", COALESCE(CAST(g.{column} AS CHAR), '') AS {column}"
            for column in justified_extra_columns
        )

        query = f"""
            SELECT
                g.cedula,
                DATE(g.fecha_edit) AS fecha_ausentismo,
                UPPER(TRIM(COALESCE(g.ausentismo, ''))) AS ausentismo,
                COALESCE(g.justificacion, '') AS justificacion
                {justified_extra_select}
            FROM {table} AS g
            WHERE DATE(g.fecha_edit) BETWEEN %s AND %s
            {cedula_clause}
              AND UPPER(TRIM(COALESCE(g.ausentismo, ''))) = 'SI'
              {reason_clause}
              {focus_clause}
            ORDER BY DATE(g.fecha_edit) DESC, g.cedula
            LIMIT %s
        """
        params.extend(reason_params)
        params.append(safe_limit)

        with connections[self.db_alias].cursor() as cursor:
            cursor.execute(query, params)
            base_rows = cursor.fetchall()

        cedulas = [str(row[0] or "") for row in base_rows]
        personal_columns = [
            "cedula",
            "nombre",
            "apellido",
            "supervisor",
            "area",
            "cargo",
            "carpeta",
            *[
                str(item or "").strip().lower()
                for item in list(extra_personal_columns or [])
                if str(item or "").strip()
            ],
        ]
        personal_columns = list(dict.fromkeys(personal_columns))
        employer_catalog = self.get_data_employers(
            personal_columns,
            cedulas,
            status=personal_status,
        )
        by_cedula = employer_catalog["by_cedula"]

        supervisor_ids = [
            str(item.get("supervisor") or "")
            for item in by_cedula.values()
            if str(item.get("supervisor") or "").strip()
        ]
        supervisor_catalog = self.get_data_employers(
            ["cedula", "nombre", "apellido"],
            supervisor_ids,
            status="all",
        )
        supervisors = supervisor_catalog["by_cedula"]

        rows: list[dict] = []
        select_columns = [
            "cedula",
            "fecha_ausentismo",
            "ausentismo",
            "justificacion",
            *justified_extra_columns,
        ]
        for raw_row in base_rows:
            row_data = {
                column_name: raw_row[idx] if idx < len(raw_row) else ""
                for idx, column_name in enumerate(select_columns)
            }
            cedula_raw = str(row_data.get("cedula") or "")
            cedula_norm = self._normalize_id_value(cedula_raw)
            emp = by_cedula.get(cedula_norm)

            nombre = str((emp or {}).get("nombre") or "").strip()
            apellido = str((emp or {}).get("apellido") or "").strip()
            nombre_completo = self._compose_full_name(nombre, apellido)

            supervisor_cedula_raw = str((emp or {}).get("supervisor") or "").strip()
            supervisor_norm = self._normalize_id_value(supervisor_cedula_raw)
            sup = supervisors.get(supervisor_norm)
            supervisor_nombre = self._compose_full_name(
                str((sup or {}).get("nombre") or ""),
                str((sup or {}).get("apellido") or ""),
            )
            supervisor = supervisor_nombre or supervisor_cedula_raw or "N/D"

            estado_justificacion = "INJUSTIFICADO"
            if str(row_data.get("justificacion") or "").strip() and str(row_data.get("justificacion") or "").strip().upper() != "SIN JUSTIFICAR":
                estado_justificacion = "JUSTIFICADO"

            rows.append(
                {
                    "cedula": cedula_raw,
                    "nombre": nombre,
                    "apellido": apellido,
                    "nombre_completo": nombre_completo,
                    "fecha_ausentismo": str(row_data.get("fecha_ausentismo") or ""),
                    "ausentismo": str(row_data.get("ausentismo") or ""),
                    "justificacion": str(row_data.get("justificacion") or ""),
                    "estado_justificacion": estado_justificacion,
                    "supervisor_cedula": supervisor_cedula_raw,
                    "supervisor": supervisor,
                    "area": str((emp or {}).get("area") or ""),
                    "cargo": str((emp or {}).get("cargo") or ""),
                    "carpeta": str((emp or {}).get("carpeta") or ""),
                }
            )
            for attendance_key in justified_extra_columns:
                rows[-1][attendance_key] = str(row_data.get(attendance_key) or "")
            for extra_key in personal_columns:
                if extra_key in {"cedula", "nombre", "apellido", "supervisor", "area", "cargo", "carpeta"}:
                    continue
                rows[-1][extra_key] = str((emp or {}).get(extra_key) or "")

        return {
            "periodo_inicio": start_date.isoformat(),
            "periodo_fin": end_date.isoformat(),
            "rows": rows,
            "rowcount": len(rows),
            "personal_status_filter": employer_catalog.get("status_filter", "all"),
            "personal_status_column": employer_catalog.get("status_column"),
            "personal_catalog_count": employer_catalog.get("catalog_count", 0),
            "personal_table": self.personal_table,
            "personal_table_source": self.personal_table_source,
            "attendance_table": self.table,
            "attendance_table_source": self.table_source,
            "truncated": len(rows) == safe_limit,
            "justificacion_filter": canonical_reason,
        }

    def get_recurrent_unjustified_with_supervisor(
        self,
        start_date: date,
        end_date: date,
        *,
        threshold: int = 3,
        limit: int = 150,
        personal_status: str = "all",
    ) -> dict:
        table = self._safe_table()
        safe_limit = max(1, min(int(limit), 500))
        safe_threshold = max(1, int(threshold))

        query = f"""
            SELECT
                g.cedula,
                COUNT(*) AS cantidad_incidencias,
                GROUP_CONCAT(
                    DISTINCT DATE(g.fecha_edit)
                    ORDER BY DATE(g.fecha_edit) DESC
                    SEPARATOR ', '
                ) AS fechas
            FROM {table} AS g
            WHERE DATE(g.fecha_edit) BETWEEN %s AND %s
              AND UPPER(TRIM(g.ausentismo)) = 'SI'
              AND (
                    g.justificacion IS NULL
                    OR TRIM(g.justificacion) = ''
                    OR UPPER(TRIM(g.justificacion)) = 'SIN JUSTIFICAR'
              )
            GROUP BY g.cedula
            HAVING COUNT(*) >= %s
            ORDER BY cantidad_incidencias DESC, g.cedula
            LIMIT %s
        """

        with connections[self.db_alias].cursor() as cursor:
            cursor.execute(query, [start_date, end_date, safe_threshold, safe_limit])
            base_rows = cursor.fetchall()

        cedulas = [str(row[0] or "") for row in base_rows]
        employer_catalog = self.get_data_employers(
            ["cedula", "nombre", "apellido", "supervisor", "area", "cargo", "carpeta"],
            cedulas,
            status=personal_status,
        )
        by_cedula = employer_catalog["by_cedula"]

        supervisor_ids = [
            str(item.get("supervisor") or "")
            for item in by_cedula.values()
            if str(item.get("supervisor") or "").strip()
        ]
        supervisor_catalog = self.get_data_employers(
            ["cedula", "nombre", "apellido"],
            supervisor_ids,
            status="all",
        )
        supervisors = supervisor_catalog["by_cedula"]

        rows: list[dict] = []
        for cedula, cantidad_incidencias, fechas in base_rows:
            cedula_raw = str(cedula or "")
            cedula_norm = self._normalize_id_value(cedula_raw)
            emp = by_cedula.get(cedula_norm)

            nombre = str((emp or {}).get("nombre") or "").strip()
            apellido = str((emp or {}).get("apellido") or "").strip()
            empleado = self._compose_full_name(nombre, apellido)
            if not empleado:
                empleado = f"Cedula {cedula_raw}"

            supervisor_cedula_raw = str((emp or {}).get("supervisor") or "").strip()
            supervisor_norm = self._normalize_id_value(supervisor_cedula_raw)
            sup = supervisors.get(supervisor_norm)
            supervisor_nombre = self._compose_full_name(
                str((sup or {}).get("nombre") or ""),
                str((sup or {}).get("apellido") or ""),
            )
            supervisor = supervisor_nombre or supervisor_cedula_raw or "N/D"

            rows.append(
                {
                    "cedula": cedula_raw,
                    "nombre": nombre,
                    "apellido": apellido,
                    "supervisor_cedula": supervisor_cedula_raw,
                    "empleado": empleado,
                    "supervisor": supervisor,
                    "area": str((emp or {}).get("area") or ""),
                    "cargo": str((emp or {}).get("cargo") or ""),
                    "carpeta": str((emp or {}).get("carpeta") or ""),
                    "cantidad_incidencias": int(cantidad_incidencias or 0),
                    "fechas": str(fechas or ""),
                }
            )

        return {
            "periodo_inicio": start_date.isoformat(),
            "periodo_fin": end_date.isoformat(),
            "threshold": safe_threshold,
            "rows": rows,
            "rowcount": len(rows),
            "personal_status_filter": employer_catalog.get("status_filter", "all"),
            "personal_status_column": employer_catalog.get("status_column"),
            "personal_catalog_count": employer_catalog.get("catalog_count", 0),
            "personal_table": self.personal_table,
            "personal_table_source": self.personal_table_source,
            "attendance_table": self.table,
            "attendance_table_source": self.table_source,
            "truncated": len(rows) == safe_limit,
        }
