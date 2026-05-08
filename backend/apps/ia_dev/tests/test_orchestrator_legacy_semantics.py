from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from apps.ia_dev.application.contracts.chat_contracts import build_chat_response_snapshot
from apps.ia_dev.services.runtime_fallback_service import RuntimeFallbackService


def _chat_snapshot(*, reply: str = "ok") -> dict:
    payload = build_chat_response_snapshot()
    payload["session_id"] = "sess-orch"
    payload["reply"] = reply
    payload["orchestrator"] = {
        "intent": "general_question",
        "domain": "general",
        "selected_agent": "analista_agent",
        "classifier_source": "chat_application_service",
        "needs_database": False,
        "output_mode": "summary",
        "used_tools": [],
    }
    return payload


class OrchestratorLegacySemanticsTests(SimpleTestCase):
    def _service(self) -> RuntimeFallbackService:
        service = RuntimeFallbackService()
        service._legacy_runtime = MagicMock()
        service.observability = MagicMock()
        return service

    def test_runtime_fallback_executes_legacy_runtime_on_direct_fallback(self):
        service = self._service()
        service._legacy_runtime.run.return_value = _chat_snapshot(reply="legacy directo")

        response = service.run(message="hola", session_id="sess-1", actor_user_key="user:9")

        self.assertEqual(response["reply"], "legacy directo")
        self.assertTrue(
            bool(((response.get("data_sources") or {}).get("runtime") or {}).get("legacy_runtime_fallback_used"))
        )
        call_kwargs = service._legacy_runtime.run.call_args.kwargs
        self.assertEqual(call_kwargs["message"], "hola")
        self.assertEqual(call_kwargs["session_id"], "sess-1")
        self.assertEqual(call_kwargs["actor_user_key"], "user:9")
        self.assertEqual(call_kwargs["reset_memory"], False)
        self.assertTrue(service._legacy_runtime.run.called)
        runtime = dict((response.get("data_sources") or {}).get("runtime") or {})
        self.assertEqual(
            str(runtime.get("legacy_runtime_fallback_reason") or ""),
            "legacy_runtime_fallback",
        )

    def test_covered_analytics_does_not_fall_back_to_legacy_runtime(self):
        service = self._service()

        with patch.dict("os.environ", {"IA_DEV_ATTENDANCE_EMPLOYEES_PILOT_ENABLED": "1"}, clear=False):
            with patch(
                "apps.ia_dev.services.runtime_fallback_service.SessionMemoryStore.get_or_create",
                return_value=("sess-4", False),
            ):
                response = service.run(
                    message="Que patrones existen por area, cargo y sede en ausentismo",
                    session_id="sess-4",
                )

        service._legacy_runtime.run.assert_not_called()
        runtime = dict((response.get("data_sources") or {}).get("runtime") or {})
        self.assertFalse(bool(runtime.get("legacy_runtime_fallback_used")))
        self.assertTrue(bool(runtime.get("blocked_run_legacy_for_analytics")))
        self.assertEqual(str((response.get("orchestrator") or {}).get("runtime_flow") or ""), "runtime_only_fallback")

    def test_runtime_fallback_marks_metadata_when_used_explicitly(self):
        service = self._service()
        service._legacy_runtime.run.return_value = _chat_snapshot(reply="legacy directo")

        response = service.run(message="necesito compatibilidad", session_id="sess-5")

        runtime = dict((response.get("data_sources") or {}).get("runtime") or {})
        self.assertTrue(bool(runtime.get("legacy_runtime_fallback_used")))
        self.assertEqual(
            str(runtime.get("legacy_runtime_fallback_reason") or ""),
            "legacy_runtime_fallback",
        )

    def test_kpro_response_keeps_working_through_legacy_runtime_fallback(self):
        service = self._service()
        legacy_response = _chat_snapshot(reply="KPRO creado")
        legacy_response["orchestrator"]["intent"] = "knowledge_change_request"
        legacy_response["actions"] = [
            {
                "id": "approve-kpro",
                "type": "knowledge_proposal",
                "payload": {"proposal_id": "KPRO-01"},
            }
        ]
        service._legacy_runtime.run.return_value = legacy_response

        response = service.run(message="propongo actualizar una regla", session_id="sess-kpro")

        self.assertEqual(str((response.get("actions") or [])[0].get("payload", {}).get("proposal_id") or ""), "KPRO-01")
        self.assertTrue(
            bool(((response.get("data_sources") or {}).get("runtime") or {}).get("legacy_runtime_fallback_used"))
        )
        service._legacy_runtime.run.assert_called_once()
