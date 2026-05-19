from __future__ import annotations

import re
from typing import Any

from apps.ia_dev.application.contracts.chat_contracts import ensure_chat_response_contract


class BusinessResponseComposerService:
    FORBIDDEN_USER_TERMS = (
        "runtime_only_fallback",
        "legacy",
        "ai_dictionary",
        "agent_contract",
        "traceback",
        "sql",
        "planner",
        "handler",
        "pilot",
        "runtime",
        "fallback",
        "compiler",
        "join-aware",
        "policy_forced",
        "unsupported_capability_domain",
    )

    def compose(
        self,
        *,
        response: dict[str, Any],
        semantic_orchestrator: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = ensure_chat_response_contract(response)
        semantic = dict(semantic_orchestrator or {})
        data = dict(payload.get("data") or {})
        business_response = self._enrich_business_response(
            payload=payload,
            semantic=semantic,
            business_response=dict(data.get("business_response") or {}),
        )
        if business_response:
            data["business_response"] = business_response
        reply = self._sanitize(str(payload.get("reply") or ""))

        composed = {
            "que_entendi": self._build_understanding(
                reply=reply,
                semantic=semantic,
                business_response=business_response,
            ),
            "datos_usados": self._build_data_used(
                payload=payload,
                semantic=semantic,
                business_response=business_response,
            ),
            "resultado": self._build_result(reply=reply, business_response=business_response),
            "alertas": self._build_alerts(
                payload=payload,
                semantic=semantic,
                business_response=business_response,
            ),
            "limitaciones": self._build_limitations(
                payload=payload,
                semantic=semantic,
                business_response=business_response,
            ),
            "siguiente_accion": self._build_next_action(
                semantic=semantic,
                business_response=business_response,
            ),
        }
        data["business_response_composer"] = composed
        payload["data"] = data

        if self._is_provider_serial_background_active(payload=payload):
            payload["reply"] = reply
            return payload

        if business_response:
            payload["reply"] = self._sanitize(
                " ".join(
                    part
                    for part in (
                        composed["resultado"],
                        composed["alertas"],
                        composed["limitaciones"],
                        composed["siguiente_accion"],
                    )
                    if str(part or "").strip()
                )
            )
        elif not reply or self._looks_too_technical(reply):
            payload["reply"] = self._sanitize(
                " ".join(
                    part
                    for part in (
                        composed["que_entendi"],
                        composed["resultado"],
                        composed["alertas"],
                        composed["limitaciones"],
                        composed["siguiente_accion"],
                    )
                    if str(part or "").strip()
                )
            )
        else:
            payload["reply"] = reply
        return payload

    @staticmethod
    def _is_provider_serial_background_active(*, payload: dict[str, Any]) -> bool:
        task_run = dict(((payload.get("task") or {}).get("current_run") or {}))
        semantic = dict(task_run.get("semantic_explanation") or {})
        background = dict(task_run.get("background") or {})
        capability = str(
            semantic.get("selected_capability")
            or semantic.get("candidate_capability")
            or task_run.get("intent")
            or dict(payload.get("orchestrator") or {}).get("intent")
            or ""
        ).strip()
        route_hint = str(semantic.get("planner_route_hint") or "").strip()
        background_status = str(background.get("run_status") or task_run.get("status") or "").strip().lower()
        return (
            capability == "inventory_provider_serial_validation"
            and route_hint == "inventory.serial.validation.provider_file"
            and background_status in {"queued", "running", "resumed"}
        )

    def _build_understanding(
        self,
        *,
        reply: str,
        semantic: dict[str, Any],
        business_response: dict[str, Any],
    ) -> str:
        domain = str(semantic.get("domain") or "").strip()
        intent = str(semantic.get("intent") or "").strip()
        metadata = dict(business_response.get("metadata") or {})
        response_profile = str(metadata.get("response_profile_usado") or "").strip()
        if domain and intent and response_profile:
            return self._sanitize(
                f"Consulta de {domain.replace('_', ' ')} resuelta con el perfil {response_profile.replace('.', ' ')}."
            )
        if domain and intent:
            return self._sanitize(
                f"EntendÃ­ una consulta del dominio {domain.replace('_', ' ')} con intenciÃ³n {intent.replace('_', ' ')}."
            )
        if reply:
            return self._sanitize("EntendÃ­ la solicitud y la preparÃ© en formato empresarial.")
        return "EntendÃ­ la solicitud y la normalicÃ© al dominio correcto."

    def _build_data_used(
        self,
        *,
        payload: dict[str, Any],
        semantic: dict[str, Any],
        business_response: dict[str, Any],
    ) -> str:
        tables = [str(item) for item in list(semantic.get("required_tables") or []) if str(item).strip()]
        filters = [str(item) for item in sorted(dict(semantic.get("filters") or {}).keys()) if str(item).strip()]
        evidence_summary = dict(business_response.get("evidence_summary") or {})
        response_profile = str(evidence_summary.get("response_profile_usado") or "").strip()
        evidence_sources = [
            str(item or "")
            for item in list(evidence_summary.get("evidence_sources_used") or [])
            if str(item or "").strip()
        ]
        parts: list[str] = []
        if response_profile:
            parts.append(f"Perfil de respuesta: {response_profile}.")
        if tables:
            parts.append(f"Datos usados: {', '.join(tables[:4])}.")
        if filters:
            parts.append(f"Filtros aplicados: {', '.join(filters[:5])}.")
        if evidence_sources:
            parts.append(f"Fuentes de evidencia: {', '.join(evidence_sources[:5])}.")
        if not parts:
            rowcount = int((((payload.get("data") or {}).get("table") or {}).get("rowcount") or 0))
            if rowcount:
                parts.append(f"Datos usados: {rowcount} registros devueltos por la consulta.")
        return self._sanitize(" ".join(parts))

    def _build_result(
        self,
        *,
        reply: str,
        business_response: dict[str, Any],
    ) -> str:
        for key in ("dato", "hallazgo", "interpretacion"):
            value = self._sanitize(str(business_response.get(key) or ""))
            if value:
                return value
        return reply

    def _build_alerts(
        self,
        *,
        payload: dict[str, Any],
        semantic: dict[str, Any],
        business_response: dict[str, Any],
    ) -> str:
        for key in ("riesgo", "recomendacion"):
            value = self._sanitize(str(business_response.get(key) or ""))
            if value:
                return value
        warnings = [
            self._sanitize(str(item))
            for item in list((semantic.get("user_response_strategy") or {}).get("warnings_to_include") or [])
            if str(item).strip()
        ]
        if warnings:
            return "Alertas: " + " ".join(warnings[:2])
        if bool((payload.get("response_envelope") or {}).get("needs_clarification")):
            return "Alertas: hace falta una precisiÃ³n breve para continuar con seguridad."
        return ""

    def _build_limitations(
        self,
        *,
        payload: dict[str, Any],
        semantic: dict[str, Any],
        business_response: dict[str, Any],
    ) -> str:
        metadata = dict(business_response.get("metadata") or {})
        missing_evidence_reason = str(metadata.get("missing_evidence_reason") or "").strip()
        response_status = str(metadata.get("response_status") or "").strip()
        if response_status == "limitation_declared":
            return self._sanitize(str(business_response.get("hallazgo") or ""))
        if response_status == "clarification_required":
            return "Limitaciones: falta una aclaracion estructural antes de ejecutar o cerrar la respuesta."
        if response_status == "empty_result":
            return "Limitaciones: la ejecucion termino sin evidencia util para afirmar un resultado positivo."
        if missing_evidence_reason:
            return self._sanitize(f"Limitaciones: evidencia insuficiente ({missing_evidence_reason}).")
        if str(semantic.get("recommended_route") or "") == "external_pending":
            return "Limitaciones: la fuente requerida todavÃ­a no estÃ¡ disponible como productiva."
        if bool(semantic.get("needs_clarification")) or bool(
            (payload.get("response_envelope") or {}).get("needs_clarification")
        ):
            return "Limitaciones: todavÃ­a no es seguro ejecutar la solicitud sin una aclaraciÃ³n."
        return ""

    def _build_next_action(
        self,
        *,
        semantic: dict[str, Any],
        business_response: dict[str, Any],
    ) -> str:
        explicit = self._sanitize(str(business_response.get("siguiente_accion") or ""))
        if explicit:
            return explicit
        return self._sanitize(
            str(((semantic.get("user_response_strategy") or {}).get("next_best_action") or "")).strip()
        )

    def _sanitize(self, text: str) -> str:
        clean = str(text or "").strip()
        if not clean:
            return ""
        for term in self.FORBIDDEN_USER_TERMS:
            clean = re.sub(re.escape(term), "", clean, flags=re.IGNORECASE)
        clean = re.sub(r"\s+", " ", clean).strip(" .")
        return clean

    def _looks_too_technical(self, text: str) -> bool:
        lowered = str(text or "").strip().lower()
        return any(term in lowered for term in self.FORBIDDEN_USER_TERMS)

    def _enrich_business_response(
        self,
        *,
        payload: dict[str, Any],
        semantic: dict[str, Any],
        business_response: dict[str, Any],
    ) -> dict[str, Any]:
        if not business_response:
            return {}
        enriched = dict(business_response)
        metadata = dict(enriched.get("metadata") or {})
        evidence_summary = dict(enriched.get("evidence_summary") or {})
        task_run = dict(((payload.get("task") or {}).get("current_run") or {}))
        validation = dict(task_run.get("validation") or {})
        tool_execution = dict(task_run.get("tool_execution") or {})
        runtime = dict(((payload.get("data_sources") or {}).get("runtime") or {}))

        evidence_summary.setdefault(
            "validation",
            {
                "satisfied": bool(validation.get("satisfied", True)),
                "reason": str(validation.get("reason") or ""),
                "needs_clarification": bool(validation.get("needs_clarification")),
            },
        )
        evidence_summary.setdefault(
            "tool_execution",
            {
                "selected_tool_id": str(tool_execution.get("selected_tool_id") or ""),
                "trace_count": len(list(tool_execution.get("trace") or [])),
            },
        )
        evidence_summary.setdefault(
            "runtime_trace",
            {
                "response_flow": str((runtime.get("route") or {}).get("response_flow") or ""),
                "final_domain": str(runtime.get("final_domain") or ""),
                "final_intent": str(runtime.get("final_intent") or ""),
            },
        )
        metadata.setdefault(
            "evidence_sources_used",
            list(evidence_summary.get("evidence_sources_used") or []),
        )
        metadata.setdefault(
            "response_profile_usado",
            str(evidence_summary.get("response_profile_usado") or ""),
        )
        metadata.setdefault(
            "semantic_context_used",
            bool(evidence_summary.get("semantic_context_used")),
        )
        metadata.setdefault(
            "fallback_narrativo_usado",
            bool(evidence_summary.get("fallback_narrativo_usado")),
        )
        metadata.setdefault(
            "missing_evidence_reason",
            str(evidence_summary.get("missing_evidence_reason") or ""),
        )
        if not metadata.get("response_status") and not bool(validation.get("satisfied", True)):
            metadata["response_status"] = "validation_failed"
        if semantic and not metadata.get("intent"):
            metadata["intent"] = str(semantic.get("intent") or "")
        enriched["metadata"] = metadata
        enriched["evidence_summary"] = evidence_summary
        return enriched
