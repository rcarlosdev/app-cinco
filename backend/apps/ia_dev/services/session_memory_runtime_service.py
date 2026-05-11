from __future__ import annotations

from typing import Any

from apps.ia_dev.services.memory_service import SessionMemoryStore


class SessionMemoryRuntimeService:
    def reset_memory(self, session_id: str) -> dict[str, Any]:
        sid = str(session_id or "").strip()
        if not sid:
            return {"error": "session_id is required"}

        SessionMemoryStore.reset(sid)
        return {
            "session_id": sid,
            "memory": SessionMemoryStore.status(sid),
        }

