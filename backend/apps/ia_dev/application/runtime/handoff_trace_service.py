from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from apps.ia_dev.application.context.run_context import RunContext
from apps.ia_dev.application.contracts.runtime_governance_contracts import HandoffTraceContract


class HandoffTraceService:
    SERVICE_VERSION = "handoff_trace.v1"

    def build_handoff(
        self,
        *,
        run_context: RunContext | None,
        handoff_origin: str,
        handoff_target: str,
        requested_by_agent: str,
        reason: str,
        target_tool: str = "",
        evidence: dict[str, Any] | None = None,
        status: str = "completed",
    ) -> dict[str, Any]:
        now_iso = datetime.now(timezone.utc).isoformat()
        record = HandoffTraceContract(
            handoff_id=f"handoff_{uuid4().hex[:16]}",
            handoff_origin=str(handoff_origin or ""),
            handoff_target=str(handoff_target or ""),
            requested_by_agent=str(requested_by_agent or handoff_origin or ""),
            target_tool=str(target_tool or ""),
            reason=str(reason or ""),
            status=str(status or "completed"),
            evidence=dict(evidence or {}),
            created_at=now_iso,
        )
        payload = record.as_dict()
        payload.update(
            {
                "run_id": str((run_context.run_id if run_context else "") or ""),
                "trace_id": str((run_context.trace_id if run_context else "") or ""),
                "event": "handoff_recorded",
                "service_version": self.SERVICE_VERSION,
            }
        )
        return payload
