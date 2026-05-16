from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from apps.ia_dev.application.context.run_context import RunContext
from apps.ia_dev.application.contracts.runtime_governance_contracts import ApprovalRequestContract
from apps.ia_dev.application.contracts.tool_contracts import ToolDefinition
from apps.ia_dev.application.policies.approval_policy_service import ApprovalPolicyService
from apps.ia_dev.application.runtime.runtime_hardening_service import RuntimeHardeningService


class ApprovalRuntimeService:
    SERVICE_VERSION = "approval_runtime.v1"

    def __init__(
        self,
        *,
        approval_policy_service: ApprovalPolicyService | None = None,
        runtime_hardening_service: RuntimeHardeningService | None = None,
    ) -> None:
        self.approval_policy_service = approval_policy_service or ApprovalPolicyService()
        self.runtime_hardening_service = runtime_hardening_service or RuntimeHardeningService()

    def evaluate_tool_execution(
        self,
        *,
        run_context: RunContext,
        tool_definition: ToolDefinition,
        requested_by_agent: str,
        target_action: str,
        evidence_before_approval: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        policy = self._normalize_policy(tool_definition=tool_definition)
        if not bool(policy.get("approval_required")):
            return {
                "approval_required": False,
                "approval_status": "approved",
                "task_status": "approved",
                "approvals": [],
                "approval_trace": [],
                "policy": policy,
            }

        now_iso = datetime.now(timezone.utc).isoformat()
        approval_request_id = f"apr_{uuid4().hex[:16]}"
        resume_token = f"resume_{run_context.run_id}_{approval_request_id}"
        correlation = self.runtime_hardening_service.build_correlation_metadata(
            run_id=run_context.run_id,
            trace_id=run_context.trace_id,
            session_id=run_context.session_id,
            tool_id=str(tool_definition.tool_id or ""),
        )
        approval = ApprovalRequestContract(
            approval_request_id=approval_request_id,
            approval_type=str(policy.get("approval_type") or "human_review"),
            requested_by_agent=str(requested_by_agent or ""),
            target_tool=str(tool_definition.tool_id or ""),
            target_action=str(target_action or "execute"),
            risk_level=str(policy.get("risk_level") or "medium"),
            reason=str(policy.get("reason") or "approval_required_by_policy"),
            required_role=str(policy.get("required_role") or ""),
            approval_status="awaiting_approval",
            resume_token=resume_token,
            evidence_before_approval=dict(
                self.runtime_hardening_service.sanitize_payload(
                    dict(evidence_before_approval or {})
                )
            ),
            evidence_after_approval={},
            requested_at=now_iso,
            expires_at=self.runtime_hardening_service.approval_expires_at(requested_at=now_iso),
            approval_role_matrix=self.approval_policy_service.as_metadata().get("roles") or {},
            correlation=correlation,
        )
        trace = {
            **approval.as_dict(),
            "run_id": str(run_context.run_id or ""),
            "trace_id": str(run_context.trace_id or ""),
            "status": "awaiting_approval",
            "event": "approval_requested",
            "policy_version": self.approval_policy_service.version,
            "service_version": self.SERVICE_VERSION,
        }
        return {
            "approval_required": True,
            "approval_status": "awaiting_approval",
            "task_status": "awaiting_approval",
            "approvals": [approval.as_dict()],
            "approval_trace": [trace],
            "policy": policy,
        }

    def approve_request(
        self,
        *,
        request: dict[str, Any],
        approved_by: str,
        approver_role: str,
        evidence_after_approval: dict[str, Any] | None = None,
        approved_at: str | None = None,
    ) -> dict[str, Any]:
        if not self.approval_policy_service.can_review(
            scope="business",
            role=approver_role,
            action="approve",
        ):
            return self.reject_request(
                request=request,
                rejected_reason="approver_role_not_allowed",
                approved_by=approved_by,
                approver_role=approver_role,
                evidence_after_approval=evidence_after_approval,
                rejected_at=approved_at,
            )
        now_iso = str(approved_at or datetime.now(timezone.utc).isoformat())
        updated = {
            **dict(request or {}),
            "approval_status": "approved",
            "approved_by": str(approved_by or ""),
            "approved_at": now_iso,
            "rejected_reason": "",
            "evidence_after_approval": dict(
                self.runtime_hardening_service.sanitize_payload(
                    dict(evidence_after_approval or {})
                )
            ),
        }
        trace = {
            **updated,
            "status": "approved",
            "event": "approval_approved",
            "policy_version": self.approval_policy_service.version,
            "service_version": self.SERVICE_VERSION,
        }
        return {"approval": updated, "approval_trace": trace, "task_status": "approved"}

    def reject_request(
        self,
        *,
        request: dict[str, Any],
        rejected_reason: str,
        approved_by: str,
        approver_role: str,
        evidence_after_approval: dict[str, Any] | None = None,
        rejected_at: str | None = None,
    ) -> dict[str, Any]:
        now_iso = str(rejected_at or datetime.now(timezone.utc).isoformat())
        updated = {
            **dict(request or {}),
            "approval_status": "rejected",
            "approved_by": str(approved_by or ""),
            "approved_at": now_iso,
            "rejected_reason": str(rejected_reason or "rejected"),
            "evidence_after_approval": dict(
                self.runtime_hardening_service.sanitize_payload(
                    dict(evidence_after_approval or {})
                )
            ),
        }
        trace = {
            **updated,
            "status": "rejected",
            "event": "approval_rejected",
            "approver_role": str(approver_role or ""),
            "policy_version": self.approval_policy_service.version,
            "service_version": self.SERVICE_VERSION,
        }
        return {"approval": updated, "approval_trace": trace, "task_status": "rejected"}

    @staticmethod
    def _normalize_policy(*, tool_definition: ToolDefinition) -> dict[str, Any]:
        policy = dict(tool_definition.approval_policy.as_dict() or {})
        if str(tool_definition.tool_id or "") == "query_execution_planner.sql_assisted":
            policy.update(
                {
                    "approval_required": False,
                    "approval_type": "none",
                    "risk_level": "low",
                }
            )
        if not str(policy.get("approval_type") or "").strip():
            policy["approval_type"] = "human_review" if bool(policy.get("approval_required")) else "none"
        if not str(policy.get("required_role") or "").strip() and bool(policy.get("approval_required")):
            policy["required_role"] = "governance"
        if not str(policy.get("risk_level") or "").strip():
            policy["risk_level"] = "high" if bool(policy.get("approval_required")) else "low"
        return policy
