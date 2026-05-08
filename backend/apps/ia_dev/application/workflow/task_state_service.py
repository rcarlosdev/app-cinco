from __future__ import annotations

import time
from typing import Any

from apps.ia_dev.application.memory.repositories import MemoryRepository


class TaskStateService:
    WORKFLOW_TYPE_TASK_RUNTIME = "task_runtime"
    VALID_STATES = {
        "planned",
        "executing",
        "verified",
        "replanned",
        "needs_input",
        "completed",
        "failed",
    }

    def __init__(self, *, repo: MemoryRepository | None = None):
        self.repo = repo or MemoryRepository()

    @staticmethod
    def workflow_key_for_run(run_id: str) -> str:
        return f"task_runtime:{str(run_id or '').strip()}"

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
        existing = self.repo.get_workflow_state(workflow_key) or {}
        state = dict((existing or {}).get("state") or {})
        now = int(time.time())

        state.update(
            {
                "run_id": str(run_id or ""),
                "task_status": normalized_status,
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
        if "created_at" not in state:
            state["created_at"] = now

        history = list(state.get("history") or [])
        history.append(
            {
                "at": now,
                "status": normalized_status,
                "domain": str(detected_domain or state.get("detected_domain") or ""),
                "has_query": bool(str(executed_query or "").strip()),
                "fallback": dict(fallback_used or {}),
            }
        )
        state["history"] = history[-20:]

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
