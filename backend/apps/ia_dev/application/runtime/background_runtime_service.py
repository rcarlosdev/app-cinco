from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Callable
from uuid import uuid4

from apps.ia_dev.application.context.run_context import RunContext
from apps.ia_dev.application.contracts.background_run_contracts import (
    BackgroundCancellationMetadataContract,
    BackgroundPollingMetadataContract,
    BackgroundRetryMetadataContract,
    BackgroundRunContract,
    BackgroundTimeoutMetadataContract,
    VALID_BACKGROUND_RUN_STATUSES,
)
from apps.ia_dev.application.runtime.checkpoint_service import CheckpointService
from apps.ia_dev.application.runtime.runtime_hardening_service import RuntimeHardeningService
from apps.ia_dev.application.workflow.task_state_service import TaskStateService


class BackgroundRuntimeService:
    SERVICE_VERSION = "background_runtime.v1"
    DEFAULT_POLL_INTERVAL_MS = 1000
    DEFAULT_MAX_RETRIES = 2

    def __init__(
        self,
        *,
        task_state_service: TaskStateService | None = None,
        checkpoint_service: CheckpointService | None = None,
        runtime_hardening_service: RuntimeHardeningService | None = None,
    ) -> None:
        self.task_state_service = task_state_service or TaskStateService()
        self.checkpoint_service = checkpoint_service or CheckpointService()
        self.runtime_hardening_service = runtime_hardening_service or RuntimeHardeningService()

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _normalize_status(status: str, *, fallback: str = "queued") -> str:
        normalized = str(status or "").strip().lower() or fallback
        if normalized not in VALID_BACKGROUND_RUN_STATUSES:
            return fallback
        return normalized

    @classmethod
    def should_run_in_background(
        cls,
        *,
        tool_definition=None,
        arguments: dict[str, Any] | None = None,
        execution_plan: dict[str, Any] | None = None,
        approval_pending: bool = False,
    ) -> dict[str, Any]:
        payload = dict(arguments or {})
        plan = dict(execution_plan or {})
        metadata = dict(plan.get("metadata") or {})
        timeout_seconds = int(metadata.get("timeout_seconds") or payload.get("timeout_seconds") or 0)
        estimated_duration = int(metadata.get("estimated_duration_seconds") or payload.get("estimated_duration_seconds") or 0)
        if approval_pending:
            return {"enabled": True, "reason": "approval_pending", "status": "awaiting_approval"}
        if bool(getattr(getattr(tool_definition, "execution_policy", None), "supports_background", False)):
            return {"enabled": True, "reason": "tool_declares_background", "status": "queued"}
        if bool(payload.get("background")):
            return {"enabled": True, "reason": "runtime_policy_requested", "status": "queued"}
        if bool(metadata.get("background_requested")):
            return {"enabled": True, "reason": "execution_plan_background_requested", "status": "queued"}
        if estimated_duration >= 30 or timeout_seconds >= 30:
            return {"enabled": True, "reason": "runtime_policy_long_task", "status": "queued"}
        return {"enabled": False, "reason": "", "status": ""}

    def build_background_state(
        self,
        *,
        run_context: RunContext,
        status: str,
        tool_id: str = "",
        policy_reason: str = "",
        resume_token: str = "",
        partial_evidence: dict[str, Any] | None = None,
        final_evidence: dict[str, Any] | None = None,
        failure_reason: str = "",
        timeout_seconds: int = 0,
        checkpoint: dict[str, Any] | None = None,
        existing_background: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        existing = dict(existing_background or {})
        now_iso = self._now_iso()
        run_status = self._normalize_status(status)
        requested_at = str(existing.get("requested_at") or now_iso)
        background_run_id = str(existing.get("background_run_id") or f"bg_{uuid4().hex[:16]}")
        job_id = str(existing.get("job_id") or f"job_{run_context.run_id}")
        queue_status = "queued" if run_status in {"queued", "awaiting_approval"} else "dequeued"
        if run_status in {"cancelled", "completed", "failed", "expired", "partial"}:
            queue_status = "finished"
        polling = BackgroundPollingMetadataContract(
            poll_interval_ms=int(((existing.get("polling") or {}).get("poll_interval_ms") or self.DEFAULT_POLL_INTERVAL_MS)),
            next_poll_after_ms=int(((existing.get("polling") or {}).get("next_poll_after_ms") or self.DEFAULT_POLL_INTERVAL_MS)),
            last_polled_at=str(((existing.get("polling") or {}).get("last_polled_at") or "")),
            endpoint_hint=str(((existing.get("polling") or {}).get("endpoint_hint") or "/ia-dev/chat/task-status/")),
        )
        retry = BackgroundRetryMetadataContract(
            retry_count=int(((existing.get("retry") or {}).get("retry_count") or 0)),
            max_retries=int(
                ((existing.get("retry") or {}).get("max_retries") or self.runtime_hardening_service.max_background_retries())
            ),
            next_retry_at=str(((existing.get("retry") or {}).get("next_retry_at") or "")),
            last_retry_reason=str(((existing.get("retry") or {}).get("last_retry_reason") or "")),
        )
        deadline_at = ""
        effective_timeout_seconds = self.runtime_hardening_service.normalize_timeout_seconds(timeout_seconds)
        if effective_timeout_seconds > 0:
            deadline_at = (datetime.now(timezone.utc) + timedelta(seconds=int(effective_timeout_seconds))).isoformat()
        timeout = BackgroundTimeoutMetadataContract(
            timeout_seconds=int(
                effective_timeout_seconds or ((existing.get("timeout") or {}).get("timeout_seconds") or 0)
            ),
            deadline_at=str(((existing.get("timeout") or {}).get("deadline_at") or deadline_at)),
            expired_at=str(((existing.get("timeout") or {}).get("expired_at") or "")),
            timeout_reason=str(((existing.get("timeout") or {}).get("timeout_reason") or "")),
        )
        cancellation = BackgroundCancellationMetadataContract(
            cancel_requested=bool(((existing.get("cancellation") or {}).get("cancel_requested"))),
            cancel_requested_at=str(((existing.get("cancellation") or {}).get("cancel_requested_at") or "")),
            cancelled_at=str(((existing.get("cancellation") or {}).get("cancelled_at") or "")),
            cancelled_by=str(((existing.get("cancellation") or {}).get("cancelled_by") or "")),
            cancellation_reason=str(((existing.get("cancellation") or {}).get("cancellation_reason") or "")),
        )
        contract = BackgroundRunContract(
            background_run_id=background_run_id,
            job_id=job_id,
            queue_status=queue_status,
            run_status=run_status,
            polling=polling,
            retry=retry,
            timeout=timeout,
            cancellation=cancellation,
            resume_token=str(resume_token or existing.get("resume_token") or ""),
            checkpoint=dict(checkpoint or existing.get("checkpoint") or {}),
            partial_evidence=dict(partial_evidence or existing.get("partial_evidence") or {}),
            final_evidence=dict(final_evidence or existing.get("final_evidence") or {}),
            failure_reason=str(failure_reason or existing.get("failure_reason") or ""),
            requested_by=str(existing.get("requested_by") or "runtime"),
            requested_at=requested_at,
            started_at=str(existing.get("started_at") or (now_iso if run_status in {"running", "resumed"} else "")),
            finished_at=str(existing.get("finished_at") or (now_iso if run_status in {"completed", "failed", "cancelled", "expired", "partial"} else "")),
            tool_id=str(tool_id or existing.get("tool_id") or ""),
            policy_reason=str(policy_reason or existing.get("policy_reason") or ""),
        )
        return contract.as_dict()

    def apply_runtime_state(
        self,
        *,
        run_context: RunContext,
        background: dict[str, Any],
        background_trace: list[dict[str, Any]] | None = None,
        checkpoints: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        existing_state = dict(run_context.metadata.get("background_runtime") or {})
        runtime_state = {
            **existing_state,
            "background": dict(background or {}),
            "background_trace": [dict(item) for item in list(background_trace or []) if isinstance(item, dict)],
            "checkpoints": [dict(item) for item in list(checkpoints or []) if isinstance(item, dict)],
        }
        run_context.metadata["background_runtime"] = runtime_state
        return runtime_state

    def queue_run(
        self,
        *,
        run_context: RunContext,
        tool_id: str,
        policy_reason: str,
        partial_evidence: dict[str, Any] | None = None,
        timeout_seconds: int = 0,
    ) -> dict[str, Any]:
        existing_state = dict(run_context.metadata.get("background_runtime") or {})
        existing_background = dict(existing_state.get("background") or {})
        if str(existing_background.get("tool_id") or "") == str(tool_id or "") and str(existing_background.get("run_status") or "") in {
            "queued",
            "running",
            "awaiting_approval",
            "paused",
            "resumed",
        }:
            existing_trace = list(existing_state.get("background_trace") or [])
            trace = self.checkpoint_service.append_limited(
                existing_trace,
                self.checkpoint_service.build_progress_event(
                    event_type="background_run_queue_idempotent",
                    status=str(existing_background.get("run_status") or "queued"),
                    sequence=len(existing_trace) + 1,
                    message="La corrida background reutilizo un estado activo existente.",
                    progress_pct=0.0,
                    evidence={"tool_id": tool_id},
                ),
            )
            return self.apply_runtime_state(
                run_context=run_context,
                background=existing_background,
                background_trace=trace,
                checkpoints=list(existing_state.get("checkpoints") or []),
            )
        background = self.build_background_state(
            run_context=run_context,
            status="queued",
            tool_id=tool_id,
            policy_reason=policy_reason,
            partial_evidence=dict(self.runtime_hardening_service.sanitize_payload(dict(partial_evidence or {}))),
            timeout_seconds=timeout_seconds,
            existing_background=existing_background,
        )
        trace = [
            self.checkpoint_service.build_progress_event(
                event_type="background_run_queued",
                status="queued",
                sequence=1,
                message="La corrida fue enviada a background.",
                progress_pct=0.0,
                evidence={"tool_id": tool_id, "policy_reason": policy_reason},
            )
        ]
        return self.apply_runtime_state(run_context=run_context, background=background, background_trace=trace, checkpoints=[])

    def mark_awaiting_approval(
        self,
        *,
        run_context: RunContext,
        resume_token: str,
        partial_evidence: dict[str, Any] | None = None,
        tool_id: str = "",
    ) -> dict[str, Any]:
        existing_state = dict(run_context.metadata.get("background_runtime") or {})
        trace = list(existing_state.get("background_trace") or [])
        checkpoints = list(existing_state.get("checkpoints") or [])
        background = self.build_background_state(
            run_context=run_context,
            status="awaiting_approval",
            tool_id=tool_id,
            policy_reason="approval_pending",
            resume_token=resume_token,
            partial_evidence=dict(self.runtime_hardening_service.sanitize_payload(dict(partial_evidence or {}))),
            existing_background=dict(existing_state.get("background") or {}),
        )
        trace = self.checkpoint_service.append_limited(
            trace,
            self.checkpoint_service.build_progress_event(
                event_type="background_run_awaiting_approval",
                status="awaiting_approval",
                sequence=len(trace) + 1,
                message="La corrida quedo pausada esperando approval.",
                progress_pct=25.0,
                evidence={"resume_token": resume_token},
            ),
        )
        return self.apply_runtime_state(
            run_context=run_context,
            background=background,
            background_trace=trace,
            checkpoints=checkpoints,
        )

    def mark_started(self, *, workflow: dict[str, Any]) -> dict[str, Any]:
        return self._transition_existing_workflow(
            workflow=workflow,
            status="running",
            event_type="background_run_started",
            message="La corrida comenzo a ejecutarse.",
            progress_pct=10.0,
        )

    def add_checkpoint(
        self,
        *,
        workflow: dict[str, Any],
        label: str,
        checkpoint_state: dict[str, Any] | None = None,
        progress: dict[str, Any] | None = None,
        evidence: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        state = dict((workflow or {}).get("state") or {})
        checkpoints = list(state.get("checkpoints") or [])
        sanitized_evidence = dict(self.runtime_hardening_service.sanitize_payload(dict(evidence or {})))
        checkpoint = self.checkpoint_service.build_checkpoint(
            label=label,
            sequence=len(checkpoints) + 1,
            checkpoint_state=checkpoint_state,
            progress=progress,
            evidence=sanitized_evidence,
        )
        checkpoints = self.checkpoint_service.append_limited(checkpoints, checkpoint)
        trace = list(state.get("background_trace") or [])
        trace = self.checkpoint_service.append_limited(
            trace,
            self.checkpoint_service.build_progress_event(
                event_type="background_run_checkpoint",
                status=str(((state.get("background") or {}).get("run_status") or "running")),
                sequence=len(trace) + 1,
                message=f"Checkpoint registrado: {label}.",
                progress_pct=float((dict(progress or {}).get("progress_pct") or 0.0)),
                evidence=sanitized_evidence,
            ),
        )
        return self.task_state_service.update_state(
            run_id=str(state.get("run_id") or ""),
            extra_state={
                "background": {
                    **dict(state.get("background") or {}),
                    "checkpoint": checkpoint,
                    "last_progress_update_at": str(
                        sanitized_evidence.get("last_progress_update_at")
                        or ((state.get("background") or {}).get("last_progress_update_at") or "")
                    ),
                    "progress_snapshot": dict(
                        sanitized_evidence or (state.get("background") or {}).get("progress_snapshot") or {}
                    ),
                    "partial_evidence": dict(
                        sanitized_evidence or (state.get("background") or {}).get("partial_evidence") or {}
                    ),
                },
                "background_trace": trace,
                "checkpoints": checkpoints,
            },
        )

    def add_progress(
        self,
        *,
        workflow: dict[str, Any],
        message: str,
        progress_pct: float,
        partial_evidence: dict[str, Any] | None = None,
        status: str | None = None,
    ) -> dict[str, Any]:
        state = dict((workflow or {}).get("state") or {})
        current_background = dict(state.get("background") or {})
        run_status = self._normalize_status(status or current_background.get("run_status") or "running", fallback="running")
        trace = list(state.get("background_trace") or [])
        trace = self.checkpoint_service.append_limited(
            trace,
            self.checkpoint_service.build_progress_event(
                event_type="background_run_progress",
                status=run_status,
                sequence=len(trace) + 1,
                message=message,
                progress_pct=progress_pct,
                evidence=dict(self.runtime_hardening_service.sanitize_payload(dict(partial_evidence or {}))),
            ),
        )
        background = {
            **current_background,
            "run_status": run_status,
            "last_progress_update_at": str(
                dict(partial_evidence or {}).get("last_progress_update_at")
                or current_background.get("last_progress_update_at")
                or ""
            ),
            "progress_snapshot": dict(self.runtime_hardening_service.sanitize_payload(dict(partial_evidence or {}))),
            "partial_evidence": {
                **dict(current_background.get("partial_evidence") or {}),
                **dict(self.runtime_hardening_service.sanitize_payload(dict(partial_evidence or {}))),
            },
        }
        return self.task_state_service.update_state(
            run_id=str(state.get("run_id") or ""),
            status=run_status,
            extra_state={
                "background": background,
                "background_trace": trace,
            },
        )

    def complete_run(
        self,
        *,
        workflow: dict[str, Any],
        final_evidence: dict[str, Any] | None = None,
        response_snapshot: dict[str, Any] | None = None,
        tool_execution_trace: list[dict[str, Any]] | None = None,
        agent_trace_append: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        return self._transition_existing_workflow(
            workflow=workflow,
            status="completed",
            event_type="background_run_completed",
            message="La corrida background finalizo.",
            progress_pct=100.0,
            final_evidence=final_evidence,
            response_snapshot=response_snapshot,
            tool_execution_trace=tool_execution_trace,
            agent_trace_append=agent_trace_append,
        )

    def fail_run(
        self,
        *,
        workflow: dict[str, Any],
        failure_reason: str,
        final_evidence: dict[str, Any] | None = None,
        response_snapshot: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        state = dict((workflow or {}).get("state") or {})
        retry = dict((state.get("background") or {}).get("retry") or {})
        retry_count = int(retry.get("retry_count") or 0) + 1
        failed_workflow = self._transition_existing_workflow(
            workflow=workflow,
            status="failed",
            event_type="background_run_failed",
            message="La corrida background fallo.",
            progress_pct=100.0,
            failure_reason=failure_reason,
            final_evidence=final_evidence,
            response_snapshot=response_snapshot,
            background_updates={
                "retry": {
                    **retry,
                    "retry_count": retry_count,
                    "last_retry_reason": str(failure_reason or ""),
                }
            },
        )
        max_retries = int(retry.get("max_retries") or self.runtime_hardening_service.max_background_retries())
        if retry_count > max_retries:
            failed_state = dict((failed_workflow or {}).get("state") or {})
            return self.task_state_service.update_state(
                run_id=str(failed_state.get("run_id") or ""),
                extra_state={
                    "dead_letter": self.runtime_hardening_service.build_dead_letter_entry(
                        run_id=str(failed_state.get("run_id") or ""),
                        tool_id=str((failed_state.get("background") or {}).get("tool_id") or ""),
                        failure_reason=failure_reason,
                        retry_count=retry_count,
                    )
                },
            )
        return failed_workflow

    def cancel_run(self, *, run_id: str, cancelled_by: str, reason: str) -> dict[str, Any]:
        workflow = self.task_state_service.get(run_id=run_id) or {}
        state = dict((workflow or {}).get("state") or {})
        background = dict(state.get("background") or {})
        cancellation = {
            **dict(background.get("cancellation") or {}),
            "cancel_requested": True,
            "cancel_requested_at": self._now_iso(),
            "cancelled_at": self._now_iso(),
            "cancelled_by": str(cancelled_by or ""),
            "cancellation_reason": str(reason or ""),
        }
        return self._transition_existing_workflow(
            workflow=workflow,
            status="cancelled",
            event_type="background_run_cancelled",
            message="La corrida background fue cancelada.",
            progress_pct=100.0,
            background_updates={"cancellation": cancellation},
        )

    def expire_run(self, *, workflow: dict[str, Any], timeout_reason: str) -> dict[str, Any]:
        state = dict((workflow or {}).get("state") or {})
        timeout = {
            **dict(((state.get("background") or {}).get("timeout") or {})),
            "expired_at": self._now_iso(),
            "timeout_reason": str(timeout_reason or "expired"),
        }
        return self._transition_existing_workflow(
            workflow=workflow,
            status="expired",
            event_type="background_run_failed",
            message="La corrida background expiro.",
            progress_pct=100.0,
            failure_reason=timeout_reason,
            background_updates={"timeout": timeout},
        )

    def poll_run(
        self,
        *,
        run_id: str | None = None,
        background_run_id: str | None = None,
        resume_token: str | None = None,
    ) -> dict[str, Any]:
        workflow = self._resolve_workflow(
            run_id=run_id,
            background_run_id=background_run_id,
            resume_token=resume_token,
        )
        state = dict((workflow or {}).get("state") or {})
        background = dict(state.get("background") or {})
        return {
            "workflow_key": str((workflow or {}).get("workflow_key") or ""),
            "task_status": str((workflow or {}).get("status") or state.get("task_status") or ""),
            "background": background,
            "background_trace": [dict(item) for item in list(state.get("background_trace") or []) if isinstance(item, dict)],
            "checkpoints": [dict(item) for item in list(state.get("checkpoints") or []) if isinstance(item, dict)],
            "approvals": [dict(item) for item in list(state.get("approvals") or []) if isinstance(item, dict)],
            "approval_trace": [dict(item) for item in list(state.get("approval_trace") or []) if isinstance(item, dict)],
            "agent_trace": [dict(item) for item in list(state.get("agent_trace") or []) if isinstance(item, dict)],
            "tool_execution_trace": [dict(item) for item in list(state.get("tool_execution_trace") or []) if isinstance(item, dict)],
        }

    def enforce_run_expiration(self, *, workflow: dict[str, Any]) -> dict[str, Any]:
        state = dict((workflow or {}).get("state") or {})
        timeout = dict(((state.get("background") or {}).get("timeout") or {}))
        deadline_raw = str(timeout.get("deadline_at") or "")
        deadline = self.runtime_hardening_service._parse_iso_datetime(deadline_raw)
        if deadline is None or datetime.now(timezone.utc) <= deadline:
            return workflow
        return self.expire_run(workflow=workflow, timeout_reason="background_deadline_exceeded")

    def resume_after_approval(
        self,
        *,
        resume_token: str,
        approved_by: str,
        approver_role: str,
        approval_runtime_service,
        evidence_after_approval: dict[str, Any] | None = None,
        final_evidence: dict[str, Any] | None = None,
        tool_execution_trace: list[dict[str, Any]] | None = None,
        agent_trace_append: list[dict[str, Any]] | None = None,
        on_resume: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        workflow = self._resolve_workflow(resume_token=resume_token)
        state = dict((workflow or {}).get("state") or {})
        approvals = [dict(item) for item in list(state.get("approvals") or []) if isinstance(item, dict)]
        selected_approval = next((item for item in approvals if str(item.get("resume_token") or "") == str(resume_token or "")), {})
        if not selected_approval:
            raise ValueError("resume_token_not_found")
        expires_at = self.runtime_hardening_service._parse_iso_datetime(str(selected_approval.get("expires_at") or ""))
        if expires_at is not None and datetime.now(timezone.utc) > expires_at:
            rejected = approval_runtime_service.reject_request(
                request=selected_approval,
                rejected_reason="approval_wait_expired",
                approved_by=approved_by,
                approver_role=approver_role,
                evidence_after_approval=evidence_after_approval,
            )
            updated_approval = dict(rejected.get("approval") or {})
            updated_approvals = [
                updated_approval if str(item.get("approval_request_id") or "") == str(updated_approval.get("approval_request_id") or "") else item
                for item in approvals
            ]
            approval_trace = list(state.get("approval_trace") or [])
            approval_trace.append(dict(rejected.get("approval_trace") or {}))
            return self._transition_existing_workflow(
                workflow=workflow,
                status="failed",
                event_type="background_run_approval_expired",
                message="La corrida fallo porque el approval expiro.",
                progress_pct=100.0,
                failure_reason="approval_wait_expired",
                extra_state={
                    "approvals": updated_approvals,
                    "approval_trace": approval_trace,
                },
            )
        approval_result = approval_runtime_service.approve_request(
            request=selected_approval,
            approved_by=approved_by,
            approver_role=approver_role,
            evidence_after_approval=evidence_after_approval,
        )
        updated_approval = dict(approval_result.get("approval") or {})
        updated_approvals = [
            updated_approval if str(item.get("approval_request_id") or "") == str(updated_approval.get("approval_request_id") or "") else item
            for item in approvals
        ]
        approval_trace = list(state.get("approval_trace") or [])
        approval_trace.append(dict(approval_result.get("approval_trace") or {}))
        resumed = self._transition_existing_workflow(
            workflow=workflow,
            status="resumed",
            event_type="background_run_resumed",
            message="La corrida background fue reanudada.",
            progress_pct=50.0,
            background_updates={"resume_token": str(resume_token or "")},
            extra_state={
                "approvals": updated_approvals,
                "approval_trace": approval_trace,
            },
        )
        if callable(on_resume):
            resumed = dict(on_resume(resumed) or resumed)
        if final_evidence is not None or tool_execution_trace or agent_trace_append:
            return self.complete_run(
                workflow=resumed,
                final_evidence=final_evidence,
                tool_execution_trace=tool_execution_trace,
                agent_trace_append=agent_trace_append,
            )
        return resumed

    def _transition_existing_workflow(
        self,
        *,
        workflow: dict[str, Any],
        status: str,
        event_type: str,
        message: str,
        progress_pct: float,
        failure_reason: str = "",
        final_evidence: dict[str, Any] | None = None,
        background_updates: dict[str, Any] | None = None,
        extra_state: dict[str, Any] | None = None,
        response_snapshot: dict[str, Any] | None = None,
        tool_execution_trace: list[dict[str, Any]] | None = None,
        agent_trace_append: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        state = dict((workflow or {}).get("state") or {})
        current_background = dict(state.get("background") or {})
        run_id = str(state.get("run_id") or "")
        trace = list(state.get("background_trace") or [])
        trace = self.checkpoint_service.append_limited(
            trace,
            self.checkpoint_service.build_progress_event(
                event_type=event_type,
                status=status,
                sequence=len(trace) + 1,
                message=message,
                progress_pct=progress_pct,
                evidence=dict(final_evidence or {}),
            ),
        )
        background = {
            **current_background,
            "run_status": status,
            "queue_status": "finished" if status in {"completed", "failed", "cancelled", "expired", "partial"} else "dequeued",
            "failure_reason": str(failure_reason or current_background.get("failure_reason") or ""),
            "final_evidence": dict(final_evidence or current_background.get("final_evidence") or {}),
            "finished_at": self._now_iso() if status in {"completed", "failed", "cancelled", "expired", "partial"} else str(current_background.get("finished_at") or ""),
        }
        if background_updates:
            background.update(dict(background_updates or {}))
        merged_extra_state = dict(extra_state or {})
        if tool_execution_trace:
            merged_extra_state["tool_execution_trace"] = [
                *[dict(item) for item in list(state.get("tool_execution_trace") or []) if isinstance(item, dict)],
                *[dict(item) for item in list(tool_execution_trace or []) if isinstance(item, dict)],
            ]
        if agent_trace_append:
            merged_extra_state["agent_trace"] = [
                *[dict(item) for item in list(state.get("agent_trace") or []) if isinstance(item, dict)],
                *[dict(item) for item in list(agent_trace_append or []) if isinstance(item, dict)],
            ]
        if response_snapshot is not None:
            merged_extra_state["response_snapshot"] = dict(
                self.runtime_hardening_service.sanitize_payload(dict(response_snapshot or {}))
            )
        merged_extra_state.update(
            {
                "background": background,
                "background_trace": trace,
            }
        )
        return self.task_state_service.update_state(
            run_id=run_id,
            status=status,
            extra_state=merged_extra_state,
        )

    def _resolve_workflow(
        self,
        *,
        run_id: str | None = None,
        background_run_id: str | None = None,
        resume_token: str | None = None,
    ) -> dict[str, Any]:
        if str(run_id or "").strip():
            workflow = self.task_state_service.get(run_id=str(run_id or "").strip())
            if workflow:
                return workflow
        if str(resume_token or "").strip():
            workflow = self.task_state_service.find_by_resume_token(str(resume_token or "").strip())
            if workflow:
                return workflow
        if str(background_run_id or "").strip():
            workflow = self.task_state_service.find_by_background_run_id(str(background_run_id or "").strip())
            if workflow:
                return workflow
        raise ValueError("background_workflow_not_found")
