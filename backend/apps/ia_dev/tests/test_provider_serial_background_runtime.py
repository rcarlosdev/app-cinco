from __future__ import annotations

import base64
from unittest.mock import patch

from django.test import SimpleTestCase

from apps.ia_dev.application.context.run_context import RunContext
from apps.ia_dev.application.orchestration.chat_application_service import ChatApplicationService
from apps.ia_dev.application.runtime.background_runtime_service import BackgroundRuntimeService
from apps.ia_dev.application.runtime.provider_serial_background_runtime import (
    ProviderSerialBackgroundRuntime,
)
from apps.ia_dev.application.workflow.task_state_service import TaskStateService
from apps.ia_dev.tests.test_task_state_service import _FakeWorkflowRepo


def _build_attachment_csv() -> dict[str, str]:
    content = "serial\nSER-001\nSER-002\nSER-003\nSER-004\n".encode("utf-8")
    return {
        "name": "provider_serials.csv",
        "mime_type": "text/csv",
        "content_base64": base64.b64encode(content).decode("ascii"),
    }


def _build_large_attachment_csv(*, total: int = 5000) -> dict[str, str]:
    rows = ["serial", *[f"SN-{index:04d}" for index in range(total)]]
    content = ("\n".join(rows) + "\n").encode("utf-8")
    return {
        "name": f"provider_serials_{total}.csv",
        "mime_type": "text/csv",
        "content_base64": base64.b64encode(content).decode("ascii"),
    }


def _background_discovery() -> dict[str, list[dict[str, object]]]:
    return {
        "existing_tables": [
            {
                "schema": "logistica_cinco",
                "table": "logistica_base_seriales",
                "kind": "base_actual",
                "label": "base actual",
                "fqn": "logistica_cinco.logistica_base_seriales",
                "year": None,
                "columns": ["serial"],
            }
        ],
        "missing_tables": [],
    }


class ProviderSerialBackgroundRuntimeTests(SimpleTestCase):
    def setUp(self) -> None:
        self.repo = _FakeWorkflowRepo()
        self.task_state_service = TaskStateService(repo=self.repo)
        self.background_runtime_service = BackgroundRuntimeService(
            task_state_service=self.task_state_service,
        )
        self.runner = ProviderSerialBackgroundRuntime(
            task_state_service=self.task_state_service,
            background_runtime_service=self.background_runtime_service,
        )

    def _seed_workflow(
        self,
        *,
        fail_after_chunks: int = 0,
        chunk_size: int = 2,
        attachment: dict[str, str] | None = None,
    ) -> str:
        run_context = RunContext.create(
            message="Valida este archivo del proveedor",
            session_id="sess-bg-provider",
            reset_memory=False,
        )
        request = {
            "capability_id": "inventory_provider_serial_validation",
            "message": run_context.message,
            "session_id": run_context.session_id,
            "chunk_size": chunk_size,
            "fail_after_chunks": fail_after_chunks,
            "attachment": attachment or _build_attachment_csv(),
        }
        run_context.metadata["background_runtime"] = {"request": request}
        runtime_state = self.background_runtime_service.queue_run(
            run_context=run_context,
            tool_id="inventory_provider_serial_validation",
            policy_reason="tool_declares_background",
            partial_evidence={
                "phase": "archivo_encolado",
                "rows_processed": 0,
                "percentage": 0,
                "result_kind": "partial",
                "result_label": "Resultado parcial",
            },
        )
        self.task_state_service.save(
            run_id=run_context.run_id,
            status="queued",
            original_question=run_context.message,
            detected_domain="inventario_logistica",
            extra_state={
                **runtime_state,
                "background_request": request,
            },
        )
        return run_context.run_id

    @patch(
        "apps.ia_dev.domains.inventario_logistica.validador_seriales_proveedor.ValidadorSerialesProveedorService._discover_tables",
        side_effect=lambda *args, **kwargs: _background_discovery(),
    )
    @patch(
        "apps.ia_dev.domains.inventario_logistica.validador_seriales_proveedor.ValidadorSerialesProveedorService._enrich_personal",
        return_value=[],
    )
    @patch(
        "apps.ia_dev.domains.inventario_logistica.validador_seriales_proveedor.ValidadorSerialesProveedorService._query_table",
        return_value=[],
    )
    def test_executes_background_run_with_chunk_checkpoints(
        self,
        *_mocks,
    ) -> None:
        run_id = self._seed_workflow()

        self.runner.execute_provider_serial_validation_run(run_id=run_id)

        workflow = self.task_state_service.get(run_id=run_id) or {}
        state = dict((workflow or {}).get("state") or {})
        background = dict(state.get("background") or {})
        response_snapshot = dict(state.get("response_snapshot") or {})
        table = dict((dict(response_snapshot.get("data") or {}).get("table") or {}))

        self.assertEqual(str(background.get("run_status") or ""), "completed")
        self.assertGreaterEqual(len(list(state.get("checkpoints") or [])), 2)
        self.assertEqual(int((dict(background.get("final_evidence") or {}).get("rows_processed") or 0)), 4)
        self.assertEqual(str((dict(background.get("final_evidence") or {}).get("result_label") or "")), "Resultado final")
        self.assertEqual(str((dict(background.get("final_evidence") or {}).get("phase_label") or "")), "Completado")
        self.assertEqual(str((dict(background.get("final_evidence") or {}).get("table_label") or "")), "")
        self.assertEqual(int((dict(background.get("final_evidence") or {}).get("current_chunk") or 0)), 2)
        self.assertEqual(int((dict(background.get("final_evidence") or {}).get("total_chunks") or 0)), 2)
        self.assertEqual(int((dict(background.get("final_evidence") or {}).get("found_so_far") or 0)), 0)
        self.assertEqual(int((dict(background.get("final_evidence") or {}).get("not_found_so_far") or 0)), 4)
        self.assertIn("performance_metrics", dict(background.get("final_evidence") or {}))
        self.assertEqual(int(table.get("rowcount") or 0), 4)
        self.assertTrue(bool(dict(table.get("export_artifact") or {}).get("artifact_id")))

    @patch(
        "apps.ia_dev.domains.inventario_logistica.validador_seriales_proveedor.ValidadorSerialesProveedorService._discover_tables",
        side_effect=lambda *args, **kwargs: _background_discovery(),
    )
    @patch(
        "apps.ia_dev.domains.inventario_logistica.validador_seriales_proveedor.ValidadorSerialesProveedorService._enrich_personal",
        return_value=[],
    )
    @patch(
        "apps.ia_dev.domains.inventario_logistica.validador_seriales_proveedor.ValidadorSerialesProveedorService._query_table",
        return_value=[],
    )
    def test_running_snapshot_keeps_progress_lightweight(self, *_mocks) -> None:
        run_id = self._seed_workflow(fail_after_chunks=1)

        self.runner.execute_provider_serial_validation_run(run_id=run_id)

        workflow = self.task_state_service.get(run_id=run_id) or {}
        state = dict((workflow or {}).get("state") or {})
        background = dict(state.get("background") or {})
        partial = dict(background.get("partial_evidence") or {})
        progress_snapshot = dict(background.get("progress_snapshot") or {})
        performance_metrics = dict(progress_snapshot.get("performance_metrics") or {})

        self.assertEqual(str(background.get("run_status") or ""), "failed")
        self.assertTrue(bool(str(background.get("last_progress_update_at") or "")))
        self.assertTrue(bool(str(progress_snapshot.get("last_progress_update_at") or "")))
        self.assertIn("chunk_duration_ms", progress_snapshot)
        self.assertIsInstance(dict(progress_snapshot.get("last_chunk_metrics") or {}), dict)
        self.assertNotIn("chunks", performance_metrics)
        self.assertNotIn("stages", performance_metrics)
        self.assertGreaterEqual(int(performance_metrics.get("chunk_count") or 0), 1)
        self.assertEqual(progress_snapshot, partial)

    @patch(
        "apps.ia_dev.domains.inventario_logistica.validador_seriales_proveedor.ValidadorSerialesProveedorService._discover_tables",
        side_effect=lambda *args, **kwargs: _background_discovery(),
    )
    @patch(
        "apps.ia_dev.domains.inventario_logistica.validador_seriales_proveedor.ValidadorSerialesProveedorService._enrich_personal",
        return_value=[],
    )
    @patch(
        "apps.ia_dev.domains.inventario_logistica.validador_seriales_proveedor.ValidadorSerialesProveedorService._query_table",
        return_value=[],
    )
    def test_failure_keeps_partial_evidence_and_partial_artifact(
        self,
        *_mocks,
    ) -> None:
        run_id = self._seed_workflow(fail_after_chunks=1)

        self.runner.execute_provider_serial_validation_run(run_id=run_id)

        workflow = self.task_state_service.get(run_id=run_id) or {}
        state = dict((workflow or {}).get("state") or {})
        background = dict(state.get("background") or {})
        response_snapshot = dict(state.get("response_snapshot") or {})
        table = dict((dict(response_snapshot.get("data") or {}).get("table") or {}))

        self.assertEqual(str(background.get("run_status") or ""), "failed")
        self.assertGreaterEqual(len(list(state.get("checkpoints") or [])), 1)
        self.assertEqual(str((dict(background.get("final_evidence") or {}).get("result_label") or "")), "Resultado parcial")
        self.assertTrue(bool(dict(table.get("export_artifact") or {}).get("artifact_id")))
        self.assertEqual(int((dict(background.get("final_evidence") or {}).get("rows_processed") or 0)), 2)

    def test_missing_background_request_fails_explicitly(self) -> None:
        run_context = RunContext.create(
            message="Valida este archivo del proveedor",
            session_id="sess-bg-provider-missing",
            reset_memory=False,
        )
        runtime_state = self.background_runtime_service.queue_run(
            run_context=run_context,
            tool_id="inventory_provider_serial_validation",
            policy_reason="tool_declares_background",
            partial_evidence={
                "phase": "archivo_encolado",
                "rows_processed": 0,
                "percentage": 0,
                "attachment_name": "seriales.xlsx",
            },
        )
        self.task_state_service.save(
            run_id=run_context.run_id,
            status="queued",
            original_question=run_context.message,
            detected_domain="inventario_logistica",
            extra_state=runtime_state,
        )

        scheduled = self.runner.schedule_if_needed(run_id=run_context.run_id)

        self.assertFalse(scheduled)
        workflow = self.task_state_service.get(run_id=run_context.run_id) or {}
        state = dict((workflow or {}).get("state") or {})
        background = dict(state.get("background") or {})
        self.assertEqual(str(background.get("run_status") or ""), "failed")
        self.assertEqual(str(background.get("failure_reason") or ""), "background_request sin adjunto")
        self.assertEqual(str((dict(background.get("final_evidence") or {}).get("failure_reason") or "")), "background_request sin adjunto")

    @patch(
        "apps.ia_dev.domains.inventario_logistica.validador_seriales_proveedor.ValidadorSerialesProveedorService._discover_tables"
    )
    def test_large_background_case_keeps_5k_counts_and_disables_normalized_fallback(
        self,
        discover_mock,
    ) -> None:
        discover_mock.return_value = {
            "existing_tables": [
                {
                    "schema": "logistica_cinco",
                    "table": "logistica_base_seriales",
                    "kind": "base_actual",
                    "label": "base actual",
                    "fqn": "logistica_cinco.logistica_base_seriales",
                    "year": None,
                    "columns": ["serial", "estado", "cedula", "movil", "bodega", "codigo", "descripcion", "fecha"],
                },
                {
                    "schema": "logistica_cinco",
                    "table": "logistica_seriales_asociados",
                    "kind": "asociados_actual",
                    "label": "asociados actual",
                    "fqn": "logistica_cinco.logistica_seriales_asociados",
                    "year": None,
                    "columns": ["serial", "estado", "cedula", "edit", "movil", "bodega", "codigo", "descripcion", "fecha"],
                },
                {
                    "schema": "z_c3nc4_f3sc1l",
                    "table": "logistica_base_seriales_2025",
                    "kind": "backup_base",
                    "label": "backup base seriales anio 2025",
                    "fqn": "z_c3nc4_f3sc1l.logistica_base_seriales_2025",
                    "year": 2025,
                    "columns": ["serial", "estado", "cedula", "movil", "bodega", "codigo", "descripcion", "fecha"],
                },
                {
                    "schema": "z_c3nc4_f3sc1l",
                    "table": "logistica_base_seriales_2024",
                    "kind": "backup_base",
                    "label": "backup base seriales anio 2024",
                    "fqn": "z_c3nc4_f3sc1l.logistica_base_seriales_2024",
                    "year": 2024,
                    "columns": ["serial", "estado", "cedula", "movil", "bodega", "codigo", "descripcion", "fecha"],
                },
                {
                    "schema": "z_c3nc4_f3sc1l",
                    "table": "logistica_seriales_asociados_2025",
                    "kind": "backup_asociados",
                    "label": "backup asociados anio 2025",
                    "fqn": "z_c3nc4_f3sc1l.logistica_seriales_asociados_2025",
                    "year": 2025,
                    "columns": ["serial", "estado", "cedula", "edit", "movil", "bodega", "codigo", "descripcion", "fecha"],
                },
                {
                    "schema": "z_c3nc4_f3sc1l",
                    "table": "logistica_seriales_asociados_2024",
                    "kind": "backup_asociados",
                    "label": "backup asociados anio 2024",
                    "fqn": "z_c3nc4_f3sc1l.logistica_seriales_asociados_2024",
                    "year": 2024,
                    "columns": ["serial", "estado", "cedula", "edit", "movil", "bodega", "codigo", "descripcion", "fecha"],
                },
            ],
            "missing_tables": [],
        }

        query_table_calls: list[tuple[str, bool]] = []
        union_calls: list[tuple[int, bool]] = []

        def _serial_index(value: str) -> int:
            return int(str(value).split("-")[-1])

        def _query_table_side_effect(*args, **kwargs):
            table = dict(kwargs.get("table") or {})
            label = str(table.get("label") or "")
            skip_probe = bool(kwargs.get("skip_noncanonical_probe"))
            query_table_calls.append((label, skip_probe))
            rows = []
            for serial in list(kwargs.get("normalized_serials") or []):
                index = _serial_index(serial)
                if label == "base actual" and index < 3000:
                    rows.append(
                        {
                            "serial_normalizado": serial,
                            "source_label": label,
                            "source_kind": "base_actual",
                            "source_table": "logistica_cinco.logistica_base_seriales",
                            "year": None,
                            "estado": "EN MOVIL" if index < 120 else "BODEGA",
                            "lote": "",
                            "cedula": str(100000 + index) if index < 120 else "",
                            "edit": "",
                            "movil": f"MOV-{index:03d}" if index < 120 else "",
                            "bodega": "BOD-A",
                            "codigo": f"COD-{index:04d}",
                            "descripcion": "Equipo base",
                            "fecha": "2026-05-01 10:00:00",
                        }
                    )
                elif label == "asociados actual" and 3000 <= index < 4000:
                    rows.append(
                        {
                            "serial_normalizado": serial,
                            "source_label": label,
                            "source_kind": "asociados_actual",
                            "source_table": "logistica_cinco.logistica_seriales_asociados",
                            "year": None,
                            "estado": "ASOCIADO_MOVIL" if index < 4090 else "ASOCIADO",
                            "lote": "",
                            "cedula": f"OT-{index}" if index < 4090 else "",
                            "edit": str(200000 + index) if index < 4090 else "",
                            "movil": f"MOV-A-{index:03d}" if index < 4090 else "",
                            "bodega": "BOD-B",
                            "codigo": f"COD-{index:04d}",
                            "descripcion": "Equipo asociado",
                            "fecha": "2026-05-02 10:00:00",
                        }
                    )
            lookup_metrics = kwargs.get("lookup_metrics")
            if isinstance(lookup_metrics, dict):
                lookup_metrics.update(
                    {
                        "query_count": 1,
                        "sql_time_ms": 9.75,
                        "rows_returned": len(rows),
                        "chunk_count": 1,
                    }
                )
            return rows

        def _query_union_stage_side_effect(*args, **kwargs):
            tables = list(kwargs.get("tables") or [])
            normalized_serials = list(kwargs.get("normalized_serials") or [])
            union_calls.append((len(tables), bool(kwargs.get("skip_noncanonical_probe"))))
            rows = []
            kinds = {str(item.get("kind") or "") for item in tables}
            for serial in normalized_serials:
                index = _serial_index(serial)
                if "backup_base" in kinds and 4000 <= index < 4300:
                    rows.append(
                        {
                            "serial_normalizado": serial,
                            "source_label": "backup base seriales anio 2025" if index % 2 == 0 else "backup base seriales anio 2024",
                            "source_kind": "backup_base",
                            "source_table": "z_c3nc4_f3sc1l.logistica_base_seriales_2025" if index % 2 == 0 else "z_c3nc4_f3sc1l.logistica_base_seriales_2024",
                            "year": 2025 if index % 2 == 0 else 2024,
                            "estado": "MOVIL HISTORICO" if index < 4040 else "HISTORICO",
                            "lote": "",
                            "cedula": str(300000 + index) if index < 4040 else "",
                            "edit": "",
                            "movil": f"MOV-H-{index:03d}" if index < 4040 else "",
                            "bodega": "BOD-H",
                            "codigo": f"COD-{index:04d}",
                            "descripcion": "Equipo historico base",
                            "fecha": "2025-12-31 10:00:00",
                        }
                    )
                elif "backup_asociados" in kinds and 4300 <= index < 4493:
                    rows.append(
                        {
                            "serial_normalizado": serial,
                            "source_label": "backup asociados anio 2025" if index % 2 == 0 else "backup asociados anio 2024",
                            "source_kind": "backup_asociados",
                            "source_table": "z_c3nc4_f3sc1l.logistica_seriales_asociados_2025" if index % 2 == 0 else "z_c3nc4_f3sc1l.logistica_seriales_asociados_2024",
                            "year": 2025 if index % 2 == 0 else 2024,
                            "estado": "ASOCIADO_MOVIL HIST" if index < 4323 else "ASOCIADO HISTORICO",
                            "lote": "",
                            "cedula": f"OT-H-{index}" if index < 4323 else "",
                            "edit": str(400000 + index) if index < 4323 else "",
                            "movil": f"MOV-HA-{index:03d}" if index < 4323 else "",
                            "bodega": "BOD-HA",
                            "codigo": f"COD-{index:04d}",
                            "descripcion": "Equipo historico asociado",
                            "fecha": "2025-11-30 10:00:00",
                        }
                    )
            lookup_metrics = kwargs.get("lookup_metrics")
            if isinstance(lookup_metrics, dict):
                lookup_metrics.update(
                    {
                        "query_count": 1,
                        "sql_time_ms": 15.5,
                        "rows_returned": len(rows),
                        "table_count": len(tables),
                        "table_metrics": [
                            {
                                "label": str(table.get("label") or ""),
                                "table_fqn": str(table.get("fqn") or ""),
                                "rows_returned": len(rows),
                                "rows_kept": len(rows),
                            }
                            for table in tables
                        ],
                    }
                )
            return rows

        def _enrich_personal_side_effect(*args, **kwargs):
            results = []
            seen = set()
            for match in list(kwargs.get("matches") or []):
                for candidate in (str(match.get("cedula") or ""), str(match.get("edit") or "")):
                    if not candidate or candidate in seen or not candidate.isdigit():
                        continue
                    seen.add(candidate)
                    results.append(
                        {
                            "cedula": candidate,
                            "nombre": "TEC",
                            "apellido": candidate[-3:],
                            "empleado": f"TEC {candidate[-3:]}",
                            "movil": str(match.get("movil") or ""),
                        }
                    )
            return results

        with patch(
            "apps.ia_dev.domains.inventario_logistica.validador_seriales_proveedor.ValidadorSerialesProveedorService._query_table",
            side_effect=_query_table_side_effect,
        ), patch(
            "apps.ia_dev.domains.inventario_logistica.validador_seriales_proveedor.ValidadorSerialesProveedorService._query_tables_union_stage",
            side_effect=_query_union_stage_side_effect,
        ), patch(
            "apps.ia_dev.domains.inventario_logistica.validador_seriales_proveedor.ValidadorSerialesProveedorService._enrich_personal",
            side_effect=_enrich_personal_side_effect,
        ):
            run_id = self._seed_workflow(
                chunk_size=1000,
                attachment=_build_large_attachment_csv(total=5000),
            )
            self.runner.execute_provider_serial_validation_run(run_id=run_id)

        workflow = self.task_state_service.get(run_id=run_id) or {}
        state = dict((workflow or {}).get("state") or {})
        background = dict(state.get("background") or {})
        response_snapshot = dict(state.get("response_snapshot") or {})
        kpis = dict((dict(response_snapshot.get("data") or {}).get("kpis") or {}))
        final_evidence = dict(background.get("final_evidence") or {})
        performance_metrics = dict(final_evidence.get("performance_metrics") or {})

        self.assertEqual(str(background.get("run_status") or ""), "completed")
        self.assertEqual(int(kpis.get("encontrados_unicos") or 0), 4493)
        self.assertEqual(int(kpis.get("no_encontrados_unicos") or 0), 507)
        self.assertEqual(int(kpis.get("fuente_final_base_actual") or 0), 3000)
        self.assertEqual(int(kpis.get("fuente_final_asociados_actual") or 0), 1000)
        self.assertEqual(int(kpis.get("fuente_final_historico") or 0), 493)
        self.assertGreater(int(kpis.get("moviles_detectados") or 0), 0)
        self.assertGreater(int(kpis.get("moviles_con_responsable_enriquecido") or 0), 0)
        self.assertTrue(query_table_calls)
        self.assertTrue(all(skip_probe for _, skip_probe in query_table_calls))
        self.assertTrue(union_calls)
        self.assertTrue(all(skip_probe for _, skip_probe in union_calls))
        self.assertEqual(int(final_evidence.get("chunk_size") or 0), 1800)
        self.assertEqual(str(final_evidence.get("normalized_fallback_mode") or ""), "disabled_for_large_background")
        self.assertGreater(int(performance_metrics.get("query_count_total") or 0), 0)
        self.assertGreater(float(performance_metrics.get("sql_time_ms_total") or 0.0), 0.0)

    def test_background_uses_union_lookup_for_backup_stages(self) -> None:
        def _discovery_with_backups(*args, **kwargs):
            return {
                "existing_tables": [
                    {
                        "schema": "logistica_cinco",
                        "table": "logistica_base_seriales",
                        "kind": "base_actual",
                        "label": "base actual",
                        "fqn": "logistica_cinco.logistica_base_seriales",
                        "year": None,
                        "columns": ["serial"],
                    },
                    {
                        "schema": "z_c3nc4_f3sc1l",
                        "table": "logistica_base_seriales_2025",
                        "kind": "backup_base",
                        "label": "backup base seriales anio 2025",
                        "fqn": "z_c3nc4_f3sc1l.logistica_base_seriales_2025",
                        "year": 2025,
                        "columns": ["serial"],
                    },
                    {
                        "schema": "z_c3nc4_f3sc1l",
                        "table": "logistica_base_seriales_2024",
                        "kind": "backup_base",
                        "label": "backup base seriales anio 2024",
                        "fqn": "z_c3nc4_f3sc1l.logistica_base_seriales_2024",
                        "year": 2024,
                        "columns": ["serial"],
                    },
                ],
                "missing_tables": [],
            }

        with patch(
            "apps.ia_dev.domains.inventario_logistica.validador_seriales_proveedor.ValidadorSerialesProveedorService._discover_tables",
            side_effect=_discovery_with_backups,
        ), patch(
            "apps.ia_dev.domains.inventario_logistica.validador_seriales_proveedor.ValidadorSerialesProveedorService._enrich_personal",
            return_value=[],
        ), patch(
            "apps.ia_dev.domains.inventario_logistica.validador_seriales_proveedor.ValidadorSerialesProveedorService._query_table",
            return_value=[],
        ) as table_mock, patch(
            "apps.ia_dev.domains.inventario_logistica.validador_seriales_proveedor.ValidadorSerialesProveedorService._query_tables_union_stage",
            return_value=[],
        ) as union_mock:
            run_id = self._seed_workflow()
            self.runner.execute_provider_serial_validation_run(run_id=run_id)

        self.assertGreaterEqual(table_mock.call_count, 1)
        self.assertEqual(union_mock.call_count, 2)


class ChatApplicationBackgroundResponseTests(SimpleTestCase):
    def test_background_queued_response_keeps_specific_reply_and_semantic_state(self) -> None:
        service = ChatApplicationService()

        payload = service._build_background_queued_response(
            message="Valida los seriales adjuntos, dados por el proveedor",
            session_id="sess-provider-bg",
            planned_capability={
                "capability_id": "inventory_provider_serial_validation",
                "source": {
                    "domain": "inventario_logistica",
                    "intent": "inventory_provider_serial_validation",
                    "selected_agent": "inventario_logistica_agent",
                    "needs_database": True,
                },
            },
            capability_result={
                "meta": {
                    "tool_id": "inventory_provider_serial_validation",
                    "background": {
                        "tool_id": "inventory_provider_serial_validation",
                        "background_run_id": "bg-provider-init",
                        "run_status": "queued",
                        "partial_evidence": {
                            "phase": "archivo_encolado",
                            "attachment_name": "validacion seriales.xlsx",
                            "rows_processed": 0,
                            "total_rows": 0,
                            "percentage": 0.0,
                        },
                    },
                }
            },
        )

        self.assertIn("validacion seriales.xlsx", str(payload.get("reply") or "").lower())
        self.assertIn("segundo plano", str(payload.get("reply") or "").lower())
        current_run = dict(((payload.get("task") or {}).get("current_run") or {}))
        self.assertEqual(str(current_run.get("status") or ""), "queued")
        semantic = dict(current_run.get("semantic_explanation") or {})
        self.assertEqual(str(semantic.get("selected_capability") or ""), "inventory_provider_serial_validation")
        self.assertEqual(str(semantic.get("planner_route_hint") or ""), "inventory.serial.validation.provider_file")

    def test_background_status_payload_does_not_expose_partial_table_as_final(self) -> None:
        repo = _FakeWorkflowRepo()
        task_state_service = TaskStateService(repo=repo)
        service = ChatApplicationService(task_state_service=task_state_service)
        run_context = RunContext.create(
            message="Valida este archivo del proveedor",
            session_id="sess-task-status-provider",
            reset_memory=False,
        )
        task_state_service.save(
            run_id=run_context.run_id,
            status="running",
            original_question=run_context.message,
            detected_domain="inventario_logistica",
            extra_state={
                "background": {
                    "tool_id": "inventory_provider_serial_validation",
                    "background_run_id": "bg-provider-1",
                    "run_status": "running",
                    "partial_evidence": {
                        "phase": "procesando_chunks",
                        "attachment_name": "validacion seriales.xlsx",
                        "rows_processed": 2,
                        "total_rows": 10,
                        "percentage": 20.0,
                    },
                },
            },
        )

        payload = service.build_task_status_response(background_run_id="bg-provider-1")

        self.assertIsNotNone(payload)
        self.assertEqual(list((dict((payload or {}).get("data") or {}).get("table") or {}).get("rows") or []), [])
        self.assertEqual(list((payload or {}).get("trace") or []), [])
        current_run = dict((((payload or {}).get("task") or {}).get("current_run") or {}))
        self.assertEqual(str(current_run.get("intent") or ""), "inventory_provider_serial_validation")
        self.assertEqual(str(current_run.get("domain") or ""), "inventario_logistica")
        self.assertIn("segundo plano", str((payload or {}).get("reply") or "").lower())
        semantic = dict(current_run.get("semantic_explanation") or {})
        self.assertEqual(str(semantic.get("planner_route_hint") or ""), "inventory.serial.validation.provider_file")
        self.assertFalse(bool(dict(semantic.get("clarification_needed") or {}).get("required")))
        self.assertEqual(str((dict(semantic.get("validation_status") or {}).get("status") or "")), "passed")
        progress = dict((dict(current_run.get("evidence") or {}).get("background_progress") or {}))
        self.assertEqual(int(progress.get("rows_processed") or 0), 2)
        self.assertEqual(int(progress.get("total_estimated") or 0), 10)
        self.assertEqual(str(progress.get("attachment_name") or ""), "validacion seriales.xlsx")
