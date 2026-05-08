from __future__ import annotations

from django.test import SimpleTestCase

from apps.ia_dev.application.workflow.task_state_service import TaskStateService


class _FakeWorkflowRepo:
    def __init__(self):
        self._rows: dict[str, dict] = {}

    def get_workflow_state(self, workflow_key: str, *, for_update: bool = False):
        row = self._rows.get(workflow_key)
        return dict(row) if row else None

    def upsert_workflow_state(
        self,
        *,
        workflow_type: str,
        workflow_key: str,
        status: str,
        state: dict,
        retry_count: int = 0,
        lock_version: int = 1,
        next_retry_at: int | None = None,
        last_error: str | None = None,
    ) -> None:
        self._rows[workflow_key] = {
            "workflow_type": workflow_type,
            "workflow_key": workflow_key,
            "status": status,
            "state": dict(state or {}),
            "retry_count": retry_count,
            "lock_version": lock_version,
            "next_retry_at": next_retry_at,
            "last_error": last_error,
        }


class TaskStateServiceTests(SimpleTestCase):
    def setUp(self):
        self.repo = _FakeWorkflowRepo()
        self.service = TaskStateService(repo=self.repo)

    def test_save_persists_enterprise_runtime_fields(self):
        workflow = self.service.save(
            run_id="run-123",
            status="planned",
            original_question="Que areas tienen mas ausentismo",
            detected_domain="ausentismo",
            plan={"execution_plan": {"strategy": "sql_assisted"}},
            source_used={"structural_source": "ai_dictionary.dd_*"},
            executed_query="SELECT 1",
            validation_result={"satisfied": True},
            fallback_used={"used": False},
            recommendations=["Explorar por cargo"],
        )

        state = dict((workflow or {}).get("state") or {})
        self.assertEqual(str((workflow or {}).get("status") or ""), "planned")
        self.assertEqual(str(state.get("original_question") or ""), "Que areas tienen mas ausentismo")
        self.assertEqual(str(state.get("detected_domain") or ""), "ausentismo")
        self.assertEqual(str(state.get("executed_query") or ""), "SELECT 1")
        self.assertEqual(list(state.get("recommendations") or []), ["Explorar por cargo"])

    def test_save_appends_history_across_states(self):
        self.service.save(
            run_id="run-456",
            status="planned",
            original_question="Que empleados tienen mas riesgo",
            detected_domain="ausentismo",
            plan={},
            source_used={},
        )
        workflow = self.service.save(
            run_id="run-456",
            status="completed",
            original_question="Que empleados tienen mas riesgo",
            detected_domain="ausentismo",
            plan={},
            source_used={"response_flow": "sql_assisted"},
            validation_result={"satisfied": True},
        )

        history = list(((workflow or {}).get("state") or {}).get("history") or [])
        self.assertEqual(len(history), 2)
        self.assertEqual(str(history[-1].get("status") or ""), "completed")

    def test_save_persists_validation_fallback_and_source_without_memory_proposal_fields(self):
        workflow = self.service.save(
            run_id="run-789",
            status="completed",
            original_question="Que empleados tienen mas riesgo",
            detected_domain="ausentismo",
            plan={"execution_plan": {"strategy": "sql_assisted"}},
            source_used={
                "response_flow": "sql_assisted",
                "structural_authority": "dictionary_first",
            },
            executed_query="SELECT e.cedula FROM cincosas_cincosas.cinco_base_de_personal AS e LIMIT 10",
            validation_result={"satisfied": True, "gate_score": 0.91},
            fallback_used={"used": False, "reason": ""},
            recommendations=["Explorar por sede"],
        )

        state = dict((workflow or {}).get("state") or {})
        self.assertEqual(str(state.get("task_status") or ""), "completed")
        self.assertEqual(str((state.get("source_used") or {}).get("response_flow") or ""), "sql_assisted")
        self.assertTrue(bool((state.get("validation_result") or {}).get("satisfied")))
        self.assertFalse(bool((state.get("fallback_used") or {}).get("used")))
        self.assertNotIn("proposal_id", state)
        self.assertNotIn("approval_status", state)
