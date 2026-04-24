from __future__ import annotations

import os
from typing import Any


SERVICE_RUNTIME_DEFAULTS: dict[str, str] = {
    "IA_DEV_ROUTING_MODE": "capability",
    "IA_DEV_POLICY_CAPABILITY_EXECUTION_ENABLED": "1",
    "IA_DEV_POLICY_MEMORY_HINTS_ENABLED": "1",
    "IA_DEV_POLICY_ATTENDANCE_PERSONAL_JOIN_ENABLED": "1",
    "IA_DEV_QUERY_INTELLIGENCE_ENABLED": "1",
    "IA_DEV_QUERY_INTELLIGENCE_MODE": "active",
    "IA_DEV_QUERY_INTELLIGENCE_OPENAI_ENABLED": "1",
    "IA_DEV_QUERY_PATTERN_MEMORY_ENABLED": "1",
    "IA_DEV_QUERY_PATTERN_FASTPATH_ENABLED": "1",
    "IA_DEV_QUERY_PATTERN_MEMORY_BUSINESS_ENABLED": "1",
    "IA_DEV_QUERY_PATTERN_MEMORY_BUSINESS_AUTOAPPLY_ENABLED": "1",
    "IA_DEV_REASONING_LEDGER_ENABLED": "1",
    "IA_DEV_DIAGNOSTIC_ORCHESTRATOR_ENABLED": "1",
    "IA_DEV_REASONING_MEMORY_ENABLED": "1",
    "IA_DEV_REASONING_MEMORY_USER_ENABLED": "1",
    "IA_DEV_REASONING_MEMORY_BUSINESS_ENABLED": "1",
    "IA_DEV_REASONING_MEMORY_BUSINESS_AUTOAPPLY_ENABLED": "1",
    "IA_DEV_CAP_ATTENDANCE_ENABLED": "1",
    "IA_DEV_CAP_ATTENDANCE_ANALYTICS_ENABLED": "1",
    "IA_DEV_CAP_ATTENDANCE_TABLE_ENABLED": "1",
    "IA_DEV_CAP_EMPLEADOS_ENABLED": "1",
    "IA_DEV_CAP_EMPLEADOS_COUNT_ENABLED": "1",
}


def runtime_bootstrap_enabled() -> bool:
    raw = os.getenv("IA_DEV_SERVICE_RUNTIME_BOOTSTRAP_ENABLED", "1")
    return str(raw or "").strip().lower() in {"1", "true", "yes", "on"}


def runtime_bootstrap_force() -> bool:
    raw = os.getenv("IA_DEV_SERVICE_RUNTIME_BOOTSTRAP_FORCE", "1")
    return str(raw or "").strip().lower() in {"1", "true", "yes", "on"}


def apply_service_runtime_bootstrap(*, force: bool | None = None) -> dict[str, dict[str, Any]]:
    """
    Keep HTTP/runtime execution aligned with the terminal simulator.

    By default it only fills missing flags so explicit deployment values
    continue to win. `force=True` is reserved for the simulator command,
    where we want a deterministic runtime regardless of the current shell.
    """

    resolved_force = runtime_bootstrap_force() if force is None else bool(force)

    if not runtime_bootstrap_enabled():
        return {
            "enabled": False,
            "force": resolved_force,
            "applied": {},
            "skipped": dict(SERVICE_RUNTIME_DEFAULTS),
        }

    applied: dict[str, str] = {}
    skipped: dict[str, str] = {}
    for key, value in SERVICE_RUNTIME_DEFAULTS.items():
        current = os.getenv(str(key))
        if resolved_force or current in {None, ""}:
            os.environ[str(key)] = str(value)
            applied[str(key)] = str(value)
        else:
            skipped[str(key)] = str(current)
    return {
        "enabled": True,
        "force": resolved_force,
        "applied": applied,
        "skipped": skipped,
    }
