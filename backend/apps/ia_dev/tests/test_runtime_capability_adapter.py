from __future__ import annotations

import base64

from django.test import SimpleTestCase

from apps.ia_dev.application.context.run_context import RunContext
from apps.ia_dev.application.contracts.query_intelligence_contracts import (
    QueryExecutionPlan,
    ResolvedQuerySpec,
    StructuredQueryIntent,
)
from apps.ia_dev.application.runtime.runtime_capability_adapter import RuntimeCapabilityAdapter


class RuntimeCapabilityAdapterTests(SimpleTestCase):
    def test_execute_registered_tool_blocks_when_approval_is_required(self):
        adapter = RuntimeCapabilityAdapter()
        run_context = RunContext.create(message="aprueba la propuesta", session_id="sess-rt", reset_memory=False)

        result = adapter.execute_registered_tool(
            run_context=run_context,
            tool_id="knowledge.proposal.approve.v1",
            arguments={"message": "aprobar propuesta"},
            session_id="sess-rt",
            reset_memory=False,
        )

        self.assertFalse(bool(result.get("ok")))
        self.assertTrue(bool((result.get("meta") or {}).get("approval_pending")))
        self.assertEqual(str((run_context.metadata.get("approval_runtime") or {}).get("status") or ""), "awaiting_approval")

    def test_execute_registered_tool_can_queue_background_run(self):
        adapter = RuntimeCapabilityAdapter()
        run_context = RunContext.create(message="personal activo hoy", session_id="sess-rt-bg", reset_memory=False)

        result = adapter.execute_registered_tool(
            run_context=run_context,
            tool_id="empleados.count.active.v1",
            arguments={"message": "personal activo hoy", "background": True},
            session_id="sess-rt-bg",
            reset_memory=False,
        )

        self.assertFalse(bool(result.get("ok")))
        self.assertTrue(bool((result.get("meta") or {}).get("background_pending")))
        self.assertEqual(
            str((((run_context.metadata.get("background_runtime") or {}).get("background") or {}).get("run_status") or "")),
            "queued",
        )

    def test_inventory_provider_serial_validation_large_attachment_queues_background(self):
        adapter = RuntimeCapabilityAdapter()
        run_context = RunContext.create(
            message="valida este archivo del proveedor",
            session_id="sess-rt-inv-bg",
            reset_memory=False,
        )
        run_context.metadata["attachments"] = [
            {
                "name": "seriales.xlsx",
                "mime_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "size": 1_100_000,
                "content_base64": base64.b64encode(b"A" * 1_100_000).decode("ascii"),
            }
        ]
        resolved_query = ResolvedQuerySpec(
            intent=StructuredQueryIntent(
                raw_query="valida este archivo del proveedor",
                domain_code="inventario_logistica",
                operation="detail",
                template_id="inventory_provider_serial_validation",
            ),
            semantic_context={"semantic_capability_registry": {"candidate_capability": "inventory_provider_serial_validation"}},
        )
        execution_plan = QueryExecutionPlan(
            strategy="capability",
            reason="provider_file",
            domain_code="inventario_logistica",
            capability_id="inventory_provider_serial_validation",
            metadata={"background_requested": True},
        )

        result = adapter.execute(
            run_context=run_context,
            route={"execute_capability": True, "selected_capability_id": "inventory_provider_serial_validation"},
            planned_capability={"capability_id": "inventory_provider_serial_validation", "source": {"domain": "inventario_logistica", "intent": "validacion_seriales"}},
            message="valida este archivo del proveedor",
            session_id="sess-rt-inv-bg",
            reset_memory=False,
            resolved_query=resolved_query,
            execution_plan=execution_plan,
        )

        self.assertFalse(bool(result.get("ok")))
        self.assertTrue(bool((result.get("meta") or {}).get("background_pending")))
        self.assertEqual(str((result.get("error") or "")), "background_execution_queued:inventory_provider_serial_validation")
        self.assertEqual(
            str((((run_context.metadata.get("background_runtime") or {}).get("background") or {}).get("run_status") or "")),
            "queued",
        )
        background_request = dict((run_context.metadata.get("background_runtime") or {}).get("request") or {})
        attachment = dict(background_request.get("attachment") or {})
        self.assertEqual(str(background_request.get("capability_id") or ""), "inventory_provider_serial_validation")
        self.assertEqual(str(background_request.get("attachment_name") or ""), "seriales.xlsx")
        self.assertEqual(int(background_request.get("attachment_size_bytes") or 0), 1_100_000)
        self.assertEqual(str((dict(background_request.get("execution_plan") or {}).get("capability_id") or "")), "inventory_provider_serial_validation")
        self.assertEqual(str((dict(background_request.get("resolved_query") or {}).get("intent") or {}).get("template_id") or ""), "inventory_provider_serial_validation")
        self.assertTrue(bool(str(attachment.get("content_base64") or "").strip()))
