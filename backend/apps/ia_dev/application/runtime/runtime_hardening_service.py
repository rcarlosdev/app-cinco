from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any


class RuntimeHardeningService:
    SERVICE_VERSION = "runtime_hardening.v1"
    DEFAULT_MAX_TOOL_LOOP_ROUNDS = 4
    DEFAULT_MAX_TOOL_CALLS_PER_RUN = 12
    DEFAULT_MAX_REPEAT_TOOL_CALLS = 2
    DEFAULT_MAX_BACKGROUND_RETRIES = 2
    DEFAULT_MAX_BACKGROUND_DURATION_SECONDS = 1800
    DEFAULT_MAX_APPROVAL_WAIT_SECONDS = 3600
    DEFAULT_MAX_TRACE_ITEMS = 50
    SENSITIVE_KEYS = {
        "access_token",
        "api_key",
        "authorization",
        "cedula",
        "correo",
        "documento",
        "email",
        "identificacion",
        "jwt",
        "password",
        "secret",
        "serial",
        "telefono",
        "token",
    }

    def max_tool_loop_rounds(self) -> int:
        return self._read_int_env(
            "IA_DEV_MAX_TOOL_LOOP_ROUNDS",
            self.DEFAULT_MAX_TOOL_LOOP_ROUNDS,
            minimum=1,
            maximum=12,
        )

    def max_tool_calls_per_run(self) -> int:
        return self._read_int_env(
            "IA_DEV_MAX_TOOL_CALLS_PER_RUN",
            self.DEFAULT_MAX_TOOL_CALLS_PER_RUN,
            minimum=1,
            maximum=100,
        )

    def max_repeat_tool_calls(self) -> int:
        return self._read_int_env(
            "IA_DEV_MAX_REPEAT_TOOL_CALLS",
            self.DEFAULT_MAX_REPEAT_TOOL_CALLS,
            minimum=1,
            maximum=10,
        )

    def max_background_retries(self) -> int:
        return self._read_int_env(
            "IA_DEV_MAX_BACKGROUND_RETRIES",
            self.DEFAULT_MAX_BACKGROUND_RETRIES,
            minimum=0,
            maximum=10,
        )

    def max_background_duration_seconds(self) -> int:
        return self._read_int_env(
            "IA_DEV_MAX_BACKGROUND_DURATION_SECONDS",
            self.DEFAULT_MAX_BACKGROUND_DURATION_SECONDS,
            minimum=30,
            maximum=86400,
        )

    def max_approval_wait_seconds(self) -> int:
        return self._read_int_env(
            "IA_DEV_MAX_APPROVAL_WAIT_SECONDS",
            self.DEFAULT_MAX_APPROVAL_WAIT_SECONDS,
            minimum=60,
            maximum=604800,
        )

    def max_trace_items(self) -> int:
        return self._read_int_env(
            "IA_DEV_MAX_TRACE_ITEMS",
            self.DEFAULT_MAX_TRACE_ITEMS,
            minimum=10,
            maximum=500,
        )

    def sanitize_payload(self, value: Any, *, parent_key: str = "") -> Any:
        if isinstance(value, dict):
            sanitized: dict[str, Any] = {}
            for key, item in value.items():
                clean_key = str(key or "")
                if self._is_sensitive_key(clean_key):
                    sanitized[clean_key] = self._mask_value(item)
                else:
                    sanitized[clean_key] = self.sanitize_payload(item, parent_key=clean_key)
            return sanitized
        if isinstance(value, list):
            return [self.sanitize_payload(item, parent_key=parent_key) for item in list(value)]
        if self._is_sensitive_key(parent_key):
            return self._mask_value(value)
        return value

    def build_idempotency_key(
        self,
        *,
        run_id: str,
        tool_id: str,
        arguments: dict[str, Any] | None = None,
    ) -> str:
        payload = {
            "run_id": str(run_id or ""),
            "tool_id": str(tool_id or ""),
            "arguments": self.sanitize_payload(dict(arguments or {})),
        }
        serialized = json.dumps(payload, ensure_ascii=True, sort_keys=True)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def build_correlation_metadata(
        self,
        *,
        run_id: str,
        trace_id: str,
        session_id: str | None = None,
        tool_id: str = "",
    ) -> dict[str, Any]:
        correlation_id = str(trace_id or run_id or "")
        lineage = [str(item) for item in [run_id, trace_id, tool_id] if str(item or "").strip()]
        return {
            "correlation_id": correlation_id,
            "run_id": str(run_id or ""),
            "trace_id": str(trace_id or ""),
            "session_id": str(session_id or ""),
            "tool_id": str(tool_id or ""),
            "lineage": lineage,
            "service_version": self.SERVICE_VERSION,
        }

    def approval_expires_at(self, *, requested_at: str | None = None) -> str:
        base = self._parse_iso_datetime(requested_at) or datetime.now(timezone.utc)
        return (base + timedelta(seconds=self.max_approval_wait_seconds())).isoformat()

    def normalize_timeout_seconds(self, timeout_seconds: int) -> int:
        requested = int(timeout_seconds or 0)
        if requested <= 0:
            return self.max_background_duration_seconds()
        return min(requested, self.max_background_duration_seconds())

    def validate_tool_loop(
        self,
        *,
        tool_traces: list[dict[str, Any]] | None,
        function_call: dict[str, Any] | None,
    ) -> dict[str, Any]:
        traces = [dict(item) for item in list(tool_traces or []) if isinstance(item, dict)]
        call = dict(function_call or {})
        total_calls = len(traces)
        if total_calls >= self.max_tool_calls_per_run():
            return {
                "allowed": False,
                "reason": "tool_loop_call_limit_exceeded",
                "limit": self.max_tool_calls_per_run(),
                "total_calls": total_calls,
            }

        current_tool = str(call.get("name") or "").strip()
        current_arguments = self.sanitize_payload(dict(call.get("arguments") or {}))
        repeated = 0
        for item in reversed(traces):
            if str(item.get("tool_name") or "") != current_tool:
                break
            previous_arguments = self.sanitize_payload(dict(item.get("arguments") or {}))
            if previous_arguments != current_arguments:
                break
            repeated += 1
        if repeated >= self.max_repeat_tool_calls():
            return {
                "allowed": False,
                "reason": "tool_loop_repeat_detected",
                "limit": self.max_repeat_tool_calls(),
                "tool_name": current_tool,
                "repeat_count": repeated,
            }

        return {"allowed": True, "reason": "", "total_calls": total_calls}

    def build_dead_letter_entry(
        self,
        *,
        run_id: str,
        tool_id: str,
        failure_reason: str,
        retry_count: int,
    ) -> dict[str, Any]:
        return {
            "dead_lettered": True,
            "run_id": str(run_id or ""),
            "tool_id": str(tool_id or ""),
            "failure_reason": str(failure_reason or ""),
            "retry_count": int(retry_count or 0),
            "dead_lettered_at": datetime.now(timezone.utc).isoformat(),
            "service_version": self.SERVICE_VERSION,
        }

    def build_runtime_metrics(
        self,
        *,
        state: dict[str, Any],
    ) -> dict[str, Any]:
        approvals = list(state.get("approvals") or [])
        tool_trace = list(state.get("tool_execution_trace") or [])
        background = dict(state.get("background") or {})
        background_retry = dict(background.get("retry") or {})
        return {
            "tool_call_count": len(tool_trace),
            "approval_count": len(approvals),
            "approval_pending_count": sum(
                1
                for item in approvals
                if str((item or {}).get("approval_status") or "") == "awaiting_approval"
            ),
            "handoff_count": len(list(state.get("handoffs") or [])),
            "agent_count": len(list(state.get("agents") or [])),
            "background_retry_count": int(background_retry.get("retry_count") or 0),
            "background_status": str(background.get("run_status") or ""),
            "checkpoint_count": len(list(state.get("checkpoints") or [])),
            "dead_lettered": bool(dict(state.get("dead_letter") or {}).get("dead_lettered")),
            "limits": {
                "max_tool_loop_rounds": self.max_tool_loop_rounds(),
                "max_tool_calls_per_run": self.max_tool_calls_per_run(),
                "max_background_retries": self.max_background_retries(),
                "max_background_duration_seconds": self.max_background_duration_seconds(),
                "max_approval_wait_seconds": self.max_approval_wait_seconds(),
            },
            "service_version": self.SERVICE_VERSION,
        }

    @classmethod
    def _read_int_env(cls, name: str, default: int, *, minimum: int, maximum: int) -> int:
        raw = str(os.getenv(name, str(default)) or str(default)).strip()
        try:
            value = int(raw)
        except Exception:
            value = int(default)
        return max(minimum, min(maximum, value))

    @classmethod
    def _is_sensitive_key(cls, value: str) -> bool:
        normalized = str(value or "").strip().lower()
        if not normalized:
            return False
        if normalized in cls.SENSITIVE_KEYS:
            return True
        return any(token in normalized for token in ("token", "secret", "password", "authorization", "api_key"))

    @staticmethod
    def _parse_iso_datetime(value: str | None) -> datetime | None:
        raw = str(value or "").strip()
        if not raw:
            return None
        normalized = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    @staticmethod
    def _mask_value(value: Any) -> str:
        raw = str(value or "")
        if not raw:
            return ""
        if len(raw) <= 4:
            return "***"
        return f"{raw[:2]}***{raw[-2:]}"
