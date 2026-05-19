from __future__ import annotations

import time
from typing import Any

from apps.ia_dev.application.memory.repositories import MemoryRepository
from apps.ia_dev.application.runtime.runtime_hardening_service import RuntimeHardeningService


class TaskStateService:
    WORKFLOW_TYPE_TASK_RUNTIME = "task_runtime"
    VALID_STATES = {
        "planned",
        "executing",
        "queued",
        "running",
        "partial",
        "awaiting_approval",
        "paused",
        "resumed",
        "approved",
        "rejected",
        "blocked",
        "verified",
        "replanned",
        "needs_input",
        "completed",
        "failed",
        "cancelled",
        "expired",
    }

    def __init__(self, *, repo: MemoryRepository | None = None):
        self.repo = repo or MemoryRepository()
        self.runtime_hardening_service = RuntimeHardeningService()

    @staticmethod
    def workflow_key_for_run(run_id: str) -> str:
        return f"task_runtime:{str(run_id or '').strip()}"

    @classmethod
    def task_id_for_run(cls, run_id: str) -> str:
        return cls.workflow_key_for_run(run_id)

    def save(
        self,
        *,
        run_id: str,
        status: str,
        original_question: str,
        detected_domain: str | None = None,
        plan: dict[str, Any] | None = None,
        source_used: dict[str, Any] | None = None,
        executed_query: str | None = None,
        validation_result: dict[str, Any] | None = None,
        fallback_used: dict[str, Any] | None = None,
        recommendations: list[str] | None = None,
        extra_state: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        normalized_status = str(status or "").strip().lower() or "planned"
        if normalized_status not in self.VALID_STATES:
            raise ValueError(f"invalid_task_state:{normalized_status}")

        workflow_key = self.workflow_key_for_run(run_id)
        task_id = self.task_id_for_run(run_id)
        existing = self.repo.get_workflow_state(workflow_key) or {}
        state = dict((existing or {}).get("state") or {})
        now = int(time.time())

        state.update(
            {
                "run_id": str(run_id or ""),
                "task_id": task_id,
                "task_status": normalized_status,
                "status": normalized_status,
                "original_question": str(original_question or ""),
                "detected_domain": str(detected_domain or state.get("detected_domain") or ""),
                "plan": dict(plan or state.get("plan") or {}),
                "source_used": dict(source_used or state.get("source_used") or {}),
                "executed_query": str(executed_query or state.get("executed_query") or ""),
                "validation_result": dict(validation_result or state.get("validation_result") or {}),
                "fallback_used": dict(fallback_used or state.get("fallback_used") or {}),
                "recommendations": list(recommendations or state.get("recommendations") or []),
                "updated_at": now,
            }
        )
        if extra_state:
            state.update(dict(extra_state))
        if not isinstance(state.get("tool_execution"), dict):
            state["tool_execution"] = {}
        if not isinstance(state.get("tool_execution_trace"), list):
            state["tool_execution_trace"] = []
        if not isinstance(state.get("agents"), list):
            state["agents"] = []
        if not isinstance(state.get("handoffs"), list):
            state["handoffs"] = []
        if not isinstance(state.get("handoff_trace"), list):
            state["handoff_trace"] = []
        if not isinstance(state.get("agent_trace"), list):
            state["agent_trace"] = []
        if not isinstance(state.get("approvals"), list):
            state["approvals"] = []
        if not isinstance(state.get("approval_trace"), list):
            state["approval_trace"] = []
        if not isinstance(state.get("background"), dict):
            state["background"] = {}
        if not isinstance(state.get("background_trace"), list):
            state["background_trace"] = []
        if not isinstance(state.get("checkpoints"), list):
            state["checkpoints"] = []
        if not isinstance(state.get("correlation"), dict):
            state["correlation"] = {}
        if not isinstance(state.get("governance"), dict):
            state["governance"] = {}
        if not isinstance(state.get("runtime_metrics"), dict):
            state["runtime_metrics"] = {}
        if not isinstance(state.get("dead_letter"), dict):
            state["dead_letter"] = {}
        if "created_at" not in state:
            state["created_at"] = now

        state["correlation"] = {
            **dict(state.get("correlation") or {}),
            "run_id": str(run_id or ""),
            "task_id": task_id,
        }
        state["governance"] = {
            **dict(state.get("governance") or {}),
            "policy_version": self.runtime_hardening_service.SERVICE_VERSION,
            "limits": {
                "max_tool_loop_rounds": self.runtime_hardening_service.max_tool_loop_rounds(),
                "max_tool_calls_per_run": self.runtime_hardening_service.max_tool_calls_per_run(),
                "max_background_retries": self.runtime_hardening_service.max_background_retries(),
                "max_background_duration_seconds": self.runtime_hardening_service.max_background_duration_seconds(),
                "max_approval_wait_seconds": self.runtime_hardening_service.max_approval_wait_seconds(),
            },
        }

        history = list(state.get("history") or [])
        tool_execution = dict(state.get("tool_execution") or {})
        tool_trace = list(state.get("tool_execution_trace") or [])
        agents = list(state.get("agents") or [])
        handoffs = list(state.get("handoffs") or [])
        approvals = list(state.get("approvals") or [])
        background = dict(state.get("background") or {})
        checkpoints = list(state.get("checkpoints") or [])
        history.append(
            {
                "at": now,
                "task_id": task_id,
                "run_id": str(run_id or ""),
                "status": normalized_status,
                "domain": str(detected_domain or state.get("detected_domain") or ""),
                "has_query": bool(str(executed_query or "").strip()),
                "fallback": dict(fallback_used or {}),
                "selected_tool_id": str(tool_execution.get("selected_tool_id") or ""),
                "tool_trace_count": len(tool_trace),
                "agent_count": len(agents),
                "handoff_count": len(handoffs),
                "approval_count": len(approvals),
                "background_status": str(background.get("run_status") or ""),
                "background_run_id": str(background.get("background_run_id") or ""),
                "checkpoint_count": len(checkpoints),
                "dead_lettered": bool(dict(state.get("dead_letter") or {}).get("dead_lettered")),
            }
        )
        state["history"] = history[-20:]
        state["runtime_metrics"] = self.runtime_hardening_service.build_runtime_metrics(state=state)

        self.repo.upsert_workflow_state(
            workflow_type=self.WORKFLOW_TYPE_TASK_RUNTIME,
            workflow_key=workflow_key,
            status=normalized_status,
            state=state,
            retry_count=int(existing.get("retry_count") or 0),
            lock_version=int(existing.get("lock_version") or 1),
            next_retry_at=None,
            last_error=str((extra_state or {}).get("error") or "") or None,
        )
        return self.repo.get_workflow_state(workflow_key) or {"workflow_key": workflow_key, "state": state}

    def get(self, *, run_id: str) -> dict[str, Any] | None:
        return self.repo.get_workflow_state(self.workflow_key_for_run(run_id))

    def update_state(
        self,
        *,
        run_id: str,
        status: str | None = None,
        extra_state: dict[str, Any] | None = None,
        validation_result: dict[str, Any] | None = None,
        fallback_used: dict[str, Any] | None = None,
        source_used: dict[str, Any] | None = None,
        plan: dict[str, Any] | None = None,
        recommendations: list[str] | None = None,
        executed_query: str | None = None,
        detected_domain: str | None = None,
        original_question: str | None = None,
    ) -> dict[str, Any]:
        existing = self.get(run_id=run_id) or {}
        state = dict((existing or {}).get("state") or {})
        if not state:
            raise ValueError(f"task_state_not_found:{run_id}")
        return self.save(
            run_id=run_id,
            status=str(status or state.get("task_status") or existing.get("status") or "planned"),
            original_question=str(original_question or state.get("original_question") or ""),
            detected_domain=str(detected_domain or state.get("detected_domain") or ""),
            plan=dict(plan or state.get("plan") or {}),
            source_used=dict(source_used or state.get("source_used") or {}),
            executed_query=str(executed_query or state.get("executed_query") or ""),
            validation_result=dict(validation_result or state.get("validation_result") or {}),
            fallback_used=dict(fallback_used or state.get("fallback_used") or {}),
            recommendations=list(recommendations or state.get("recommendations") or []),
            extra_state=dict(extra_state or {}),
        )

    def list(self, *, status: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        return self.repo.list_workflow_states(
            workflow_type=self.WORKFLOW_TYPE_TASK_RUNTIME,
            status=status,
            limit=limit,
        )

    def find_by_resume_token(self, resume_token: str, *, limit: int = 200) -> dict[str, Any] | None:
        token = str(resume_token or "").strip()
        if not token:
            return None
        direct_lookup = getattr(self.repo, "find_workflow_state_by_resume_token", None)
        if callable(direct_lookup):
            workflow = direct_lookup(token)
            if workflow:
                return workflow
        for workflow in self.list(limit=limit):
            state = dict((workflow or {}).get("state") or {})
            background = dict(state.get("background") or {})
            if str(background.get("resume_token") or "") == token:
                return workflow
            for approval in list(state.get("approvals") or []):
                if isinstance(approval, dict) and str(approval.get("resume_token") or "") == token:
                    return workflow
        return None

    def find_by_background_run_id(self, background_run_id: str, *, limit: int = 200) -> dict[str, Any] | None:
        target = str(background_run_id or "").strip()
        if not target:
            return None
        direct_lookup = getattr(self.repo, "find_workflow_state_by_background_run_id", None)
        if callable(direct_lookup):
            workflow = direct_lookup(target)
            if workflow:
                return workflow
        for workflow in self.list(limit=limit):
            state = dict((workflow or {}).get("state") or {})
            background = dict(state.get("background") or {})
            if str(background.get("background_run_id") or "") == target:
                return workflow
        return None
