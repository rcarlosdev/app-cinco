from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class ToolExecutionPolicy:
    mode: str
    runtime_authority: str
    planner_authority: str = ""
    supports_background: bool = False
    idempotent: bool = True

    def as_dict(self) -> dict[str, Any]:
        return {
            "mode": str(self.mode or ""),
            "runtime_authority": str(self.runtime_authority or ""),
            "planner_authority": str(self.planner_authority or ""),
            "supports_background": bool(self.supports_background),
            "idempotent": bool(self.idempotent),
        }


@dataclass(frozen=True, slots=True)
class ToolApprovalPolicy:
    mode: str = "auto"
    approval_required: bool = False
    reason: str = ""
    approval_type: str = "none"
    required_role: str = ""
    risk_level: str = "low"

    def as_dict(self) -> dict[str, Any]:
        return {
            "mode": str(self.mode or "auto"),
            "approval_required": bool(self.approval_required),
            "reason": str(self.reason or ""),
            "approval_type": str(self.approval_type or "none"),
            "required_role": str(self.required_role or ""),
            "risk_level": str(self.risk_level or "low"),
        }


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    tool_id: str
    capability_id: str
    domain: str
    handler_key: str
    title: str
    description: str
    execution_policy: ToolExecutionPolicy
    approval_policy: ToolApprovalPolicy = field(default_factory=ToolApprovalPolicy)
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)
    audit_metadata: dict[str, Any] = field(default_factory=dict)
    enabled: bool = True
    model_visible: bool = True

    def as_dict(self) -> dict[str, Any]:
        return {
            "tool_id": str(self.tool_id or ""),
            "capability_id": str(self.capability_id or ""),
            "domain": str(self.domain or ""),
            "handler_key": str(self.handler_key or ""),
            "title": str(self.title or ""),
            "description": str(self.description or ""),
            "execution_policy": self.execution_policy.as_dict(),
            "approval_policy": self.approval_policy.as_dict(),
            "input_schema": dict(self.input_schema or {}),
            "output_schema": dict(self.output_schema or {}),
            "audit_metadata": dict(self.audit_metadata or {}),
            "enabled": bool(self.enabled),
            "model_visible": bool(self.model_visible),
        }


@dataclass(slots=True)
class ToolExecutionTrace:
    tool_id: str
    capability_id: str
    status: str
    run_id: str
    trace_id: str
    started_at: str
    finished_at: str
    duration_ms: int = 0
    tool_call_id: str = ""
    tool_name: str = ""
    arguments: dict[str, Any] = field(default_factory=dict)
    execution_status: str = ""
    validation_status: str = ""
    evidence_metadata: dict[str, Any] = field(default_factory=dict)
    model_response_id: str = ""
    loop_iteration: int = 0
    tool_definition: dict[str, Any] = field(default_factory=dict)
    input_payload: dict[str, Any] = field(default_factory=dict)
    output_payload: dict[str, Any] = field(default_factory=dict)
    execution_policy: dict[str, Any] = field(default_factory=dict)
    approval_policy: dict[str, Any] = field(default_factory=dict)
    audit_metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "tool_id": str(self.tool_id or ""),
            "capability_id": str(self.capability_id or ""),
            "status": str(self.status or ""),
            "run_id": str(self.run_id or ""),
            "trace_id": str(self.trace_id or ""),
            "started_at": str(self.started_at or ""),
            "finished_at": str(self.finished_at or ""),
            "duration_ms": int(self.duration_ms or 0),
            "tool_call_id": str(self.tool_call_id or ""),
            "tool_name": str(self.tool_name or self.tool_id or ""),
            "arguments": dict(self.arguments or {}),
            "execution_status": str(self.execution_status or self.status or ""),
            "validation_status": str(self.validation_status or ""),
            "evidence_metadata": dict(self.evidence_metadata or {}),
            "model_response_id": str(self.model_response_id or ""),
            "loop_iteration": int(self.loop_iteration or 0),
            "tool_definition": dict(self.tool_definition or {}),
            "input_payload": dict(self.input_payload or {}),
            "output_payload": dict(self.output_payload or {}),
            "execution_policy": dict(self.execution_policy or {}),
            "approval_policy": dict(self.approval_policy or {}),
            "audit_metadata": dict(self.audit_metadata or {}),
        }
