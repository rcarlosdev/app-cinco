from __future__ import annotations

from django.test import SimpleTestCase

from apps.ia_dev.application.context.run_context import RunContext
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
