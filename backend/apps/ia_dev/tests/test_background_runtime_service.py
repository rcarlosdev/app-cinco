from __future__ import annotations

from datetime import datetime, timedelta, timezone

from django.test import SimpleTestCase

from apps.ia_dev.application.context.run_context import RunContext
from apps.ia_dev.application.contracts.chat_contracts import build_chat_response_snapshot
from apps.ia_dev.application.runtime.approval_runtime_service import ApprovalRuntimeService
from apps.ia_dev.application.runtime.background_runtime_service import BackgroundRuntimeService
from apps.ia_dev.application.workflow.task_state_service import TaskStateService
from apps.ia_dev.tests.test_task_state_service import _FakeWorkflowRepo


class BackgroundRuntimeServiceTests(SimpleTestCase):
    def setUp(self):
        self.repo = _FakeWorkflowRepo()
        self.task_state = TaskStateService(repo=self.repo)
        self.service = BackgroundRuntimeService(task_state_service=self.task_state)
        self.approvals = ApprovalRuntimeService()

    def test_queue_and_complete_background_run_preserves_evidence(self):
        run_context = RunContext.create(message="proceso largo", session_id="sess-bg", reset_memory=False)
        runtime_state = self.service.queue_run(
            run_context=run_context,
            tool_id="empleados.count.active.v1",
            policy_reason="runtime_policy_requested",
            partial_evidence={"stage": "queued"},
        )
        self.task_state.save(
            run_id=run_context.run_id,
            status="queued",
            original_question=run_context.message,
            detected_domain="empleados",
            plan={},
            source_used={"response_flow": "handler"},
            extra_state=runtime_state,
        )

        workflow = self.task_state.get(run_id=run_context.run_id)
        workflow = self.service.mark_started(workflow=workflow or {})
        workflow = self.service.add_progress(
            workflow=workflow,
            message="Mitad del proceso",
            progress_pct=50.0,
            partial_evidence={"rows_processed": 20},
        )
        workflow = self.service.add_checkpoint(
            workflow=workflow,
            label="halfway",
            checkpoint_state={"cursor": "page-2"},
            progress={"progress_pct": 50.0},
            evidence={"rows_processed": 20},
        )
        workflow = self.service.complete_run(
            workflow=workflow,
            final_evidence={"rows_processed": 40, "result": "ok"},
        )

        state = dict((workflow or {}).get("state") or {})
        self.assertEqual(str((state.get("background") or {}).get("run_status") or ""), "completed")
        self.assertEqual(int(((state.get("background") or {}).get("partial_evidence") or {}).get("rows_processed") or 0), 20)
        self.assertEqual(int(((state.get("background") or {}).get("final_evidence") or {}).get("rows_processed") or 0), 40)
        self.assertGreaterEqual(len(list(state.get("background_trace") or [])), 4)
        self.assertEqual(len(list(state.get("checkpoints") or [])), 1)

    def test_complete_run_persists_response_snapshot(self):
        run_context = RunContext.create(message="proceso largo", session_id="sess-snapshot", reset_memory=False)
        runtime_state = self.service.queue_run(
            run_context=run_context,
            tool_id="inventory_provider_serial_validation",
            policy_reason="runtime_policy_requested",
            partial_evidence={"phase": "queued"},
        )
        self.task_state.save(
            run_id=run_context.run_id,
            status="running",
            original_question=run_context.message,
            detected_domain="inventario_logistica",
            plan={},
            source_used={"response_flow": "handler"},
            extra_state=runtime_state,
        )
        workflow = self.task_state.get(run_id=run_context.run_id)
        response_snapshot = build_chat_response_snapshot()
        response_snapshot["reply"] = "Resultado listo"

        workflow = self.service.complete_run(
            workflow=workflow or {},
            final_evidence={"result": "ok"},
            response_snapshot=response_snapshot,
        )

        state = dict((workflow or {}).get("state") or {})
        self.assertEqual(str((state.get("response_snapshot") or {}).get("reply") or ""), "Resultado listo")

    def test_resume_after_approval_updates_approval_and_agent_trace(self):
        run_context = RunContext.create(message="aprobar y continuar", session_id="sess-resume", reset_memory=False)
        runtime_state = self.service.queue_run(
            run_context=run_context,
            tool_id="knowledge.proposal.approve.v1",
            policy_reason="approval_pending",
            partial_evidence={"proposal_id": "KPRO-1"},
        )
        runtime_state = self.service.mark_awaiting_approval(
            run_context=run_context,
            resume_token="resume-123",
            partial_evidence={"proposal_id": "KPRO-1"},
            tool_id="knowledge.proposal.approve.v1",
        )
        self.task_state.save(
            run_id=run_context.run_id,
            status="awaiting_approval",
            original_question=run_context.message,
            detected_domain="knowledge",
            plan={},
            source_used={"response_flow": "handler"},
            extra_state={
                **runtime_state,
                "approvals": [
                    {
                        "approval_request_id": "apr-1",
                        "resume_token": "resume-123",
                        "approval_status": "awaiting_approval",
                        "target_tool": "knowledge.proposal.approve.v1",
                    }
                ],
                "approval_trace": [{"approval_request_id": "apr-1", "status": "awaiting_approval"}],
                "agent_trace": [{"agent_name": "manager_agent"}],
            },
        )

        workflow = self.service.resume_after_approval(
            resume_token="resume-123",
            approved_by="alice",
            approver_role="governance",
            approval_runtime_service=self.approvals,
            evidence_after_approval={"decision": "approved"},
            final_evidence={"applied": True},
            tool_execution_trace=[{"tool_id": "knowledge.proposal.approve.v1", "status": "completed"}],
            agent_trace_append=[{"agent_name": "knowledge_agent", "status": "completed"}],
        )

        state = dict((workflow or {}).get("state") or {})
        approvals = list(state.get("approvals") or [])
        self.assertEqual(str((state.get("background") or {}).get("run_status") or ""), "completed")
        self.assertEqual(str((approvals[0] or {}).get("approval_status") or ""), "approved")
        self.assertEqual(len(list(state.get("agent_trace") or [])), 2)
        self.assertEqual(len(list(state.get("tool_execution_trace") or [])), 1)

    def test_cancel_run_keeps_previous_partial_evidence(self):
        run_context = RunContext.create(message="cancelame", session_id="sess-cancel", reset_memory=False)
        runtime_state = self.service.queue_run(
            run_context=run_context,
            tool_id="empleados.detail.v1",
            policy_reason="runtime_policy_requested",
            partial_evidence={"rows_processed": 5},
        )
        self.task_state.save(
            run_id=run_context.run_id,
            status="running",
            original_question=run_context.message,
            detected_domain="empleados",
            plan={},
            source_used={},
            extra_state=runtime_state,
        )

        workflow = self.service.cancel_run(
            run_id=run_context.run_id,
            cancelled_by="bob",
            reason="user_requested",
        )

        state = dict((workflow or {}).get("state") or {})
        self.assertEqual(str((state.get("background") or {}).get("run_status") or ""), "cancelled")
        self.assertEqual(int(((state.get("background") or {}).get("partial_evidence") or {}).get("rows_processed") or 0), 5)
        self.assertEqual(str((((state.get("background") or {}).get("cancellation") or {}).get("cancelled_by") or "")), "bob")

    def test_queue_run_is_idempotent_for_same_active_tool(self):
        run_context = RunContext.create(message="proceso largo", session_id="sess-idempotent", reset_memory=False)

        first = self.service.queue_run(
            run_context=run_context,
            tool_id="empleados.count.active.v1",
            policy_reason="runtime_policy_requested",
            partial_evidence={"token": "abc12345"},
        )
        second = self.service.queue_run(
            run_context=run_context,
            tool_id="empleados.count.active.v1",
            policy_reason="runtime_policy_requested",
            partial_evidence={"token": "abc12345"},
        )

        self.assertEqual(
            str((first.get("background") or {}).get("background_run_id") or ""),
            str((second.get("background") or {}).get("background_run_id") or ""),
        )
        self.assertTrue(
            any(item.get("event_type") == "background_run_queue_idempotent" for item in list(second.get("background_trace") or []))
        )
        self.assertEqual(str(((first.get("background") or {}).get("partial_evidence") or {}).get("token") or ""), "ab***45")

    def test_fail_run_moves_to_dead_letter_after_retry_limit(self):
        run_context = RunContext.create(message="proceso largo", session_id="sess-dead", reset_memory=False)
        runtime_state = self.service.queue_run(
            run_context=run_context,
            tool_id="empleados.detail.v1",
            policy_reason="runtime_policy_requested",
            partial_evidence={"rows_processed": 1},
        )
        self.task_state.save(
            run_id=run_context.run_id,
            status="running",
            original_question=run_context.message,
            detected_domain="empleados",
            plan={},
            source_used={},
            extra_state=runtime_state,
        )
        workflow = self.task_state.get(run_id=run_context.run_id)

        workflow = self.service.fail_run(workflow=workflow or {}, failure_reason="timeout_1")
        workflow = self.service.fail_run(workflow=workflow or {}, failure_reason="timeout_2")
        workflow = self.service.fail_run(workflow=workflow or {}, failure_reason="timeout_3")

        state = dict((workflow or {}).get("state") or {})
        self.assertTrue(bool((state.get("dead_letter") or {}).get("dead_lettered")))
        self.assertEqual(str(((state.get("dead_letter") or {}).get("failure_reason") or "")), "timeout_3")

    def test_resume_after_approval_fails_when_approval_expired(self):
        run_context = RunContext.create(message="aprobar y continuar", session_id="sess-expired", reset_memory=False)
        runtime_state = self.service.mark_awaiting_approval(
            run_context=run_context,
            resume_token="resume-expired",
            partial_evidence={"proposal_id": "KPRO-2"},
            tool_id="knowledge.proposal.approve.v1",
        )
        expired_at = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        self.task_state.save(
            run_id=run_context.run_id,
            status="awaiting_approval",
            original_question=run_context.message,
            detected_domain="knowledge",
            plan={},
            source_used={"response_flow": "handler"},
            extra_state={
                **runtime_state,
                "approvals": [
                    {
                        "approval_request_id": "apr-expired",
                        "resume_token": "resume-expired",
                        "approval_status": "awaiting_approval",
                        "target_tool": "knowledge.proposal.approve.v1",
                        "expires_at": expired_at,
                    }
                ],
                "approval_trace": [{"approval_request_id": "apr-expired", "status": "awaiting_approval"}],
            },
        )

        workflow = self.service.resume_after_approval(
            resume_token="resume-expired",
            approved_by="alice",
            approver_role="governance",
            approval_runtime_service=self.approvals,
        )

        state = dict((workflow or {}).get("state") or {})
        self.assertEqual(str((state.get("background") or {}).get("run_status") or ""), "failed")
        self.assertEqual(str((state.get("background") or {}).get("failure_reason") or ""), "approval_wait_expired")
