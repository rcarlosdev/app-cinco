from __future__ import annotations

import base64
import csv
import io
import json
import time
import tracemalloc
from collections import Counter
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError

from apps.ia_dev.domains.inventario_logistica.validador_seriales_proveedor import (
    LectorArchivoTabularProveedor,
    ValidadorSerialesProveedorService,
    _normalize_serial,
)


class Command(BaseCommand):
    help = (
        "Ejecuta la validacion progresiva de inventory_provider_serial_validation "
        "contra un archivo real de proveedor sin hardcodear seriales ni archivo."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument("--attachment-path", required=True, type=str)
        parser.add_argument("--previous-year", type=int, default=2025)
        parser.add_argument("--output", type=str, default="")

    def handle(self, *args, **options) -> None:
        attachment_path = Path(str(options["attachment_path"] or "")).expanduser()
        if not attachment_path.exists():
            raise CommandError(f"attachment_not_found:{attachment_path}")

        mime_type = self._guess_mime_type(attachment_path)
        content = attachment_path.read_bytes()
        archivo = LectorArchivoTabularProveedor().parse(
            filename=attachment_path.name,
            mime_type=mime_type,
            content=content,
        )
        if not archivo.rows:
            raise CommandError("provider_file_empty")

        serial_header = self._detect_serial_header(archivo.headers)
        if not serial_header:
            raise CommandError("serial_column_not_detected")

        all_source_metrics = self._source_metrics(archivo=archivo, serial_header=serial_header)
        phase_rows = self._build_phase_rows(archivo=archivo, serial_header=serial_header)
        validator = ValidadorSerialesProveedorService()
        phases: list[dict[str, Any]] = []

        for phase_name, rows in phase_rows:
            phase_summary = self._run_phase(
                validator=validator,
                headers=archivo.headers,
                rows=rows,
                phase_name=phase_name,
                previous_year=int(options["previous_year"]),
                original_attachment_name=attachment_path.name,
                original_mime_type=mime_type,
                original_content=content,
            )
            phases.append(phase_summary)
            if not bool(phase_summary.get("phase_passed")):
                break

        summary = {
            "attachment": {
                "path": str(attachment_path),
                "name": attachment_path.name,
                "size_bytes": len(content),
                "sheet_name": archivo.sheet_name,
                "headers": archivo.headers,
                "rowcount": len(archivo.rows),
            },
            "source_metrics": all_source_metrics,
            "phases": phases,
            "stopped_early": not all(bool(item.get("phase_passed")) for item in phases),
            "final_recommendation": self._final_recommendation(phases=phases),
        }

        output_path = str(options.get("output") or "").strip()
        if output_path:
            Path(output_path).write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        self.stdout.write(json.dumps(summary, ensure_ascii=False, indent=2))

    def _guess_mime_type(self, path: Path) -> str:
        lower_name = path.name.lower()
        if lower_name.endswith(".csv"):
            return "text/csv"
        if lower_name.endswith(".xlsx"):
            return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        return "application/octet-stream"

    def _detect_serial_header(self, headers: list[str]) -> str:
        for header in headers:
            normalized = str(header or "").strip().lower()
            if "serial" in normalized or "serie" in normalized:
                return header
        return headers[0] if headers else ""

    def _source_metrics(self, *, archivo, serial_header: str) -> dict[str, Any]:
        normalized_serials = [
            _normalize_serial((row or {}).get(serial_header))
            for row in archivo.rows
            if _normalize_serial((row or {}).get(serial_header))
        ]
        counter = Counter(normalized_serials)
        duplicates = [serial for serial, count in counter.items() if count > 1]
        duplicate_positions = {
            serial: [index + 2 for index, row in enumerate(archivo.rows) if _normalize_serial((row or {}).get(serial_header)) == serial]
            for serial in duplicates[:3]
        }
        return {
            "total_seriales_recibidos": len(archivo.rows),
            "seriales_unicos": len(counter),
            "duplicados_en_archivo": max(0, len(normalized_serials) - len(counter)),
            "seriales_duplicados_distintos": len(duplicates),
            "serial_header": serial_header,
            "duplicate_examples": duplicate_positions,
        }

    def _build_phase_rows(self, *, archivo, serial_header: str) -> list[tuple[str, list[dict[str, Any]]]]:
        duplicate_rows: list[dict[str, Any]] = []
        seen_serials: set[str] = set()
        duplicate_serial = ""
        for row in archivo.rows:
            normalized = _normalize_serial((row or {}).get(serial_header))
            if not normalized:
                continue
            if normalized in seen_serials:
                duplicate_serial = normalized
                break
            seen_serials.add(normalized)
        if duplicate_serial:
            for row in archivo.rows:
                if _normalize_serial((row or {}).get(serial_header)) == duplicate_serial:
                    duplicate_rows.append(row)
                if len(duplicate_rows) == 2:
                    break

        selected_rows: list[dict[str, Any]] = list(duplicate_rows)
        selected_signatures = {id(row) for row in selected_rows}
        for row in archivo.rows:
            if id(row) in selected_signatures:
                continue
            selected_rows.append(row)
            selected_signatures.add(id(row))

        phase_sizes = [2, 10, 100, 1000, len(archivo.rows)]
        phases: list[tuple[str, list[dict[str, Any]]]] = []
        for size in phase_sizes:
            capped_size = min(size, len(selected_rows))
            label = "full" if capped_size == len(archivo.rows) else str(capped_size)
            phases.append((label, selected_rows[:capped_size]))
        return phases

    def _build_attachment(self, *, headers: list[str], rows: list[dict[str, Any]], phase_name: str) -> dict[str, str]:
        text = io.StringIO()
        writer = csv.writer(text, lineterminator="\n")
        writer.writerow(headers)
        for row in rows:
            writer.writerow([row.get(header, "") for header in headers])
        content = text.getvalue().encode("utf-8")
        return {
            "name": f"provider_serial_validation_{phase_name}.csv",
            "mime_type": "text/csv",
            "content_base64": base64.b64encode(content).decode("ascii"),
        }

    def _run_phase(
        self,
        *,
        validator: ValidadorSerialesProveedorService,
        headers: list[str],
        rows: list[dict[str, Any]],
        phase_name: str,
        previous_year: int,
        original_attachment_name: str,
        original_mime_type: str,
        original_content: bytes,
    ) -> dict[str, Any]:
        if phase_name == "full":
            attachment = {
                "name": original_attachment_name,
                "mime_type": original_mime_type,
                "content_base64": base64.b64encode(original_content).decode("ascii"),
            }
        else:
            attachment = self._build_attachment(headers=headers, rows=rows, phase_name=phase_name)
        tracemalloc.start()
        started_at = time.perf_counter()
        result = validator.validate(
            attachment=attachment,
            user_message="Valida este archivo del proveedor",
            previous_year=previous_year,
        )
        elapsed_ms = round((time.perf_counter() - started_at) * 1000, 2)
        _, peak_mem_bytes = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        table = dict(((result.get("data") or {}).get("table") or {}))
        business_response = dict(((result.get("data") or {}).get("business_response") or {}))
        dashboard = dict(business_response.get("dashboard_composition") or {})
        rows_out = list(table.get("rows") or [])
        payload_bytes = len(json.dumps(result, ensure_ascii=False).encode("utf-8"))
        consulted = self._trace_detail(result=result, phase="consultas_gobernadas")
        discovery = self._trace_detail(result=result, phase="descubrimiento_tablas")
        column_detection = self._trace_detail(result=result, phase="deteccion_columnas")
        performance_diagnostics = dict(consulted.get("diagnostico_rendimiento") or {})

        validations = {
            "serial_column_detected": bool((column_detection.get("serial") or {}).get("header")),
            "normalization_present": all(str(item.get("serial_normalizado") or "") == _normalize_serial(item.get("serial_proveedor")) for item in rows_out),
            "duplicates_processed": all("duplicado_en_archivo" in item and "ocurrencias_archivo" in item for item in rows_out),
            "consulted_current_tables": "base actual" in list(consulted.get("tablas_consultadas") or []) and "asociados actual" in list(consulted.get("tablas_consultadas") or []),
            "historical_checked_without_inventing": isinstance(discovery.get("no_existian"), list),
            "no_missing_table_crash": str(result.get("status") or "") == "success",
            "movil_flag_present": all("estado_contiene_movil" in item for item in rows_out),
            "responsible_fields_present": all("empleado" in item and "cedula_persona" in item and "responsable_candidate_source" in item and "responsable_enriched" in item for item in rows_out),
            "evidence_per_serial_present": all("fuentes_coincidencia" in item and "tablas_consultadas" in item for item in rows_out),
            "kpis_present": all(
                key in dict((result.get("data") or {}).get("kpis") or {})
                for key in (
                    "total_filas_archivo",
                    "seriales_unicos",
                    "duplicados_archivo",
                    "encontrados_por_fila",
                    "encontrados_unicos",
                    "no_encontrados_por_fila",
                    "no_encontrados_unicos",
                )
            ),
            "dashboard_composition_generated": bool(dashboard),
            "drilldown_present": bool(list(dashboard.get("priority_tables") or [])),
            "export_present": bool(dict(table.get("export_artifact") or {}).get("artifact_id")) and int(table.get("export_records") or 0) == int(table.get("rowcount") or 0),
        }
        phase_passed = str(result.get("status") or "") == "success" and all(validations.values())

        return {
            "phase": phase_name,
            "input_rows": len(rows),
            "result_status": str(result.get("status") or ""),
            "phase_passed": phase_passed,
            "root_cause": "" if phase_passed else "validation_contract_failed",
            "execution_ms": elapsed_ms,
            "payload_bytes": payload_bytes,
            "peak_mem_bytes": peak_mem_bytes,
            "kpis": dict((result.get("data") or {}).get("kpis") or {}),
            "table": {
                "rowcount": int(table.get("rowcount") or 0),
                "returned_records": int(table.get("returned_records") or 0),
                "total_records": int(table.get("total_records") or 0),
                "export_records": int(table.get("export_records") or 0),
                "truncated": bool(table.get("truncated")),
                "export_truncated": bool(table.get("export_truncated")),
            },
            "dashboard": {
                "generated": bool(dashboard),
                "kpi_count": len(list(dashboard.get("primary_kpis") or [])),
                "chart_count": len(list(dashboard.get("recommended_charts") or [])),
                "drilldown_count": len(list(dashboard.get("priority_tables") or [])),
                "table_ids": [str(item.get("id") or "") for item in list(dashboard.get("priority_tables") or [])],
            },
            "trace_checks": {
                "column_detection": column_detection,
                "table_discovery": discovery,
                "query_execution": consulted,
            },
            "performance_diagnostics": performance_diagnostics,
            "observed_cases": self._observed_cases(rows_out),
            "sample_rows": self._sample_rows(rows_out),
            "validations": validations,
        }

    def _trace_detail(self, *, result: dict[str, Any], phase: str) -> dict[str, Any]:
        for item in list(result.get("trace") or []):
            if str(item.get("phase") or "") == phase:
                return dict(item.get("detail") or {})
        return {}

    def _observed_cases(self, rows: list[dict[str, Any]]) -> dict[str, Any]:
        current_and_backup = next(
            (
                row["serial_proveedor"]
                for row in rows
                if "base actual" in str(row.get("fuentes_coincidencia") or "").lower()
                and "backup" in str(row.get("fuentes_coincidencia") or "").lower()
            ),
            "",
        )
        asociados_and_backup = next(
            (
                row["serial_proveedor"]
                for row in rows
                if "asociados actual" in str(row.get("fuentes_coincidencia") or "").lower()
                and "backup" in str(row.get("fuentes_coincidencia") or "").lower()
            ),
            "",
        )
        duplicate_row = next((row["serial_proveedor"] for row in rows if str(row.get("duplicado_en_archivo") or "") == "SI"), "")
        movil_with_responsable = next(
            (
                row["serial_proveedor"]
                for row in rows
                if str(row.get("estado_contiene_movil") or "") == "SI"
                and any(str(row.get(field) or "").strip() for field in ("empleado", "nombre", "cedula_persona", "movil_asociado"))
            ),
            "",
        )
        not_found = next((row["serial_proveedor"] for row in rows if str(row.get("encontrado") or "") == "NO"), "")
        historical_only = next((row["serial_proveedor"] for row in rows if str(row.get("solo_historico") or "") == "SI"), "")
        return {
            "found_current_and_backup": current_and_backup,
            "found_asociados_and_backup": asociados_and_backup,
            "duplicate_in_file": duplicate_row,
            "multiple_appearances": duplicate_row,
            "movil_with_responsable": movil_with_responsable,
            "not_found": not_found,
            "historical_only": historical_only,
        }

    def _sample_rows(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        samples: list[dict[str, Any]] = []
        for predicate in (
            lambda row: str(row.get("duplicado_en_archivo") or "") == "SI",
            lambda row: str(row.get("solo_historico") or "") == "SI",
            lambda row: str(row.get("estado_contiene_movil") or "") == "SI",
            lambda row: str(row.get("encontrado") or "") == "NO",
            lambda row: str(row.get("encontrado") or "") == "SI",
        ):
            match = next((row for row in rows if predicate(row)), None)
            if match and match not in samples:
                samples.append(match)
        return samples[:5]

    def _final_recommendation(self, *, phases: list[dict[str, Any]]) -> dict[str, Any]:
        completed = phases[-1] if phases else {}
        payload_bytes = int(completed.get("payload_bytes") or 0)
        input_rows = int(completed.get("input_rows") or 0)
        if input_rows >= 10_000 or payload_bytes >= 10_000_000:
            return {
                "sync_is_sufficient": False,
                "should_use_background_runtime": True,
                "should_use_approval_runtime": False,
                "should_expose_job_status": True,
                "reason": "large_provider_file_generates_high_payload_or_volume",
            }
        return {
            "sync_is_sufficient": True,
            "should_use_background_runtime": False,
            "should_use_approval_runtime": False,
            "should_expose_job_status": False,
            "reason": "current_volume_is_safe_for_sync",
        }
