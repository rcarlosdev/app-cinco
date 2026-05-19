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

    def _seed_workflow(self, *, fail_after_chunks: int = 0) -> str:
        run_context = RunContext.create(
            message="Valida este archivo del proveedor",
            session_id="sess-bg-provider",
            reset_memory=False,
        )
        request = {
            "capability_id": "inventory_provider_serial_validation",
            "message": run_context.message,
            "session_id": run_context.session_id,
            "chunk_size": 2,
            "fail_after_chunks": fail_after_chunks,
            "attachment": _build_attachment_csv(),
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
        self.assertEqual(int((dict(background.get("final_evidence") or {}).get("current_chunk") or 0)), 2)
        self.assertEqual(int((dict(background.get("final_evidence") or {}).get("total_chunks") or 0)), 2)
        self.assertEqual(int((dict(background.get("final_evidence") or {}).get("found_so_far") or 0)), 0)
        self.assertEqual(int((dict(background.get("final_evidence") or {}).get("not_found_so_far") or 0)), 4)
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
