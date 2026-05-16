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

    def list_workflow_states(self, *, workflow_type=None, status=None, limit: int = 100):
        rows = list(self._rows.values())
        if workflow_type:
            rows = [row for row in rows if str(row.get("workflow_type") or "") == str(workflow_type)]
        if status:
            rows = [row for row in rows if str(row.get("status") or "") == str(status)]
        return rows[:limit]


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
        self.assertEqual(str(state.get("task_id") or ""), "task_runtime:run-123")
        self.assertEqual(str(state.get("run_id") or ""), "run-123")
        self.assertEqual(str((state.get("correlation") or {}).get("task_id") or ""), "task_runtime:run-123")
        self.assertEqual(int(((state.get("runtime_metrics") or {}).get("tool_call_count") or 0)), 0)
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
        self.assertEqual(str(history[-1].get("task_id") or ""), "task_runtime:run-456")

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
        self.assertEqual(str(state.get("status") or ""), "completed")
        self.assertNotIn("proposal_id", state)
        self.assertNotIn("approval_status", state)

    def test_save_persists_tool_execution_metadata_and_trace(self):
        workflow = self.service.save(
            run_id="run-tool-1",
            status="completed",
            original_question="personal activo hoy",
            detected_domain="empleados",
            plan={"execution_plan": {"strategy": "capability"}},
            source_used={"response_flow": "handler"},
            validation_result={"satisfied": True},
            fallback_used={"used": False},
            extra_state={
                "tool_execution": {
                    "selected_tool_id": "empleados.count.active.v1",
                    "registry_version": "tool_registry.v1",
                },
                "tool_execution_trace": [
                    {
                        "tool_id": "empleados.count.active.v1",
                        "status": "completed",
                    }
                ],
            },
        )

        state = dict((workflow or {}).get("state") or {})
        history = list(state.get("history") or [])
        self.assertEqual(str((state.get("tool_execution") or {}).get("selected_tool_id") or ""), "empleados.count.active.v1")
        self.assertEqual(len(list(state.get("tool_execution_trace") or [])), 1)
        self.assertEqual(int(((state.get("runtime_metrics") or {}).get("tool_call_count") or 0)), 1)
        self.assertEqual(str((history[-1] or {}).get("selected_tool_id") or ""), "empleados.count.active.v1")
        self.assertEqual(int((history[-1] or {}).get("tool_trace_count") or 0), 1)

    def test_save_persists_agents_handoffs_and_agent_trace(self):
        workflow = self.service.save(
            run_id="run-agent-1",
            status="completed",
            original_question="inventario cuadrilla TIRAN224",
            detected_domain="inventario_logistica",
            plan={"execution_plan": {"strategy": "sql_assisted"}},
            source_used={"response_flow": "sql_assisted"},
            validation_result={"satisfied": True},
            fallback_used={"used": False},
            extra_state={
                "agents": [
                    {"agent_name": "manager_agent", "role": "manager"},
                    {"agent_name": "inventory_agent", "role": "specialist"},
                ],
                "handoffs": [
                    {
                        "handoff_origin": "manager_agent",
                        "handoff_target": "inventory_agent",
                    }
                ],
                "agent_trace": [
                    {"agent_name": "manager_agent"},
                    {"agent_name": "inventory_agent"},
                ],
            },
        )

        state = dict((workflow or {}).get("state") or {})
        history = list(state.get("history") or [])
        self.assertEqual(len(list(state.get("agents") or [])), 2)
        self.assertEqual(len(list(state.get("handoffs") or [])), 1)
        self.assertEqual(len(list(state.get("agent_trace") or [])), 2)
        self.assertEqual(int((history[-1] or {}).get("agent_count") or 0), 2)
        self.assertEqual(int((history[-1] or {}).get("handoff_count") or 0), 1)

    def test_save_persists_approvals_and_handoff_trace(self):
        workflow = self.service.save(
            run_id="run-approval-1",
            status="awaiting_approval",
            original_question="aprobar propuesta de conocimiento",
            detected_domain="knowledge",
            plan={"execution_plan": {"strategy": "capability"}},
            source_used={"response_flow": "handler"},
            extra_state={
                "handoff_trace": [{"handoff_id": "handoff-1", "handoff_origin": "manager_agent"}],
                "approvals": [
                    {
                        "approval_request_id": "apr-1",
                        "approval_status": "awaiting_approval",
                        "resume_token": "resume-1",
                    }
                ],
                "approval_trace": [{"approval_request_id": "apr-1", "status": "awaiting_approval"}],
            },
        )

        state = dict((workflow or {}).get("state") or {})
        history = list(state.get("history") or [])
        self.assertEqual(str(state.get("task_status") or ""), "awaiting_approval")
        self.assertEqual(len(list(state.get("handoff_trace") or [])), 1)
        self.assertEqual(len(list(state.get("approvals") or [])), 1)
        self.assertEqual(len(list(state.get("approval_trace") or [])), 1)
        self.assertEqual(int((history[-1] or {}).get("approval_count") or 0), 1)

    def test_save_persists_background_trace_and_checkpoints(self):
        workflow = self.service.save(
            run_id="run-bg-1",
            status="queued",
            original_question="proceso largo",
            detected_domain="empleados",
            plan={"execution_plan": {"strategy": "capability"}},
            source_used={"response_flow": "handler"},
            extra_state={
                "background": {
                    "background_run_id": "bg-1",
                    "run_status": "queued",
                    "queue_status": "queued",
                },
                "background_trace": [{"event_type": "background_run_queued"}],
                "checkpoints": [{"checkpoint_id": "chk-1"}],
            },
        )

        state = dict((workflow or {}).get("state") or {})
        history = list(state.get("history") or [])
        self.assertEqual(str((state.get("background") or {}).get("background_run_id") or ""), "bg-1")
        self.assertEqual(len(list(state.get("background_trace") or [])), 1)
        self.assertEqual(len(list(state.get("checkpoints") or [])), 1)
        self.assertEqual(str(((state.get("runtime_metrics") or {}).get("background_status") or "")), "queued")
        self.assertEqual(str((history[-1] or {}).get("background_status") or ""), "queued")
        self.assertEqual(int((history[-1] or {}).get("checkpoint_count") or 0), 1)

    def test_find_by_resume_token_scans_background_and_approvals(self):
        self.service.save(
            run_id="run-find-token",
            status="awaiting_approval",
            original_question="aprobar",
            detected_domain="knowledge",
            plan={},
            source_used={},
            extra_state={
                "background": {"background_run_id": "bg-find", "resume_token": "resume-bg"},
                "approvals": [{"approval_request_id": "apr-1", "resume_token": "resume-apr"}],
            },
        )

        found_background = self.service.find_by_resume_token("resume-bg")
        found_approval = self.service.find_by_resume_token("resume-apr")
        self.assertEqual(str((found_background or {}).get("workflow_key") or ""), "task_runtime:run-find-token")
        self.assertEqual(str((found_approval or {}).get("workflow_key") or ""), "task_runtime:run-find-token")
