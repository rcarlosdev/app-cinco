from __future__ import annotations

from django.test import SimpleTestCase

from apps.ia_dev.application.context.run_context import RunContext
from apps.ia_dev.application.contracts.tool_contracts import ToolApprovalPolicy, ToolDefinition, ToolExecutionPolicy
from apps.ia_dev.application.runtime.approval_runtime_service import ApprovalRuntimeService


class ApprovalRuntimeServiceTests(SimpleTestCase):
    def setUp(self):
        self.service = ApprovalRuntimeService()
        self.run_context = RunContext.create(message="aprobar memoria de negocio", session_id="sess-approval", reset_memory=False)

    def test_manual_tool_creates_awaiting_approval_contract(self):
        tool = ToolDefinition(
            tool_id="knowledge.proposal.approve.v1",
            capability_id="knowledge.proposal.approve.v1",
            domain="knowledge",
            handler_key="knowledge",
            title="knowledge approve",
            description="approval",
            execution_policy=ToolExecutionPolicy(mode="handler", runtime_authority="runtime_capability_adapter"),
            approval_policy=ToolApprovalPolicy(
                mode="manual",
                approval_required=True,
                reason="policy_tag_requires_approval",
                approval_type="human_review",
                required_role="governance",
                risk_level="high",
            ),
        )

        result = self.service.evaluate_tool_execution(
            run_context=self.run_context,
            tool_definition=tool,
            requested_by_agent="manager_agent",
            target_action="execute_handler",
            evidence_before_approval={"proposal_id": "KPRO-1"},
        )

        self.assertTrue(bool(result.get("approval_required")))
        self.assertEqual(str(result.get("task_status") or ""), "awaiting_approval")
        approval = dict(((result.get("approvals") or [])[0]) or {})
        self.assertEqual(str(approval.get("approval_status") or ""), "awaiting_approval")
        self.assertEqual(str(approval.get("target_tool") or ""), "knowledge.proposal.approve.v1")
        self.assertTrue(bool(approval.get("resume_token")))
        self.assertTrue(bool(approval.get("expires_at")))
        self.assertEqual(str((((approval.get("approval_role_matrix") or {}).get("approve") or [None])[0]) or ""), "admin")

    def test_safe_sql_tool_is_auto_approved(self):
        tool = ToolDefinition(
            tool_id="query_execution_planner.sql_assisted",
            capability_id="query_execution_planner.sql_assisted",
            domain="shared",
            handler_key="query_execution_planner",
            title="sql",
            description="sql safe",
            execution_policy=ToolExecutionPolicy(mode="sql_assisted", runtime_authority="query_execution_planner"),
            approval_policy=ToolApprovalPolicy(mode="auto", approval_required=False),
        )

        result = self.service.evaluate_tool_execution(
            run_context=self.run_context,
            tool_definition=tool,
            requested_by_agent="inventory_agent",
            target_action="execute",
        )

        self.assertFalse(bool(result.get("approval_required")))
        self.assertEqual(str(result.get("approval_status") or ""), "approved")

    def test_sensitive_evidence_is_masked_before_persisting_approval(self):
        tool = ToolDefinition(
            tool_id="knowledge.proposal.approve.v1",
            capability_id="knowledge.proposal.approve.v1",
            domain="knowledge",
            handler_key="knowledge",
            title="knowledge approve",
            description="approval",
            execution_policy=ToolExecutionPolicy(mode="handler", runtime_authority="runtime_capability_adapter"),
            approval_policy=ToolApprovalPolicy(
                mode="manual",
                approval_required=True,
                reason="policy_tag_requires_approval",
                approval_type="human_review",
                required_role="governance",
                risk_level="high",
            ),
        )

        result = self.service.evaluate_tool_execution(
            run_context=self.run_context,
            tool_definition=tool,
            requested_by_agent="manager_agent",
            target_action="execute_handler",
            evidence_before_approval={"cedula": "1234567890", "token": "secret-token"},
        )

        approval = dict(((result.get("approvals") or [])[0]) or {})
        self.assertEqual(str(((approval.get("evidence_before_approval") or {}).get("cedula") or "")), "12***90")
        self.assertEqual(str(((approval.get("evidence_before_approval") or {}).get("token") or "")), "se***en")
