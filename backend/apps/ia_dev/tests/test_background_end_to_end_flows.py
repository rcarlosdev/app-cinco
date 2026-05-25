from __future__ import annotations

from django.test import SimpleTestCase

from apps.ia_dev.application.context.run_context import RunContext
from apps.ia_dev.application.orchestration.chat_application_service import ChatApplicationService
from apps.ia_dev.application.workflow.task_state_service import TaskStateService
from apps.ia_dev.tests.test_task_state_service import _FakeWorkflowRepo


class BackgroundEndToEndFlowTests(SimpleTestCase):
    def setUp(self):
        self.repo = _FakeWorkflowRepo()
        self.task_state_service = TaskStateService(repo=self.repo)
        self.service = ChatApplicationService(task_state_service=self.task_state_service)

    def test_case_a_sync_query_keeps_task_envelope_and_completed_status(self):
        run_context = RunContext.create(message="personal activo hoy", session_id="case-a", reset_memory=False)
        self.service._save_task_state(
            run_context=run_context,
            status="completed",
            original_question=run_context.message,
            detected_domain="empleados",
            plan={"query_intelligence": {"execution_plan": {"strategy": "sql_assisted"}}},
            source_used={"response_flow": "sql_assisted"},
            validation_result={"satisfied": True},
            extra_state={"tool_execution": {"selected_tool_id": "query_execution_planner.sql_assisted"}},
        )
        run_context.metadata["query_intelligence"] = {"execution_plan": {"strategy": "sql_assisted"}}

        response = ChatApplicationService._attach_runtime_metadata(
            response={"reply": "ok", "orchestrator": {"domain": "empleados", "intent": "analytics_query"}, "data_sources": {}},
            run_context=run_context,
            response_flow="sql_assisted",
        )

        current_run = dict(((response.get("task") or {}).get("current_run") or {}))
        self.assertEqual(str(current_run.get("status") or ""), "completed")
        self.assertEqual(str(((current_run.get("tool_execution") or {}).get("selected_tool_id") or "")), "query_execution_planner.sql_assisted")

    def test_case_b_native_tool_trace_is_persisted(self):
        run_context = RunContext.create(message="inventario tiran224", session_id="case-b", reset_memory=False)
        run_context.metadata["response_native_tool_trace"] = [
            {
                "tool_call_id": "call-1",
                "tool_name": "semantic_orchestrator.dictionary_summary.v1",
                "tool_id": "semantic_orchestrator.dictionary_summary.v1",
                "status": "completed",
            }
        ]
        tool_state = self.service._build_runtime_tool_execution_state(
            run_context=run_context,
            response_flow="sql_assisted",
            route_payload={},
            execution_plan={"capability_id": "inventory_stock_balance_by_mobile"},
            response={"reply": "ok", "data": {"table": {"rowcount": 1}}, "observability": {"duration_ms": 1}},
            fallback_used={"used": False},
            validation_result={"satisfied": True},
        )

        self.service._save_task_state(
            run_context=run_context,
            status="completed",
            original_question=run_context.message,
            detected_domain="inventario_logistica",
            plan={},
            source_used={"response_flow": "sql_assisted"},
            extra_state=tool_state,
        )
        workflow = self.task_state_service.get(run_id=run_context.run_id) or {}
        trace = list(((workflow.get("state") or {}).get("tool_execution_trace") or []))
        self.assertEqual(len(trace), 2)

    def test_case_c_multiagent_handoff_persists_traces(self):
        run_context = RunContext.create(message="inventario cuadrilla TIRAN224", session_id="case-c", reset_memory=False)
        run_context.metadata["agents_runtime"] = {
            "agents": [{"agent_name": "manager_agent"}, {"agent_name": "inventory_agent"}],
            "handoffs": [{"handoff_origin": "manager_agent", "handoff_target": "inventory_agent"}],
            "handoff_trace": [{"handoff_id": "handoff-1", "handoff_origin": "manager_agent", "handoff_target": "inventory_agent"}],
            "agent_trace": [{"agent_name": "manager_agent"}, {"agent_name": "inventory_agent"}],
        }
        self.service._save_task_state(
            run_context=run_context,
            status="completed",
            original_question=run_context.message,
            detected_domain="inventario_logistica",
            plan={},
            source_used={"response_flow": "sql_assisted"},
            extra_state=self.service._build_runtime_agent_execution_state(run_context=run_context),
        )
        workflow = self.task_state_service.get(run_id=run_context.run_id) or {}
        state = dict(workflow.get("state") or {})
        self.assertEqual(len(list(state.get("agent_trace") or [])), 2)
        self.assertEqual(len(list(state.get("handoff_trace") or [])), 1)

    def test_case_d_and_e_approval_then_resume_after_approval(self):
        run_context = RunContext.create(message="aprobar propuesta", session_id="case-de", reset_memory=False)
        result = self.service.capability_runtime.execute_registered_tool(
            run_context=run_context,
            tool_id="knowledge.proposal.approve.v1",
            arguments={"message": "aprobar propuesta"},
            session_id="case-de",
            reset_memory=False,
        )
        self.service._save_task_state(
            run_context=run_context,
            status="awaiting_approval",
            original_question=run_context.message,
            detected_domain="knowledge",
            plan={},
            source_used={"response_flow": "handler"},
            extra_state={
                **self.service._build_runtime_approval_execution_state(run_context=run_context),
                **self.service._build_runtime_background_execution_state(run_context=run_context),
            },
        )
        workflow = self.task_state_service.get(run_id=run_context.run_id) or {}
        state = dict(workflow.get("state") or {})
        approval = dict(((state.get("approvals") or [None])[0]) or {})
        self.assertTrue(bool((result.get("meta") or {}).get("approval_pending")))
        self.assertEqual(str(state.get("task_status") or ""), "awaiting_approval")
        self.assertTrue(bool(approval.get("resume_token")))

        resumed = self.service.resume_background_run(
            resume_token=str(approval.get("resume_token") or ""),
            approved_by="alice",
            approver_role="governance",
            evidence_after_approval={"decision": "approved"},
            final_evidence={"applied": True},
            tool_execution_trace=[{"tool_id": "knowledge.proposal.approve.v1", "status": "completed"}],
            agent_trace_append=[{"agent_name": "knowledge_agent", "status": "completed"}],
        )
        resumed_state = dict((resumed or {}).get("state") or {})
        self.assertEqual(str((resumed_state.get("background") or {}).get("run_status") or ""), "completed")
        self.assertEqual(str((((resumed_state.get("approvals") or [None])[0]) or {}).get("approval_status") or ""), "approved")

    def test_case_f_background_long_run_supports_polling_and_completion(self):
        run_context = RunContext.create(message="empleados por area", session_id="case-f", reset_memory=False)
        result = self.service.capability_runtime.execute_registered_tool(
            run_context=run_context,
            tool_id="empleados.count.active.v1",
            arguments={"message": "empleados por area", "background": True},
            session_id="case-f",
            reset_memory=False,
        )
        self.service._save_task_state(
            run_context=run_context,
            status="queued",
            original_question=run_context.message,
            detected_domain="empleados",
            plan={},
            source_used={"response_flow": "handler"},
            extra_state=self.service._build_runtime_background_execution_state(run_context=run_context),
        )
        self.assertTrue(bool((result.get("meta") or {}).get("background_pending")))

        polled = self.service.poll_background_run(run_id=run_context.run_id)
        self.assertEqual(str((polled.get("background") or {}).get("run_status") or ""), "queued")

        completed = self.service.background_runtime_service.complete_run(
            workflow=self.task_state_service.get(run_id=run_context.run_id) or {},
            final_evidence={"rows_processed": 12},
        )
        self.assertEqual(str(((completed.get("state") or {}).get("background") or {}).get("run_status") or ""), "completed")

    def test_case_g_cancel_and_failure_keep_previous_traces(self):
        run_context = RunContext.create(message="corrida inestable", session_id="case-g", reset_memory=False)
        runtime_state = self.service.background_runtime_service.queue_run(
            run_context=run_context,
            tool_id="empleados.detail.v1",
            policy_reason="runtime_policy_requested",
            partial_evidence={"rows_processed": 3},
        )
        self.service._save_task_state(
            run_context=run_context,
            status="running",
            original_question=run_context.message,
            detected_domain="empleados",
            plan={},
            source_used={"response_flow": "handler"},
            extra_state=runtime_state,
        )

        cancelled = self.service.cancel_background_run(
            run_id=run_context.run_id,
            cancelled_by="ops",
            reason="user_cancelled",
        )
        cancelled_state = dict((cancelled or {}).get("state") or {})
        self.assertEqual(str((cancelled_state.get("background") or {}).get("run_status") or ""), "cancelled")
        self.assertEqual(int(((cancelled_state.get("background") or {}).get("partial_evidence") or {}).get("rows_processed") or 0), 3)

        failed = self.service.background_runtime_service.fail_run(
            workflow=cancelled,
            failure_reason="timeout_worker",
            final_evidence={"rows_processed": 3},
        )
        failed_state = dict((failed or {}).get("state") or {})
        self.assertEqual(str((failed_state.get("background") or {}).get("run_status") or ""), "failed")
        self.assertGreaterEqual(len(list(failed_state.get("background_trace") or [])), 2)
