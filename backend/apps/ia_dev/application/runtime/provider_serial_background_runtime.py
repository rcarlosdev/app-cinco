from __future__ import annotations

import threading
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from django.db import close_old_connections

from apps.ia_dev.application.contracts.chat_contracts import (
    build_chat_response_snapshot,
    ensure_chat_response_contract,
)
from apps.ia_dev.application.runtime.background_runtime_service import BackgroundRuntimeService
from apps.ia_dev.application.workflow.task_state_service import TaskStateService
from apps.ia_dev.domains.inventario_logistica.validador_seriales_proveedor import (
    ValidadorSerialesProveedorService,
)


class ProviderSerialBackgroundRuntime:
    CAPABILITY_ID = "inventory_provider_serial_validation"
    ACTIVE_STATUSES = {"queued", "running", "resumed"}
    PARTIAL_ARTIFACT_INTERVAL_CHUNKS = 5
    PARTIAL_ARTIFACT_INTERVAL_ROWS = 5000
    CHECKPOINT_EVERY_N_CHUNKS = 1
    ATTACHMENT_SPOOL_DIR = "tmp_provider_serial_validation_runtime"
    DEFAULT_CHUNK_SIZE = 1000
    SAFE_MAX_CHUNK_SIZE = 2000

    def __init__(
        self,
        *,
        task_state_service: TaskStateService | None = None,
        background_runtime_service: BackgroundRuntimeService | None = None,
    ) -> None:
        self.task_state_service = task_state_service or TaskStateService()
        self.background_runtime_service = background_runtime_service or BackgroundRuntimeService(
            task_state_service=self.task_state_service,
        )
        self._active_runs: set[str] = set()
        self._lock = threading.Lock()

    def schedule_if_needed(self, *, run_id: str) -> bool:
        normalized_run_id = str(run_id or "").strip()
        if not normalized_run_id:
            return False
        workflow = self.task_state_service.get(run_id=normalized_run_id) or {}
        state = dict((workflow or {}).get("state") or {})
        background = dict(state.get("background") or {})
        if str(background.get("tool_id") or "").strip() != self.CAPABILITY_ID:
            return False
        if str(background.get("run_status") or "").strip().lower() not in self.ACTIVE_STATUSES:
            return False
        background_request = dict(state.get("background_request") or {})
        if not background_request:
            self._fail_missing_background_request(workflow=workflow, reason="background_request sin adjunto")
            return False
        with self._lock:
            if normalized_run_id in self._active_runs:
                return False
            self._active_runs.add(normalized_run_id)
        worker = threading.Thread(
            target=self.execute_provider_serial_validation_run,
            kwargs={"run_id": normalized_run_id},
            name=f"provider-serial-bg-{normalized_run_id[:8]}",
            daemon=True,
        )
        worker.start()
        return True

    def execute_provider_serial_validation_run(self, *, run_id: str) -> None:
        normalized_run_id = str(run_id or "").strip()
        workflow = self.task_state_service.get(run_id=normalized_run_id) or {}
        state = dict((workflow or {}).get("state") or {})
        background = dict(state.get("background") or {})
        request = dict(state.get("background_request") or {})
        if (
            not normalized_run_id
            or str(background.get("tool_id") or "").strip() != self.CAPABILITY_ID
            or not request
        ):
            self._release_run(normalized_run_id)
            return

        validator = ValidadorSerialesProveedorService()
        accumulated_rows: list[dict[str, Any]] = []
        discovery: dict[str, Any] = {"existing_tables": [], "missing_tables": []}
        archivo = None
        provider_columns: dict[str, Any] = {}
        runtime_state: dict[str, Any] = {}
        attachment = dict(request.get("attachment") or {})
        user_message = str(request.get("message") or "Valida este archivo del proveedor")
        previous_year = int(request.get("previous_year") or (datetime.now(timezone.utc).year - 1))
        chunk_size = max(1, min(int(request.get("chunk_size") or self.DEFAULT_CHUNK_SIZE), self.SAFE_MAX_CHUNK_SIZE))
        fail_after_chunks = int(request.get("fail_after_chunks") or 0)

        try:
            close_old_connections()
            attachment = self._compact_background_request(
                run_id=normalized_run_id,
                request=request,
            )
            workflow = self.task_state_service.get(run_id=normalized_run_id) or workflow
            workflow = self.background_runtime_service.mark_started(workflow=workflow)
            self.background_runtime_service.add_progress(
                workflow=workflow,
                message="Validacion en proceso: preparando archivo y metadatos.",
                progress_pct=2.0,
                partial_evidence={
                    "phase": "preparacion_archivo",
                    "current_stage": "running",
                    "result_kind": "partial",
                    "result_label": "Resultado parcial",
                    "current_chunk": 0,
                    "total_chunks": 0,
                    "found_so_far": 0,
                    "not_found_so_far": 0,
                    "movil_so_far": 0,
                    "enriched_responsible_so_far": 0,
                },
                status="running",
            )
            result, final_evidence = self._execute_progressive_validation(
                validator=validator,
                attachment=attachment,
                user_message=user_message,
                previous_year=previous_year,
                chunk_size=chunk_size,
                run_id=normalized_run_id,
                fail_after_chunks=fail_after_chunks,
                runtime_state=runtime_state,
            )
            response_snapshot = self._build_response_snapshot(
                result=result,
                session_id=str(request.get("session_id") or ""),
            )
            workflow = self.task_state_service.get(run_id=normalized_run_id) or workflow
            result_status = str(result.get("status") or "").strip().lower()
            if result_status == "success":
                self.background_runtime_service.complete_run(
                    workflow=workflow,
                    final_evidence=final_evidence,
                    response_snapshot=response_snapshot,
                )
                return
            self.background_runtime_service.fail_run(
                workflow=workflow,
                failure_reason=result_status or "background_validation_failed",
                final_evidence=final_evidence,
                response_snapshot=response_snapshot,
            )
        except Exception as exc:
            workflow = self.task_state_service.get(run_id=normalized_run_id) or workflow
            partial_result, partial_evidence = self._build_partial_failure_result(
                validator=validator,
                attachment=attachment,
                user_message=user_message,
                archivo=runtime_state.get("archivo"),
                provider_columns=dict(runtime_state.get("provider_columns") or {}),
                discovery=dict(runtime_state.get("discovery") or {}),
                rows=self._materialize_rows(runtime_state=runtime_state),
                provider_rows=list(runtime_state.get("provider_rows") or []),
                processed_serials=set(runtime_state.get("processed_serials") or set()),
                matches=list(runtime_state.get("matches") or []),
                matches_by_serial=dict(runtime_state.get("matches_by_serial") or {}),
                progress_state=dict(runtime_state.get("progress_state") or {}),
                failure_reason=str(exc),
                session_id=str(request.get("session_id") or ""),
            )
            self.background_runtime_service.fail_run(
                workflow=workflow,
                failure_reason=str(exc),
                final_evidence=partial_evidence,
                response_snapshot=partial_result,
            )
        finally:
            close_old_connections()
            self._release_run(normalized_run_id)

    def _execute_progressive_validation(
        self,
        *,
        validator: ValidadorSerialesProveedorService,
        attachment: dict[str, Any],
        user_message: str,
        previous_year: int,
        chunk_size: int,
        run_id: str,
        fail_after_chunks: int,
        runtime_state: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        trace: list[dict[str, Any]] = []
        filename = str(attachment.get("name") or "").strip()
        mime_type = str(attachment.get("mime_type") or attachment.get("mimeType") or "").strip()
        encoded = str(attachment.get("content_base64") or "").strip()
        if not filename or not encoded:
            spooled_path = str(attachment.get("spooled_path") or attachment.get("attachment_path") or "").strip()
            if filename and spooled_path:
                try:
                    content = Path(spooled_path).read_bytes()
                except OSError as exc:
                    result = validator._blocked_result(
                        trace=trace,
                        response_status="clarification_required",
                        limitation="El adjunto no se pudo rehidratar desde el spool temporal.",
                        missing_reason=f"attachment_spool_unavailable:{exc}",
                        user_message=user_message,
                    )
                    evidence = self._build_terminal_evidence(
                        result=result,
                        phase="attachment_spool_unavailable",
                        rows_processed=0,
                    )
                    evidence["failure_reason"] = "attachment_spool_unavailable"
                    return result, evidence
            else:
                result = validator._blocked_result(
                    trace=trace,
                    response_status="clarification_required",
                    limitation="El adjunto no trae nombre o contenido suficiente para procesarlo.",
                    missing_reason="attachment_incomplete",
                    user_message=user_message,
                )
                evidence = self._build_terminal_evidence(result=result, phase="attachment_incomplete", rows_processed=0)
                evidence["failure_reason"] = "attachment no disponible"
                return result, evidence
        else:
            content = validator._decode_attachment(encoded=encoded)
        archivo = validator.file_reader.parse(filename=filename, mime_type=mime_type, content=content)
        runtime_state["archivo"] = archivo
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
        provider_columns = validator._detect_provider_columns(archivo=archivo)
        runtime_state["provider_columns"] = dict(provider_columns)
        trace.append(
            {
                "phase": "deteccion_columnas",
                "status": "ok" if provider_columns.get("serial") else "warning",
                "detail": provider_columns,
            }
        )
        serial_column = str((provider_columns.get("serial") or {}).get("header") or "")
        if not archivo.rows:
            result = validator._blocked_result(
                trace=trace,
                response_status="empty_result",
                limitation="El archivo no contiene filas operativas para validar.",
                missing_reason="provider_file_empty",
                user_message=user_message,
                extra_filters={"sheet_name": archivo.sheet_name},
            )
            evidence = self._build_terminal_evidence(result=result, phase="provider_file_empty", rows_processed=0)
            evidence["failure_reason"] = "provider_file_empty"
            return result, evidence
        if not serial_column:
            result = validator._blocked_result(
                trace=trace,
                response_status="clarification_required",
                limitation="No se detecto una columna de serial con evidencia semantica suficiente.",
                missing_reason="serial_column_not_detected",
                user_message=user_message,
                extra_filters={"sheet_name": archivo.sheet_name},
            )
            evidence = self._build_terminal_evidence(result=result, phase="serial_column_not_detected", rows_processed=0)
            evidence["failure_reason"] = "serial_column_not_detected"
            return result, evidence

        provider_rows = validator._build_provider_rows(archivo=archivo, provider_columns=provider_columns)
        runtime_state["provider_rows"] = list(provider_rows)
        non_empty_rows = [row for row in provider_rows if row["serial_normalizado"]]
        if not non_empty_rows:
            result = validator._blocked_result(
                trace=trace,
                response_status="empty_result",
                limitation="La columna candidata de serial no trae valores operativos para consultar.",
                missing_reason="provider_serials_empty",
                user_message=user_message,
                extra_filters={"sheet_name": archivo.sheet_name, "serial_column": serial_column},
            )
            evidence = self._build_terminal_evidence(result=result, phase="provider_serials_empty", rows_processed=0)
            evidence["failure_reason"] = "provider_serials_empty"
            return result, evidence

        duplicate_counter: dict[str, int] = {}
        for row in non_empty_rows:
            normalized = str(row.get("serial_normalizado") or "")
            duplicate_counter[normalized] = int(duplicate_counter.get(normalized, 0)) + 1
        for row in provider_rows:
            normalized = str(row.get("serial_normalizado") or "")
            row["duplicado_en_archivo"] = bool(normalized and duplicate_counter.get(normalized, 0) > 1)
            row["ocurrencias_archivo"] = int(duplicate_counter.get(normalized, 0))

        years = list(
            range(
                validator.HISTORICAL_START_YEAR,
                max(validator.HISTORICAL_START_YEAR, int(previous_year)) + 1,
            )
        )
        discovery = validator._discover_tables(years=years)
        runtime_state["discovery"] = dict(discovery)
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

        total_rows = len(provider_rows)
        grouped_rows: OrderedDict[str, list[dict[str, Any]]] = OrderedDict()
        empty_rows: list[dict[str, Any]] = []
        for row in provider_rows:
            serial = str(row.get("serial_normalizado") or "")
            if not serial:
                empty_rows.append(row)
                continue
            grouped_rows.setdefault(serial, []).append(row)
        serials = list(grouped_rows.keys())
        requested_chunk_size = chunk_size
        chunk_size = self._resolve_chunk_size(
            requested_chunk_size=requested_chunk_size,
            total_unique_serials=len(serials),
        )
        rowcount_by_serial = {serial: len(list(rows)) for serial, rows in grouped_rows.items()}
        runtime_state["attachment_name"] = filename
        progress_state = self._build_progress_state(
            total_rows=total_rows,
            total_chunks=0,
            attachment_name=filename,
            total_unique_serials=len(serials),
            rowcount_by_serial=rowcount_by_serial,
        )
        progress_state["chunk_size"] = chunk_size
        progress_state["requested_chunk_size"] = requested_chunk_size
        progress_state["normalized_fallback_mode"] = "disabled_for_large_background"
        progress_state["elapsed_seconds"] = 0
        performance_metrics = self._init_performance_metrics(
            requested_chunk_size=requested_chunk_size,
            effective_chunk_size=chunk_size,
            total_unique_serials=len(serials),
        )
        progress_state["performance_metrics"] = performance_metrics
        runtime_state["progress_state"] = progress_state

        self._checkpoint(
            run_id=run_id,
            label="leyendo_archivo",
            progress_state=progress_state,
            phase="leyendo_archivo",
            current_stage="running",
        )
        self._checkpoint(
            run_id=run_id,
            label="normalizando_seriales",
            progress_state=progress_state,
            phase="normalizando_seriales",
            current_stage="running",
        )

        pending_serials = list(serials)
        matches: list[dict[str, Any]] = []
        matches_by_serial: dict[str, list[dict[str, Any]]] = {}
        runtime_state["matches"] = matches
        runtime_state["matches_by_serial"] = matches_by_serial
        runtime_state["processed_serials"] = set()
        total_chunks_counter = 0
        current_chunk_counter = 0
        stage_plan = validator._build_lookup_stage_plan(tables=discovery["existing_tables"])

        for stage in stage_plan:
            stage_key = str(stage.get("stage_key") or "")
            stage_tables = list(stage.get("tables") or [])
            if not pending_serials:
                break
            progress_state["phase_label"] = str(stage.get("label") or "")
            progress_state["table_label"] = ""
            progress_state["stage_serials_total"] = len(pending_serials)
            progress_state["stage_serials_processed"] = 0
            progress_state["stage_serials_pending"] = len(pending_serials)
            if not stage_tables:
                self._record_stage_metrics(
                    progress_state=progress_state,
                    stage_key=stage_key,
                    stage_label=str(stage.get("label") or ""),
                    input_serials=len(pending_serials),
                    found_serials=0,
                    pending_after_stage=len(pending_serials),
                    query_count=0,
                    sql_time_ms=0.0,
                    rows_returned=0,
                    table_count=0,
                )
                self._checkpoint(
                    run_id=run_id,
                    label=str(stage.get("phase") or ""),
                    progress_state=progress_state,
                    phase=str(stage.get("phase") or ""),
                    current_stage="running",
                )
                continue

            stage_input_serials = list(pending_serials)
            stage_query_count = 0
            stage_sql_time_ms = 0.0
            stage_rows_returned = 0
            stage_table_count = 0
            use_union_stage = stage_key in {"backup_base", "backup_asociados"} and len(stage_tables) > 1
            if use_union_stage:
                union_chunk_size = validator._safe_union_chunk_size(
                    requested_chunk_size=chunk_size,
                    table_count=len(stage_tables),
                )
                stage_pending = list(pending_serials)
                serial_chunks = [
                    stage_pending[index : index + union_chunk_size]
                    for index in range(0, len(stage_pending), union_chunk_size)
                ]
                total_chunks_counter += len(serial_chunks)
                progress_state["total_chunks"] = total_chunks_counter
                progress_state["phase_label"] = str(stage.get("label") or "")
                progress_state["table_label"] = self._build_stage_table_label(
                    stage_label=str(stage.get("label") or ""),
                    tables=stage_tables,
                )
                progress_state["table_serials_total"] = len(stage_pending)
                progress_state["table_serials_pending"] = len(stage_pending)
                progress_state["table_chunk_total"] = len(serial_chunks)
                progress_state["chunk_size"] = union_chunk_size
                for local_chunk_index, chunk_serials in enumerate(serial_chunks, start=1):
                    progress_state["active_chunk"] = current_chunk_counter + 1
                    progress_state["table_serials_pending"] = len(stage_pending)
                    stage_lookup_metrics: dict[str, Any] = {}
                    chunk_started_at = datetime.now(timezone.utc).timestamp()
                    table_matches = validator._query_tables_union_stage(
                        tables=stage_tables,
                        normalized_serials=chunk_serials,
                        lookup_metrics=stage_lookup_metrics,
                        skip_noncanonical_probe=True,
                    )
                    matches.extend(table_matches)
                    found_in_chunk: set[str] = set()
                    for item in table_matches:
                        serial_normalizado = str(item.get("serial_normalizado") or "")
                        if not serial_normalizado:
                            continue
                        found_in_chunk.add(serial_normalizado)
                        matches_by_serial.setdefault(serial_normalizado, []).append(item)
                    pending_serials = [
                        serial for serial in pending_serials if serial and serial not in found_in_chunk
                    ]
                    stage_pending = [
                        serial for serial in stage_pending if serial and serial not in found_in_chunk
                    ]
                    runtime_state["matches"] = list(matches)
                    runtime_state["matches_by_serial"] = dict(matches_by_serial)
                    current_chunk_counter += 1
                    stage_query_count += int(stage_lookup_metrics.get("query_count") or 0)
                    stage_sql_time_ms += float(stage_lookup_metrics.get("sql_time_ms") or 0.0)
                    stage_rows_returned += int(stage_lookup_metrics.get("rows_returned") or 0)
                    stage_table_count = max(
                        stage_table_count,
                        int(stage_lookup_metrics.get("table_count") or len(stage_tables)),
                    )
                    self._update_progress_state(
                        progress_state=progress_state,
                        processed_serials=chunk_serials,
                        found_serials=found_in_chunk,
                        pending_serials=pending_serials,
                        current_chunk=current_chunk_counter,
                        stage_key=stage_key,
                    )
                    progress_state["table_serials_pending"] = len(stage_pending)
                    progress_state["active_chunk"] = current_chunk_counter
                    runtime_state["processed_serials"] = set(progress_state.get("_processed_serials") or set())
                    self._record_runtime_chunk_metrics(
                        progress_state=progress_state,
                        stage_key=stage_key,
                        stage_label=str(stage.get("label") or ""),
                        table_label=str(progress_state.get("table_label") or ""),
                        chunk_index=local_chunk_index,
                        input_serials=len(chunk_serials),
                        found_serials=len(found_in_chunk),
                        pending_after_stage=len(pending_serials),
                        query_count=int(stage_lookup_metrics.get("query_count") or 0),
                        sql_time_ms=float(stage_lookup_metrics.get("sql_time_ms") or 0.0),
                        rows_returned=int(stage_lookup_metrics.get("rows_returned") or 0),
                        union_stage=True,
                        table_metrics=list(stage_lookup_metrics.get("table_metrics") or []),
                        chunk_duration_ms=(datetime.now(timezone.utc).timestamp() - chunk_started_at) * 1000.0,
                    )
                    should_checkpoint = (
                        current_chunk_counter % self.CHECKPOINT_EVERY_N_CHUNKS == 0
                        or not stage_pending
                        or not pending_serials
                    )
                    if should_checkpoint:
                        self._checkpoint(
                            run_id=run_id,
                            label=f"{stage.get('phase')}_{current_chunk_counter}",
                            progress_state=progress_state,
                            phase=str(stage.get("phase") or ""),
                            current_stage="running",
                        )
                    if fail_after_chunks > 0 and current_chunk_counter >= fail_after_chunks:
                        raise RuntimeError(f"simulated_chunk_failure:{current_chunk_counter}")
                self._record_stage_metrics(
                    progress_state=progress_state,
                    stage_key=stage_key,
                    stage_label=str(stage.get("label") or ""),
                    input_serials=len(stage_input_serials),
                    found_serials=len([serial for serial in stage_input_serials if serial not in pending_serials]),
                    pending_after_stage=len(pending_serials),
                    query_count=stage_query_count,
                    sql_time_ms=stage_sql_time_ms,
                    rows_returned=stage_rows_returned,
                    table_count=stage_table_count or len(stage_tables),
                )
                progress_state["chunk_size"] = chunk_size
                continue

            for table in stage_tables:
                table_pending = list(pending_serials)
                if not table_pending:
                    break
                serial_chunks = [
                    table_pending[index : index + chunk_size]
                    for index in range(0, len(table_pending), chunk_size)
                ]
                total_chunks_counter += len(serial_chunks)
                progress_state["total_chunks"] = total_chunks_counter
                progress_state["phase_label"] = (
                    f"{str(stage.get('label') or '').strip()} | {str(table.get('label') or '').strip()}"
                ).strip(" |")
                progress_state["table_label"] = str(table.get("label") or "")
                progress_state["table_serials_total"] = len(table_pending)
                progress_state["table_serials_pending"] = len(table_pending)
                progress_state["table_chunk_total"] = len(serial_chunks)
                progress_state["active_chunk"] = current_chunk_counter + 1 if serial_chunks else current_chunk_counter
                for local_chunk_index, chunk_serials in enumerate(serial_chunks, start=1):
                    progress_state["active_chunk"] = current_chunk_counter + 1
                    progress_state["table_serials_pending"] = len(table_pending)
                    table_lookup_metrics: dict[str, Any] = {}
                    chunk_started_at = datetime.now(timezone.utc).timestamp()
                    table_matches = validator._query_table(
                        table=table,
                        normalized_serials=chunk_serials,
                        lookup_metrics=table_lookup_metrics,
                        skip_noncanonical_probe=True,
                    )
                    matches.extend(table_matches)
                    found_in_chunk: set[str] = set()
                    for item in table_matches:
                        serial_normalizado = str(item.get("serial_normalizado") or "")
                        if not serial_normalizado:
                            continue
                        found_in_chunk.add(serial_normalizado)
                        matches_by_serial.setdefault(serial_normalizado, []).append(item)
                    pending_serials = [
                        serial for serial in pending_serials if serial and serial not in found_in_chunk
                    ]
                    runtime_state["matches"] = list(matches)
                    runtime_state["matches_by_serial"] = dict(matches_by_serial)
                    current_chunk_counter += 1
                    stage_query_count += int(table_lookup_metrics.get("query_count") or 0)
                    stage_sql_time_ms += float(table_lookup_metrics.get("sql_time_ms") or 0.0)
                    stage_rows_returned += int(table_lookup_metrics.get("rows_returned") or 0)
                    stage_table_count = len(stage_tables)
                    table_pending = [
                        serial for serial in table_pending if serial and serial not in found_in_chunk
                    ]
                    self._update_progress_state(
                        progress_state=progress_state,
                        processed_serials=chunk_serials,
                        found_serials=found_in_chunk,
                        pending_serials=pending_serials,
                        current_chunk=current_chunk_counter,
                        stage_key=str(stage.get("stage_key") or ""),
                    )
                    progress_state["table_serials_pending"] = len(table_pending)
                    progress_state["active_chunk"] = current_chunk_counter
                    runtime_state["processed_serials"] = set(progress_state.get("_processed_serials") or set())
                    self._record_runtime_chunk_metrics(
                        progress_state=progress_state,
                        stage_key=stage_key,
                        stage_label=str(stage.get("label") or ""),
                        table_label=str(table.get("label") or ""),
                        chunk_index=local_chunk_index,
                        input_serials=len(chunk_serials),
                        found_serials=len(found_in_chunk),
                        pending_after_stage=len(pending_serials),
                        query_count=int(table_lookup_metrics.get("query_count") or 0),
                        sql_time_ms=float(table_lookup_metrics.get("sql_time_ms") or 0.0),
                        rows_returned=int(table_lookup_metrics.get("rows_returned") or 0),
                        union_stage=False,
                        table_metrics=[],
                        chunk_duration_ms=(datetime.now(timezone.utc).timestamp() - chunk_started_at) * 1000.0,
                    )
                    should_checkpoint = (
                        current_chunk_counter % self.CHECKPOINT_EVERY_N_CHUNKS == 0
                        or not table_pending
                        or not pending_serials
                    )
                    if should_checkpoint:
                        self._checkpoint(
                            run_id=run_id,
                            label=f"{stage.get('phase')}_{current_chunk_counter}",
                            progress_state=progress_state,
                            phase=str(stage.get("phase") or ""),
                            current_stage="running",
                        )
                    if fail_after_chunks > 0 and current_chunk_counter >= fail_after_chunks:
                        raise RuntimeError(f"simulated_chunk_failure:{current_chunk_counter}")
            self._record_stage_metrics(
                progress_state=progress_state,
                stage_key=stage_key,
                stage_label=str(stage.get("label") or ""),
                input_serials=len(stage_input_serials),
                found_serials=len([serial for serial in stage_input_serials if serial not in pending_serials]),
                pending_after_stage=len(pending_serials),
                query_count=stage_query_count,
                sql_time_ms=stage_sql_time_ms,
                rows_returned=stage_rows_returned,
                table_count=stage_table_count,
            )

        progress_state["not_found_so_far"] = len(pending_serials)
        progress_state["serials_pending"] = len(pending_serials)
        progress_state["phase_label"] = "Enriqueciendo responsables"
        progress_state["table_label"] = ""
        self._checkpoint(
            run_id=run_id,
            label="enriqueciendo_movil_responsables",
            progress_state=progress_state,
            phase="enriqueciendo_movil_responsables",
            current_stage="running",
        )

        personal_rows = validator._enrich_personal(matches=matches)
        personal_by_identifier = {
            str(row.get("cedula") or "").strip(): row
            for row in personal_rows
            if str(row.get("cedula") or "").strip()
        }
        consolidated_rows = validator._consolidate_rows(
            provider_rows=provider_rows,
            matches_by_serial=matches_by_serial,
            personal_by_identifier=personal_by_identifier,
            discovery=discovery,
        )
        runtime_state["rows"] = list(consolidated_rows)
        progress_state["movil_so_far"] = int(
            sum(1 for row in consolidated_rows if str(row.get("estado_contiene_movil") or "") == "SI")
        )
        progress_state["enriched_responsible_so_far"] = int(
            sum(
                1
                for row in consolidated_rows
                if str(row.get("estado_contiene_movil") or "") == "SI" and bool(row.get("responsable_enriched"))
            )
        )
        progress_state["rows_processed"] = total_rows
        progress_state["serials_processed"] = len(serials)
        progress_state["serials_pending"] = len(
            {
                str(row.get("serial_normalizado") or "")
                for row in consolidated_rows
                if str(row.get("serial_normalizado") or "") and str(row.get("encontrado") or "") == "NO"
            }
        )
        progress_state["not_found_so_far"] = progress_state["serials_pending"]
        progress_state["phase_label"] = "Generando dashboard final"
        progress_state["table_label"] = ""
        self._checkpoint(
            run_id=run_id,
            label="generando_dashboard_final",
            progress_state=progress_state,
            phase="generando_dashboard_final",
            current_stage="running",
        )

        export_artifact = validator._write_export_artifact(rows=consolidated_rows)
        progress_state["artifact_id"] = str(export_artifact.get("artifact_id") or "")
        result_table = validator._build_main_table(rows=consolidated_rows, export_artifact=export_artifact)
        extra_tables = validator._build_extra_tables(rows=consolidated_rows, discovery=discovery)
        kpis = validator._build_kpis(rows=consolidated_rows)
        progress_state["phase_label"] = "Generando export CSV"
        progress_state["table_label"] = ""
        self._checkpoint(
            run_id=run_id,
            label="generando_export_csv",
            progress_state=progress_state,
            phase="generando_export_csv",
            current_stage="running",
        )
        business_response = validator._build_business_response(
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
        trace.append(
            {
                "phase": "consultas_gobernadas",
                "status": "ok",
                "detail": {
                    "tablas_consultadas": [item["label"] for item in discovery["existing_tables"]],
                    "coincidencias_por_tabla": {},
                },
            }
        )
        final_result = {
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
        final_evidence = self._build_terminal_evidence(
            result=final_result,
            phase="completed",
            rows_processed=int(progress_state.get("rows_processed") or 0),
        )
        final_evidence.update(
            {
                "phase": "completed",
                "phase_label": "Completado",
                "table_label": "",
                "total_rows": total_rows,
                "total_estimated": total_rows,
                "current_stage": "completed",
                "result_kind": "final",
                "result_label": "Resultado final",
                "artifact_id": str(export_artifact.get("artifact_id") or ""),
                "current_chunk": int(progress_state.get("current_chunk") or total_chunks_counter),
                "total_chunks": total_chunks_counter,
                "found_so_far": int(progress_state.get("found_so_far") or 0),
                "not_found_so_far": int(progress_state.get("not_found_so_far") or 0),
                "movil_so_far": int(progress_state.get("movil_so_far") or 0),
                "enriched_responsible_so_far": int(progress_state.get("enriched_responsible_so_far") or 0),
                "attachment_name": filename,
                "serials_unique_total": len(serials),
                "serials_processed": len(serials),
                "serials_pending": int(progress_state.get("serials_pending") or 0),
                "found_in_base_actual": int(progress_state.get("found_in_base_actual") or 0),
                "found_in_asociados_actual": int(progress_state.get("found_in_asociados_actual") or 0),
                "found_in_historico": int(progress_state.get("found_in_historico") or 0),
                "chunk_size": chunk_size,
                "requested_chunk_size": requested_chunk_size,
                "normalized_fallback_mode": "disabled_for_large_background",
                "moviles_detectados": int(kpis.get("moviles_detectados") or 0),
                "moviles_con_responsable_enriquecido": int(kpis.get("moviles_con_responsable_enriquecido") or 0),
                "moviles_sin_responsable_enriquecido": int(kpis.get("moviles_sin_responsable_enriquecido") or 0),
                "movil_kpi_definition": {
                    "moviles_detectados": "Seriales unicos cuyo estado final contiene MOVIL.",
                    "moviles_con_responsable_enriquecido": "Subset de MOVIL detectados con responsable/persona enriquecido.",
                },
                "performance_metrics": dict(progress_state.get("performance_metrics") or {}),
            }
        )
        return final_result, final_evidence

    def _build_partial_failure_result(
        self,
        *,
        validator: ValidadorSerialesProveedorService,
        attachment: dict[str, Any],
        user_message: str,
        archivo,
        provider_columns: dict[str, Any],
        discovery: dict[str, Any],
        rows: list[dict[str, Any]],
        provider_rows: list[dict[str, Any]],
        processed_serials: set[str],
        matches: list[dict[str, Any]],
        matches_by_serial: dict[str, list[dict[str, Any]]],
        progress_state: dict[str, Any],
        failure_reason: str,
        session_id: str,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        if not rows and provider_rows and processed_serials:
            partial_rows = [
                row
                for row in provider_rows
                if not str(row.get("serial_normalizado") or "")
                or str(row.get("serial_normalizado") or "") in processed_serials
            ]
            personal_rows = validator._enrich_personal(matches=matches)
            personal_by_identifier = {
                str(row.get("cedula") or "").strip(): row
                for row in personal_rows
                if str(row.get("cedula") or "").strip()
            }
            rows = validator._consolidate_rows(
                provider_rows=partial_rows,
                matches_by_serial=matches_by_serial,
                personal_by_identifier=personal_by_identifier,
                discovery=discovery,
            )
        if not rows:
            snapshot = build_chat_response_snapshot()
            snapshot["session_id"] = session_id
            snapshot["reply"] = "La validacion en background fallo antes de producir evidencia parcial."
            snapshot["data"] = {
                "kpis": {},
                "series": [],
                "labels": [],
                "insights": [failure_reason],
                "table": {"columns": [], "rows": [], "rowcount": 0},
            }
            return ensure_chat_response_contract(snapshot), {
                "phase": "failed",
                "phase_label": "",
                "table_label": "",
                "failure_reason": failure_reason,
                "rows_processed": 0,
                "total_rows": 0,
                "percentage": 0.0,
                "current_stage": "failed",
                "result_kind": "partial",
                "result_label": "Resultado parcial",
                "current_chunk": 0,
                "total_chunks": 0,
                "found_so_far": 0,
                "not_found_so_far": 0,
                "movil_so_far": 0,
                "enriched_responsible_so_far": 0,
                "performance_metrics": dict(progress_state.get("performance_metrics") or {}),
                "movil_kpi_definition": {
                    "moviles_detectados": "Seriales unicos cuyo estado final contiene MOVIL.",
                    "moviles_con_responsable_enriquecido": "Subset de MOVIL detectados con responsable/persona enriquecido.",
                },
            }

        export_artifact = validator._write_export_artifact(rows=rows)
        result_table = validator._build_main_table(rows=rows, export_artifact=export_artifact)
        extra_tables = validator._build_extra_tables(rows=rows, discovery=discovery)
        kpis = validator._build_kpis(rows=rows)
        business_response = validator._business_response_payload(
            user_message=user_message,
            attachment_name=str(attachment.get("name") or ""),
            sheet_name=str(getattr(archivo, "sheet_name", "") or ""),
            serial_column=str((provider_columns.get("serial") or {}).get("header") or ""),
            rows=rows,
            kpis=kpis,
            discovery=discovery,
            response_status="partial",
            dato=(
                f"Validacion parcial: se procesaron {int(kpis.get('total_filas_archivo') or len(rows))} "
                "filas antes de que el job fallara."
            ),
            hallazgo=failure_reason,
            interpretacion="El runtime conserva la evidencia parcial obtenida hasta el ultimo chunk exitoso.",
            recomendacion="Descarga el artifact parcial, revisa la causa y relanza la validacion.",
            limitations=[failure_reason],
            extra_filters={
                "sheet_name": str(getattr(archivo, "sheet_name", "") or ""),
                "serial_column": str((provider_columns.get("serial") or {}).get("header") or ""),
            },
            supplemental_tables=extra_tables,
            export_artifact=export_artifact,
        )
        result = {
            "status": "partial",
            "reply": str(business_response.get("dato") or ""),
            "data": {
                "kpis": kpis,
                "series": [],
                "labels": [],
                "insights": [failure_reason, str(business_response.get("recomendacion") or "")],
                "table": result_table,
                "extra_tables": extra_tables,
                "business_response": business_response,
            },
            "trace": [
                {
                    "phase": "background_failure",
                    "status": "failed",
                    "detail": {"reason": failure_reason},
                }
            ],
        }
        return self._build_response_snapshot(result=result, session_id=session_id), {
            "phase": "failed",
            "phase_label": "",
            "table_label": "",
            "failure_reason": failure_reason,
            "rows_processed": len(rows),
            "total_rows": len(rows),
            "percentage": 100.0,
            "current_stage": "failed",
            "result_kind": "partial",
            "result_label": "Resultado parcial",
            "artifact_id": str(export_artifact.get("artifact_id") or ""),
            "artifact_available": bool(export_artifact.get("available")),
            "serials_unique_total": int(kpis.get("seriales_unicos") or 0),
            "serials_processed": int(kpis.get("seriales_unicos") or 0),
            "serials_pending": int(kpis.get("no_encontrados_unicos") or 0),
            "encontrados_parciales": int(kpis.get("encontrados_por_fila") or 0),
            "no_encontrados_parciales": int(kpis.get("no_encontrados_por_fila") or 0),
            "movil_detectados_parciales": int(kpis.get("moviles_detectados") or 0),
            "errores_parciales": 1,
            "found_so_far": int(kpis.get("encontrados_por_fila") or 0),
            "not_found_so_far": int(kpis.get("no_encontrados_por_fila") or 0),
            "movil_so_far": int(kpis.get("moviles_detectados") or 0),
            "enriched_responsible_so_far": int(kpis.get("moviles_con_responsable_enriquecido") or 0),
            "found_in_base_actual": int(kpis.get("fuente_final_base_actual") or 0),
            "found_in_asociados_actual": int(kpis.get("fuente_final_asociados_actual") or 0),
            "found_in_historico": int(kpis.get("fuente_final_historico") or 0),
            "chunk_size": int(progress_state.get("chunk_size") or 0),
            "requested_chunk_size": int(progress_state.get("requested_chunk_size") or 0),
            "normalized_fallback_mode": str(progress_state.get("normalized_fallback_mode") or ""),
            "moviles_detectados": int(kpis.get("moviles_detectados") or 0),
            "moviles_con_responsable_enriquecido": int(kpis.get("moviles_con_responsable_enriquecido") or 0),
            "moviles_sin_responsable_enriquecido": int(kpis.get("moviles_sin_responsable_enriquecido") or 0),
            "movil_kpi_definition": {
                "moviles_detectados": "Seriales unicos cuyo estado final contiene MOVIL.",
                "moviles_con_responsable_enriquecido": "Subset de MOVIL detectados con responsable/persona enriquecido.",
            },
            "performance_metrics": dict(progress_state.get("performance_metrics") or {}),
        }

    def _build_response_snapshot(self, *, result: dict[str, Any], session_id: str) -> dict[str, Any]:
        snapshot = build_chat_response_snapshot()
        snapshot["session_id"] = str(session_id or "")
        snapshot["reply"] = str(result.get("reply") or "")
        snapshot["data"] = dict(result.get("data") or {})
        snapshot["trace"] = list(result.get("trace") or [])
        snapshot["orchestrator"] = {
            "intent": self.CAPABILITY_ID,
            "domain": "inventario_logistica",
            "selected_agent": "inventory_agent",
            "classifier_source": "background_runtime",
            "needs_database": True,
            "output_mode": "table",
            "used_tools": [
                self.CAPABILITY_ID,
                "query_execution_planner.governed_select",
            ],
        }
        snapshot["data_sources"] = {
            "inventario_logistica": {"ok": True, "source": "background_runtime"},
            "ai_dictionary": {"ok": True, "source": "background_runtime"},
        }
        return ensure_chat_response_contract(snapshot)

    def _build_terminal_evidence(
        self,
        *,
        result: dict[str, Any],
        phase: str,
        rows_processed: int,
    ) -> dict[str, Any]:
        kpis = dict((result.get("data") or {}).get("kpis") or {})
        table = dict((result.get("data") or {}).get("table") or {})
        return {
            "phase": phase,
            "phase_label": "Completado" if str(result.get("status") or "") == "success" else "",
            "table_label": "",
            "rows_processed": rows_processed,
            "total_rows": int(table.get("rowcount") or rows_processed),
            "percentage": 100.0 if rows_processed else 0.0,
            "current_stage": "completed" if str(result.get("status") or "") == "success" else "failed",
            "result_kind": "final" if str(result.get("status") or "") == "success" else "partial",
            "result_label": "Resultado final" if str(result.get("status") or "") == "success" else "Resultado parcial",
            "encontrados_parciales": int(kpis.get("encontrados_por_fila") or 0),
            "no_encontrados_parciales": int(kpis.get("no_encontrados_por_fila") or 0),
            "movil_detectados_parciales": int(kpis.get("moviles_detectados") or 0),
            "errores_parciales": 0,
            "current_chunk": 0,
            "total_chunks": 0,
            "serials_unique_total": int(kpis.get("seriales_unicos") or 0),
            "serials_processed": int(kpis.get("seriales_unicos") or 0),
            "serials_pending": int(kpis.get("no_encontrados_unicos") or 0),
            "found_so_far": int(kpis.get("encontrados_por_fila") or 0),
            "not_found_so_far": int(kpis.get("no_encontrados_por_fila") or 0),
            "movil_so_far": int(kpis.get("moviles_detectados") or 0),
            "enriched_responsible_so_far": int(kpis.get("moviles_con_responsable_enriquecido") or 0),
            "moviles_detectados": int(kpis.get("moviles_detectados") or 0),
            "moviles_con_responsable_enriquecido": int(kpis.get("moviles_con_responsable_enriquecido") or 0),
            "moviles_sin_responsable_enriquecido": int(kpis.get("moviles_sin_responsable_enriquecido") or 0),
            "movil_kpi_definition": {
                "moviles_detectados": "Seriales unicos cuyo estado final contiene MOVIL.",
                "moviles_con_responsable_enriquecido": "Subset de MOVIL detectados con responsable/persona enriquecido.",
            },
            "found_in_base_actual": int(kpis.get("fuente_final_base_actual") or 0),
            "found_in_asociados_actual": int(kpis.get("fuente_final_asociados_actual") or 0),
            "found_in_historico": int(kpis.get("fuente_final_historico") or 0),
        }

    def _checkpoint(
        self,
        *,
        run_id: str,
        label: str,
        progress_state: dict[str, Any],
        phase: str,
        current_stage: str,
    ) -> None:
        workflow = self.task_state_service.get(run_id=run_id) or {}
        progress_state["elapsed_seconds"] = self._compute_elapsed_seconds(progress_state=progress_state)
        rows_processed = int(progress_state.get("rows_processed") or 0)
        total_rows = int(progress_state.get("total_rows") or 0)
        total_unique_serials = int(progress_state.get("total_unique_serials") or 0)
        serials_processed = int(progress_state.get("serials_processed") or 0)
        percentage = round((serials_processed / max(1, total_unique_serials)) * 82.0, 1) if total_unique_serials > 0 else 0.0
        if phase == "leyendo_archivo":
            percentage = max(percentage, 3.0)
        elif phase == "normalizando_seriales":
            percentage = max(percentage, 8.0)
        elif phase == "enriqueciendo_movil_responsables":
            percentage = max(percentage, 88.0)
        elif phase == "generando_dashboard_final":
            percentage = max(percentage, 94.0)
        elif phase == "generando_export_csv":
            percentage = max(percentage, 97.0)
        elapsed_seconds = int(progress_state.get("elapsed_seconds") or 0)
        evidence = self._build_live_progress_snapshot(
            progress_state=progress_state,
            phase=phase,
            current_stage=current_stage,
            percentage=percentage,
        )
        artifact_id = str(progress_state.get("artifact_id") or "").strip()
        if artifact_id:
            evidence["artifact_id"] = artifact_id
        progress = {
            "rows_processed": rows_processed,
            "total_rows": total_rows,
            "progress_pct": percentage,
            "percentage": percentage,
            "phase": phase,
        }
        workflow = self.background_runtime_service.add_progress(
            workflow=workflow,
            message=self._build_progress_message(evidence=evidence),
            progress_pct=percentage,
            partial_evidence=evidence,
            status="running",
        )
        self.background_runtime_service.add_checkpoint(
            workflow=workflow,
            label=label,
            checkpoint_state={
                "rows_processed": rows_processed,
                "chunks_processed": int(progress_state.get("current_chunk") or 0),
                "total_chunks": int(progress_state.get("total_chunks") or 0),
            },
            progress=progress,
            evidence=evidence,
        )

    @staticmethod
    def _build_progress_message(*, evidence: dict[str, Any]) -> str:
        phase_label = str(evidence.get("phase_label") or evidence.get("phase") or "validacion").strip()
        serials_processed = int(evidence.get("stage_serials_processed") or evidence.get("serials_processed") or 0)
        serials_total = int(evidence.get("serials_unique_total") or evidence.get("stage_serials_total") or 0)
        active_chunk = int(evidence.get("active_chunk") or evidence.get("current_chunk") or 0)
        total_chunks = int(evidence.get("total_chunks") or 0)
        table_label = str(evidence.get("table_label") or "").strip()
        encontrados = int(evidence.get("found_so_far") or 0)
        pendientes = int(evidence.get("serials_pending") or 0)
        movil = int(evidence.get("movil_so_far") or 0)
        responsables = int(evidence.get("enriched_responsible_so_far") or 0)
        chunk_fragment = (
            f" Va por el chunk {active_chunk} de {total_chunks}."
            if active_chunk > 0 and total_chunks > 0
            else ""
        )
        table_fragment = f" Tabla actual: {table_label}." if table_label else ""
        return (
            f"Validacion en curso en segundo plano. En la etapa actual van {serials_processed} de {serials_total} seriales unicos. "
            f"Globalmente se han encontrado {encontrados} coincidencias y {pendientes} siguen pendientes, "
            f"{movil} estan en MOVIL y {responsables} tienen responsable enriquecido. "
            f"La fase actual es {phase_label.lower()}.{table_fragment}{chunk_fragment}"
        )

    @staticmethod
    def _sorted_rows(rows_by_index: dict[int, dict[str, Any]]) -> list[dict[str, Any]]:
        return [rows_by_index[key] for key in sorted(rows_by_index.keys())]

    def _materialize_rows(self, *, runtime_state: dict[str, Any]) -> list[dict[str, Any]]:
        rows = list(runtime_state.get("rows") or [])
        if rows:
            return rows
        rows_by_index = dict(runtime_state.get("rows_by_index") or {})
        if not rows_by_index:
            return []
        return self._sorted_rows(rows_by_index)

    @staticmethod
    def _build_progress_state(
        *,
        total_rows: int,
        total_chunks: int,
        attachment_name: str,
        total_unique_serials: int,
        rowcount_by_serial: dict[str, int],
    ) -> dict[str, Any]:
        return {
            "rows_processed": 0,
            "total_rows": total_rows,
            "total_chunks": total_chunks,
            "current_chunk": 0,
            "total_unique_serials": total_unique_serials,
            "serials_processed": 0,
            "serials_pending": total_unique_serials,
            "stage_serials_total": total_unique_serials,
            "stage_serials_processed": 0,
            "stage_serials_pending": total_unique_serials,
            "phase_label": "",
            "found_so_far": 0,
            "not_found_so_far": 0,
            "movil_so_far": 0,
            "enriched_responsible_so_far": 0,
            "rows_with_errors": 0,
            "artifact_id": "",
            "attachment_name": attachment_name,
            "found_in_base_actual": 0,
            "found_in_asociados_actual": 0,
            "found_in_historico": 0,
            "table_label": "",
            "table_serials_total": 0,
            "table_serials_pending": 0,
            "table_chunk_total": 0,
            "active_chunk": 0,
            "chunk_size": 0,
            "requested_chunk_size": 0,
            "normalized_fallback_mode": "",
            "_rowcount_by_serial": dict(rowcount_by_serial),
            "_processed_serials": set(),
            "_found_base_actual": set(),
            "_found_asociados_actual": set(),
            "_found_historico": set(),
            "_movil_serials": set(),
            "_enriched_serials": set(),
            "performance_metrics": {},
            "last_chunk_metrics": {},
            "_started_at_monotonic": datetime.now(timezone.utc).timestamp(),
            "_started_at_iso": datetime.now(timezone.utc).isoformat(),
            "last_progress_update_at": "",
        }

    @staticmethod
    def _update_progress_state(
        *,
        progress_state: dict[str, Any],
        processed_serials: list[str],
        found_serials: set[str],
        pending_serials: list[str],
        current_chunk: int,
        stage_key: str,
    ) -> None:
        progress_state["current_chunk"] = current_chunk
        rowcount_by_serial = dict(progress_state.get("_rowcount_by_serial") or {})
        processed_so_far = set(progress_state.get("_processed_serials") or set())
        new_processed = [
            serial for serial in processed_serials if serial and serial not in processed_so_far
        ]
        processed_so_far.update(new_processed)
        progress_state["_processed_serials"] = processed_so_far
        progress_state["serials_processed"] = len(processed_so_far)
        progress_state["rows_processed"] = sum(
            int(rowcount_by_serial.get(serial) or 0)
            for serial in processed_so_far
        )
        progress_state["stage_serials_processed"] = int(progress_state.get("stage_serials_processed") or 0) + len(
            processed_serials
        )
        progress_state["stage_serials_pending"] = max(
            0,
            int(progress_state.get("stage_serials_total") or 0)
            - int(progress_state.get("stage_serials_processed") or 0),
        )
        progress_state["serials_pending"] = len([serial for serial in pending_serials if serial])
        if stage_key == "base_actual":
            found_base = set(progress_state.get("_found_base_actual") or set())
            found_base.update(found_serials)
            progress_state["_found_base_actual"] = found_base
            progress_state["found_in_base_actual"] = len(found_base)
        elif stage_key == "asociados_actual":
            found_assoc = set(progress_state.get("_found_asociados_actual") or set())
            found_assoc.update(found_serials)
            progress_state["_found_asociados_actual"] = found_assoc
            progress_state["found_in_asociados_actual"] = len(found_assoc)
        elif stage_key in {"backup_base", "backup_asociados"}:
            found_hist = set(progress_state.get("_found_historico") or set())
            found_hist.update(found_serials)
            progress_state["_found_historico"] = found_hist
            progress_state["found_in_historico"] = len(found_hist)
        progress_state["found_so_far"] = (
            int(progress_state.get("found_in_base_actual") or 0)
            + int(progress_state.get("found_in_asociados_actual") or 0)
            + int(progress_state.get("found_in_historico") or 0)
        )

    @classmethod
    def _resolve_chunk_size(
        cls,
        *,
        requested_chunk_size: int,
        total_unique_serials: int,
    ) -> int:
        requested = max(1, min(int(requested_chunk_size or cls.DEFAULT_CHUNK_SIZE), cls.SAFE_MAX_CHUNK_SIZE))
        if requested != cls.DEFAULT_CHUNK_SIZE:
            return requested
        if total_unique_serials >= 5000:
            return 1800
        if total_unique_serials >= 3000:
            return 1600
        if total_unique_serials >= 1500:
            return 1200
        return requested

    @staticmethod
    def _init_performance_metrics(
        *,
        requested_chunk_size: int,
        effective_chunk_size: int,
        total_unique_serials: int,
    ) -> dict[str, Any]:
        return {
            "requested_chunk_size": int(requested_chunk_size or 0),
            "effective_chunk_size": int(effective_chunk_size or 0),
            "total_unique_serials": int(total_unique_serials or 0),
            "normalized_fallback_mode": "disabled_for_large_background",
            "query_count_total": 0,
            "sql_time_ms_total": 0.0,
            "rows_returned_total": 0,
            "stages": [],
            "chunks": [],
        }

    @staticmethod
    def _build_stage_table_label(*, stage_label: str, tables: list[dict[str, Any]]) -> str:
        normalized_label = str(stage_label or "").strip()
        table_count = len(list(tables or []))
        if table_count <= 1:
            return normalized_label
        return f"{normalized_label} ({table_count} tablas en union)"

    @staticmethod
    def _compute_elapsed_seconds(*, progress_state: dict[str, Any]) -> int:
        started_at = float(progress_state.get("_started_at_monotonic") or 0.0)
        if started_at <= 0:
            return int(progress_state.get("elapsed_seconds") or 0)
        return max(0, int(datetime.now(timezone.utc).timestamp() - started_at))

    @classmethod
    def _record_runtime_chunk_metrics(
        cls,
        *,
        progress_state: dict[str, Any],
        stage_key: str,
        stage_label: str,
        table_label: str,
        chunk_index: int,
        input_serials: int,
        found_serials: int,
        pending_after_stage: int,
        query_count: int,
        sql_time_ms: float,
        rows_returned: int,
        union_stage: bool,
        table_metrics: list[dict[str, Any]],
        chunk_duration_ms: float = 0.0,
    ) -> None:
        performance_metrics = dict(progress_state.get("performance_metrics") or {})
        chunks = list(performance_metrics.get("chunks") or [])
        chunk_payload = {
            "stage_key": stage_key,
            "stage_label": stage_label,
            "table_label": table_label,
            "chunk_index": int(chunk_index or 0),
            "global_chunk": int(progress_state.get("current_chunk") or 0),
            "input_serials": int(input_serials or 0),
            "found_serials": int(found_serials or 0),
            "pending_after_stage": int(pending_after_stage or 0),
            "query_count": int(query_count or 0),
            "sql_time_ms": round(float(sql_time_ms or 0.0), 2),
            "chunk_duration_ms": round(float(chunk_duration_ms or 0.0), 2),
            "rows_returned": int(rows_returned or 0),
            "union_stage": bool(union_stage),
            "table_metrics": list(table_metrics or []),
        }
        chunks.append(chunk_payload)
        performance_metrics["chunks"] = chunks
        performance_metrics["query_count_total"] = int(performance_metrics.get("query_count_total") or 0) + int(
            query_count or 0
        )
        performance_metrics["sql_time_ms_total"] = round(
            float(performance_metrics.get("sql_time_ms_total") or 0.0) + float(sql_time_ms or 0.0),
            2,
        )
        performance_metrics["rows_returned_total"] = int(performance_metrics.get("rows_returned_total") or 0) + int(
            rows_returned or 0
        )
        progress_state["performance_metrics"] = performance_metrics
        progress_state["last_chunk_metrics"] = chunk_payload

    @staticmethod
    def _summarize_performance_metrics(*, performance_metrics: dict[str, Any]) -> dict[str, Any]:
        metrics = dict(performance_metrics or {})
        stages = list(metrics.get("stages") or [])
        chunks = list(metrics.get("chunks") or [])
        summary = {
            "requested_chunk_size": int(metrics.get("requested_chunk_size") or 0),
            "effective_chunk_size": int(metrics.get("effective_chunk_size") or 0),
            "total_unique_serials": int(metrics.get("total_unique_serials") or 0),
            "normalized_fallback_mode": str(metrics.get("normalized_fallback_mode") or ""),
            "query_count_total": int(metrics.get("query_count_total") or 0),
            "sql_time_ms_total": round(float(metrics.get("sql_time_ms_total") or 0.0), 2),
            "rows_returned_total": int(metrics.get("rows_returned_total") or 0),
            "stage_count": len(stages),
            "chunk_count": len(chunks),
        }
        if stages:
            summary["last_stage"] = dict(stages[-1])
        return summary

    @classmethod
    def _build_live_progress_snapshot(
        cls,
        *,
        progress_state: dict[str, Any],
        phase: str,
        current_stage: str,
        percentage: float,
    ) -> dict[str, Any]:
        now_iso = datetime.now(timezone.utc).isoformat()
        progress_state["last_progress_update_at"] = now_iso
        elapsed_seconds = int(progress_state.get("elapsed_seconds") or cls._compute_elapsed_seconds(progress_state=progress_state))
        eta_seconds = 0
        if percentage > 0 and percentage < 100 and elapsed_seconds > 0:
            eta_seconds = max(0, int((elapsed_seconds / percentage) * (100 - percentage)))
        last_chunk_metrics = dict(progress_state.get("last_chunk_metrics") or {})
        return {
            "rows_processed": int(progress_state.get("rows_processed") or 0),
            "total_rows": int(progress_state.get("total_rows") or 0),
            "total_estimated": int(progress_state.get("total_rows") or 0),
            "percentage": round(float(percentage or 0.0), 1),
            "phase": phase,
            "phase_label": str(progress_state.get("phase_label") or ""),
            "current_stage": current_stage,
            "result_kind": "partial",
            "result_label": "Resultado parcial",
            "chunks_processed": int(progress_state.get("current_chunk") or 0),
            "total_chunks": int(progress_state.get("total_chunks") or 0),
            "current_chunk": int(progress_state.get("current_chunk") or 0),
            "encontrados_parciales": int(progress_state.get("found_so_far") or 0),
            "no_encontrados_parciales": int(progress_state.get("not_found_so_far") or 0),
            "movil_detectados_parciales": int(progress_state.get("movil_so_far") or 0),
            "errores_parciales": int(progress_state.get("rows_with_errors") or 0),
            "serials_unique_total": int(progress_state.get("total_unique_serials") or 0),
            "serials_processed": int(progress_state.get("serials_processed") or 0),
            "serials_pending": int(progress_state.get("serials_pending") or 0),
            "stage_serials_total": int(progress_state.get("stage_serials_total") or 0),
            "stage_serials_processed": int(progress_state.get("stage_serials_processed") or 0),
            "stage_serials_pending": int(progress_state.get("stage_serials_pending") or 0),
            "found_so_far": int(progress_state.get("found_so_far") or 0),
            "not_found_so_far": int(progress_state.get("not_found_so_far") or 0),
            "movil_so_far": int(progress_state.get("movil_so_far") or 0),
            "enriched_responsible_so_far": int(progress_state.get("enriched_responsible_so_far") or 0),
            "found_in_base_actual": int(progress_state.get("found_in_base_actual") or 0),
            "found_in_asociados_actual": int(progress_state.get("found_in_asociados_actual") or 0),
            "found_in_historico": int(progress_state.get("found_in_historico") or 0),
            "table_label": str(progress_state.get("table_label") or ""),
            "table_serials_total": int(progress_state.get("table_serials_total") or 0),
            "table_serials_pending": int(progress_state.get("table_serials_pending") or 0),
            "table_chunk_total": int(progress_state.get("table_chunk_total") or 0),
            "active_chunk": int(progress_state.get("active_chunk") or 0),
            "attachment_name": str(progress_state.get("attachment_name") or ""),
            "elapsed_seconds": elapsed_seconds,
            "eta_seconds": eta_seconds,
            "chunk_size": int(progress_state.get("chunk_size") or 0),
            "requested_chunk_size": int(progress_state.get("requested_chunk_size") or 0),
            "normalized_fallback_mode": str(progress_state.get("normalized_fallback_mode") or ""),
            "last_chunk_metrics": last_chunk_metrics,
            "chunk_duration_ms": round(float(last_chunk_metrics.get("chunk_duration_ms") or 0.0), 2),
            "last_progress_update_at": now_iso,
            "started_at": str(progress_state.get("_started_at_iso") or ""),
            "performance_metrics": cls._summarize_performance_metrics(
                performance_metrics=dict(progress_state.get("performance_metrics") or {})
            ),
        }

    @staticmethod
    def _record_stage_metrics(
        *,
        progress_state: dict[str, Any],
        stage_key: str,
        stage_label: str,
        input_serials: int,
        found_serials: int,
        pending_after_stage: int,
        query_count: int,
        sql_time_ms: float,
        rows_returned: int,
        table_count: int,
    ) -> None:
        performance_metrics = dict(progress_state.get("performance_metrics") or {})
        stages = list(performance_metrics.get("stages") or [])
        stages.append(
            {
                "stage_key": stage_key,
                "stage_label": stage_label,
                "input_serials": int(input_serials or 0),
                "found_serials": int(found_serials or 0),
                "pending_after_stage": int(pending_after_stage or 0),
                "query_count": int(query_count or 0),
                "sql_time_ms": round(float(sql_time_ms or 0.0), 2),
                "rows_returned": int(rows_returned or 0),
                "table_count": int(table_count or 0),
            }
        )
        performance_metrics["stages"] = stages
        progress_state["performance_metrics"] = performance_metrics

    def _should_persist_partial_artifact(
        self,
        *,
        progress_state: dict[str, Any],
        current_chunk: int,
    ) -> bool:
        total_chunks = int(progress_state.get("total_chunks") or 0)
        rows_processed = int(progress_state.get("rows_processed") or 0)
        return (
            current_chunk >= total_chunks
            or current_chunk % self.PARTIAL_ARTIFACT_INTERVAL_CHUNKS == 0
            or rows_processed % self.PARTIAL_ARTIFACT_INTERVAL_ROWS == 0
        )

    def _fail_missing_background_request(self, *, workflow: dict[str, Any], reason: str) -> None:
        state = dict((workflow or {}).get("state") or {})
        background = dict(state.get("background") or {})
        request = dict(state.get("background_request") or {})
        attachment_name = str((request.get("attachment") or {}).get("name") or request.get("attachment_name") or "")
        payload = build_chat_response_snapshot()
        payload["session_id"] = str(state.get("session_id") or "")
        payload["reply"] = reason
        payload["orchestrator"] = {
            "intent": self.CAPABILITY_ID,
            "domain": "inventario_logistica",
            "selected_agent": "inventory_agent",
            "classifier_source": "background_runtime",
            "needs_database": True,
            "output_mode": "summary",
            "used_tools": [self.CAPABILITY_ID],
        }
        payload["data"] = {
            "kpis": {},
            "series": [],
            "labels": [],
            "insights": [reason],
            "table": {"columns": [], "rows": [], "rowcount": 0},
            "meta": {
                "background_job": {
                    "status": "failed",
                    "background_run_id": str(background.get("background_run_id") or ""),
                    "job_id": str(background.get("job_id") or ""),
                    "phase": "failed",
                    "rows_processed": 0,
                    "total_estimated": 0,
                    "percentage": 0.0,
                    "attachment_name": attachment_name,
                    "failure_reason": reason,
                }
            },
        }
        self.background_runtime_service.fail_run(
            workflow=workflow,
            failure_reason=reason,
            final_evidence={
                "phase": "failed",
                "rows_processed": 0,
                "total_rows": 0,
                "total_estimated": 0,
                "percentage": 0.0,
                "current_stage": "failed",
                "result_kind": "partial",
                "result_label": "Resultado parcial",
                "failure_reason": reason,
                "attachment_name": attachment_name,
                "current_chunk": 0,
                "total_chunks": 0,
                "found_so_far": 0,
                "not_found_so_far": 0,
                "movil_so_far": 0,
                "enriched_responsible_so_far": 0,
            },
            response_snapshot=ensure_chat_response_contract(payload),
        )

    def _release_run(self, run_id: str) -> None:
        normalized_run_id = str(run_id or "").strip()
        if not normalized_run_id:
            return
        with self._lock:
            self._active_runs.discard(normalized_run_id)

    @classmethod
    def _spool_dir(cls) -> Path:
        return Path(__file__).resolve().parents[4] / cls.ATTACHMENT_SPOOL_DIR

    def _compact_background_request(
        self,
        *,
        run_id: str,
        request: dict[str, Any],
    ) -> dict[str, Any]:
        attachment = dict(request.get("attachment") or {})
        encoded = str(attachment.get("content_base64") or "").strip()
        if not encoded:
            return attachment
        spool_dir = self._spool_dir()
        spool_dir.mkdir(parents=True, exist_ok=True)
        filename = str(attachment.get("name") or f"{run_id}.bin").strip() or f"{run_id}.bin"
        spool_path = spool_dir / f"{run_id}_{Path(filename).name}"
        if not spool_path.exists():
            content = ValidadorSerialesProveedorService()._decode_attachment(encoded=encoded)
            spool_path.write_bytes(content)
        compact_attachment = {
            **attachment,
            "content_base64": "",
            "spooled_path": str(spool_path),
            "size": int(attachment.get("size") or spool_path.stat().st_size),
        }
        compact_request = {
            **request,
            "attachment": compact_attachment,
        }
        self.task_state_service.update_state(
            run_id=run_id,
            extra_state={"background_request": compact_request},
        )
        return {
            **attachment,
            "spooled_path": str(spool_path),
        }
