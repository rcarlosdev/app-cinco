from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ApprovalRequestContract:
    approval_request_id: str
    approval_type: str
    requested_by_agent: str
    target_tool: str
    target_action: str
    risk_level: str
    reason: str
    required_role: str
    approval_status: str
    approved_by: str = ""
    approved_at: str = ""
    rejected_reason: str = ""
    resume_token: str = ""
    evidence_before_approval: dict[str, Any] = field(default_factory=dict)
    evidence_after_approval: dict[str, Any] = field(default_factory=dict)
    requested_at: str = ""
    expires_at: str = ""
    approval_role_matrix: dict[str, Any] = field(default_factory=dict)
    correlation: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "approval_request_id": str(self.approval_request_id or ""),
            "approval_type": str(self.approval_type or ""),
            "requested_by_agent": str(self.requested_by_agent or ""),
            "target_tool": str(self.target_tool or ""),
            "target_action": str(self.target_action or ""),
            "risk_level": str(self.risk_level or ""),
            "reason": str(self.reason or ""),
            "required_role": str(self.required_role or ""),
            "approval_status": str(self.approval_status or ""),
            "approved_by": str(self.approved_by or ""),
            "approved_at": str(self.approved_at or ""),
            "rejected_reason": str(self.rejected_reason or ""),
            "resume_token": str(self.resume_token or ""),
            "evidence_before_approval": dict(self.evidence_before_approval or {}),
            "evidence_after_approval": dict(self.evidence_after_approval or {}),
            "requested_at": str(self.requested_at or ""),
            "expires_at": str(self.expires_at or ""),
            "approval_role_matrix": dict(self.approval_role_matrix or {}),
            "correlation": dict(self.correlation or {}),
        }


@dataclass(slots=True)
class HandoffTraceContract:
    handoff_id: str
    handoff_origin: str
    handoff_target: str
    requested_by_agent: str
    target_tool: str
    reason: str
    status: str
    evidence: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "handoff_id": str(self.handoff_id or ""),
            "handoff_origin": str(self.handoff_origin or ""),
            "handoff_target": str(self.handoff_target or ""),
            "requested_by_agent": str(self.requested_by_agent or ""),
            "target_tool": str(self.target_tool or ""),
            "reason": str(self.reason or ""),
            "status": str(self.status or ""),
            "evidence": dict(self.evidence or {}),
            "created_at": str(self.created_at or ""),
        }
