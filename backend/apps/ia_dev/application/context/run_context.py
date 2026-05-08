from __future__ import annotations

import os
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def normalize_routing_mode(raw: str | None) -> str:
    value = (raw or "").strip().lower()
    if value in {"capability_shadow", "shadow"}:
        return "intent"
    if value in {"intent", "capability"}:
        return value
    return "intent"


@dataclass(slots=True)
class RunContext:
    run_id: str
    trace_id: str
    session_id: str | None
    message: str
    reset_memory: bool
    routing_mode: str
    started_at_ms: int
    started_at_iso: str
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        *,
        message: str,
        session_id: str | None = None,
        reset_memory: bool = False,
    ) -> "RunContext":
        now_ms = int(time.time() * 1000)
        now_iso = datetime.now(timezone.utc).isoformat()
        return cls(
            run_id=f"run_{uuid.uuid4().hex[:16]}",
            trace_id=f"trace_{uuid.uuid4().hex[:16]}",
            session_id=(session_id or "").strip() or None,
            message=str(message or ""),
            reset_memory=bool(reset_memory),
            routing_mode=normalize_routing_mode(os.getenv("IA_DEV_ROUTING_MODE", "intent")),
            started_at_ms=now_ms,
            started_at_iso=now_iso,
            metadata={},
        )

    @property
    def is_shadow_mode(self) -> bool:
        return False

    @property
    def is_capability_mode_requested(self) -> bool:
        return self.routing_mode == "capability"
