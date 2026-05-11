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
        business_response = dict(data.get("business_response") or {})
        reply = self._sanitize(str(payload.get("reply") or ""))

        composed = {
            "que_entendi": self._build_understanding(reply=reply, semantic=semantic),
            "datos_usados": self._build_data_used(payload=payload, semantic=semantic),
            "resultado": self._build_result(reply=reply, business_response=business_response),
            "alertas": self._build_alerts(payload=payload, semantic=semantic, business_response=business_response),
            "limitaciones": self._build_limitations(semantic=semantic),
            "siguiente_accion": self._build_next_action(semantic=semantic, business_response=business_response),
        }
        data["business_response_composer"] = composed
        payload["data"] = data
        if not reply or self._looks_too_technical(reply):
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

    def _build_understanding(self, *, reply: str, semantic: dict[str, Any]) -> str:
        domain = str(semantic.get("domain") or "").strip()
        intent = str(semantic.get("intent") or "").strip()
        if domain and intent:
            return self._sanitize(
                f"Entendí una consulta del dominio {domain.replace('_', ' ')} con intención {intent.replace('_', ' ')}."
            )
        if reply:
            return self._sanitize("Entendí la solicitud y la preparé en formato empresarial.")
        return "Entendí la solicitud y la normalicé al dominio correcto."

    def _build_data_used(self, *, payload: dict[str, Any], semantic: dict[str, Any]) -> str:
        tables = [str(item) for item in list(semantic.get("required_tables") or []) if str(item).strip()]
        filters = [str(item) for item in sorted(dict(semantic.get("filters") or {}).keys()) if str(item).strip()]
        parts: list[str] = []
        if tables:
            parts.append(f"Datos usados: {', '.join(tables[:4])}.")
        if filters:
            parts.append(f"Filtros aplicados: {', '.join(filters[:5])}.")
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
        warnings = [self._sanitize(str(item)) for item in list((semantic.get("user_response_strategy") or {}).get("warnings_to_include") or []) if str(item).strip()]
        if warnings:
            return "Alertas: " + " ".join(warnings[:2])
        if bool((payload.get("response_envelope") or {}).get("needs_clarification")):
            return "Alertas: hace falta una precisión breve para continuar con seguridad."
        return ""

    def _build_limitations(self, *, semantic: dict[str, Any]) -> str:
        if str(semantic.get("recommended_route") or "") == "external_pending":
            return "Limitaciones: la fuente requerida todavía no está disponible como productiva."
        if bool(semantic.get("needs_clarification")):
            return "Limitaciones: todavía no es seguro ejecutar la solicitud sin una aclaración."
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
