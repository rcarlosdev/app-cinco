from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from apps.ia_dev.application.contracts.background_run_contracts import (
    BackgroundCheckpointContract,
    BackgroundProgressEventContract,
)


class CheckpointService:
    SERVICE_VERSION = "checkpoint_service.v1"

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    def build_checkpoint(
        self,
        *,
        label: str,
        sequence: int,
        checkpoint_state: dict[str, Any] | None = None,
        progress: dict[str, Any] | None = None,
        evidence: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return BackgroundCheckpointContract(
            checkpoint_id=f"chk_{uuid4().hex[:16]}",
            sequence=int(sequence or 0),
            label=str(label or ""),
            created_at=self._now_iso(),
            checkpoint_state=dict(checkpoint_state or {}),
            progress=dict(progress or {}),
            evidence=dict(evidence or {}),
        ).as_dict()

    def build_progress_event(
        self,
        *,
        event_type: str,
        status: str,
        sequence: int,
        message: str = "",
        progress_pct: float = 0.0,
        evidence: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return BackgroundProgressEventContract(
            event_id=f"bg_evt_{uuid4().hex[:16]}",
            event_type=str(event_type or ""),
            status=str(status or ""),
            created_at=self._now_iso(),
            sequence=int(sequence or 0),
            message=str(message or ""),
            progress_pct=float(progress_pct or 0.0),
            evidence=dict(evidence or {}),
        ).as_dict()

    @staticmethod
    def append_limited(items: list[dict[str, Any]] | None, item: dict[str, Any], *, limit: int = 50) -> list[dict[str, Any]]:
        payload = [dict(entry) for entry in list(items or []) if isinstance(entry, dict)]
        payload.append(dict(item or {}))
        return payload[-max(1, int(limit or 1)) :]
