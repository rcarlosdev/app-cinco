from __future__ import annotations

import base64
import csv
import io
import re
import time
import unicodedata
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from apps.ia_dev.application.orchestration.dashboard_composition_planner import (
    DashboardCompositionPlanner,
)
from apps.ia_dev.services.runtime_artifact_service import RuntimeArtifactService
from apps.ia_dev.application.semantic.query_execution_planner import QueryExecutionPlanner


_XML_NS = {
    "main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "rel": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "pkg": "http://schemas.openxmlformats.org/package/2006/relationships",
}
_SAFE_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9_]+$")
_INVISIBLE_RE = re.compile(r"[\u200b\u200c\u200d\ufeff]")
_PERSON_IDENTIFIER_RE = re.compile(r"^\d{5,15}$")
_MAX_ATTACHMENT_BYTES = 12 * 1024 * 1024
_MAX_SAMPLE_VALUES = 120
_PREVIEW_ROW_LIMIT = 200
_EXTRA_TABLE_PREVIEW_ROW_LIMIT = 50
_EXPORT_ARTIFACT_DIR = "tmp_provider_serial_validation_exports"
_RUNTIME_ARTIFACT_SERVICE = RuntimeArtifactService()
_DB_LOOKUP_CHUNK_SIZE = 1000
_NONCANONICAL_SERIAL_CACHE_LIMIT = 5000
_CURRENT_TABLES = (
    {"schema": "logistica_cinco", "table": "logistica_base_seriales", "kind": "base_actual", "label": "base actual"},
    {"schema": "logistica_cinco", "table": "logistica_seriales_asociados", "kind": "asociados_actual", "label": "asociados actual"},
)
_HISTORICAL_SCHEMAS = (
    {
        "schema": "z_c3nc4_f3sc1l",
        "table_prefix": "logistica_base_seriales_",
        "kind": "backup_base",
        "label_prefix": "backup base seriales",
    },
    {
        "schema": "z_c3nc4_f3sc1l",
        "table_prefix": "logistica_seriales_asociados_",
        "kind": "backup_asociados",
        "label_prefix": "backup asociados",
    },
)
_PROVIDER_COLUMN_ALIASES = {
    "serial": (
        "numero de serie",
        "numero serie",
        "número de serie",
        "número serie",
        "numero serial",
        "número serial",
        "serial",
        "serial equipo",
        "serie",
        "cpe",
        "sn",
        "mac",
    ),
    "material": ("material", "codigo material", "cod material", "material proveedor"),
    "denominacion": ("denominacion", "denominación", "descripcion", "descripción", "detalle"),
    "familia": ("familia", "family"),
}
_TABLE_FIELD_ALIASES = {
    "serial": ("serial", "numero serial", "numero de serie", "numero_serie", "numero_serial", "serie", "sn"),
    "estado": ("estado", "status", "status sistema", "status_sistema", "estado sistema"),
    "lote": ("lote", "lote de stock"),
    "cedula": ("cedula", "cédula", "documento", "identificacion", "identificación"),
    "edit": ("edit", "editor", "editado", "editado por", "edit_persona"),
    "movil": ("movil", "móvil", "cuadrilla", "brigada"),
    "bodega": ("bodega", "almacen", "almacén", "ubicacion", "ubicación", "centro"),
    "codigo": ("codigo", "código", "material", "cod material"),
    "descripcion": ("descripcion", "descripción", "denominacion", "denominación", "detalle"),
    "fecha": (
        "modificado el",
        "modificado",
        "creado el",
        "fecha",
        "fecha asociacion",
        "fecha_asociacion",
        "updated at",
        "updated_at",
        "created at",
        "created_at",
    ),
    "nombre": ("nombre",),
    "apellido": ("apellido",),
    "empleado": ("empleado", "codigo empleado", "id empleado"),
}


def _normalize_text(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = _INVISIBLE_RE.sub("", text)
    text = re.sub(r"[^a-zA-Z0-9]+", " ", text).strip().lower()
    return re.sub(r"\s+", " ", text).strip()


def _clean_text(value: Any) -> str:
    text = _INVISIBLE_RE.sub("", str(value or "")).strip()
    return re.sub(r"\s+", " ", text).strip()


def _row_get(row: dict[str, Any], key: str) -> Any:
    if key in row:
        return row.get(key)
    lowered = str(key or "").strip().lower()
    for row_key, row_value in row.items():
        if str(row_key or "").strip().lower() == lowered:
            return row_value
    return None


def _normalize_serial(value: Any) -> str:
    text = _clean_text(value)
    if not text:
        return ""
    return text.upper()


def _as_bool_label(value: bool) -> str:
    return "SI" if bool(value) else "NO"


def _looks_like_person_identifier(value: Any) -> bool:
    return bool(_PERSON_IDENTIFIER_RE.match(_clean_text(value)))


def _parse_datetime(value: Any) -> datetime | None:
    text = _clean_text(value)
    if not text:
        return None
    candidates = [text.replace("Z", "+00:00")]
    if " " in text and "T" not in text:
        candidates.append(text.replace(" ", "T"))
    for candidate in candidates:
        try:
            return datetime.fromisoformat(candidate)
        except Exception:
            continue
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y",
        "%d-%m-%Y %H:%M:%S",
        "%d-%m-%Y",
    ):
        try:
            return datetime.strptime(text, fmt)
        except Exception:
            continue
    return None


def _format_datetime(value: Any) -> str:
    parsed = _parse_datetime(value)
    if parsed is None:
        return _clean_text(value)
    return parsed.isoformat(sep=" ", timespec="seconds")


def _quote_identifier(value: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError("empty_identifier")
    if "." in normalized:
        return ".".join(_quote_identifier(part) for part in normalized.split("."))
    if not _SAFE_IDENTIFIER_RE.match(normalized):
        raise ValueError(f"unsafe_identifier:{normalized}")
    return f"`{normalized}`"


def _column_letter_index(reference: str) -> int:
    letters = "".join(ch for ch in str(reference or "") if ch.isalpha()).upper()
    result = 0
    for char in letters:
        result = result * 26 + (ord(char) - 64)
    return max(result - 1, 0)


@dataclass(slots=True)
class ArchivoTabular:
    sheet_name: str
    headers: list[str]
    rows: list[dict[str, Any]]


class LectorArchivoTabularProveedor:
    def parse(self, *, filename: str, mime_type: str, content: bytes) -> ArchivoTabular:
        lower_name = str(filename or "").strip().lower()
        lower_mime = str(mime_type or "").strip().lower()
        if lower_name.endswith(".csv") or "csv" in lower_mime:
            return self._parse_csv(content=content)
        if lower_name.endswith(".xlsx") or "spreadsheetml" in lower_mime or zipfile.is_zipfile(io.BytesIO(content)):
            return self._parse_xlsx(content=content)
        raise ValueError("archivo_no_soportado:solo_xlsx_o_csv")

    def _parse_csv(self, *, content: bytes) -> ArchivoTabular:
        text = ""
        for encoding in ("utf-8-sig", "utf-8", "latin-1"):
            try:
                text = content.decode(encoding)
                break
            except Exception:
                continue
        if not text:
            raise ValueError("archivo_csv_vacio_o_no_legible")
        reader = csv.reader(io.StringIO(text))
        rows = list(reader)
        if not rows:
            return ArchivoTabular(sheet_name="CSV", headers=[], rows=[])
        headers = [_clean_text(item) for item in rows[0]]
        body: list[dict[str, Any]] = []
        for raw_row in rows[1:]:
            row_payload = {
                headers[index]: raw_row[index] if index < len(raw_row) else ""
                for index in range(len(headers))
                if headers[index]
            }
            if any(_clean_text(value) for value in row_payload.values()):
                body.append(row_payload)
        return ArchivoTabular(sheet_name="CSV", headers=headers, rows=body)

    def _parse_xlsx(self, *, content: bytes) -> ArchivoTabular:
        workbook = zipfile.ZipFile(io.BytesIO(content))
        shared_strings = self._shared_strings(workbook=workbook)
        sheet_name, sheet_path = self._resolve_sheet(workbook=workbook)
        rows = self._sheet_rows(workbook=workbook, sheet_path=sheet_path, shared_strings=shared_strings)
        if not rows:
            return ArchivoTabular(sheet_name=sheet_name, headers=[], rows=[])
        headers = [_clean_text(item) for item in rows[0]]
        body: list[dict[str, Any]] = []
        for raw_row in rows[1:]:
            payload = {
                headers[index]: raw_row[index] if index < len(raw_row) else ""
                for index in range(len(headers))
                if headers[index]
            }
            if any(_clean_text(value) for value in payload.values()):
                body.append(payload)
        return ArchivoTabular(sheet_name=sheet_name, headers=headers, rows=body)

    def _shared_strings(self, *, workbook: zipfile.ZipFile) -> list[str]:
        try:
            raw = workbook.read("xl/sharedStrings.xml")
        except KeyError:
            return []
        root = ET.fromstring(raw)
        values: list[str] = []
        for item in root.findall("main:si", _XML_NS):
            text_nodes = item.findall(".//main:t", _XML_NS)
            values.append("".join(node.text or "" for node in text_nodes))
        return values

    def _resolve_sheet(self, *, workbook: zipfile.ZipFile) -> tuple[str, str]:
        workbook_root = ET.fromstring(workbook.read("xl/workbook.xml"))
        rel_root = ET.fromstring(workbook.read("xl/_rels/workbook.xml.rels"))
        rel_map = {
            str(item.attrib.get("Id") or ""): str(item.attrib.get("Target") or "")
            for item in rel_root.findall("pkg:Relationship", _XML_NS)
        }
        selected_name = ""
        selected_target = ""
        fallback_name = ""
        fallback_target = ""
        for sheet in workbook_root.findall("main:sheets/main:sheet", _XML_NS):
            sheet_name = str(sheet.attrib.get("name") or "").strip()
            relation_id = str(sheet.attrib.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id") or "")
            target = rel_map.get(relation_id, "")
            if target and not target.startswith("xl/"):
                target = f"xl/{target.lstrip('/')}"
            if not target:
                continue
            if not fallback_target:
                fallback_name, fallback_target = sheet_name or "Sheet1", target
            if _normalize_text(sheet_name) == "hoja1":
                selected_name, selected_target = sheet_name or "Hoja1", target
                break
        return (
            selected_name or fallback_name or "Sheet1",
            selected_target or fallback_target or "xl/worksheets/sheet1.xml",
        )

    def _sheet_rows(
        self,
        *,
        workbook: zipfile.ZipFile,
        sheet_path: str,
        shared_strings: list[str],
    ) -> list[list[str]]:
        root = ET.fromstring(workbook.read(sheet_path))
        rows: list[list[str]] = []
        for row in root.findall(".//main:sheetData/main:row", _XML_NS):
            indexed_values: dict[int, str] = {}
            for cell in row.findall("main:c", _XML_NS):
                ref = str(cell.attrib.get("r") or "")
                index = _column_letter_index(ref)
                cell_type = str(cell.attrib.get("t") or "")
                value = ""
                if cell_type == "inlineStr":
                    value = "".join(node.text or "" for node in cell.findall(".//main:t", _XML_NS))
                else:
                    raw_value = str((cell.findtext("main:v", default="", namespaces=_XML_NS) or "")).strip()
                    if cell_type == "s" and raw_value.isdigit():
                        shared_index = int(raw_value)
                        if 0 <= shared_index < len(shared_strings):
                            value = shared_strings[shared_index]
                    else:
                        value = raw_value
                indexed_values[index] = value
            if not indexed_values:
                continue
            max_index = max(indexed_values)
            rows.append([indexed_values.get(index, "") for index in range(max_index + 1)])
        return rows


class ValidadorSerialesProveedorService:
    CAPABILITY_ID = "inventory_provider_serial_validation"
    TEMPLATE_ID = "inventory_provider_serial_validation"
    PLANNER_ROUTE_HINT = "inventory.serial.validation.provider_file"
    RESPONSE_PROFILE_ID = "inventory.serial.validation.provider_file.detail"
    DB_ALIAS = "logistica_cinco"
    HISTORICAL_START_YEAR = 2023

    def __init__(
        self,
        *,
        planner: QueryExecutionPlanner | None = None,
        dashboard_planner: DashboardCompositionPlanner | None = None,
        file_reader: LectorArchivoTabularProveedor | None = None,
    ):
        self.planner = planner or QueryExecutionPlanner()
        self.dashboard_planner = dashboard_planner or DashboardCompositionPlanner()
        self.file_reader = file_reader or LectorArchivoTabularProveedor()
        self._table_exists_cache: dict[tuple[str, str], bool] = {}
        self._table_columns_cache: dict[tuple[str, str], list[str]] = {}
        self._noncanonical_serial_cache: dict[tuple[str, str], dict[str, Any]] = {}

    def validate(
        self,
        *,
        attachment: dict[str, Any] | None,
        user_message: str,
        previous_year: int,
    ) -> dict[str, Any]:
        trace: list[dict[str, Any]] = []
        if not attachment:
            return self._blocked_result(
                trace=trace,
                response_status="clarification_required",
                limitation="Adjunta un archivo Excel o CSV con seriales para ejecutar la validacion.",
                missing_reason="attachment_required",
                user_message=user_message,
            )

        filename = _clean_text(attachment.get("name"))
        mime_type = _clean_text(attachment.get("mime_type") or attachment.get("mimeType"))
        encoded = str(attachment.get("content_base64") or "").strip()
        if not filename or not encoded:
            return self._blocked_result(
                trace=trace,
                response_status="clarification_required",
                limitation="El adjunto no trae nombre o contenido suficiente para procesarlo.",
                missing_reason="attachment_incomplete",
                user_message=user_message,
            )

        content = self._decode_attachment(encoded=encoded)
        if len(content) > _MAX_ATTACHMENT_BYTES:
            return self._blocked_result(
                trace=trace,
                response_status="limitation_declared",
                limitation="El archivo supera el tamano maximo seguro soportado para esta ruta.",
                missing_reason="attachment_too_large",
                user_message=user_message,
            )

        archivo = self.file_reader.parse(filename=filename, mime_type=mime_type, content=content)
        trace.append(
            {
                "phase": "archivo",
                "status": "ok",
                "detail": {
                    "filename": filename,
                    "mime_type": mime_type,
                    "sheet_name": archivo.sheet_name,
                    "headers": archivo.headers,
                    "rowcount": len(archivo.rows),
                },
            }
        )

        if not archivo.rows:
            return self._blocked_result(
                trace=trace,
                response_status="empty_result",
                limitation="El archivo no contiene filas operativas para validar.",
                missing_reason="provider_file_empty",
                user_message=user_message,
                extra_filters={"sheet_name": archivo.sheet_name},
            )

        provider_columns = self._detect_provider_columns(archivo=archivo)
        trace.append(
            {
                "phase": "deteccion_columnas",
                "status": "ok" if provider_columns.get("serial") else "warning",
                "detail": provider_columns,
            }
        )
        serial_column = str((provider_columns.get("serial") or {}).get("header") or "")
        if not serial_column:
            return self._blocked_result(
                trace=trace,
                response_status="clarification_required",
                limitation="No se detecto una columna de serial con evidencia semantica suficiente.",
                missing_reason="serial_column_not_detected",
                user_message=user_message,
                extra_filters={"sheet_name": archivo.sheet_name},
            )

        provider_rows = self._build_provider_rows(archivo=archivo, provider_columns=provider_columns)
        non_empty_rows = [row for row in provider_rows if row["serial_normalizado"]]
        if not non_empty_rows:
            return self._blocked_result(
                trace=trace,
                response_status="empty_result",
                limitation="La columna candidata de serial no trae valores operativos para consultar.",
                missing_reason="provider_serials_empty",
                user_message=user_message,
                extra_filters={"sheet_name": archivo.sheet_name, "serial_column": serial_column},
            )

        duplicate_counter = Counter(row["serial_normalizado"] for row in non_empty_rows if row["serial_normalizado"])
        for row in provider_rows:
            normalized = row["serial_normalizado"]
            row["duplicado_en_archivo"] = bool(normalized and duplicate_counter.get(normalized, 0) > 1)
            row["ocurrencias_archivo"] = int(duplicate_counter.get(normalized, 0))

        years = list(range(self.HISTORICAL_START_YEAR, max(self.HISTORICAL_START_YEAR, int(previous_year)) + 1))
        discovery = self._discover_tables(years=years)
        trace.append(
            {
                "phase": "descubrimiento_tablas",
                "status": "ok",
                "detail": {
                    "consultadas": [item["label"] for item in discovery["existing_tables"]],
                    "no_existian": [item["label"] for item in discovery["missing_tables"]],
                },
            }
        )

        lookup_results = self._query_all_tables(
            normalized_serials=sorted({row["serial_normalizado"] for row in non_empty_rows if row["serial_normalizado"]}),
            tables=discovery["existing_tables"],
        )
        trace.append(
            {
                "phase": "consultas_gobernadas",
                "status": "ok",
                "detail": {
                    "tablas_consultadas": [item["label"] for item in discovery["existing_tables"]],
                    "coincidencias_por_tabla": {
                        item["label"]: int(item["match_count"]) for item in lookup_results["table_results"]
                    },
                    "coincidencias_por_etapa": {
                        str(item.get("label") or ""): {
                            "seriales_entrada": int(item.get("input_serials") or 0),
                            "seriales_encontrados": int(item.get("found_serials") or 0),
                            "seriales_pendientes": int(item.get("pending_after_stage") or 0),
                        }
                        for item in list(lookup_results.get("stage_results") or [])
                    },
                    "diagnostico_rendimiento": dict(lookup_results.get("performance_diagnostics") or {}),
                },
            }
        )

        personal_rows = self._enrich_personal(matches=lookup_results["matches"])
        trace.append(
            {
                "phase": "enriquecimiento_personal",
                "status": "ok",
                "detail": {"identificadores_enriquecidos": len(personal_rows)},
            }
        )
        personal_by_identifier = {
            _clean_text(row.get("cedula")): row
            for row in personal_rows
            if _clean_text(row.get("cedula"))
        }

        consolidated_rows = self._consolidate_rows(
            provider_rows=provider_rows,
            matches_by_serial=lookup_results["matches_by_serial"],
            personal_by_identifier=personal_by_identifier,
            discovery=discovery,
        )
        export_artifact = self._write_export_artifact(rows=consolidated_rows)
        result_table = self._build_main_table(rows=consolidated_rows, export_artifact=export_artifact)
        extra_tables = self._build_extra_tables(rows=consolidated_rows, discovery=discovery)
        kpis = self._build_kpis(rows=consolidated_rows)
        business_response = self._build_business_response(
            user_message=user_message,
            attachment=attachment,
            archivo=archivo,
            provider_columns=provider_columns,
            rows=consolidated_rows,
            kpis=kpis,
            discovery=discovery,
            extra_tables=extra_tables,
            export_artifact=export_artifact,
        )

        return {
            "status": "success" if consolidated_rows else "empty_result",
            "reply": str(business_response.get("dato") or ""),
            "data": {
                "kpis": kpis,
                "series": [],
                "labels": [],
                "insights": [
                    str(business_response.get("hallazgo") or ""),
                    str(business_response.get("recomendacion") or ""),
                ],
                "table": result_table,
                "extra_tables": extra_tables,
                "business_response": business_response,
            },
            "trace": trace,
        }

    def _decode_attachment(self, *, encoded: str) -> bytes:
        try:
            return base64.b64decode(encoded, validate=True)
        except Exception as exc:
            raise ValueError(f"attachment_base64_invalido:{exc}") from exc

    def _blocked_result(
        self,
        *,
        trace: list[dict[str, Any]],
        response_status: str,
        limitation: str,
        missing_reason: str,
        user_message: str,
        extra_filters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        business_response = self._business_response_payload(
            user_message=user_message,
            attachment_name="",
            sheet_name=str((extra_filters or {}).get("sheet_name") or ""),
            serial_column="",
            rows=[],
            kpis={},
            discovery={"existing_tables": [], "missing_tables": []},
            response_status=response_status,
            dato=limitation,
            hallazgo=limitation,
            interpretacion="La capacidad no presento exito porque falta evidencia operativa suficiente para ejecutar.",
            recomendacion="Adjunta un archivo valido y vuelve a intentarlo." if response_status != "limitation_declared" else "Reduce el alcance o usa un archivo mas pequeno.",
            limitations=[missing_reason],
            extra_filters=extra_filters or {},
        )
        return {
            "status": response_status,
            "reply": str(business_response.get("dato") or ""),
            "data": {
                "kpis": {},
                "series": [],
                "labels": [],
                "insights": [limitation],
                "table": {"columns": [], "rows": [], "rowcount": 0},
                "extra_tables": [],
                "business_response": business_response,
            },
            "trace": trace,
        }

    def _detect_provider_columns(self, *, archivo: ArchivoTabular) -> dict[str, Any]:
        detected: dict[str, Any] = {}
        for logical_name, aliases in _PROVIDER_COLUMN_ALIASES.items():
            best = {"header": "", "index": -1, "confidence": 0.0}
            for index, header in enumerate(archivo.headers):
                score = self._score_header_against_aliases(header=header, aliases=aliases)
                if logical_name == "serial":
                    score += self._serial_value_confidence(archivo=archivo, header=header)
                if score > float(best["confidence"]):
                    best = {"header": header, "index": index, "confidence": round(score, 3)}
            if best["header"] and float(best["confidence"]) >= (0.72 if logical_name == "serial" else 0.65):
                detected[logical_name] = best
        return detected

    def _score_header_against_aliases(self, *, header: str, aliases: tuple[str, ...]) -> float:
        normalized_header = _normalize_text(header)
        if not normalized_header:
            return 0.0
        header_tokens = set(normalized_header.split())
        best = 0.0
        for alias in aliases:
            normalized_alias = _normalize_text(alias)
            alias_tokens = set(normalized_alias.split())
            if normalized_header == normalized_alias:
                best = max(best, 0.9)
            elif alias_tokens and alias_tokens.issubset(header_tokens):
                best = max(best, 0.82)
            elif (
                len(normalized_header) >= 4
                and len(normalized_alias) >= 4
                and (normalized_alias in normalized_header or normalized_header in normalized_alias)
            ):
                best = max(best, 0.74)
        return best

    def _serial_value_confidence(self, *, archivo: ArchivoTabular, header: str) -> float:
        if not header:
            return 0.0
        samples = [
            _normalize_serial((row or {}).get(header))
            for row in archivo.rows[: _MAX_SAMPLE_VALUES]
            if _normalize_serial((row or {}).get(header))
        ]
        if not samples:
            return 0.0
        unique_ratio = len(set(samples)) / max(1, len(samples))
        alnum_ratio = sum(1 for item in samples if re.search(r"[A-Z0-9]", item)) / max(1, len(samples))
        length_ratio = sum(1 for item in samples if len(item) >= 4) / max(1, len(samples))
        mac_like = _normalize_text(header) in {"mac", "sn"}
        if mac_like and unique_ratio < 0.8:
            return 0.0
        return round((unique_ratio * 0.22) + (alnum_ratio * 0.1) + (length_ratio * 0.08), 3)

    def _build_provider_rows(
        self,
        *,
        archivo: ArchivoTabular,
        provider_columns: dict[str, Any],
    ) -> list[dict[str, Any]]:
        serial_header = str((provider_columns.get("serial") or {}).get("header") or "")
        material_header = str((provider_columns.get("material") or {}).get("header") or "")
        denominacion_header = str((provider_columns.get("denominacion") or {}).get("header") or "")
        familia_header = str((provider_columns.get("familia") or {}).get("header") or "")
        rows: list[dict[str, Any]] = []
        for index, row in enumerate(archivo.rows, start=2):
            serial_original = _clean_text((row or {}).get(serial_header))
            rows.append(
                {
                    "fila_archivo": index,
                    "serial_proveedor": serial_original,
                    "serial_normalizado": _normalize_serial(serial_original),
                    "material_proveedor": _clean_text((row or {}).get(material_header)),
                    "denominacion_proveedor": _clean_text((row or {}).get(denominacion_header)),
                    "familia_proveedor": _clean_text((row or {}).get(familia_header)),
                }
            )
        return rows

    def _discover_tables(self, *, years: list[int]) -> dict[str, Any]:
        existing_tables: list[dict[str, Any]] = []
        missing_tables: list[dict[str, Any]] = []
        for item in _CURRENT_TABLES:
            if self._table_exists(schema=item["schema"], table=item["table"]):
                existing_tables.append(
                    {
                        **item,
                        "year": None,
                        "fqn": f"{item['schema']}.{item['table']}",
                        "columns": self._get_table_columns(schema=item["schema"], table=item["table"]),
                    }
                )
            else:
                missing_tables.append({**item, "year": None, "label": item["label"]})
        for descriptor in _HISTORICAL_SCHEMAS:
            for year in years:
                table_name = f"{descriptor['table_prefix']}{year}"
                label = f"{descriptor['label_prefix']} anio {year}"
                if self._table_exists(schema=descriptor["schema"], table=table_name):
                    existing_tables.append(
                        {
                            "schema": descriptor["schema"],
                            "table": table_name,
                            "year": year,
                            "kind": descriptor["kind"],
                            "label": label,
                            "fqn": f"{descriptor['schema']}.{table_name}",
                            "columns": self._get_table_columns(schema=descriptor["schema"], table=table_name),
                        }
                    )
                else:
                    missing_tables.append(
                        {
                            "schema": descriptor["schema"],
                            "table": table_name,
                            "year": year,
                            "kind": descriptor["kind"],
                            "label": label,
                        }
                    )
        return {"existing_tables": existing_tables, "missing_tables": missing_tables}

    def _table_exists(self, *, schema: str, table: str) -> bool:
        cache_key = (_clean_text(schema).lower(), _clean_text(table).lower())
        if cache_key in self._table_exists_cache:
            return bool(self._table_exists_cache[cache_key])
        query = (
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = %s AND table_name = %s LIMIT 1"
        )
        result = self.planner.execute_governed_select(
            db_alias=self.DB_ALIAS,
            query=query,
            params=[schema, table],
            allowed_tables=["information_schema.tables"],
            allowed_columns=["table_schema", "table_name"],
            declared_columns=["table_schema", "table_name"],
            max_limit=10,
        )
        exists = bool(result.get("ok")) and int(result.get("rowcount") or 0) > 0
        self._table_exists_cache[cache_key] = exists
        return exists

    def _get_table_columns(self, *, schema: str, table: str) -> list[str]:
        cache_key = (_clean_text(schema).lower(), _clean_text(table).lower())
        cached = self._table_columns_cache.get(cache_key)
        if cached is not None:
            return list(cached)
        query = (
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = %s AND table_name = %s "
            "ORDER BY ordinal_position ASC LIMIT 200"
        )
        result = self.planner.execute_governed_select(
            db_alias=self.DB_ALIAS,
            query=query,
            params=[schema, table],
            allowed_tables=["information_schema.columns"],
            allowed_columns=["table_schema", "table_name", "column_name", "ordinal_position"],
            declared_columns=["table_schema", "table_name", "column_name", "ordinal_position"],
            max_limit=200,
        )
        if not result.get("ok"):
            return []
        columns = [
            _clean_text(_row_get(row, "column_name"))
            for row in list(result.get("rows") or [])
            if _clean_text(_row_get(row, "column_name"))
        ]
        self._table_columns_cache[cache_key] = list(columns)
        return columns

    def _table_lookup_priority(self, *, table: dict[str, Any]) -> tuple[int, int]:
        kind = str(table.get("kind") or "")
        year = int(table.get("year") or 0)
        kind_rank = {
            "base_actual": 0,
            "asociados_actual": 1,
            "backup_base": 2,
            "backup_asociados": 3,
        }.get(kind, 9)
        return (kind_rank, -year)

    def _resolve_table_field(self, *, columns: list[str], logical_name: str) -> str:
        normalized_logical = _normalize_text(logical_name)
        exact_logical_matches = [
            column for column in columns if _normalize_text(column) == normalized_logical
        ]
        if exact_logical_matches:
            return exact_logical_matches[0]
        best_column = ""
        best_score = 0.0
        aliases = _TABLE_FIELD_ALIASES.get(logical_name, ())
        for column in columns:
            score = self._score_header_against_aliases(header=column, aliases=aliases)
            if score > best_score:
                best_score = score
                best_column = column
        return best_column if best_score >= 0.65 else ""

    def _build_lookup_stage_plan(self, *, tables: list[dict[str, Any]]) -> list[dict[str, Any]]:
        ordered_tables = sorted(list(tables), key=lambda item: self._table_lookup_priority(table=item))
        grouped_tables: dict[str, list[dict[str, Any]]] = {
            "base_actual": [],
            "asociados_actual": [],
            "backup_base": [],
            "backup_asociados": [],
        }
        for table in ordered_tables:
            kind = str(table.get("kind") or "")
            if kind in grouped_tables:
                grouped_tables[kind].append(table)
        return [
            {
                "stage_key": "base_actual",
                "phase": "buscando_base_actual",
                "label": "Buscando en base actual",
                "tables": grouped_tables["base_actual"],
            },
            {
                "stage_key": "asociados_actual",
                "phase": "buscando_asociados_actual",
                "label": "Buscando no encontrados en asociados",
                "tables": grouped_tables["asociados_actual"],
            },
            {
                "stage_key": "backup_base",
                "phase": "buscando_backups_base",
                "label": "Buscando remanentes en backups base",
                "tables": grouped_tables["backup_base"],
            },
            {
                "stage_key": "backup_asociados",
                "phase": "buscando_backups_asociados",
                "label": "Buscando remanentes en backups asociados",
                "tables": grouped_tables["backup_asociados"],
            },
        ]

    def _query_all_tables(
        self,
        *,
        normalized_serials: list[str],
        tables: list[dict[str, Any]],
    ) -> dict[str, Any]:
        matches: list[dict[str, Any]] = []
        matches_by_serial: dict[str, list[dict[str, Any]]] = defaultdict(list)
        table_results: list[dict[str, Any]] = []
        pending_serials = [serial for serial in normalized_serials if serial]
        found_in_base_actual: set[str] = set()
        found_in_asociados_actual: set[str] = set()
        found_in_historico: set[str] = set()
        stage_results: list[dict[str, Any]] = []
        performance_diagnostics = {
            "chunk_size": int(_DB_LOOKUP_CHUNK_SIZE),
            "query_count_total": 0,
            "sql_time_ms_total": 0.0,
            "python_time_ms_total": 0.0,
            "serialization_time_ms_total": 0.0,
            "rows_returned_total": 0,
            "stages": [],
            "tables": [],
        }

        for stage in self._build_lookup_stage_plan(tables=tables):
            stage_key = str(stage.get("stage_key") or "")
            stage_tables = list(stage.get("tables") or [])
            if not pending_serials or not stage_tables:
                stage_results.append(
                    {
                        "stage_key": stage_key,
                        "phase": stage.get("phase"),
                        "label": stage.get("label"),
                        "input_serials": len(pending_serials),
                        "found_serials": 0,
                        "pending_after_stage": len(pending_serials),
                        "queried_tables": [],
                    }
                )
                continue

            stage_input_serials = list(pending_serials)
            queried_tables: list[dict[str, Any]] = []
            stage_sql_ms = 0.0
            stage_python_ms = 0.0
            stage_serialization_ms = 0.0
            stage_query_count = 0
            stage_rows_returned = 0
            for table in stage_tables:
                table_input = list(pending_serials)
                if not table_input:
                    break
                table_metrics: dict[str, Any] = {}
                table_matches = self._query_table(
                    table=table,
                    normalized_serials=table_input,
                    lookup_metrics=table_metrics,
                )
                table_results.append({"label": table["label"], "match_count": len(table_matches)})
                queried_tables.append(
                    {
                        "stage_key": stage_key,
                        "stage_label": str(stage.get("label") or ""),
                        "label": table["label"],
                        "match_count": len(table_matches),
                        "input_serials": len(table_input),
                        "query_count": int(table_metrics.get("query_count") or 0),
                        "preflight_query_count": int(table_metrics.get("preflight_query_count") or 0),
                        "preflight_sql_time_ms": round(float(table_metrics.get("preflight_sql_time_ms") or 0.0), 2),
                        "sql_time_ms": round(float(table_metrics.get("sql_time_ms") or 0.0), 2),
                        "lookup_sql_time_ms": round(float(table_metrics.get("lookup_sql_time_ms") or 0.0), 2),
                        "python_time_ms": round(float(table_metrics.get("python_time_ms") or 0.0), 2),
                        "serialization_time_ms": round(float(table_metrics.get("serialization_time_ms") or 0.0), 2),
                        "rows_returned": int(table_metrics.get("rows_returned") or 0),
                        "normalized_fallback_enabled": bool(table_metrics.get("normalized_fallback_enabled")),
                        "normalized_fallback_reason": str(table_metrics.get("normalized_fallback_reason") or ""),
                        "noncanonical_rows_loaded": int(table_metrics.get("noncanonical_rows_loaded") or 0),
                        "noncanonical_cache_hits": int(table_metrics.get("noncanonical_cache_hits") or 0),
                        "noncanonical_cache_truncated": bool(table_metrics.get("noncanonical_cache_truncated")),
                        "chunk_count": int(table_metrics.get("chunk_count") or 0),
                        "chunk_metrics": list(table_metrics.get("chunk_metrics") or []),
                    }
                )
                stage_query_count += int(table_metrics.get("query_count") or 0)
                stage_sql_ms += float(table_metrics.get("sql_time_ms") or 0.0)
                stage_python_ms += float(table_metrics.get("python_time_ms") or 0.0)
                stage_serialization_ms += float(table_metrics.get("serialization_time_ms") or 0.0)
                stage_rows_returned += int(table_metrics.get("rows_returned") or 0)
                matches.extend(table_matches)
                found_in_table: set[str] = set()
                for item in table_matches:
                    serial_normalizado = str(item.get("serial_normalizado") or "")
                    if not serial_normalizado:
                        continue
                    found_in_table.add(serial_normalizado)
                    matches_by_serial[serial_normalizado].append(item)
                if stage_key == "base_actual":
                    found_in_base_actual.update(found_in_table)
                elif stage_key == "asociados_actual":
                    found_in_asociados_actual.update(found_in_table)
                elif stage_key in {"backup_base", "backup_asociados"}:
                    found_in_historico.update(found_in_table)
                pending_serials = [
                    serial for serial in pending_serials if serial and serial not in found_in_table
                ]

            stage_results.append(
                {
                    "stage_key": stage_key,
                    "phase": stage.get("phase"),
                    "label": stage.get("label"),
                    "input_serials": len(stage_input_serials),
                    "found_serials": len([serial for serial in stage_input_serials if serial not in pending_serials]),
                    "pending_after_stage": len(pending_serials),
                    "queried_tables": queried_tables,
                    "query_count": stage_query_count,
                    "sql_time_ms": round(stage_sql_ms, 2),
                    "python_time_ms": round(stage_python_ms, 2),
                    "serialization_time_ms": round(stage_serialization_ms, 2),
                    "rows_returned": stage_rows_returned,
                }
            )
            performance_diagnostics["query_count_total"] += stage_query_count
            performance_diagnostics["sql_time_ms_total"] += stage_sql_ms
            performance_diagnostics["python_time_ms_total"] += stage_python_ms
            performance_diagnostics["serialization_time_ms_total"] += stage_serialization_ms
            performance_diagnostics["rows_returned_total"] += stage_rows_returned
            performance_diagnostics["stages"].append(
                {
                    "stage_key": stage_key,
                    "label": str(stage.get("label") or ""),
                    "input_serials": len(stage_input_serials),
                    "query_count": stage_query_count,
                    "sql_time_ms": round(stage_sql_ms, 2),
                    "python_time_ms": round(stage_python_ms, 2),
                    "serialization_time_ms": round(stage_serialization_ms, 2),
                    "rows_returned": stage_rows_returned,
                    "pending_after_stage": len(pending_serials),
                }
            )
            performance_diagnostics["tables"].extend(list(queried_tables))

        return {
            "matches": matches,
            "matches_by_serial": matches_by_serial,
            "table_results": table_results,
            "stage_results": stage_results,
            "found_in_base_actual": len(found_in_base_actual),
            "found_in_asociados_actual": len(found_in_asociados_actual),
            "found_in_historico": len(found_in_historico),
            "remaining_unresolved": len(pending_serials),
            "performance_diagnostics": {
                **performance_diagnostics,
                "sql_time_ms_total": round(float(performance_diagnostics.get("sql_time_ms_total") or 0.0), 2),
                "python_time_ms_total": round(float(performance_diagnostics.get("python_time_ms_total") or 0.0), 2),
                "serialization_time_ms_total": round(float(performance_diagnostics.get("serialization_time_ms_total") or 0.0), 2),
            },
        }

    def _query_table(
        self,
        *,
        table: dict[str, Any],
        normalized_serials: list[str],
        lookup_metrics: dict[str, Any] | None = None,
        skip_noncanonical_probe: bool = False,
    ) -> list[dict[str, Any]]:
        columns = list(table.get("columns") or [])
        serial_column = self._resolve_table_field(columns=columns, logical_name="serial")
        if not serial_column:
            return []
        estado_column = self._resolve_table_field(columns=columns, logical_name="estado")
        lote_column = self._resolve_table_field(columns=columns, logical_name="lote")
        cedula_column = self._resolve_table_field(columns=columns, logical_name="cedula")
        edit_column = self._resolve_table_field(columns=columns, logical_name="edit")
        movil_column = self._resolve_table_field(columns=columns, logical_name="movil")
        bodega_column = self._resolve_table_field(columns=columns, logical_name="bodega")
        codigo_column = self._resolve_table_field(columns=columns, logical_name="codigo")
        descripcion_column = self._resolve_table_field(columns=columns, logical_name="descripcion")
        fecha_column = self._resolve_table_field(columns=columns, logical_name="fecha")

        selected_columns = [
            item
            for item in [
                serial_column,
                estado_column,
                lote_column,
                cedula_column,
                edit_column,
                movil_column,
                bodega_column,
                codigo_column,
                descripcion_column,
                fecha_column,
            ]
            if item
        ]
        select_parts = [f"s.{_quote_identifier(serial_column)} AS serial_raw"]
        alias_map = {
            "estado": estado_column,
            "lote": lote_column,
            "cedula": cedula_column,
            "edit": edit_column,
            "movil": movil_column,
            "bodega": bodega_column,
            "codigo": codigo_column,
            "descripcion": descripcion_column,
            "fecha": fecha_column,
        }
        for alias, column_name in alias_map.items():
            if column_name:
                select_parts.append(f"s.{_quote_identifier(column_name)} AS {_quote_identifier(alias)}")

        chunk_size = _DB_LOOKUP_CHUNK_SIZE
        limit_per_chunk = max(1, chunk_size * 20)
        fqn = f"{str(table['schema']).strip()}.{str(table['table']).strip()}"
        results: list[dict[str, Any]] = []
        noncanonical_cache = (
            {
                "query_count": 0,
                "sql_time_ms": 0.0,
                "row_count": 0,
                "rows_by_serial": {},
                "truncated": False,
                "use_db_fallback": False,
                "reason": "disabled_for_large_provider_validation",
            }
            if skip_noncanonical_probe
            else self._get_noncanonical_serial_cache(
                table_fqn=fqn,
                serial_column=serial_column,
                select_parts=select_parts,
                selected_columns=selected_columns,
            )
        )
        normalized_fallback_enabled = bool(noncanonical_cache.get("rows_by_serial")) or bool(
            noncanonical_cache.get("use_db_fallback")
        )
        sql_time_ms_total = 0.0
        python_time_ms_total = 0.0
        serialization_time_ms_total = 0.0
        query_count = int(noncanonical_cache.get("query_count") or 0)
        rows_returned = 0
        chunk_metrics: list[dict[str, Any]] = []
        noncanonical_cache_hits = 0
        for start in range(0, len(normalized_serials), chunk_size):
            chunk = normalized_serials[start : start + chunk_size]
            chunk_started_at = time.perf_counter()
            exact_started_at = time.perf_counter()
            exact_matches = self._execute_serial_lookup(
                table_fqn=fqn,
                serial_column=serial_column,
                select_parts=select_parts,
                selected_columns=selected_columns,
                chunk=chunk,
                limit_per_chunk=limit_per_chunk,
                normalized_fallback=False,
            )
            exact_sql_ms = (time.perf_counter() - exact_started_at) * 1000
            sql_time_ms_total += exact_sql_ms
            query_count += 1
            rows_returned += len(exact_matches)
            exact_serials = {
                _normalize_serial(item.get("serial_raw"))
                for item in exact_matches
                if _normalize_serial(item.get("serial_raw"))
            }
            unresolved_chunk = [
                serial for serial in chunk if serial and serial not in exact_serials
            ]
            fallback_matches: list[dict[str, Any]] = []
            fallback_sql_ms = 0.0
            fallback_strategy = "skipped"
            if unresolved_chunk and normalized_fallback_enabled:
                cached_rows_by_serial = dict(noncanonical_cache.get("rows_by_serial") or {})
                if cached_rows_by_serial:
                    fallback_strategy = "noncanonical_cache"
                    for serial in unresolved_chunk:
                        serial_rows = list(cached_rows_by_serial.get(serial) or [])
                        if not serial_rows:
                            continue
                        noncanonical_cache_hits += len(serial_rows)
                        fallback_matches.extend(dict(row) for row in serial_rows if isinstance(row, dict))
                    rows_returned += len(fallback_matches)
                elif bool(noncanonical_cache.get("use_db_fallback")):
                    fallback_strategy = "db_normalized_fallback"
                    fallback_started_at = time.perf_counter()
                    fallback_matches = self._execute_serial_lookup(
                        table_fqn=fqn,
                        serial_column=serial_column,
                        select_parts=select_parts,
                        selected_columns=selected_columns,
                        chunk=unresolved_chunk,
                        limit_per_chunk=limit_per_chunk,
                        normalized_fallback=True,
                    )
                    fallback_sql_ms = (time.perf_counter() - fallback_started_at) * 1000
                    sql_time_ms_total += fallback_sql_ms
                    query_count += 1
                    rows_returned += len(fallback_matches)
            serialization_started_at = time.perf_counter()
            for row in [*exact_matches, *fallback_matches]:
                serial_normalizado = _normalize_serial(row.get("serial_raw"))
                if not serial_normalizado:
                    continue
                results.append(
                    {
                        "serial_normalizado": serial_normalizado,
                        "source_label": str(table["label"]),
                        "source_kind": str(table["kind"]),
                        "source_table": str(table["fqn"]),
                        "year": table.get("year"),
                        "estado": _clean_text(row.get("estado")),
                        "lote": _clean_text(row.get("lote")),
                        "cedula": _clean_text(row.get("cedula")),
                        "edit": _clean_text(row.get("edit")),
                        "movil": _clean_text(row.get("movil")),
                        "bodega": _clean_text(row.get("bodega")),
                        "codigo": _clean_text(row.get("codigo")),
                        "descripcion": _clean_text(row.get("descripcion")),
                        "fecha": _format_datetime(row.get("fecha")),
                    }
                )
            serialization_ms = (time.perf_counter() - serialization_started_at) * 1000
            chunk_elapsed_ms = (time.perf_counter() - chunk_started_at) * 1000
            python_ms = max(0.0, chunk_elapsed_ms - exact_sql_ms - fallback_sql_ms - serialization_ms)
            serialization_time_ms_total += serialization_ms
            python_time_ms_total += python_ms
            chunk_metrics.append(
                {
                    "chunk_index": int((start // chunk_size) + 1),
                    "input_serials": len(chunk),
                    "exact_rows": len(exact_matches),
                    "exact_sql_ms": round(exact_sql_ms, 2),
                    "fallback_input_serials": len(unresolved_chunk),
                    "fallback_rows": len(fallback_matches),
                    "fallback_strategy": fallback_strategy,
                    "fallback_sql_ms": round(fallback_sql_ms, 2),
                    "serialization_ms": round(serialization_ms, 2),
                    "python_ms": round(python_ms, 2),
                    "elapsed_ms": round(chunk_elapsed_ms, 2),
                    "query_count": 1 + (1 if fallback_strategy == "db_normalized_fallback" else 0),
                }
            )
        if lookup_metrics is not None:
            preflight_sql_time_ms = float(noncanonical_cache.get("sql_time_ms") or 0.0)
            lookup_metrics.update(
                {
                    "table_label": str(table.get("label") or ""),
                    "table_fqn": fqn,
                    "chunk_size": chunk_size,
                    "chunk_count": len(chunk_metrics),
                    "query_count": query_count,
                    "preflight_query_count": int(noncanonical_cache.get("query_count") or 0),
                    "preflight_sql_time_ms": round(preflight_sql_time_ms, 2),
                    "sql_time_ms": round(sql_time_ms_total + preflight_sql_time_ms, 2),
                    "lookup_sql_time_ms": round(sql_time_ms_total, 2),
                    "python_time_ms": round(python_time_ms_total, 2),
                    "serialization_time_ms": round(serialization_time_ms_total, 2),
                    "rows_returned": rows_returned,
                    "normalized_fallback_enabled": normalized_fallback_enabled,
                    "normalized_fallback_reason": str(noncanonical_cache.get("reason") or ""),
                    "noncanonical_rows_loaded": int(noncanonical_cache.get("row_count") or 0),
                    "noncanonical_cache_hits": noncanonical_cache_hits,
                    "noncanonical_cache_truncated": bool(noncanonical_cache.get("truncated")),
                    "chunk_metrics": chunk_metrics,
                }
            )
        return results

    def _get_noncanonical_serial_cache(
        self,
        *,
        table_fqn: str,
        serial_column: str,
        select_parts: list[str],
        selected_columns: list[str],
    ) -> dict[str, Any]:
        cache_key = (
            str(table_fqn or "").strip().lower(),
            str(serial_column or "").strip().lower(),
        )
        cached = self._noncanonical_serial_cache.get(cache_key)
        if cached is not None:
            return dict(cached)
        query = (
            f"SELECT {', '.join(select_parts)} "
            f"FROM {table_fqn} AS s "
            f"WHERE CAST(s.{_quote_identifier(serial_column)} AS CHAR) <> "
            f"UPPER(TRIM(CAST(s.{_quote_identifier(serial_column)} AS CHAR))) "
            f"LIMIT {_NONCANONICAL_SERIAL_CACHE_LIMIT + 1}"
        )
        started_at = time.perf_counter()
        executed = self.planner.execute_governed_select(
            db_alias=self.DB_ALIAS,
            query=query,
            params=[],
            allowed_tables=[table_fqn],
            allowed_columns=selected_columns,
            declared_columns=selected_columns,
            max_limit=max(_NONCANONICAL_SERIAL_CACHE_LIMIT + 1, 1000),
        )
        sql_time_ms = (time.perf_counter() - started_at) * 1000
        if not executed.get("ok"):
            payload = {
                "query_count": 1,
                "sql_time_ms": round(sql_time_ms, 2),
                "row_count": 0,
                "rows_by_serial": {},
                "truncated": False,
                "use_db_fallback": True,
                "reason": "noncanonical_probe_failed_db_fallback_allowed",
            }
            self._noncanonical_serial_cache[cache_key] = dict(payload)
            return dict(payload)
        raw_rows = [
            dict(row)
            for row in list(executed.get("rows") or [])
            if isinstance(row, dict)
        ]
        truncated = len(raw_rows) > _NONCANONICAL_SERIAL_CACHE_LIMIT
        if truncated:
            payload = {
                "query_count": 1,
                "sql_time_ms": round(sql_time_ms, 2),
                "row_count": len(raw_rows),
                "rows_by_serial": {},
                "truncated": True,
                "use_db_fallback": True,
                "reason": "noncanonical_cache_truncated_db_fallback_allowed",
            }
            self._noncanonical_serial_cache[cache_key] = dict(payload)
            return dict(payload)
        rows_by_serial: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in raw_rows:
            serial_normalizado = _normalize_serial(row.get("serial_raw"))
            if not serial_normalizado:
                continue
            rows_by_serial[serial_normalizado].append(dict(row))
        payload = {
            "query_count": 1,
            "sql_time_ms": round(sql_time_ms, 2),
            "row_count": len(raw_rows),
            "rows_by_serial": dict(rows_by_serial),
            "truncated": False,
            "use_db_fallback": False,
            "reason": (
                "using_noncanonical_exception_cache"
                if rows_by_serial
                else "skipped_table_values_already_canonical"
            ),
        }
        self._noncanonical_serial_cache[cache_key] = dict(payload)
        return dict(payload)

    def _execute_serial_lookup(
        self,
        *,
        table_fqn: str,
        serial_column: str,
        select_parts: list[str],
        selected_columns: list[str],
        chunk: list[str],
        limit_per_chunk: int,
        normalized_fallback: bool,
    ) -> list[dict[str, Any]]:
        if not chunk:
            return []
        placeholders = ", ".join(["%s"] * len(chunk))
        where_clause = (
            f"UPPER(TRIM(CAST(s.{_quote_identifier(serial_column)} AS CHAR))) IN ({placeholders})"
            if normalized_fallback
            else f"s.{_quote_identifier(serial_column)} IN ({placeholders})"
        )
        query = (
            f"SELECT {', '.join(select_parts)} FROM {table_fqn} AS s "
            f"WHERE {where_clause} "
            f"LIMIT {limit_per_chunk}"
        )
        executed = self.planner.execute_governed_select(
            db_alias=self.DB_ALIAS,
            query=query,
            params=list(chunk),
            allowed_tables=[table_fqn],
            allowed_columns=selected_columns,
            declared_columns=selected_columns,
            max_limit=max(limit_per_chunk, 1000),
        )
        if not executed.get("ok"):
            return []
        return [
            dict(row)
            for row in list(executed.get("rows") or [])
            if isinstance(row, dict)
        ]

    def _enrich_personal(self, *, matches: list[dict[str, Any]]) -> list[dict[str, Any]]:
        candidate_identifiers = sorted(
            {
                candidate
                for item in matches
                if self._state_contains_movil(item.get("estado"))
                for candidate in (
                    _clean_text(item.get("cedula")),
                    _clean_text(item.get("edit")),
                )
                if _looks_like_person_identifier(candidate)
            }
        )
        if not candidate_identifiers:
            return []
        if not self._table_exists(schema="bd_c3nc4s1s", table="cinco_base_de_personal"):
            return []
        columns = self._get_table_columns(schema="bd_c3nc4s1s", table="cinco_base_de_personal")
        cedula_column = self._resolve_table_field(columns=columns, logical_name="cedula")
        movil_column = self._resolve_table_field(columns=columns, logical_name="movil")
        nombre_column = self._resolve_table_field(columns=columns, logical_name="nombre")
        apellido_column = self._resolve_table_field(columns=columns, logical_name="apellido")
        empleado_column = self._resolve_table_field(columns=columns, logical_name="empleado")
        estado_column = self._resolve_table_field(columns=columns, logical_name="estado")
        if not cedula_column:
            return []
        selected_columns = [item for item in [cedula_column, movil_column, nombre_column, apellido_column, empleado_column, estado_column] if item]
        select_parts = [f"p.{_quote_identifier(cedula_column)} AS cedula"]
        for alias, column_name in {
            "movil": movil_column,
            "nombre": nombre_column,
            "apellido": apellido_column,
            "empleado": empleado_column,
            "estado_empleado": estado_column,
        }.items():
            if column_name:
                select_parts.append(f"p.{_quote_identifier(column_name)} AS {_quote_identifier(alias)}")
        results: list[dict[str, Any]] = []
        chunk_size = _DB_LOOKUP_CHUNK_SIZE
        for start in range(0, len(candidate_identifiers), chunk_size):
            chunk = candidate_identifiers[start : start + chunk_size]
            exact_rows = self._execute_personal_lookup(
                cedula_column=cedula_column,
                select_parts=select_parts,
                selected_columns=selected_columns,
                chunk=chunk,
                normalized_fallback=False,
            )
            exact_identifiers = {
                _clean_text(item.get("cedula"))
                for item in exact_rows
                if _clean_text(item.get("cedula"))
            }
            unresolved_chunk = [
                identifier
                for identifier in chunk
                if identifier and identifier not in exact_identifiers
            ]
            fallback_rows = self._execute_personal_lookup(
                cedula_column=cedula_column,
                select_parts=select_parts,
                selected_columns=selected_columns,
                chunk=unresolved_chunk,
                normalized_fallback=True,
            )
            results.extend(list(exact_rows))
            results.extend(list(fallback_rows))
        return results

    def _execute_personal_lookup(
        self,
        *,
        cedula_column: str,
        select_parts: list[str],
        selected_columns: list[str],
        chunk: list[str],
        normalized_fallback: bool,
    ) -> list[dict[str, Any]]:
        if not chunk:
            return []
        placeholders = ", ".join(["%s"] * len(chunk))
        where_clause = (
            f"TRIM(CAST(p.{_quote_identifier(cedula_column)} AS CHAR)) IN ({placeholders})"
            if normalized_fallback
            else f"p.{_quote_identifier(cedula_column)} IN ({placeholders})"
        )
        query = (
            f"SELECT {', '.join(select_parts)} "
            "FROM bd_c3nc4s1s.cinco_base_de_personal AS p "
            f"WHERE {where_clause} "
            f"LIMIT {max(1, len(chunk) * 5)}"
        )
        executed = self.planner.execute_governed_select(
            db_alias=self.DB_ALIAS,
            query=query,
            params=list(chunk),
            allowed_tables=["bd_c3nc4s1s.cinco_base_de_personal"],
            allowed_columns=selected_columns,
            declared_columns=selected_columns,
            max_limit=max(1000, len(chunk) * 5),
        )
        if not executed.get("ok"):
            return []
        return [
            dict(row)
            for row in list(executed.get("rows") or [])
            if isinstance(row, dict)
        ]

    @staticmethod
    def _state_contains_movil(value: Any) -> bool:
        return "MOVIL" in _clean_text(value).upper()

    @staticmethod
    def _state_contains_asociado(value: Any) -> bool:
        return "ASOCIADO" in _clean_text(value).upper()

    def _iter_responsable_candidates(
        self,
        *,
        selected: dict[str, Any] | None,
        serial_matches: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        selected_id = id(selected) if selected is not None else None
        for match in ([selected] if selected else []) + [item for item in serial_matches if id(item) != selected_id]:
            if not match:
                continue
            source_kind = _clean_text(match.get("source_kind"))
            historical = source_kind.startswith("backup_")
            selected_match = id(match) == selected_id if selected_id is not None else False
            for field_name in ("cedula", "edit"):
                raw_value = _clean_text(match.get(field_name))
                if not raw_value:
                    continue
                candidates.append(
                    {
                        "field_name": field_name,
                        "source": "historial" if historical else field_name,
                        "value": raw_value,
                        "selected_match": selected_match,
                        "historical": historical,
                        "looks_like_person_identifier": _looks_like_person_identifier(raw_value),
                    }
                )
        unique_candidates: list[dict[str, Any]] = []
        seen: set[tuple[str, str, bool]] = set()
        for candidate in candidates:
            key = (
                str(candidate.get("source") or ""),
                str(candidate.get("value") or ""),
                bool(candidate.get("selected_match")),
            )
            if key in seen:
                continue
            seen.add(key)
            unique_candidates.append(candidate)
        return unique_candidates

    def _resolve_responsable(
        self,
        *,
        selected: dict[str, Any] | None,
        serial_matches: list[dict[str, Any]],
        personal_by_identifier: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        estado = _clean_text((selected or {}).get("estado"))
        if not self._state_contains_movil(estado):
            return {
                "candidate_source": "no_resuelto",
                "candidate_value": "",
                "responsable_enriched": False,
                "personal": {},
                "limitation": "",
            }
        selected_cedula = _clean_text((selected or {}).get("cedula"))
        selected_edit = _clean_text((selected or {}).get("edit"))
        prefer_selected_edit = (
            self._state_contains_asociado(estado) and _looks_like_person_identifier(selected_edit)
        ) or (not _looks_like_person_identifier(selected_cedula) and _looks_like_person_identifier(selected_edit))

        def _candidate_priority(candidate: dict[str, Any]) -> tuple[int, int, int]:
            field_name = str(candidate.get("field_name") or "")
            selected_match = bool(candidate.get("selected_match"))
            historical = bool(candidate.get("historical"))
            looks_like_person = bool(candidate.get("looks_like_person_identifier"))
            if selected_match and field_name == "cedula" and _looks_like_person_identifier(selected_cedula):
                primary_rank = 0
            elif selected_match and field_name == "edit" and prefer_selected_edit:
                primary_rank = 1
            elif selected_match and field_name == "edit" and looks_like_person:
                primary_rank = 2
            elif (not historical) and field_name == "cedula" and looks_like_person:
                primary_rank = 3
            elif (not historical) and field_name == "edit" and looks_like_person:
                primary_rank = 4
            elif historical and looks_like_person:
                primary_rank = 5
            elif selected_match and field_name == "cedula":
                primary_rank = 6
            elif selected_match and field_name == "edit":
                primary_rank = 7
            else:
                primary_rank = 8
            return (primary_rank, 0 if selected_match else 1, 1 if historical else 0)

        candidates = sorted(
            self._iter_responsable_candidates(selected=selected, serial_matches=serial_matches),
            key=_candidate_priority,
        )
        if not candidates:
            return {
                "candidate_source": "no_resuelto",
                "candidate_value": "",
                "responsable_enriched": False,
                "personal": {},
                "limitation": "No se encontro identificador candidato en cedula, edit ni historial para intentar enrichment de responsable.",
            }
        for candidate in candidates:
            identifier = _clean_text(candidate.get("value"))
            personal = personal_by_identifier.get(identifier, {})
            if personal:
                return {
                    "candidate_source": str(candidate.get("source") or "no_resuelto"),
                    "candidate_value": identifier,
                    "responsable_enriched": True,
                    "personal": personal,
                    "limitation": "",
                }
        best_candidate = candidates[0]
        return {
            "candidate_source": str(best_candidate.get("source") or "no_resuelto"),
            "candidate_value": _clean_text(best_candidate.get("value")),
            "responsable_enriched": False,
            "personal": {},
            "limitation": "Se encontro identificador asociado, pero no se pudo enriquecer responsable/persona con evidencia de personal.",
        }

    def _consolidate_rows(
        self,
        *,
        provider_rows: list[dict[str, Any]],
        matches_by_serial: dict[str, list[dict[str, Any]]],
        personal_by_identifier: dict[str, dict[str, Any]],
        discovery: dict[str, Any],
    ) -> list[dict[str, Any]]:
        consulted_existing = [str(item.get("label") or "") for item in list(discovery.get("existing_tables") or [])]
        consulted_missing = [str(item.get("label") or "") for item in list(discovery.get("missing_tables") or [])]
        consolidated: list[dict[str, Any]] = []
        for row in provider_rows:
            serial_normalizado = str(row.get("serial_normalizado") or "")
            serial_matches = list(matches_by_serial.get(serial_normalizado, [])) if serial_normalizado else []
            selected = self._select_best_match(serial_matches=serial_matches)
            estado = _clean_text((selected or {}).get("estado"))
            estado_movil = self._state_contains_movil(estado)
            cedula_original = _clean_text((selected or {}).get("cedula"))
            edit_original = _clean_text((selected or {}).get("edit"))
            responsable_resolution = self._resolve_responsable(
                selected=selected,
                serial_matches=serial_matches,
                personal_by_identifier=personal_by_identifier,
            )
            personal = dict(responsable_resolution.get("personal") or {})
            responsable_enriched = bool(responsable_resolution.get("responsable_enriched"))
            cedula = _clean_text(personal.get("cedula")) if responsable_enriched else ""
            nombre = _clean_text(personal.get("nombre"))
            apellido = _clean_text(personal.get("apellido"))
            empleado = _clean_text(personal.get("empleado")) or _clean_text(" ".join(item for item in [nombre, apellido] if item))
            movil = _clean_text((selected or {}).get("movil")) or _clean_text(personal.get("movil"))
            matched_sources = [str(item.get("source_label") or "") for item in serial_matches]
            only_historical = bool(serial_matches) and not any(
                str(item.get("source_kind") or "").endswith("_actual") for item in serial_matches
            )
            encontrado = bool(selected)
            observation = self._build_observation(
                found=encontrado,
                only_historical=only_historical,
                estado_movil=estado_movil,
                responsable_enriched=responsable_enriched,
                responsable_limitation=_clean_text(responsable_resolution.get("limitation")),
                duplicated=bool(row.get("duplicado_en_archivo")),
            )
            consolidated.append(
                {
                    "fila_archivo": row["fila_archivo"],
                    "serial_proveedor": row["serial_proveedor"],
                    "serial_normalizado": serial_normalizado,
                    "material_proveedor": row["material_proveedor"],
                    "denominacion_proveedor": row["denominacion_proveedor"],
                    "familia_proveedor": row["familia_proveedor"],
                    "encontrado": _as_bool_label(encontrado),
                    "fuente": _clean_text((selected or {}).get("source_label")) or "no encontrado",
                    "estado": estado,
                    "lote": _clean_text((selected or {}).get("lote")),
                    "estado_contiene_movil": _as_bool_label(estado_movil),
                    "estado_contiene_asociado": _as_bool_label(self._state_contains_asociado(estado)),
                    "movil_asociado": movil,
                    "cedula_original": cedula_original,
                    "edit_original": edit_original,
                    "responsable_candidate_source": _clean_text(responsable_resolution.get("candidate_source")) or "no_resuelto",
                    "responsable_candidate_value": _clean_text(responsable_resolution.get("candidate_value")),
                    "responsable_enriched": responsable_enriched,
                    "cedula_persona": cedula,
                    "nombre": nombre,
                    "apellido": apellido,
                    "empleado": empleado,
                    "bodega": _clean_text((selected or {}).get("bodega")),
                    "codigo_interno": _clean_text((selected or {}).get("codigo")),
                    "descripcion_interna": _clean_text((selected or {}).get("descripcion")),
                    "ultima_fecha_encontrada": _clean_text((selected or {}).get("fecha")),
                    "duplicado_en_archivo": _as_bool_label(bool(row.get("duplicado_en_archivo"))),
                    "ocurrencias_archivo": int(row.get("ocurrencias_archivo") or 0),
                    "solo_historico": _as_bool_label(only_historical),
                    "fuentes_coincidencia": "; ".join(matched_sources),
                    "tablas_consultadas": "; ".join(consulted_existing),
                    "tablas_historicas_no_existian": "; ".join(consulted_missing),
                    "limitation": _clean_text(responsable_resolution.get("limitation")),
                    "observacion_operativa": observation,
                }
            )
        return consolidated

    def _select_best_match(self, *, serial_matches: list[dict[str, Any]]) -> dict[str, Any] | None:
        if not serial_matches:
            return None

        def _source_priority(item: dict[str, Any]) -> tuple[int, int, float]:
            kind = str(item.get("source_kind") or "")
            year = int(item.get("year") or 0)
            source_rank = {
                "base_actual": 0,
                "asociados_actual": 1,
                "backup_base": 2,
                "backup_asociados": 3,
            }.get(kind, 9)
            parsed = _parse_datetime(item.get("fecha"))
            timestamp = 0.0
            if parsed is not None:
                try:
                    timestamp = float(parsed.strftime("%Y%m%d%H%M%S"))
                except Exception:
                    timestamp = 0.0
            return (source_rank, -year, -timestamp)

        ordered = sorted(serial_matches, key=_source_priority)
        return ordered[0] if ordered else None

    def _build_observation(
        self,
        *,
        found: bool,
        only_historical: bool,
        estado_movil: bool,
        responsable_enriched: bool,
        responsable_limitation: str,
        duplicated: bool,
    ) -> str:
        observations: list[str] = []
        if duplicated:
            observations.append("Serial duplicado en el archivo del proveedor.")
        if not found:
            observations.append("No hubo coincidencia en bases actuales ni historicas consultadas.")
        elif only_historical:
            observations.append("La coincidencia aparece solo en backup historico.")
        else:
            observations.append("La coincidencia aparece en base operativa actual.")
        if estado_movil and responsable_enriched:
            observations.append("El estado contiene MOVIL y se logro enriquecer responsable con evidencia de personal.")
        elif estado_movil and responsable_limitation:
            observations.append(responsable_limitation)
        elif estado_movil:
            observations.append("El estado contiene MOVIL, pero no hubo responsable enriquecido.")
        return " ".join(observations)

    def _write_export_artifact(self, *, rows: list[dict[str, Any]]) -> dict[str, Any]:
        columns = list(rows[0].keys()) if rows else []
        export_dir = Path(__file__).resolve().parents[4] / _EXPORT_ARTIFACT_DIR
        export_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
        export_path = export_dir / f"inventory_provider_serial_validation_{timestamp}.csv"
        with export_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=columns or ["serial_proveedor"])
            writer.writeheader()
            for row in rows:
                writer.writerow({column: row.get(column, "") for column in (columns or ["serial_proveedor"])})
        return {
            "available": True,
            "format": "csv",
            "artifact_id": _RUNTIME_ARTIFACT_SERVICE.issue_artifact_id(filename=export_path.name),
            "filename": export_path.name,
            "record_count": len(rows),
            "endpoint_hint": "/ia-dev/runtime/artifacts/provider-serial-validation/",
            "expires_in_seconds": _RUNTIME_ARTIFACT_SERVICE.DEFAULT_ARTIFACT_TTL_SECONDS,
        }

    @staticmethod
    def _preview_rows(rows: list[dict[str, Any]], limit: int = _PREVIEW_ROW_LIMIT) -> list[dict[str, Any]]:
        return list(rows[: max(1, limit)])

    @staticmethod
    def _project_rows(rows: list[dict[str, Any]], columns: list[str]) -> list[dict[str, Any]]:
        return [
            {column: row.get(column, "") for column in columns}
            for row in rows
        ]

    def _build_main_table(
        self,
        *,
        rows: list[dict[str, Any]],
        export_artifact: dict[str, Any],
    ) -> dict[str, Any]:
        columns = [
            "fila_archivo",
            "serial_proveedor",
            "encontrado",
            "fuente",
            "estado",
            "estado_contiene_movil",
            "movil_asociado",
            "cedula_persona",
            "empleado",
            "bodega",
            "codigo_interno",
            "ultima_fecha_encontrada",
            "solo_historico",
            "observacion_operativa",
        ]
        preview_rows = self._preview_rows(rows)
        truncated = len(preview_rows) < len(rows)
        return {
            "columns": columns,
            "rows": preview_rows,
            "rowcount": len(rows),
            "total_records": len(rows),
            "returned_records": len(preview_rows),
            "export_rows": preview_rows,
            "export_records": len(rows),
            "export_truncated": truncated,
            "export_limit": len(preview_rows),
            "limit": len(preview_rows),
            "truncated": truncated,
            "export_artifact": export_artifact,
        }

    def _build_extra_tables(self, *, rows: list[dict[str, Any]], discovery: dict[str, Any]) -> list[dict[str, Any]]:
        duplicated_rows = [row for row in rows if str(row.get("duplicado_en_archivo") or "") == "SI"]
        movil_rows = [
            row
            for row in rows
            if str(row.get("estado_contiene_movil") or "") == "SI"
        ]
        movil_enriched_rows = [
            row for row in movil_rows if bool(row.get("responsable_enriched"))
        ]
        not_found_rows = [row for row in rows if str(row.get("encontrado") or "") == "NO"]
        historical_only_rows = [row for row in rows if str(row.get("solo_historico") or "") == "SI"]
        technical_rows = [
            {
                "tablas_consultadas": "; ".join(str(item.get("label") or "") for item in list(discovery.get("existing_tables") or [])),
                "tablas_historicas_no_existian": "; ".join(str(item.get("label") or "") for item in list(discovery.get("missing_tables") or [])),
            }
        ]
        return [
            self._named_table(
                "resultado_por_serial",
                "Resultado por serial",
                rows,
                columns=[
                    "fila_archivo",
                    "serial_proveedor",
                    "encontrado",
                    "fuente",
                    "estado",
                    "estado_contiene_movil",
                    "movil_asociado",
                    "cedula_persona",
                    "empleado",
                    "bodega",
                    "codigo_interno",
                    "ultima_fecha_encontrada",
                    "solo_historico",
                    "observacion_operativa",
                ],
            ),
            self._named_table(
                "seriales_en_movil",
                "Seriales en MOVIL",
                movil_rows,
                columns=[
                    "fila_archivo",
                    "serial_proveedor",
                    "fuente",
                    "estado",
                    "movil_asociado",
                    "cedula_persona",
                    "empleado",
                    "observacion_operativa",
                ],
            ),
            self._named_table(
                "seriales_en_movil_con_responsable",
                "Seriales en MOVIL con responsable",
                movil_enriched_rows,
                columns=[
                    "fila_archivo",
                    "serial_proveedor",
                    "fuente",
                    "movil_asociado",
                    "cedula_persona",
                    "empleado",
                ],
            ),
            self._named_table(
                "seriales_no_encontrados",
                "Seriales no encontrados",
                not_found_rows,
                columns=[
                    "fila_archivo",
                    "serial_proveedor",
                    "material_proveedor",
                    "denominacion_proveedor",
                    "familia_proveedor",
                    "observacion_operativa",
                ],
            ),
            self._named_table(
                "seriales_duplicados_archivo",
                "Seriales duplicados en archivo",
                duplicated_rows,
                columns=[
                    "fila_archivo",
                    "serial_proveedor",
                    "ocurrencias_archivo",
                    "observacion_operativa",
                ],
            ),
            self._named_table(
                "seriales_solo_historicos",
                "Seriales solo historicos",
                historical_only_rows,
                columns=[
                    "fila_archivo",
                    "serial_proveedor",
                    "fuente",
                    "estado",
                    "ultima_fecha_encontrada",
                    "observacion_operativa",
                ],
            ),
            self._named_table("evidencia_tecnica_colapsada", "Evidencia tecnica colapsada", technical_rows),
        ]

    def _named_table(
        self,
        table_id: str,
        title: str,
        rows: list[dict[str, Any]],
        columns: list[str] | None = None,
    ) -> dict[str, Any]:
        selected_columns = list(columns or (list(rows[0].keys()) if rows else []))
        preview_rows = self._project_rows(
            self._preview_rows(rows, limit=_EXTRA_TABLE_PREVIEW_ROW_LIMIT),
            selected_columns,
        )
        truncated = len(preview_rows) < len(rows)
        return {
            "name": table_id,
            "title": title,
            "columns": selected_columns,
            "rows": preview_rows,
            "rowcount": len(rows),
            "total_records": len(rows),
            "returned_records": len(preview_rows),
            "export_rows": preview_rows,
            "export_records": len(rows),
            "export_truncated": truncated,
            "export_limit": len(preview_rows),
            "truncated": truncated,
            "limit": len(preview_rows),
        }

    def _build_kpis(self, *, rows: list[dict[str, Any]]) -> dict[str, Any]:
        normalized_serials = [
            str(row.get("serial_normalizado") or "")
            for row in rows
            if str(row.get("serial_normalizado") or "")
        ]
        unique_serials = set(normalized_serials)
        found_rows = [row for row in rows if str(row.get("encontrado") or "") == "SI"]
        found_unique = {
            str(row.get("serial_normalizado") or "")
            for row in found_rows
            if str(row.get("serial_normalizado") or "")
        }
        not_found_rows = [row for row in rows if str(row.get("encontrado") or "") == "NO"]
        not_found_unique = {
            str(row.get("serial_normalizado") or "")
            for row in not_found_rows
            if str(row.get("serial_normalizado") or "")
        }
        current_base = {
            str(row.get("serial_normalizado") or "")
            for row in rows
            if "base actual" in str(row.get("fuentes_coincidencia") or "").lower()
        }
        current_assoc = {
            str(row.get("serial_normalizado") or "")
            for row in rows
            if "asociados actual" in str(row.get("fuentes_coincidencia") or "").lower()
        }
        historical_matches = {
            str(row.get("serial_normalizado") or "")
            for row in rows
            if "backup" in str(row.get("fuentes_coincidencia") or "").lower()
        }
        final_source_base = {
            str(row.get("serial_normalizado") or "")
            for row in rows
            if str(row.get("fuente") or "").strip().lower() == "base actual"
        }
        final_source_assoc = {
            str(row.get("serial_normalizado") or "")
            for row in rows
            if str(row.get("fuente") or "").strip().lower() == "asociados actual"
        }
        final_source_historical = {
            str(row.get("serial_normalizado") or "")
            for row in rows
            if "backup" in str(row.get("fuente") or "").lower()
        }
        movil_unique = {
            str(row.get("serial_normalizado") or "")
            for row in rows
            if str(row.get("estado_contiene_movil") or "") == "SI"
        }
        movil_enriched = {
            str(row.get("serial_normalizado") or "")
            for row in rows
            if str(row.get("estado_contiene_movil") or "") == "SI" and bool(row.get("responsable_enriched"))
        }
        return {
            "total_filas_archivo": len(rows),
            "seriales_unicos": len(unique_serials),
            "duplicados_archivo": max(0, len(rows) - len(unique_serials)),
            "encontrados_por_fila": len(found_rows),
            "encontrados_unicos": len(found_unique),
            "no_encontrados_por_fila": len(not_found_rows),
            "no_encontrados_unicos": len(not_found_unique),
            "coincidencias_base_actual": len(current_base),
            "coincidencias_asociados_actual": len(current_assoc),
            "coincidencias_historico": len(historical_matches),
            "fuente_final_base_actual": len(final_source_base),
            "fuente_final_asociados_actual": len(final_source_assoc),
            "fuente_final_historico": len(final_source_historical),
            "moviles_detectados": len(movil_unique),
            "moviles_con_responsable_enriquecido": len(movil_enriched),
            "moviles_sin_responsable_enriquecido": max(0, len(movil_unique) - len(movil_enriched)),
        }

    def _build_business_response(
        self,
        *,
        user_message: str,
        attachment: dict[str, Any],
        archivo: ArchivoTabular,
        provider_columns: dict[str, Any],
        rows: list[dict[str, Any]],
        kpis: dict[str, Any],
        discovery: dict[str, Any],
        extra_tables: list[dict[str, Any]],
        export_artifact: dict[str, Any],
    ) -> dict[str, Any]:
        found = int(kpis.get("encontrados_unicos") or 0)
        not_found = int(kpis.get("no_encontrados_unicos") or 0)
        in_movil = int(kpis.get("moviles_detectados") or 0)
        moviles_enriched = int(kpis.get("moviles_con_responsable_enriquecido") or 0)
        dato = (
            f"Se validaron {int(kpis.get('total_filas_archivo') or 0)} filas del archivo del proveedor; "
            f"{found} seriales unicos tuvieron coincidencia y {not_found} quedaron sin evidencia."
        )
        hallazgo = (
            f"Se consultaron {len(list(discovery.get('existing_tables') or []))} tablas disponibles; "
            f"{len(list(discovery.get('missing_tables') or []))} tablas historicas no existian. "
            f"{in_movil} seriales unicos quedaron con estado que contiene MOVIL y {moviles_enriched} lograron enrichment real de responsable."
        )
        interpretacion = (
            "La consolidacion priorizo base actual sobre asociados actual y luego historico; en estados con MOVIL se intento resolver responsable desde cedula, luego edit y despues historial si aportaba evidencia."
        )
        recomendacion = (
            "Revisa primero los seriales sin evidencia, luego los MOVIL sin responsable enriquecido y finalmente las coincidencias solo historicas para validar alcance operativo."
        )
        return self._business_response_payload(
            user_message=user_message,
            attachment_name=_clean_text(attachment.get("name")),
            sheet_name=archivo.sheet_name,
            serial_column=str((provider_columns.get("serial") or {}).get("header") or ""),
            rows=rows,
            kpis=kpis,
            discovery=discovery,
            response_status="success",
            dato=dato,
            hallazgo=hallazgo,
            interpretacion=interpretacion,
            recomendacion=recomendacion,
            limitations=[],
            extra_filters={
                "sheet_name": archivo.sheet_name,
                "serial_column": str((provider_columns.get("serial") or {}).get("header") or ""),
            },
            supplemental_tables=extra_tables,
            export_artifact=export_artifact,
        )

    def _business_response_payload(
        self,
        *,
        user_message: str,
        attachment_name: str,
        sheet_name: str,
        serial_column: str,
        rows: list[dict[str, Any]],
        kpis: dict[str, Any],
        discovery: dict[str, Any],
        response_status: str,
        dato: str,
        hallazgo: str,
        interpretacion: str,
        recomendacion: str,
        limitations: list[str],
        extra_filters: dict[str, Any],
        supplemental_tables: list[dict[str, Any]] | None = None,
        export_artifact: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        result_set = {
            "rowcount": len(rows),
            "returned_records": min(len(rows), _PREVIEW_ROW_LIMIT),
            "total_records": len(rows),
            "truncated": len(rows) > _PREVIEW_ROW_LIMIT,
        }
        response_profile = {
            "id": self.RESPONSE_PROFILE_ID,
            "expected_output": "validacion_seriales_proveedor",
            "grain": "serial_proveedor_validado",
            "columns": list(rows[0].keys()) if rows else [],
        }
        dashboard_composition = self.dashboard_planner.plan(
            user_question=user_message,
            rows=rows,
            result_set=result_set,
            semantic_explanation={
                "domain": "inventario_logistica",
                "intent": self.CAPABILITY_ID,
                "entity": {"type": "archivo_externo", "field": "serial", "identifier": attachment_name},
                "filters": {
                    "sheet_name": sheet_name,
                    "serial_column": serial_column,
                    **dict(extra_filters or {}),
                },
                "candidate_capability": self.CAPABILITY_ID,
                "planner_route_hint": self.PLANNER_ROUTE_HINT,
            },
            response_profile=response_profile,
            supplemental_tables=supplemental_tables,
        )
        historical_years_consulted = sorted(
            {
                int(item.get("year"))
                for item in list(discovery.get("existing_tables") or []) + list(discovery.get("missing_tables") or [])
                if item.get("year") is not None
            }
        )
        evidence_contract_updates = {
            "run_timestamp": datetime.utcnow().isoformat(timespec="seconds"),
            "tables_consulted": [str(item.get("label") or "") for item in list(discovery.get("existing_tables") or [])],
            "historical_years_consulted": historical_years_consulted,
            "historical_tables_missing": [
                str(item.get("label") or "") for item in list(discovery.get("missing_tables") or [])
            ],
            "mutable_operational_base_warning": "La base operativa es viva; los resultados pueden variar entre corridas.",
            "precedence_strategy": [
                "fuente_final_base_actual",
                "fuente_final_asociados_actual",
                "fuente_final_historico",
                "responsable: cedula -> edit -> historial",
            ],
            "payload_strategy": {
                "main_payload": "kpis_dashboard_preview",
                "preview_row_limit": _PREVIEW_ROW_LIMIT,
                "drilldown_mode": "paginated_preview",
                "full_export_mode": "csv_artifact",
            },
            "export_artifact": dict(export_artifact or {}),
        }
        if isinstance(dashboard_composition, dict):
            dashboard_composition["evidence_contract"] = {
                **dict(dashboard_composition.get("evidence_contract") or {}),
                **evidence_contract_updates,
            }
        metadata = {
            "domain": "inventario_logistica",
            "response_status": response_status,
            "material_family": "serializados",
            "intent": self.CAPABILITY_ID,
            "business_concept": "validacion_seriales_externos_contra_inventario_propio",
            "operation": "validate_file",
            "tables_used": [str(item.get("label") or "") for item in list(discovery.get("existing_tables") or [])],
            "fields_used": [serial_column] if serial_column else [],
            "filters": {
                "sheet_name": sheet_name,
                "serial_column": serial_column,
                **dict(extra_filters or {}),
            },
            "group_by": [],
            "runtime_flow": "handler",
            "limitations": limitations,
            "export_artifact": dict(export_artifact or {}),
            "requires_business_validation": False,
            "requires_external_source": False,
            "missing_metadata": [],
            "implementation_status": "ready_with_attachment" if response_status == "success" else response_status,
            "requires_threshold_metadata": False,
            "template_id": self.TEMPLATE_ID,
            "candidate_capability": self.CAPABILITY_ID,
            "planner_route_hint": self.PLANNER_ROUTE_HINT,
            "response_profile_usado": self.RESPONSE_PROFILE_ID,
            "tool_id": self.CAPABILITY_ID,
            "paquete_capacidad_usado": "inventario_logistica",
            "version_paquete": "1.0.0",
            "capacidades_declaradas": [self.CAPABILITY_ID],
            "reglas_declaradas": ["inventario.route.provider_serial_validation"],
            "perfiles_respuesta": [self.RESPONSE_PROFILE_ID],
            "evaluaciones_asociadas": ["inventario_provider_serial_validation_v1"],
            "evidence_sources_used": [
                "provider_file",
                "information_schema.tables",
                "information_schema.columns",
                "current_operational_tables",
                "historical_inventory_backups",
                "personal_enrichment",
            ],
            "semantic_context_used": True,
            "fallback_narrativo_usado": False,
            "missing_evidence_reason": limitations[0] if limitations else "",
            "semantic_trace": {
                "template_id": self.TEMPLATE_ID,
                "candidate_capability": self.CAPABILITY_ID,
                "planner_route_hint": self.PLANNER_ROUTE_HINT,
                "regla_metadata_usada": ["inventario.route.provider_serial_validation"],
                "fuente_dd": [
                    "ai_dictionary.dd_sinonimos",
                    "ai_dictionary.dd_reglas",
                    "ai_dictionary.ia_dev_capacidades_columna",
                ],
                "fallback_sombreado_usado": False,
                "regla_legacy_detectada": False,
                "paquete_capacidad_usado": "inventario_logistica",
                "version_paquete": "1.0.0",
                "capacidades_declaradas": [self.CAPABILITY_ID],
                "reglas_declaradas": ["inventario.route.provider_serial_validation"],
                "perfiles_respuesta": [self.RESPONSE_PROFILE_ID],
                "evaluaciones_asociadas": ["inventario_provider_serial_validation_v1"],
            },
            "dashboard_composition_generated": bool(dashboard_composition),
            "payload_strategy": dict(evidence_contract_updates["payload_strategy"]),
        }
        evidence_summary = {
            "response_profile_usado": self.RESPONSE_PROFILE_ID,
            "evidence_sources_used": list(metadata["evidence_sources_used"]),
            "semantic_context_used": True,
            "fallback_narrativo_usado": False,
            "missing_evidence_reason": metadata["missing_evidence_reason"],
            "semantic_trace": dict(metadata["semantic_trace"]),
            "result_set": dict(result_set),
            "extra_tables": [],
            "output_profile": dict(response_profile),
            "entity": {"type": "archivo_externo", "field": "serial", "identifier": attachment_name},
            "filters": dict(metadata["filters"]),
            "capability_pack": {
                "paquete_capacidad_usado": "inventario_logistica",
                "version_paquete": "1.0.0",
                "capacidades_declaradas": [self.CAPABILITY_ID],
                "reglas_declaradas": ["inventario.route.provider_serial_validation"],
                "perfiles_respuesta": [self.RESPONSE_PROFILE_ID],
                "evaluaciones_asociadas": ["inventario_provider_serial_validation_v1"],
            },
            "dashboard_composition_generated": bool(dashboard_composition),
            "kpis": dict(kpis or {}),
            "historical_tables_missing": list(evidence_contract_updates["historical_tables_missing"]),
            "runtime_mutability": {
                "run_timestamp": evidence_contract_updates["run_timestamp"],
                "tables_consulted": list(evidence_contract_updates["tables_consulted"]),
                "historical_years_consulted": list(evidence_contract_updates["historical_years_consulted"]),
                "mutable_operational_base_warning": evidence_contract_updates["mutable_operational_base_warning"],
                "precedence_strategy": list(evidence_contract_updates["precedence_strategy"]),
            },
            "export_artifact": dict(export_artifact or {}),
            "payload_strategy": dict(metadata["payload_strategy"]),
        }
        return {
            "dato": dato,
            "hallazgo": hallazgo,
            "riesgo_o_interpretacion": interpretacion,
            "riesgo": interpretacion,
            "interpretacion": interpretacion,
            "recomendacion": recomendacion,
            "siguiente_accion": recomendacion,
            "response_profile": response_profile,
            "dashboard_composition": dashboard_composition,
            "evidence_summary": evidence_summary,
            "metadata": metadata,
        }
