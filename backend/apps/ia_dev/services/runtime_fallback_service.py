from __future__ import annotations

import os
import unicodedata
from typing import Any

from apps.ia_dev.application.contracts.chat_contracts import (
    build_chat_response_snapshot,
    ensure_chat_response_contract,
)
from apps.ia_dev.application.runtime.service_runtime_bootstrap import (
    apply_service_runtime_bootstrap,
)
from apps.ia_dev.services.memory_service import SessionMemoryStore
from apps.ia_dev.services.observability_service import ObservabilityService
from apps.ia_dev.services.orchestrator_legacy_runtime import LegacyOrchestratorRuntime


class RuntimeFallbackService:
    def __init__(self):
        self.runtime_bootstrap = apply_service_runtime_bootstrap()
        self.observability = ObservabilityService()
        self._legacy_runtime: LegacyOrchestratorRuntime | None = None

    def run(
        self,
        *,
        message: str,
        session_id: str | None = None,
        reset_memory: bool = False,
        actor_user_key: str | None = None,
        fallback_reason: str | None = None,
    ) -> dict[str, Any]:
        if self._should_block_legacy_for_covered_analytics(message):
            response = self._build_blocked_legacy_response(
                message=message,
                session_id=session_id,
                reason=str(fallback_reason or "blocked_covered_analytics"),
            )
            self._record_runtime_fallback_event(
                runtime_entry="blocked_legacy_runtime",
                session_id=response.get("session_id") or session_id,
                response=response,
            )
            return response

        response = self._get_legacy_runtime().run(
            message=str(message or ""),
            session_id=session_id,
            reset_memory=reset_memory,
            actor_user_key=actor_user_key,
        )
        response = self._attach_runtime_fallback_metadata(
            response=response,
            legacy_runtime_fallback_used=True,
            legacy_runtime_fallback_reason=str(fallback_reason or "legacy_runtime_fallback"),
        )
        self._record_runtime_fallback_event(
            runtime_entry="legacy_runtime",
            session_id=response.get("session_id") or session_id,
            response=response,
        )
        return response

    def _get_legacy_runtime(self) -> LegacyOrchestratorRuntime:
        if self._legacy_runtime is None:
            self._legacy_runtime = LegacyOrchestratorRuntime()
        self._legacy_runtime.observability = self.observability
        return self._legacy_runtime

    def _attach_runtime_fallback_metadata(
        self,
        *,
        response: dict[str, Any] | None,
        legacy_runtime_fallback_used: bool,
        legacy_runtime_fallback_reason: str | None,
    ) -> dict[str, Any]:
        payload = ensure_chat_response_contract(response)
        data_sources = dict(payload.get("data_sources") or {})
        runtime = dict(data_sources.get("runtime") or {})
        runtime["legacy_runtime_fallback_used"] = bool(legacy_runtime_fallback_used)
        if legacy_runtime_fallback_reason:
            runtime["legacy_runtime_fallback_reason"] = str(legacy_runtime_fallback_reason)
        else:
            runtime.pop("legacy_runtime_fallback_reason", None)
        data_sources["runtime"] = runtime
        payload["data_sources"] = data_sources
        return payload

    def _record_runtime_fallback_event(
        self,
        *,
        runtime_entry: str,
        session_id: str | None,
        response: dict[str, Any],
    ) -> None:
        runtime = dict((response.get("data_sources") or {}).get("runtime") or {})
        self.observability.record_event(
            event_type="runtime_fallback_resolved",
            source="RuntimeFallbackService",
            meta={
                "runtime_entry": str(runtime_entry or ""),
                "session_id": str(session_id or ""),
                "response_flow": str(
                    runtime.get("flow")
                    or ((response.get("orchestrator") or {}).get("runtime_flow") or "")
                ),
                "legacy_runtime_fallback_used": bool(runtime.get("legacy_runtime_fallback_used")),
                "legacy_runtime_fallback_reason": str(
                    runtime.get("legacy_runtime_fallback_reason") or ""
                ),
            },
        )

    def _build_blocked_legacy_response(
        self,
        *,
        message: str,
        session_id: str | None,
        reason: str,
    ) -> dict[str, Any]:
        sid, _ = SessionMemoryStore.get_or_create(session_id)
        response = build_chat_response_snapshot()
        response["session_id"] = sid
        response["reply"] = (
            "No pude usar el runtime legacy para esta consulta porque el analytics cubierto "
            "del piloto debe resolverse solo por el runtime moderno."
        )
        response["orchestrator"] = {
            "intent": "analytics_query",
            "domain": "ausentismo",
            "selected_agent": "ausentismo_agent",
            "classifier_source": "legacy_runtime_blocked",
            "needs_database": True,
            "output_mode": "table",
            "used_tools": [],
            "runtime_flow": "runtime_only_fallback",
        }
        response["data"]["insights"] = [
            "El fallback legacy fue bloqueado para evitar reactivar rutas antiguas sobre analytics cubierto.",
            "Revisa ChatApplicationService, QueryExecutionPlanner o ai_dictionary para restaurar el flujo moderno.",
        ]
        response["data_sources"] = {
            "runtime": {
                "flow": "runtime_only_fallback",
                "runtime_owner": "RuntimeFallbackService",
                "legacy_runtime_fallback_used": False,
                "legacy_runtime_fallback_reason": str(reason or ""),
                "blocked_legacy_fallback": True,
                "blocked_run_legacy_for_analytics": True,
                "runtime_only_fallback_reason": "chat_application_service_failure",
                "final_domain": "ausentismo",
            }
        }
        response["trace"] = [
            {
                "phase": "runtime_fallback_guard",
                "status": "blocked",
                "detail": {
                    "reason": str(reason or ""),
                    "message_preview": str(message or "")[:160],
                },
            }
        ]
        return response

    @classmethod
    def _should_block_legacy_for_covered_analytics(cls, message: str) -> bool:
        if not cls._attendance_employees_pilot_enabled():
            return False
        normalized = cls._normalize_text(message)
        if not normalized:
            return False
        analytics_tokens = (
            "patron",
            "patrones",
            "tendencia",
            "tendencias",
            "concentran",
            "concentracion",
            "top ",
            "ranking",
            "por area",
            "por cargo",
            "por sede",
            "por tipo",
            "distribucion",
            "comparativo",
            "resumen",
            "cuantas areas",
            "que areas",
        )
        domain_tokens = (
            "ausent",
            "incapacidad",
            "dias perdidos",
            "empleado",
            "empleados",
            "personal",
            "colaborador",
            "colaboradores",
        )
        return any(token in normalized for token in analytics_tokens) and any(
            token in normalized for token in domain_tokens
        )

    @staticmethod
    def _attendance_employees_pilot_enabled() -> bool:
        return str(os.getenv("IA_DEV_ATTENDANCE_EMPLOYEES_PILOT_ENABLED", "0")).strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

    @staticmethod
    def _normalize_text(text: str) -> str:
        lowered = str(text or "").strip().lower()
        normalized = unicodedata.normalize("NFKD", lowered)
        return "".join(ch for ch in normalized if not unicodedata.combining(ch))
