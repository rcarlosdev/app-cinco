from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


VALID_BACKGROUND_RUN_STATUSES = {
    "queued",
    "running",
    "awaiting_approval",
    "paused",
    "resumed",
    "completed",
    "failed",
    "cancelled",
    "expired",
}


@dataclass(slots=True)
class BackgroundPollingMetadataContract:
    poll_interval_ms: int = 0
    next_poll_after_ms: int = 0
    last_polled_at: str = ""
    endpoint_hint: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "poll_interval_ms": int(self.poll_interval_ms or 0),
            "next_poll_after_ms": int(self.next_poll_after_ms or 0),
            "last_polled_at": str(self.last_polled_at or ""),
            "endpoint_hint": str(self.endpoint_hint or ""),
        }


@dataclass(slots=True)
class BackgroundRetryMetadataContract:
    retry_count: int = 0
    max_retries: int = 0
    next_retry_at: str = ""
    last_retry_reason: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "retry_count": int(self.retry_count or 0),
            "max_retries": int(self.max_retries or 0),
            "next_retry_at": str(self.next_retry_at or ""),
            "last_retry_reason": str(self.last_retry_reason or ""),
        }


@dataclass(slots=True)
class BackgroundTimeoutMetadataContract:
    timeout_seconds: int = 0
    deadline_at: str = ""
    expired_at: str = ""
    timeout_reason: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "timeout_seconds": int(self.timeout_seconds or 0),
            "deadline_at": str(self.deadline_at or ""),
            "expired_at": str(self.expired_at or ""),
            "timeout_reason": str(self.timeout_reason or ""),
        }


@dataclass(slots=True)
class BackgroundCancellationMetadataContract:
    cancel_requested: bool = False
    cancel_requested_at: str = ""
    cancelled_at: str = ""
    cancelled_by: str = ""
    cancellation_reason: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "cancel_requested": bool(self.cancel_requested),
            "cancel_requested_at": str(self.cancel_requested_at or ""),
            "cancelled_at": str(self.cancelled_at or ""),
            "cancelled_by": str(self.cancelled_by or ""),
            "cancellation_reason": str(self.cancellation_reason or ""),
        }


@dataclass(slots=True)
class BackgroundCheckpointContract:
    checkpoint_id: str
    sequence: int
    label: str
    created_at: str
    checkpoint_state: dict[str, Any] = field(default_factory=dict)
    progress: dict[str, Any] = field(default_factory=dict)
    evidence: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "checkpoint_id": str(self.checkpoint_id or ""),
            "sequence": int(self.sequence or 0),
            "label": str(self.label or ""),
            "created_at": str(self.created_at or ""),
            "checkpoint_state": dict(self.checkpoint_state or {}),
            "progress": dict(self.progress or {}),
            "evidence": dict(self.evidence or {}),
        }


@dataclass(slots=True)
class BackgroundProgressEventContract:
    event_id: str
    event_type: str
    status: str
    created_at: str
    sequence: int = 0
    message: str = ""
    progress_pct: float = 0.0
    evidence: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "event_id": str(self.event_id or ""),
            "event_type": str(self.event_type or ""),
            "status": str(self.status or ""),
            "created_at": str(self.created_at or ""),
            "sequence": int(self.sequence or 0),
            "message": str(self.message or ""),
            "progress_pct": float(self.progress_pct or 0.0),
            "evidence": dict(self.evidence or {}),
        }


@dataclass(slots=True)
class BackgroundRunContract:
    background_run_id: str
    job_id: str
    queue_status: str
    run_status: str
    polling: BackgroundPollingMetadataContract = field(default_factory=BackgroundPollingMetadataContract)
    retry: BackgroundRetryMetadataContract = field(default_factory=BackgroundRetryMetadataContract)
    timeout: BackgroundTimeoutMetadataContract = field(default_factory=BackgroundTimeoutMetadataContract)
    cancellation: BackgroundCancellationMetadataContract = field(default_factory=BackgroundCancellationMetadataContract)
    resume_token: str = ""
    checkpoint: dict[str, Any] = field(default_factory=dict)
    partial_evidence: dict[str, Any] = field(default_factory=dict)
    final_evidence: dict[str, Any] = field(default_factory=dict)
    failure_reason: str = ""
    requested_by: str = ""
    requested_at: str = ""
    started_at: str = ""
    finished_at: str = ""
    tool_id: str = ""
    policy_reason: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "background_run_id": str(self.background_run_id or ""),
            "job_id": str(self.job_id or ""),
            "queue_status": str(self.queue_status or ""),
            "run_status": str(self.run_status or ""),
            "polling": self.polling.as_dict(),
            "retry": self.retry.as_dict(),
            "timeout": self.timeout.as_dict(),
            "cancellation": self.cancellation.as_dict(),
            "resume_token": str(self.resume_token or ""),
            "checkpoint": dict(self.checkpoint or {}),
            "partial_evidence": dict(self.partial_evidence or {}),
            "final_evidence": dict(self.final_evidence or {}),
            "failure_reason": str(self.failure_reason or ""),
            "requested_by": str(self.requested_by or ""),
            "requested_at": str(self.requested_at or ""),
            "started_at": str(self.started_at or ""),
            "finished_at": str(self.finished_at or ""),
            "tool_id": str(self.tool_id or ""),
            "policy_reason": str(self.policy_reason or ""),
        }
