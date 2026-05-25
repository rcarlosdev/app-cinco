from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from apps.ia_dev.application.context.run_context import RunContext
from apps.ia_dev.application.contracts.query_intelligence_contracts import (
    QueryExecutionPlan,
    ResolvedQuerySpec,
)
from apps.ia_dev.domains.inventario_logistica.validador_seriales_proveedor import (
    ValidadorSerialesProveedorService,
)
from apps.ia_dev.services.memory_service import SessionMemoryStore


@dataclass(slots=True)
class InventarioLogisticaHandleResult:
    ok: bool
    response: dict[str, Any] | None = None
    error: str | None = None
    metadata: dict[str, Any] | None = None


class InventarioLogisticaHandler:
    SUPPORTED_CAPABILITIES = {"inventory_provider_serial_validation"}

    def __init__(
        self,
        *,
        provider_serial_validator: ValidadorSerialesProveedorService | None = None,
    ):
        self.provider_serial_validator = provider_serial_validator or ValidadorSerialesProveedorService()

    def handle(
        self,
        *,
        capability_id: str,
        message: str,
        session_id: str | None,
        reset_memory: bool,
        run_context: RunContext,
        planned_capability: dict[str, Any],
        memory_context: dict[str, Any] | None = None,
        resolved_query: ResolvedQuerySpec | None = None,
        execution_plan: QueryExecutionPlan | None = None,
        observability=None,
    ) -> InventarioLogisticaHandleResult:
        sid, _ = SessionMemoryStore.get_or_create(session_id)
        if reset_memory:
            SessionMemoryStore.reset(sid)

        if capability_id not in self.SUPPORTED_CAPABILITIES:
            return InventarioLogisticaHandleResult(
                ok=False,
                error=f"inventario_logistica capability no soportada: {capability_id}",
                metadata={"capability_id": capability_id},
            )

        started_at = time.perf_counter()
        attachments = list(run_context.metadata.get("attachments") or [])
        attachment = dict(attachments[0] or {}) if attachments else None

        try:
            validation = self.provider_serial_validator.validate(
                attachment=attachment,
                user_message=message,
                previous_year=datetime.now(timezone.utc).year - 1,
            )
            reply = str(validation.get("reply") or "")
            trace = list(validation.get("trace") or [])
            payload = dict(validation.get("data") or {})

            SessionMemoryStore.update_context(
                sid,
                {
                    "last_domain": "inventario_logistica",
                    "last_intent": capability_id,
                    "last_focus": "validacion_seriales_proveedor",
                    "last_output_mode": "table",
                    "last_needs_database": True,
                    "last_selected_agent": "inventory_agent",
                },
            )
            SessionMemoryStore.append_turn(sid, message, reply)
            memory_status = SessionMemoryStore.status(sid)

            total_duration_ms = int((time.perf_counter() - started_at) * 1000)
            response = {
                "session_id": sid,
                "reply": reply,
                "orchestrator": {
                    "intent": capability_id,
                    "domain": "inventario_logistica",
                    "selected_agent": "inventory_agent",
                    "classifier_source": "capability_handler",
                    "needs_database": True,
                    "output_mode": "table",
                    "used_tools": [
                        "inventory_provider_serial_validation",
                        "query_execution_planner.governed_select",
                    ],
                },
                "data": payload,
                "actions": [],
                "data_sources": {
                    "inventario_logistica": {"ok": True, "source": "capability_handler"},
                    "ai_dictionary": {"ok": True, "source": "capability_handler"},
                },
                "trace": trace,
                "memory": memory_status,
                "observability": {
                    "enabled": bool(getattr(observability, "enabled", True)),
                    "duration_ms": total_duration_ms,
                    "tool_latencies_ms": {},
                    "tokens_in": 0,
                    "tokens_out": 0,
                    "estimated_cost_usd": 0.0,
                },
                "active_nodes": ["inventario", "q", "result", "route"],
            }
            return InventarioLogisticaHandleResult(
                ok=True,
                response=response,
                metadata={
                    "capability_id": capability_id,
                    "response_status": str(validation.get("status") or ""),
                    "attachment_present": bool(attachment),
                    "policy_tags": list(planned_capability.get("policy_tags") or []),
                },
            )
        except Exception as exc:
            return InventarioLogisticaHandleResult(
                ok=False,
                error=str(exc),
                metadata={"capability_id": capability_id},
            )
