from __future__ import annotations

import json
import logging
import os
import re
import unicodedata
from datetime import date, timedelta
from typing import Any

from apps.ia_dev.services.memory_service import SessionMemoryStore
from apps.ia_dev.services.period_service import resolve_period_from_text


logger = logging.getLogger(__name__)
_YES_FOLLOW_UP_RE = re.compile(r"^(si|sí|dale|ok|okay|de acuerdo|hazlo|muestralo|mu[eé]stralo)\b")


class AttendancePeriodResolverService:
    def __init__(
        self,
        *,
        enable_openai_period: bool | None = None,
        period_model: str | None = None,
    ):
        self.enable_openai_period = (
            self._env_flag("IA_DEV_USE_OPENAI_PERIOD", default="1")
            if enable_openai_period is None
            else bool(enable_openai_period)
        )
        self.period_model = str(
            period_model or os.getenv("IA_DEV_OPENAI_PERIOD_MODEL", "gpt-4.1-mini")
        ).strip()

    def resolve_attendance_period(
        self,
        *,
        message: str,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        text = str(message or "").strip()
        if not text:
            return {"error": "message is required"}

        sid, _ = SessionMemoryStore.get_or_create(session_id)
        session_context = SessionMemoryStore.get_context(sid)
        recent_messages = SessionMemoryStore.get_recent_messages(sid, limit=8)
        rules_period = resolve_period_from_text(text)
        final_period = self.resolve_period_for_attendance(
            message=text,
            session_context=session_context,
            recent_messages=recent_messages,
        )
        period_alternative_hint = self.build_period_alternative_hint(
            message=text,
            period=final_period,
        )

        return {
            "session_id": sid,
            "input": {
                "message": text,
                "explicit_period_detected": self.has_explicit_period(text),
            },
            "resolved_period": self.serialize_period(final_period),
            "rules_fallback_period": self.serialize_period({**rules_period, "source": "rules"}),
            "alternative_hint": period_alternative_hint,
        }

    def resolve_period_for_attendance(
        self,
        *,
        message: str,
        session_context: dict[str, Any] | None,
        recent_messages: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        period = resolve_period_from_text(message)
        normalized = self.normalize_text(message)
        explicit_period = self.has_explicit_period(message) or "reincid" in normalized

        if explicit_period:
            if self.prefers_rules_period_resolution(normalized):
                return {**period, "source": "rules"}
            openai_period = self.resolve_period_with_openai(
                message=message,
                recent_messages=recent_messages,
                session_context=session_context or {},
            )
            if openai_period:
                return openai_period
            return {**period, "source": "rules"}

        if not (_YES_FOLLOW_UP_RE.match(normalized) or self.is_contextual_reference_request(normalized)):
            return {**period, "source": "rules"}

        context = dict(session_context or {})
        start = context.get("last_period_start")
        end = context.get("last_period_end")
        if not start or not end:
            return {**period, "source": "rules"}

        try:
            return {
                "label": "contexto_previo",
                "start": date.fromisoformat(str(start)),
                "end": date.fromisoformat(str(end)),
                "source": "context",
            }
        except ValueError:
            return {**period, "source": "rules"}

    @staticmethod
    def serialize_period(period: dict[str, Any] | None) -> dict[str, Any]:
        item = period or {}
        start = item.get("start")
        end = item.get("end")
        payload = {
            "label": str(item.get("label") or ""),
            "source": str(item.get("source") or "rules"),
            "start_date": start.isoformat() if hasattr(start, "isoformat") else None,
            "end_date": end.isoformat() if hasattr(end, "isoformat") else None,
        }
        if "confidence" in item:
            payload["confidence"] = item.get("confidence")
        return payload

    @staticmethod
    def normalize_text(text: str) -> str:
        lowered = (text or "").strip().lower()
        normalized = unicodedata.normalize("NFKD", lowered)
        return "".join(ch for ch in normalized if not unicodedata.combining(ch))

    @classmethod
    def has_explicit_period(cls, text: str) -> bool:
        msg = cls.normalize_text(text)
        if re.search(r"\d{4}-\d{2}-\d{2}", msg):
            return True
        if re.search(r"\b(lunes|martes|mi.?rcoles|jueves|viernes|s.?bado|domingo)\b", msg):
            return True
        period_tokens = (
            "hoy",
            "ayer",
            "esta semana",
            "semana actual",
            "semana pasada",
            "semana anterior",
            "ultima semana",
            "ultimos",
            "mes",
            "anio",
            "rango",
        )
        return any(token in msg for token in period_tokens)

    @classmethod
    def prefers_rules_period_resolution(cls, normalized_message: str) -> bool:
        msg = cls.normalize_text(normalized_message)
        return any(
            token in msg
            for token in (
                "esta semana",
                "semana actual",
                "semana pasada",
                "semana anterior",
            )
        )

    def resolve_period_with_openai(
        self,
        *,
        message: str,
        recent_messages: list[dict[str, Any]] | None = None,
        session_context: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        if not self.enable_openai_period:
            return None

        openai_api_key = self.get_openai_api_key()
        if not openai_api_key:
            return None

        try:
            from openai import OpenAI

            client = OpenAI(api_key=openai_api_key)
            today_iso = date.today().isoformat()
            history_text = self.format_recent_messages_for_prompt(recent_messages or [])
            context_period = ""
            if session_context:
                start = str(session_context.get("last_period_start") or "").strip()
                end = str(session_context.get("last_period_end") or "").strip()
                if start and end:
                    context_period = f"Last period in session: {start} to {end}"

            response = client.responses.create(
                model=self.period_model,
                input=[
                    {
                        "role": "system",
                        "content": (
                            "You extract date ranges for attendance analytics.\n"
                            "Return strict JSON: {\"label\":\"...\",\"start_date\":\"YYYY-MM-DD\","
                            "\"end_date\":\"YYYY-MM-DD\",\"confidence\":0.0-1.0}.\n"
                            f"Today is {today_iso}.\n"
                            "Rules:\n"
                            "- If user says 'ultimo mes' and is ambiguous, default to rolling last 30 days.\n"
                            "- If user says 'mes pasado' or 'mes anterior', return previous calendar month.\n"
                            "- Keep end_date <= today."
                        ),
                    },
                    {
                        "role": "system",
                        "content": (
                            "Conversation context (latest first):\n"
                            f"{history_text}\n"
                            f"{context_period}"
                        ),
                    },
                    {"role": "user", "content": message},
                ],
            )

            text = (getattr(response, "output_text", "") or "").strip()
            if not text:
                return None
            json_match = re.search(r"\{.*\}", text, re.DOTALL)
            raw = json_match.group(0) if json_match else text
            data = json.loads(raw)

            start = date.fromisoformat(str(data.get("start_date") or "").strip())
            end = date.fromisoformat(str(data.get("end_date") or "").strip())
            if start > end:
                start, end = end, start
            if end > date.today():
                end = date.today()
            max_window_days = max(30, min(int(os.getenv("IA_DEV_MAX_PERIOD_DAYS", "370")), 1095))
            if (end - start).days > max_window_days:
                return None

            confidence = float(data.get("confidence") or 0.0)
            if confidence < 0.45:
                return None

            return {
                "label": str(data.get("label") or "openai_period"),
                "start": start,
                "end": end,
                "source": "openai_period",
                "confidence": round(confidence, 3),
            }
        except Exception:
            logger.exception("OpenAI period resolution failed")
            return None

    def build_period_alternative_hint(self, *, message: str, period: dict[str, Any]) -> str | None:
        normalized = self.normalize_text(message)
        label = str(period.get("label") or "").lower()
        today = date.today()

        if "mes anterior" in normalized or "mes pasado" in normalized or label == "mes_anterior":
            rolling_start = today - timedelta(days=29)
            rolling_end = today
            return (
                "Si quieres, tambien puedo mostrarlo como ultimo mes movil de 30 dias "
                f"({rolling_start.isoformat()} a {rolling_end.isoformat()}). "
                "Responde: si, ultimo mes."
            )

        if re.search(r"\bultim[oa]s?\s+mes\b", normalized) or label == "ultimo_mes_30_dias":
            first_current = today.replace(day=1)
            prev_end = first_current - timedelta(days=1)
            prev_start = prev_end.replace(day=1)
            return (
                "Si prefieres, tambien puedo mostrarlo como mes anterior calendario "
                f"({prev_start.isoformat()} a {prev_end.isoformat()}). "
                "Responde: si, mes anterior."
            )

        return None

    @classmethod
    def is_contextual_reference_request(cls, normalized_message: str) -> bool:
        msg = cls.normalize_text(normalized_message)
        return any(
            token in msg
            for token in (
                "mismo periodo",
                "mismo rango",
                "ese periodo",
                "ese rango",
                "igual periodo",
                "igual rango",
                "lo mismo",
                "asi mismo",
            )
        )

    @staticmethod
    def format_recent_messages_for_prompt(recent_messages: list[dict[str, Any]]) -> str:
        lines: list[str] = []
        for item in list(reversed(recent_messages or []))[:8]:
            role = str(item.get("role") or "user").strip().lower()
            content = str(item.get("content") or "").strip()
            if not content:
                continue
            lines.append(f"{role}: {content[:300]}")
        return "\n".join(lines)

    @staticmethod
    def get_openai_api_key() -> str | None:
        for key in ("OPENAI_API_KEY", "IA_DEV_OPENAI_API_KEY"):
            value = str(os.getenv(key) or "").strip()
            if value:
                return value
        return None

    @staticmethod
    def _env_flag(name: str, default: str = "0") -> bool:
        value = os.getenv(name, default)
        return str(value or "").strip().lower() in {"1", "true", "yes", "on"}
