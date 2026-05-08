from __future__ import annotations

from unittest.mock import MagicMock

from django.test import SimpleTestCase

from apps.ia_dev.application.orchestration.chat_application_service import (
    ChatApplicationService,
)


class _FakeMemoryRuntime:
    def __init__(self):
        self.loaded_user_keys: list[str | None] = []

    def load_context_for_chat(self, *, user_key, domain_code, capability_id, run_context, observability=None):
        self.loaded_user_keys.append(user_key)
        return {
            "flags": {
                "read_enabled": True,
                "write_enabled": True,
                "proposals_enabled": True,
            },
            "decision": {"action": "read", "reason": "test"},
            "user_memory": [{"memory_key": "attendance.output_mode", "memory_value": {"value": "grouped"}}],
            "business_memory": [],
            "used": True,
        }

    def detect_candidates(
        self,
        *,
        message,
        classification,
        planned_capability,
        legacy_response,
        run_context,
        user_key,
        observability=None,
    ):
        return [
            {
                "scope": "user",
                "candidate_key": "attendance.output_mode",
                "candidate_value": {"value": "grouped"},
                "reason": "detected in test",
                "sensitivity": "low",
                "domain_code": "ATTENDANCE",
                "capability_id": planned_capability.get("capability_id"),
            }
        ]

    def persist_candidates(self, *, user_key, candidates, run_context, observability=None):
        return {
            "memory_candidates": [
                {
                    "scope": "user",
                    "candidate_key": "attendance.output_mode",
                    "candidate_value": {"value": "grouped"},
                    "reason": "detected in test",
                    "decision": "propose",
                    "proposal_id": "MPRO-001",
                    "result_ok": True,
                }
            ],
            "pending_proposals": [
                {
                    "proposal_id": "MPRO-001",
                    "scope": "user",
                    "status": "pending",
                    "candidate_key": "attendance.output_mode",
                }
            ],
            "actions": [
                {
                    "id": "action-memory-review-test",
                    "type": "memory_review",
                    "label": "Revisar 1 propuesta(s) de memoria",
                    "payload": {"pending_count": 1},
                }
            ],
        }


def _legacy_response() -> dict:
    return {
        "session_id": "sess-test",
        "reply": "ok",
        "orchestrator": {
            "intent": "attendance_query",
            "domain": "attendance",
            "selected_agent": "attendance_agent",
            "classifier_source": "rules",
            "needs_database": True,
            "output_mode": "table",
            "used_tools": ["get_attendance_summary"],
        },
        "data": {
            "table": {
                "columns": ["empleado"],
                "rows": [{"empleado": "A"}],
                "rowcount": 1,
            }
        },
        "actions": [],
        "trace": [],
        "data_sources": {},
    }


class ChatMemoryIntegrationTests(SimpleTestCase):
    def test_chat_includes_memory_candidates_and_pending_proposals(self):
        fake_runtime = _FakeMemoryRuntime()
        fake_adapter = MagicMock()
        fake_adapter.build_bootstrap_plan.return_value = {
            "capability_id": "attendance.summary.by_attribute.v1",
            "capability_exists": True,
            "rollout_enabled": True,
            "handler_key": "attendance.summary.by_attribute",
            "policy_tags": [],
            "legacy_intents": [],
            "reason": "test_bootstrap",
            "source": {"intent": "attendance_query", "domain": "attendance", "output_mode": "table", "needs_database": True},
            "dictionary_hints": {},
            "query_constraints": {},
            "candidate_rank": 1,
            "candidate_score": 100,
            "workflow_hints": {},
        }
        fake_adapter.build_candidate_plans.return_value = [dict(fake_adapter.build_bootstrap_plan.return_value)]
        fake_adapter.build_candidate_hints.return_value = []
        fake_adapter.build_route.return_value = {
            "execute_capability": False,
            "use_legacy": True,
            "selected_capability_id": "attendance.summary.by_attribute.v1",
            "reason": "test_forces_legacy_path",
            "routing_mode": "intent",
        }
        service = ChatApplicationService(memory_runtime=fake_runtime, capability_runtime_adapter=fake_adapter)

        response = service.run(
            message="dame asistencia agrupada",
            session_id="sess-1",
            reset_memory=False,
            legacy_runner=lambda **_: _legacy_response(),
            actor_user_key="user:11",
        )

        self.assertIn("memory_candidates", response)
        self.assertIn("pending_proposals", response)
        self.assertIn("working_updates", response)
        self.assertIn("reasoning", response)
        self.assertEqual(len(response.get("memory_candidates") or []), 1)
        self.assertEqual(len(response.get("pending_proposals") or []), 1)
        self.assertEqual((response.get("pending_proposals") or [])[0].get("proposal_id"), "MPRO-001")
        self.assertTrue(any(action.get("type") == "memory_review" for action in (response.get("actions") or [])))
        self.assertIsInstance(response.get("working_updates"), list)
        self.assertIsInstance(response.get("reasoning"), dict)

    def test_chat_uses_session_user_key_fallback_when_actor_not_provided(self):
        fake_runtime = _FakeMemoryRuntime()
        fake_adapter = MagicMock()
        fake_adapter.build_bootstrap_plan.return_value = {
            "capability_id": "general.answer.v1",
            "capability_exists": True,
            "rollout_enabled": True,
            "handler_key": "general.answer",
            "policy_tags": [],
            "legacy_intents": [],
            "reason": "test_bootstrap",
            "source": {"intent": "general_question", "domain": "general", "output_mode": "summary", "needs_database": False},
            "dictionary_hints": {},
            "query_constraints": {},
            "candidate_rank": 1,
            "candidate_score": 100,
            "workflow_hints": {},
        }
        fake_adapter.build_candidate_plans.return_value = [dict(fake_adapter.build_bootstrap_plan.return_value)]
        fake_adapter.build_candidate_hints.return_value = []
        fake_adapter.build_route.return_value = {
            "execute_capability": False,
            "use_legacy": True,
            "selected_capability_id": "general.answer.v1",
            "reason": "test_forces_legacy_path",
            "routing_mode": "intent",
        }
        service = ChatApplicationService(memory_runtime=fake_runtime, capability_runtime_adapter=fake_adapter)

        service.run(
            message="consulta general",
            session_id="sess-fallback",
            reset_memory=False,
            legacy_runner=lambda **_: _legacy_response(),
            actor_user_key=None,
        )

        self.assertTrue(fake_runtime.loaded_user_keys)
        self.assertEqual(fake_runtime.loaded_user_keys[0], "session:sess-fallback")

