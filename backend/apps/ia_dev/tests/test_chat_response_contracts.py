from __future__ import annotations

from django.test import SimpleTestCase

from apps.ia_dev.application.contracts.chat_contracts import (
    build_chat_response_snapshot,
    ensure_chat_response_contract,
)


class ChatResponseContractsTests(SimpleTestCase):
    def test_snapshot_includes_cause_generation_meta(self):
        snapshot = build_chat_response_snapshot()
        data = dict(snapshot.get("data") or {})
        self.assertIn("cause_generation_meta", data)
        self.assertIsInstance(data.get("cause_generation_meta"), dict)
        task = dict(snapshot.get("task") or {})
        self.assertIn("task_id", task)
        self.assertIsInstance(task.get("current_run"), dict)
        current_run = dict(task.get("current_run") or {})
        self.assertIsInstance(current_run.get("background"), dict)
        self.assertIsInstance(current_run.get("agents"), list)
        self.assertIsInstance(current_run.get("handoffs"), list)
        self.assertIsInstance(current_run.get("approvals"), list)
        self.assertIsInstance(current_run.get("tool_execution"), dict)
        self.assertIsInstance(current_run.get("semantic_explanation"), dict)

    def test_ensure_contract_backfills_cause_generation_meta(self):
        response = ensure_chat_response_contract(
            {
                "session_id": "s1",
                "reply": "ok",
                "data": {"insights": [], "table": {"rows": [], "columns": []}},
            }
        )
        data = dict(response.get("data") or {})
        self.assertIn("cause_generation_meta", data)
        self.assertIsInstance(data.get("cause_generation_meta"), dict)
        task = dict(response.get("task") or {})
        current_run = dict(task.get("current_run") or {})
        self.assertEqual(str(task.get("task_id") or ""), "")
        self.assertEqual(str(current_run.get("reply") or ""), "ok")
        self.assertIsInstance(current_run.get("plan"), dict)
        self.assertIsInstance(current_run.get("background"), dict)
        self.assertIsInstance(current_run.get("agents"), list)
        self.assertIsInstance(current_run.get("handoffs"), list)
        self.assertIsInstance(current_run.get("approvals"), list)
        self.assertIsInstance(current_run.get("required_tools"), list)
        self.assertIsInstance(current_run.get("tool_execution"), dict)
        self.assertIsInstance((current_run.get("tool_execution") or {}).get("trace"), list)
        self.assertIsInstance(current_run.get("semantic_explanation"), dict)
